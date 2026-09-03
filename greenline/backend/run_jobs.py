"""In-memory background run jobs with pollable incremental output."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

OUTPUT_LIMIT = 20_000
TERMINAL_JOB_LIMIT = 100


class RunJobStore:
    def __init__(
        self,
        *,
        workers: int = 4,
        terminal_job_limit: int = TERMINAL_JOB_LIMIT,
    ) -> None:
        if terminal_job_limit < 1:
            raise ValueError("terminal_job_limit must be positive")
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="run-job")
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._terminal_job_limit = terminal_job_limit
        self._terminal_jobs: deque[str] = deque()

    def check_ready(self) -> None:
        return None

    def _record_terminal(self, job_id: str) -> None:
        """Keep active jobs plus a bounded history ordered by completion time.

        The caller must hold ``self._lock``.
        """
        self._terminal_jobs.append(job_id)
        while len(self._terminal_jobs) > self._terminal_job_limit:
            expired_id = self._terminal_jobs.popleft()
            self._jobs.pop(expired_id, None)

    def start(
        self,
        slug: str,
        work: Callable[[Callable[[str], None]], dict[str, Any]],
        *,
        user_id: str | None = None,
        release: Callable[[], None],
    ) -> dict[str, Any]:
        job_id = uuid4().hex
        job = {
            "id": job_id,
            "slug": slug,
            "user_id": user_id,
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
                    self._record_terminal(job_id)
            except Exception as exc:  # surfaced through the polling contract
                with self._lock:
                    job["status"] = "failed"
                    job["error"] = str(exc)
                    self._record_terminal(job_id)
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

    def get(
        self,
        job_id: str,
        *,
        after: int = 0,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.get("user_id") != user_id:
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
