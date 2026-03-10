from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .job_store import InMemoryJobStore, RedisJobStore
from .models import (
    SimulationJobCreateResponse,
    SimulationJobStatusResponse,
    SimulationRequest,
    SimulationResponse,
)
from .simulation import run_simulation

app = FastAPI(title="Prop Firm Challenge Dashboard API", version="1.0.0")

use_in_memory_store = not bool(os.environ.get("REDIS_URL"))
store = InMemoryJobStore() if use_in_memory_store else RedisJobStore.from_env()
local_executor = ThreadPoolExecutor(max_workers=1) if use_in_memory_store else None


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def api_status() -> dict[str, str]:
    if use_in_memory_store:
        return {
            "status": "ok",
            "store": "in-memory",
            "note": "REDIS_URL is not set; jobs run in-process on the web instance.",
        }
    return {"status": "ok", "store": "ok" if store.ping() else "unreachable"}


@app.post("/api/simulate/jobs", response_model=SimulationJobCreateResponse)
def create_simulation_job(request: SimulationRequest) -> SimulationJobCreateResponse:
    job_id = str(uuid4())
    store.enqueue_job(job_id, request)

    if use_in_memory_store and local_executor is not None:
        def run_local_job() -> None:
            store.set_job_running(job_id)

            def on_progress(completed: int, total: int) -> None:
                store.update_progress(job_id, completed, total)

            try:
                result = run_simulation(request, chunk_size=100, on_progress=on_progress)
                store.set_job_completed(job_id, result=result, completed=request.simulations)
            except Exception as exc:  # pragma: no cover - defensive fallback guard
                store.set_job_failed(job_id, str(exc))

        local_executor.submit(run_local_job)

    return SimulationJobCreateResponse(job_id=job_id)


@app.get("/api/simulate/jobs/{job_id}", response_model=SimulationJobStatusResponse)
def get_simulation_job(job_id: str) -> SimulationJobStatusResponse:
    state = store.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")

    raw_result = state.get("result")
    result = SimulationResponse.model_validate_json(raw_result) if raw_result else None
    error = state.get("error") or None

    return SimulationJobStatusResponse(
        job_id=job_id,
        status=state.get("status", "unknown"),
        completed_simulations=int(state.get("completed_simulations", "0")),
        total_simulations=int(state.get("total_simulations", "0")),
        result=result,
        error=error,
    )


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        target = frontend_dist / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html")
