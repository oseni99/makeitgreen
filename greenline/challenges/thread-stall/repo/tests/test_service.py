from __future__ import annotations

import time
from threading import Barrier, Lock, current_thread

from reporting.service import ReportService


def load_profile(user_id: str) -> str:
    return {"acct-101": "Ada", "acct-202": "Lin", "acct-303": "Grace"}[user_id]


def test_empty_batch_does_no_work() -> None:
    calls = 0

    def tracked_loader(user_id: str) -> str:
        nonlocal calls
        calls += 1
        return user_id

    with ReportService(tracked_loader) as service:
        assert service.reports_for([]) == []
    assert calls == 0


def test_single_request_builds_report() -> None:
    with ReportService(load_profile, wait_seconds=0.15) as service:
        assert service.reports_for(["acct-101"]) == ["report:acct-101:Ada"]


def test_saturated_pool_completes_without_starvation() -> None:
    started = time.monotonic()
    with ReportService(load_profile, max_workers=2, wait_seconds=0.15) as service:
        reports = service.reports_for(["acct-101", "acct-202"])

    assert reports == ["report:acct-101:Ada", "report:acct-202:Lin"]
    assert time.monotonic() - started < 1.0


def test_report_work_overlaps_on_the_bounded_worker_pool() -> None:
    loader_gate = Barrier(2)
    names: set[str] = set()
    names_lock = Lock()

    def overlapping_loader(user_id: str) -> str:
        with names_lock:
            names.add(current_thread().name)
        # A synchronous list comprehension cannot reach the second loader and
        # breaks this bounded barrier instead of accidentally passing the test.
        loader_gate.wait(timeout=0.3)
        return user_id

    with ReportService(overlapping_loader, max_workers=2, wait_seconds=0.35) as service:
        assert service.reports_for(["acct-101", "acct-202"]) == [
            "report:acct-101:acct-101",
            "report:acct-202:acct-202",
        ]

    assert len(names) == 2
    assert all(name.startswith("report-worker") for name in names)
