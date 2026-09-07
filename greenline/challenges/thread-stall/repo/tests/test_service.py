from __future__ import annotations

from threading import Barrier

import pytest

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


@pytest.mark.parametrize("max_workers", [2, 3, 4, 5, 6, 7])
def test_saturated_pool_completes_without_starvation(max_workers: int) -> None:
    user_ids = [f"acct-{index}" for index in range(max_workers)]
    with ReportService(lambda user_id: user_id, max_workers=max_workers, wait_seconds=0.05) as service:
        reports = service.reports_for(user_ids)

    assert reports == [f"report:{user_id}:{user_id}" for user_id in user_ids]


@pytest.mark.parametrize(
    "user_ids",
    [
        ["acct-101", "acct-202"],
        ["acct-a", "acct-b"],
        ["acct-1", "acct-2"],
        ["north", "south"],
        ["red", "blue"],
        ["primary", "secondary"],
        ["sender", "receiver"],
    ],
)
def test_report_work_overlaps_on_the_bounded_worker_pool(
    user_ids: list[str],
) -> None:
    loader_gate = Barrier(2)

    def overlapping_loader(user_id: str) -> str:
        # A synchronous list comprehension cannot reach the second loader and
        # breaks this bounded barrier instead of accidentally passing the test.
        loader_gate.wait(timeout=0.3)
        return user_id

    with ReportService(overlapping_loader, max_workers=2, wait_seconds=0.1) as service:
        assert service.reports_for(user_ids) == [
            f"report:{user_id}:{user_id}" for user_id in user_ids
        ]
