"""Progress + run-history store."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

import progress


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")


def test_every_run_increments_attempts_including_post_solve() -> None:
    """#26: every run counts, even after the challenge is already solved."""
    progress.record_run("demo", green=False, passed=1, failed=1)
    progress.record_run("demo", green=True, passed=2, failed=0)
    progress.record_run("demo", green=True, passed=2, failed=0)

    state = progress.get_all()["demo"]
    assert state["status"] == "solved"
    assert state["attempts"] == 3
    assert state["solved_at"] is not None
    assert state["spoiled"] is False


def test_solved_status_never_downgrades() -> None:
    progress.record_run("demo", green=True)
    progress.record_run("demo", green=False)
    assert progress.get_all()["demo"]["status"] == "solved"


def test_first_solved_at_is_sticky() -> None:
    progress.record_run("demo", green=True)
    first = progress.get_all()["demo"]["solved_at"]
    time.sleep(0.02)
    progress.record_run("demo", green=True)
    second = progress.get_all()["demo"]["solved_at"]
    assert first is not None
    assert first == second


def test_list_runs_newest_first_with_payload() -> None:
    progress.record_run(
        "demo",
        green=False,
        duration_ms=120,
        session_elapsed_ms=45_000,
        passed=1,
        failed=2,
        output="FAIL stuff",
        tests=[{"id": "t::a", "outcome": "failed"}],
    )
    progress.record_run("demo", green=True, duration_ms=80, passed=3)

    runs = progress.list_runs("demo")
    assert len(runs) == 2
    assert runs[0]["green"] is True
    assert runs[0]["passed"] == 3
    assert runs[1]["green"] is False
    assert runs[1]["session_elapsed_ms"] == 45_000
    assert runs[1]["duration_ms"] == 120
    assert runs[1]["tests"][0]["id"] == "t::a"
    assert "FAIL" in runs[1]["output_tail"]


def test_run_history_preserves_supplied_start_time() -> None:
    started_at = "2026-08-30T04:05:06+00:00"

    recorded = progress.record_run(
        "demo", green=False, started_at=started_at, duration_ms=120
    )

    assert recorded["started_at"] == started_at
    assert progress.list_runs("demo")[0]["started_at"] == started_at


def test_run_history_reports_when_its_output_tail_was_truncated() -> None:
    output = "prefix-marker" + "x" * progress.OUTPUT_TAIL_LIMIT

    progress.record_run("demo", green=False, output=output)

    run = progress.list_runs("demo")[0]
    assert run["output_truncated"] is True
    assert len(run["output_tail"]) == progress.OUTPUT_TAIL_LIMIT
    assert "prefix-marker" not in run["output_tail"]


def test_reset_clears_progress_and_history() -> None:
    progress.record_run("demo", green=True)
    progress.reset("demo")
    assert "demo" not in progress.get_all()
    assert progress.list_runs("demo") == []


def test_mark_spoiled_does_not_change_status_attempts_or_solved_at() -> None:
    progress.record_run("demo", green=True)
    before = progress.get_all()["demo"]
    updated = progress.mark_spoiled("demo")
    assert updated["spoiled"] is True
    assert updated["status"] == before["status"] == "solved"
    assert updated["attempts"] == before["attempts"] == 1
    assert updated["solved_at"] == before["solved_at"]
    assert progress.get_all()["demo"]["spoiled"] is True


def test_mark_spoiled_creates_todo_row_without_a_run() -> None:
    updated = progress.mark_spoiled("fresh")
    assert updated == {
        "status": "todo",
        "attempts": 0,
        "solved_at": None,
        "spoiled": True,
    }


def test_reset_clears_spoiled() -> None:
    progress.mark_spoiled("demo")
    assert progress.get_all()["demo"]["spoiled"] is True
    progress.reset("demo")
    assert "demo" not in progress.get_all()


def test_migrates_existing_db_missing_spoiled_column() -> None:
    conn = sqlite3.connect(progress.DB_PATH)
    conn.execute(
        """CREATE TABLE progress (
            slug TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'todo',
            attempts INTEGER NOT NULL DEFAULT 0,
            solved_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO progress (slug, status, attempts) VALUES ('old', 'solved', 2)"
    )
    conn.commit()
    conn.close()

    state = progress.get_all()["old"]
    assert state["spoiled"] is False
    assert state["status"] == "solved"
    assert state["attempts"] == 2
    marked = progress.mark_spoiled("old")
    assert marked["spoiled"] is True
    assert marked["status"] == "solved"
    assert marked["attempts"] == 2


def test_migrates_existing_run_history_missing_truncation_column() -> None:
    conn = sqlite3.connect(progress.DB_PATH)
    conn.execute(
        """CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            session_elapsed_ms INTEGER,
            green INTEGER NOT NULL DEFAULT 0,
            passed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER NOT NULL DEFAULT 0,
            output_tail TEXT NOT NULL DEFAULT '',
            tests_json TEXT NOT NULL DEFAULT '[]'
        )"""
    )
    conn.execute(
        "INSERT INTO runs (slug, started_at, output_tail) VALUES (?, ?, ?)",
        ("old", "2026-08-30T04:05:06+00:00", "legacy output"),
    )
    conn.commit()
    conn.close()

    run = progress.list_runs("old")[0]

    assert run["output_tail"] == "legacy output"
    assert run["output_truncated"] is False


def test_concurrent_sqlite_calls_do_not_crash() -> None:
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        slug = f"slug-{i % 3}"
        try:
            progress.record_run(slug, green=i % 2 == 0)
            progress.get_all()
            progress.mark_spoiled(slug)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
