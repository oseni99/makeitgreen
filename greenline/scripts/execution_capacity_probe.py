#!/usr/bin/env python3
"""Measure named beta workloads against the real staging worker pool.

The probe bypasses Clerk and the public API on purpose: it isolates PostgreSQL
queue and Docker-worker capacity without creating large numbers of identity
provider accounts. Run it only against a disposable staging database connected
to the same worker pool that is under test. Each synthetic learner submits one
run during the scenario's defined arrival window.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID, uuid4


BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import operations  # noqa: E402
import run_coordination  # noqa: E402


ACKNOWLEDGEMENT = "disposable-staging"
DEFAULT_CHALLENGE_MIX = (
    "config-merge",
    "webhook-batch-node",
    "report-latency",
)


@dataclass(frozen=True)
class LoadScenario:
    name: str
    active_learners: int
    arrival_window_seconds: float
    target_start_ms: float
    target_max_start_ms: float
    description: str


SCENARIOS = {
    scenario.name: scenario
    for scenario in (
        LoadScenario(
            "small-burst",
            active_learners=15,
            arrival_window_seconds=10,
            target_start_ms=30_000,
            target_max_start_ms=60_000,
            description="15 learners each submit once within 10 seconds",
        ),
        LoadScenario(
            "cohort-50",
            active_learners=50,
            arrival_window_seconds=300,
            target_start_ms=10_000,
            target_max_start_ms=30_000,
            description="50 active learners each submit once during a 5-minute cycle",
        ),
        LoadScenario(
            "cohort-100",
            active_learners=100,
            arrival_window_seconds=300,
            target_start_ms=10_000,
            target_max_start_ms=30_000,
            description="100 active learners each submit once during a 5-minute cycle",
        ),
        LoadScenario(
            "peak-burst-100",
            active_learners=100,
            arrival_window_seconds=10,
            target_start_ms=30_000,
            target_max_start_ms=60_000,
            description="100 learners each submit once within 10 seconds",
        ),
        LoadScenario(
            "retry-burst",
            active_learners=25,
            arrival_window_seconds=10,
            target_start_ms=30_000,
            target_max_start_ms=60_000,
            description="25 learners each retry once within 10 seconds",
        ),
    )
}


@dataclass(frozen=True)
class SubmittedJob:
    job_id: str
    user_id: str
    slug: str


def nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Return a deterministic nearest-rank percentile for bounded evidence."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _execution_finished(result: Any) -> bool:
    # Both supported test runners use 0 for green and 1 for failing tests.
    # Missing evidence, timeouts, signals, and runner errors must fail the gate.
    if not isinstance(result, dict):
        return False
    exit_code = result.get("exit_code")
    return type(exit_code) is int and exit_code in {0, 1}


def summarize_scenario(
    active_learners: int,
    rows: Sequence[dict[str, Any]],
    *,
    target_start_ms: float,
    target_max_start_ms: float,
    rejected: int = 0,
) -> dict[str, Any]:
    queue_waits = [
        float(row["queue_wait_ms"])
        for row in rows
        if row.get("queue_wait_ms") is not None
    ]
    execution_times = [
        float(row["execution_ms"])
        for row in rows
        if row.get("execution_ms") is not None
    ]
    completed = sum(row.get("status") == "completed" for row in rows)
    failed = sum(row.get("status") == "failed" for row in rows)
    execution_failures = sum(
        row.get("status") == "completed"
        and not _execution_finished(row.get("result"))
        for row in rows
    )
    p95_queue_wait_ms = nearest_rank(queue_waits, 0.95)
    max_queue_wait_ms = max(queue_waits, default=None)
    passed = bool(
        len(rows) == active_learners
        and rejected == 0
        and completed == active_learners
        and failed == 0
        and execution_failures == 0
        and len(queue_waits) == active_learners
        and p95_queue_wait_ms is not None
        and p95_queue_wait_ms <= target_start_ms
        and max_queue_wait_ms is not None
        and max_queue_wait_ms <= target_max_start_ms
    )
    return {
        "active_learners": active_learners,
        "jobs": len(rows),
        "rejected": rejected,
        "completed": completed,
        "failed": failed,
        "execution_failures": execution_failures,
        "p50_queue_wait_ms": nearest_rank(queue_waits, 0.50),
        "p95_queue_wait_ms": p95_queue_wait_ms,
        "max_queue_wait_ms": max_queue_wait_ms,
        "p95_execution_ms": nearest_rank(execution_times, 0.95),
        "max_execution_ms": max(execution_times, default=None),
        "target_start_ms": target_start_ms,
        "target_max_start_ms": target_max_start_ms,
        "passed": passed,
    }


def _timing_rows(dsn: str, jobs: Sequence[SubmittedJob]) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    if not jobs:
        return []
    job_ids = [UUID(job.job_id) for job in jobs]
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id, status, result, "
            "round(extract(epoch FROM (claimed_at - created_at)) * 1000)::bigint "
            "AS queue_wait_ms, "
            "round(extract(epoch FROM (completed_at - claimed_at)) * 1000)::bigint "
            "AS execution_ms "
            "FROM run_jobs WHERE id = ANY(%s)",
            (job_ids,),
        ).fetchall()
    return [dict(row) for row in rows]


def _wait_for_terminal_jobs(
    adapter: run_coordination.PostgresRunJobAdapter,
    jobs: Sequence[SubmittedJob],
    *,
    poll_interval: float,
    timeout_seconds: float,
) -> None:
    pending = {job.job_id: job for job in jobs}
    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        for job_id, job in list(pending.items()):
            current = adapter.get(job_id, user_id=job.user_id)
            if current is not None and current["status"] in {"completed", "failed"}:
                del pending[job_id]
        if pending:
            time.sleep(poll_interval)
    if pending:
        raise TimeoutError(f"{len(pending)} Run Jobs did not finish before timeout")


def run_scenario(
    adapter: run_coordination.PostgresRunJobAdapter,
    dsn: str,
    *,
    scenario: LoadScenario,
    slugs: Sequence[str],
    poll_interval: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    prefix = f"capacity-probe-{scenario.name}-{uuid4().hex}"
    jobs: list[SubmittedJob] = []
    rejected = 0
    start = time.monotonic()
    for index in range(scenario.active_learners):
        if scenario.arrival_window_seconds > 0:
            due = start + (
                scenario.arrival_window_seconds * index / scenario.active_learners
            )
            time.sleep(max(0.0, due - time.monotonic()))
        user_id = f"{prefix}-{index}"
        slug = slugs[index % len(slugs)]
        try:
            queued = adapter.enqueue(
                run_coordination.RunJobRequest(user_id=user_id, slug=slug)
            )
        except run_coordination.RunCapacityExceeded:
            rejected += 1
        else:
            jobs.append(SubmittedJob(queued["job_id"], user_id, slug))

    # Include enqueue latency, but exclude the subsequent completion wait.
    actual_arrival_window_seconds = time.monotonic() - start
    arrival_window_met = (
        actual_arrival_window_seconds <= scenario.arrival_window_seconds
    )
    _wait_for_terminal_jobs(
        adapter,
        jobs,
        poll_interval=poll_interval,
        timeout_seconds=timeout_seconds,
    )
    rows = _timing_rows(dsn, jobs)
    summary = summarize_scenario(
        scenario.active_learners,
        rows,
        target_start_ms=scenario.target_start_ms,
        target_max_start_ms=scenario.target_max_start_ms,
        rejected=rejected,
    )
    challenge_counts = {slug: 0 for slug in slugs}
    for job in jobs:
        challenge_counts[job.slug] += 1
    summary["name"] = scenario.name
    summary["description"] = scenario.description
    summary["synthetic_user_prefix"] = prefix
    summary["arrival_window_seconds"] = scenario.arrival_window_seconds
    summary["actual_arrival_window_seconds"] = actual_arrival_window_seconds
    summary["arrival_window_met"] = arrival_window_met
    summary["passed"] = summary["passed"] and arrival_window_met
    summary["arrivals_per_minute"] = round(
        scenario.active_learners / scenario.arrival_window_seconds * 60,
        2,
    )
    summary["challenge_counts"] = challenge_counts
    return summary


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _run_memory_mib(value: str) -> int:
    parsed = _positive_int(value)
    if not 128 <= parsed <= 4096:
        raise argparse.ArgumentTypeError("must be between 128 and 4096")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=tuple(SCENARIOS),
        default=tuple(SCENARIOS),
    )
    parser.add_argument("--slugs", nargs="+", default=DEFAULT_CHALLENGE_MIX)
    parser.add_argument("--poll-interval", type=_positive_float, default=0.25)
    parser.add_argument("--timeout-seconds", type=_positive_float, default=600.0)
    parser.add_argument("--worker-count", type=_positive_int, required=True)
    parser.add_argument("--worker-concurrency", type=_positive_int, required=True)
    parser.add_argument("--run-memory-mib", type=_run_memory_mib, required=True)
    parser.add_argument("--global-active-limit", type=_positive_int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if os.environ.get("GREENLINE_CAPACITY_PROBE_ACK") != ACKNOWLEDGEMENT:
        parser.error(
            "set GREENLINE_CAPACITY_PROBE_ACK=disposable-staging to confirm the target"
        )
    try:
        dsn = operations.read_secret(os.environ, "GREENLINE_TEST_DATABASE_URL")
    except operations.OperationalConfigurationError as exc:
        parser.error(str(exc))
    if not dsn:
        parser.error(
            "GREENLINE_TEST_DATABASE_URL or GREENLINE_TEST_DATABASE_URL_FILE is required"
        )

    scenarios = tuple(SCENARIOS[name] for name in dict.fromkeys(args.scenarios))
    slugs = tuple(dict.fromkeys(args.slugs))
    admission = run_coordination.RunAdmissionPolicy(
        max_active_runs=args.global_active_limit,
        max_active_runs_per_user=1,
    )
    adapter = run_coordination.PostgresRunJobAdapter.connect(dsn, admission)
    try:
        results = [
            run_scenario(
                adapter,
                dsn,
                scenario=scenario,
                slugs=slugs,
                poll_interval=args.poll_interval,
                timeout_seconds=args.timeout_seconds,
            )
            for scenario in scenarios
        ]
    finally:
        adapter.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "challenge_mix": slugs,
        "worker_count": args.worker_count,
        "worker_concurrency": args.worker_concurrency,
        "total_worker_slots": args.worker_count * args.worker_concurrency,
        "run_memory_mib": args.run_memory_mib,
        "global_active_limit": args.global_active_limit,
        "max_active_runs_per_user": 1,
        "results": results,
        "passed": all(result["passed"] for result in results),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
