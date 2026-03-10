from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    SimulationJobCreateResponse,
    SimulationJobStatusResponse,
    SimulationRequest,
    SimulationResponse,
)
from .simulation import run_simulation

app = FastAPI(title="Prop Firm Challenge Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobState(dict):
    pass


job_store: dict[str, JobState] = {}
job_store_lock = Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _run_simulation_job(job_id: str, request: SimulationRequest) -> None:
    with job_store_lock:
        state = job_store.get(job_id)
        if state is None:
            return
        state["status"] = "running"

    def update_progress(completed: int, total: int) -> None:
        with job_store_lock:
            current = job_store.get(job_id)
            if current is None:
                return
            current["completed_simulations"] = completed
            current["total_simulations"] = total

    try:
        result = run_simulation(request, chunk_size=100, on_progress=update_progress)
        with job_store_lock:
            state = job_store.get(job_id)
            if state is None:
                return
            state["status"] = "completed"
            state["result"] = result
            state["completed_simulations"] = request.simulations
    except Exception as exc:  # pragma: no cover - defensive server-side guard
        with job_store_lock:
            state = job_store.get(job_id)
            if state is None:
                return
            state["status"] = "failed"
            state["error"] = str(exc)


@app.post("/api/simulate/jobs", response_model=SimulationJobCreateResponse)
def create_simulation_job(request: SimulationRequest) -> SimulationJobCreateResponse:
    job_id = str(uuid4())
    with job_store_lock:
        job_store[job_id] = JobState(
            status="queued",
            completed_simulations=0,
            total_simulations=request.simulations,
            result=None,
            error=None,
        )

    worker = Thread(target=_run_simulation_job, args=(job_id, request), daemon=True)
    worker.start()

    return SimulationJobCreateResponse(job_id=job_id)


@app.get("/api/simulate/jobs/{job_id}", response_model=SimulationJobStatusResponse)
def get_simulation_job(job_id: str) -> SimulationJobStatusResponse:
    with job_store_lock:
        state = job_store.get(job_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Job not found")

        result: SimulationResponse | None = state.get("result") if state.get("status") == "completed" else None
        return SimulationJobStatusResponse(
            job_id=job_id,
            status=state["status"],
            completed_simulations=state["completed_simulations"],
            total_simulations=state["total_simulations"],
            result=result,
            error=state.get("error"),
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
