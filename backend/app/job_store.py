from __future__ import annotations

import json
import os
from redis import Redis

from .models import SimulationRequest, SimulationResponse

JOB_KEY_PREFIX = "simulation:job:"
QUEUE_KEY = "simulation:queue"


class RedisJobStore:
    def __init__(self, client: Redis):
        self.client = client

    @classmethod
    def from_env(cls) -> "RedisJobStore":
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL must be set")
        client = Redis.from_url(redis_url, decode_responses=True)
        return cls(client)

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"{JOB_KEY_PREFIX}{job_id}"

    def ping(self) -> bool:
        return bool(self.client.ping())

    def enqueue_job(self, job_id: str, request: SimulationRequest) -> None:
        payload = request.model_dump_json()
        self.client.hset(
            self._job_key(job_id),
            mapping={
                "status": "queued",
                "completed_simulations": 0,
                "total_simulations": request.simulations,
                "request": payload,
                "result": "",
                "error": "",
            },
        )
        self.client.rpush(QUEUE_KEY, json.dumps({"job_id": job_id, "request": payload}))

    def pop_job(self, timeout_seconds: int = 5) -> tuple[str, SimulationRequest] | None:
        item = self.client.blpop(QUEUE_KEY, timeout=timeout_seconds)
        if item is None:
            return None

        _, raw_payload = item
        payload = json.loads(raw_payload)
        return payload["job_id"], SimulationRequest.model_validate_json(payload["request"])

    def get_job(self, job_id: str) -> dict[str, str] | None:
        state = self.client.hgetall(self._job_key(job_id))
        if not state:
            return None
        return state

    def set_job_running(self, job_id: str) -> None:
        self.client.hset(self._job_key(job_id), mapping={"status": "running"})

    def update_progress(self, job_id: str, completed: int, total: int) -> None:
        self.client.hset(
            self._job_key(job_id),
            mapping={
                "completed_simulations": completed,
                "total_simulations": total,
            },
        )

    def set_job_completed(self, job_id: str, result: SimulationResponse, completed: int) -> None:
        self.client.hset(
            self._job_key(job_id),
            mapping={
                "status": "completed",
                "result": result.model_dump_json(),
                "completed_simulations": completed,
                "error": "",
            },
        )

    def set_job_failed(self, job_id: str, error: str) -> None:
        self.client.hset(self._job_key(job_id), mapping={"status": "failed", "error": error})
