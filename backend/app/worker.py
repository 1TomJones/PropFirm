from __future__ import annotations

import time

from .job_store import RedisJobStore
from .simulation import run_simulation


def run_worker() -> None:
    store = RedisJobStore.from_env()
    print("Simulation worker started; awaiting jobs...")

    while True:
        job = store.pop_job(timeout_seconds=5)
        if job is None:
            continue

        job_id, request = job
        store.set_job_running(job_id)

        def on_progress(completed: int, total: int) -> None:
            store.update_progress(job_id, completed, total)

        try:
            result = run_simulation(request, chunk_size=100, on_progress=on_progress)
            store.set_job_completed(job_id, result=result, completed=request.simulations)
        except Exception as exc:  # pragma: no cover - defensive worker-side guard
            store.set_job_failed(job_id, str(exc))
            time.sleep(0.1)


if __name__ == "__main__":
    run_worker()
