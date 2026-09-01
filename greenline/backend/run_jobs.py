"""In-memory background run jobs with pollable incremental output."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

OUTPUT_LIMIT = 20_000


class RunJobStore:
    def __init__(self, *, workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="run-job")
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(
        self,
        slug: str,
        work: Callable[[Callable[[str], None]], dict[str, Any]],
        *,
        release: Callable[[], None],
    ) -> dict[str, Any]:
        job_id = uuid4().hex
        job = {
            "id": job_id,
            "slug": slug,
            "status": "queued",
            "output": "",
            "output_base": 0,
            "result": None,
        }
        with self._lock:
            self._jobs[job_id] = job

        def emit(chunk: str) -> None:
            with self._lock:
                combined = job["output"] + chunk
                if len(combined) > OUTPUT_LIMIT:
                    dropped = len(combined) - OUTPUT_LIMIT
                    job["output_base"] += dropped
                    combined = combined[dropped:]
                job["output"] = combined

        def execute() -> None:
            try:
                with self._lock:
                    job["status"] = "running"
                result = work(emit)
                with self._lock:
                    job["result"] = result
                    job["output"] = result.get("output", job["output"])
                    job["output_base"] = max(
                        job["output_base"],
                        max(0, len(result.get("output", "")) - len(job["output"])),
                    )
                    job["status"] = "completed"
            except Exception as exc:  # surfaced through the polling contract
                with self._lock:
                    job["status"] = "failed"
                    job["error"] = str(exc)
            finally:
                release()

        try:
            self._executor.submit(execute)
        except Exception:
            release()
            with self._lock:
                self._jobs.pop(job_id, None)
            raise
        return {"job_id": job_id, "slug": slug, "status": "queued"}

    def get(self, job_id: str, *, after: int = 0) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            output = job["output"]
            base = job["output_base"]
            after = max(base, min(after, base + len(output)))
            start = after - base
            response = {
                "job_id": job["id"],
                "slug": job["slug"],
                "status": job["status"],
                "output": output[start:],
                "next_offset": base + len(output),
                "output_truncated": base > 0,
            }
            if job.get("result") is not None:
                response["result"] = deepcopy(job["result"])
            if job.get("error"):
                response["error"] = job["error"]
            return response


jobs = RunJobStore()
