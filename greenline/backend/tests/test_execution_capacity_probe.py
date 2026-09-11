from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import execution_capacity_probe as probe  # noqa: E402

from execution_capacity_probe import (  # noqa: E402
    SCENARIOS,
    nearest_rank,
    summarize_scenario,
)


def test_nearest_rank_uses_observed_value() -> None:
    assert nearest_rank([1, 2, 3, 4, 100], 0.95) == 100
    assert nearest_rank([], 0.95) is None


def test_capacity_summary_passes_only_when_every_job_meets_the_start_slo() -> None:
    passing_rows = [
        {
            "status": "completed",
            "result": {"exit_code": 0},
            "queue_wait_ms": 500 + index,
            "execution_ms": 1000 + index,
        }
        for index in range(15)
    ]
    passing = summarize_scenario(
        15,
        passing_rows,
        target_start_ms=3000,
        target_max_start_ms=5000,
    )
    assert passing["passed"] is True
    assert passing["p95_queue_wait_ms"] == 514

    passing_rows[-1]["queue_wait_ms"] = 3001
    slow = summarize_scenario(
        15,
        passing_rows,
        target_start_ms=3000,
        target_max_start_ms=5000,
    )
    assert slow["passed"] is False


def test_capacity_summary_fails_on_missing_or_failed_jobs() -> None:
    rows = [
        {
            "status": "completed",
            "result": {"exit_code": 0},
            "queue_wait_ms": 100,
            "execution_ms": 200,
        },
        {"status": "failed", "queue_wait_ms": None, "execution_ms": None},
    ]

    summary = summarize_scenario(
        3,
        rows,
        target_start_ms=3000,
        target_max_start_ms=5000,
    )

    assert summary["passed"] is False
    assert summary["completed"] == 1
    assert summary["failed"] == 1


def test_capacity_summary_fails_when_admission_rejects_a_learner() -> None:
    rows = [
        {
            "status": "completed",
            "result": {"exit_code": 0},
            "queue_wait_ms": 100,
            "execution_ms": 200,
        }
        for _ in range(14)
    ]

    summary = summarize_scenario(
        15,
        rows,
        target_start_ms=30_000,
        target_max_start_ms=60_000,
        rejected=1,
    )

    assert summary["passed"] is False
    assert summary["rejected"] == 1


def test_capacity_summary_enforces_the_maximum_queue_wait() -> None:
    rows = [
        {
            "status": "completed",
            "result": {"exit_code": 0},
            "queue_wait_ms": 100,
            "execution_ms": 200,
        }
        for _ in range(100)
    ]
    rows[-1]["queue_wait_ms"] = 5001

    summary = summarize_scenario(
        100,
        rows,
        target_start_ms=3000,
        target_max_start_ms=5000,
    )

    assert summary["p95_queue_wait_ms"] == 100
    assert summary["max_queue_wait_ms"] == 5001
    assert summary["passed"] is False


def test_named_scenarios_define_cohorts_bursts_and_their_slos() -> None:
    assert (
        SCENARIOS["small-burst"].active_learners,
        SCENARIOS["small-burst"].arrival_window_seconds,
        SCENARIOS["small-burst"].target_start_ms,
        SCENARIOS["small-burst"].target_max_start_ms,
    ) == (15, 10, 30_000, 60_000)
    assert (
        SCENARIOS["cohort-50"].active_learners,
        SCENARIOS["cohort-50"].arrival_window_seconds,
        SCENARIOS["cohort-50"].target_start_ms,
        SCENARIOS["cohort-50"].target_max_start_ms,
    ) == (50, 300, 10_000, 30_000)
    assert (
        SCENARIOS["cohort-100"].active_learners,
        SCENARIOS["cohort-100"].arrival_window_seconds,
        SCENARIOS["cohort-100"].target_start_ms,
        SCENARIOS["cohort-100"].target_max_start_ms,
    ) == (100, 300, 10_000, 30_000)
    assert (
        SCENARIOS["peak-burst-100"].active_learners,
        SCENARIOS["peak-burst-100"].arrival_window_seconds,
        SCENARIOS["peak-burst-100"].target_start_ms,
        SCENARIOS["peak-burst-100"].target_max_start_ms,
    ) == (100, 10, 30_000, 60_000)
    assert (
        SCENARIOS["retry-burst"].active_learners,
        SCENARIOS["retry-burst"].arrival_window_seconds,
        SCENARIOS["retry-burst"].target_start_ms,
        SCENARIOS["retry-burst"].target_max_start_ms,
    ) == (25, 10, 30_000, 60_000)


@pytest.mark.parametrize("exit_code", [-1, 137, 125, 2, 3, 4, 5, None, "0"])
def test_capacity_summary_rejects_execution_errors(exit_code) -> None:
    summary = summarize_scenario(
        1,
        [
            {
                "status": "completed",
                "result": {"exit_code": exit_code},
                "queue_wait_ms": 100,
                "execution_ms": 200,
            }
        ],
        target_start_ms=3000,
        target_max_start_ms=5000,
    )
    assert summary["passed"] is False
    assert summary["execution_failures"] == 1


@pytest.mark.parametrize("result", [None, {}, [], "invalid"])
def test_capacity_summary_requires_execution_evidence(result) -> None:
    summary = summarize_scenario(
        1,
        [
            {
                "status": "completed",
                "result": result,
                "queue_wait_ms": 100,
                "execution_ms": 200,
            }
        ],
        target_start_ms=3000,
        target_max_start_ms=5000,
    )
    assert summary["passed"] is False


@pytest.mark.parametrize("exit_code", [0, 1])
def test_capacity_summary_accepts_green_and_red_test_runs(exit_code) -> None:
    summary = summarize_scenario(
        1,
        [
            {
                "status": "completed",
                "result": {"exit_code": exit_code},
                "queue_wait_ms": 100,
                "execution_ms": 200,
            }
        ],
        target_start_ms=3000,
        target_max_start_ms=5000,
    )
    assert summary["passed"] is True


@pytest.mark.parametrize("enqueue_seconds, expected_pass", [(0.01, True), (0.5, False)])
def test_burst_requires_submissions_within_the_arrival_window(
    monkeypatch, enqueue_seconds, expected_pass
) -> None:
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()

    class Jobs:
        def enqueue(self, request):
            clock.sleep(enqueue_seconds)
            return {"job_id": request.user_id}

        def get(self, job_id, *, user_id):
            # Completion polling must not count toward the arrival window.
            clock.sleep(1)
            return {"status": "completed"}

    def timing_rows(dsn, jobs):
        return [
            {
                "status": "completed",
                "result": {"exit_code": 1},
                "queue_wait_ms": 100,
                "execution_ms": 200,
            }
            for job in jobs
        ]

    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    monkeypatch.setattr(probe, "_timing_rows", timing_rows)
    summary = probe.run_scenario(
        Jobs(),
        "unused",
        scenario=SCENARIOS["peak-burst-100"],
        slugs=["config-merge"],
        poll_interval=0.25,
        timeout_seconds=600,
    )
    assert summary["passed"] is expected_pass
    assert summary["arrival_window_met"] is expected_pass
    assert summary["actual_arrival_window_seconds"] == pytest.approx(
        9.91 if expected_pass else 50.0
    )
