from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable


class LeaseLost(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    due_at: int
    status: str = "due"
    owner: str | None = None
    lease_until: int | None = None
    generation: int = 0


class JobStore:
    def __init__(self, *, before_claim: Callable[[], None] | None = None) -> None:
        self.jobs: dict[str, Job] = {}
        self.before_claim = before_claim
        self._lock = Lock()

    def add(self, job_id: str, due_at: int) -> None:
        self.jobs[job_id] = Job(job_id, due_at)

    def claim(self, job_id: str, worker: str, *, now: int, lease_seconds: int) -> int | None:
        if self.before_claim:
            self.before_claim()
        with self._lock:
            job = self.jobs[job_id]
            eligible = job.due_at <= now and (
                job.status == "due" or
                (job.status == "claimed" and job.lease_until is not None and job.lease_until <= now)
            )
            if not eligible:
                return None
            job.generation += 1
            job.status = "claimed"
            job.owner = worker
            job.lease_until = now + lease_seconds
            return job.generation

    def assert_lease(self, job_id: str, worker: str, generation: int, *, now: int) -> None:
        with self._lock:
            job = self.jobs[job_id]
            if (
                job.status != "claimed" or job.owner != worker or
                job.generation != generation or job.lease_until is None or job.lease_until <= now
            ):
                raise LeaseLost(job_id)

    def complete(self, job_id: str, worker: str, generation: int, *, now: int) -> None:
        with self._lock:
            job = self.jobs[job_id]
            if (
                job.status != "claimed" or job.owner != worker or
                job.generation != generation or job.lease_until is None or job.lease_until <= now
            ):
                raise LeaseLost(job_id)
            job.status = "done"


class RecordingSink:
    def __init__(self) -> None:
        self.deliveries: list[str] = []

    def send(self, job_id: str) -> None:
        self.deliveries.append(job_id)


class DigestScheduler:
    def __init__(self, store: JobStore, sink: RecordingSink) -> None:
        self.store = store
        self.sink = sink

    def execute(self, job_id: str, worker: str, generation: int, *, now: int) -> None:
        self.store.assert_lease(job_id, worker, generation, now=now)
        self.sink.send(job_id)
        self.store.complete(job_id, worker, generation, now=now)
