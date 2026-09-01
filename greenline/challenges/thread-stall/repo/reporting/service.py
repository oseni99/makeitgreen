"""Bounded worker-pool report service."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, BrokenBarrierError


class PoolStalled(RuntimeError):
    """Raised when a request cannot make progress before the bounded deadline."""


class ReportService:
    def __init__(
        self,
        profile_loader: Callable[[str], str],
        *,
        max_workers: int = 2,
        wait_seconds: float = 0.2,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._profile_loader = profile_loader
        self._max_workers = max_workers
        self._wait_seconds = wait_seconds
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="report-worker",
        )

    def reports_for(self, user_ids: Iterable[str]) -> list[str]:
        """Build reports concurrently, preserving input order."""
        users = list(user_ids)
        if not users:
            return []
        gate = Barrier(len(users)) if len(users) == self._max_workers and len(users) > 1 else None
        requests = [self._pool.submit(self._build_report, user, gate) for user in users]
        try:
            return [request.result(timeout=self._wait_seconds * 3) for request in requests]
        except TimeoutError as exc:
            raise PoolStalled("report worker pool made no progress") from exc

    def _build_report(self, user_id: str, gate: Barrier | None) -> str:
        if gate is not None:
            try:
                gate.wait(timeout=self._wait_seconds)
            except BrokenBarrierError as exc:
                raise PoolStalled("requests did not reach the worker pool") from exc

        # A request worker synchronously waits for dependent work submitted to
        # the same bounded pool. At full request concurrency no worker remains
        # to run these profile jobs.
        profile = self._pool.submit(self._profile_loader, user_id)
        try:
            display_name = profile.result(timeout=self._wait_seconds)
        except TimeoutError as exc:
            raise PoolStalled("profile lookup starved behind request workers") from exc
        return f"report:{user_id}:{display_name}"

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> ReportService:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
