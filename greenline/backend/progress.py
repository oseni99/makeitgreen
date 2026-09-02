"""SQLite progress store: attempts, solved status, spoil flag, and per-run history.

Attempts semantics (#26): every POST /run increments attempts, including
reruns after the challenge is already solved. History rows are kept for every
run; reset clears both progress and run history for that slug.

`spoiled` is set when the learner chooses to view the solution (soft confirm
on the client). It never changes status, attempts, or solved_at.
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "data" / "progress.db"

# Cap stored output so the DB doesn't grow unbounded from huge traces.
OUTPUT_TAIL_LIMIT = 8000

_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DATABASES: set[Path] = set()


def _has_expected_schema(path: Path) -> bool:
    """Return whether a cached database still contains our tables.

    The database can be replaced externally (for example during a restore)
    without changing its path.  A path-only initialization cache must not
    let such a file skip schema setup.
    """
    try:
        conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('progress', 'runs')"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False
    return {row[0] for row in rows} == {"progress", "runs"}


def _initialize_schema(path: Path) -> None:
    """Run connection-global setup and migrations once for a database file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS progress (
                slug TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'todo',
                attempts INTEGER NOT NULL DEFAULT 0,
                solved_at TEXT,
                spoiled INTEGER NOT NULL DEFAULT 0
            )"""
        )
        try:
            conn.execute(
                "ALTER TABLE progress ADD COLUMN spoiled INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
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
                output_truncated INTEGER NOT NULL DEFAULT 0,
                tests_json TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        try:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN output_truncated "
                "INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_slug_id ON runs (slug, id DESC)"
        )
        conn.commit()
    finally:
        conn.close()


def _db_path(user_id: str | None = None) -> Path:
    if user_id is None:
        return DB_PATH.resolve()
    namespace = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return (DB_PATH.parent / "users" / namespace / DB_PATH.name).resolve()


def _ensure_schema(user_id: str | None = None) -> Path:
    path = _db_path(user_id)
    if path in _INITIALIZED_DATABASES and path.exists() and _has_expected_schema(path):
        return path
    with _SCHEMA_LOCK:
        if (
            path not in _INITIALIZED_DATABASES
            or not path.exists()
            or not _has_expected_schema(path)
        ):
            _initialize_schema(path)
            _INITIALIZED_DATABASES.add(path)
    return path


@contextmanager
def _conn(user_id: str | None = None) -> Iterator[sqlite3.Connection]:
    """Open one short-lived data connection after serialized schema setup."""
    path = _ensure_schema(user_id)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _progress_from_row(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    raw = row["spoiled"] if "spoiled" in keys else 0
    return {
        "status": row["status"],
        "attempts": row["attempts"],
        "solved_at": row["solved_at"],
        "spoiled": bool(raw),
    }


def get_all(user_id: str | None = None) -> dict[str, dict]:
    with _conn(user_id) as conn:
        rows = conn.execute(
            "SELECT slug, status, attempts, solved_at, spoiled FROM progress"
        ).fetchall()
    return {r["slug"]: _progress_from_row(r) for r in rows}


def record_run(
    slug: str,
    *,
    green: bool,
    duration_ms: int = 0,
    session_elapsed_ms: int | None = None,
    passed: int = 0,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
    exit_code: int = 0,
    output: str = "",
    tests: list[dict[str, Any]] | None = None,
    started_at: str | None = None,
    output_truncated: bool = False,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Increment attempts (always), update solved status, append a history row."""
    now = datetime.now(timezone.utc).isoformat()
    run_started_at = started_at or now
    output_tail = output[-OUTPUT_TAIL_LIMIT:]
    history_output_truncated = output_truncated or len(output) > OUTPUT_TAIL_LIMIT
    tests_json = json.dumps(tests or [])

    with _conn(user_id) as conn:
        conn.execute(
            "INSERT INTO progress (slug, status, attempts) VALUES (?, 'attempted', 0) "
            "ON CONFLICT(slug) DO NOTHING",
            (slug,),
        )
        if green:
            conn.execute(
                "UPDATE progress SET attempts = attempts + 1, status = 'solved', "
                "solved_at = COALESCE(solved_at, ?) WHERE slug = ?",
                (now, slug),
            )
        else:
            # Never downgrade a solved challenge back to attempted.
            # Attempts still increment (every run counts — see module docstring).
            conn.execute(
                "UPDATE progress SET attempts = attempts + 1, "
                "status = CASE WHEN status = 'solved' THEN 'solved' ELSE 'attempted' END "
                "WHERE slug = ?",
                (slug,),
            )

        cur = conn.execute(
            """INSERT INTO runs (
                slug, started_at, duration_ms, session_elapsed_ms, green,
                passed, failed, errors, skipped, exit_code, output_tail,
                output_truncated, tests_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slug,
                run_started_at,
                max(0, int(duration_ms)),
                None if session_elapsed_ms is None else max(0, int(session_elapsed_ms)),
                1 if green else 0,
                passed,
                failed,
                errors,
                skipped,
                exit_code,
                output_tail,
                1 if history_output_truncated else 0,
                tests_json,
            ),
        )
        run_id = cur.lastrowid

    return {
        "id": run_id,
        "slug": slug,
        "started_at": run_started_at,
        "duration_ms": max(0, int(duration_ms)),
        "session_elapsed_ms": session_elapsed_ms,
        "green": green,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "exit_code": exit_code,
    }


def list_runs(slug: str, limit: int = 50, user_id: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    with _conn(user_id) as conn:
        rows = conn.execute(
            """SELECT id, slug, started_at, duration_ms, session_elapsed_ms, green,
                      passed, failed, errors, skipped, exit_code, output_tail,
                      output_truncated, tests_json
               FROM runs WHERE slug = ? ORDER BY id DESC LIMIT ?""",
            (slug, limit),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            tests = json.loads(r["tests_json"] or "[]")
        except json.JSONDecodeError:
            tests = []
        out.append(
            {
                "id": r["id"],
                "slug": r["slug"],
                "started_at": r["started_at"],
                "duration_ms": r["duration_ms"],
                "session_elapsed_ms": r["session_elapsed_ms"],
                "green": bool(r["green"]),
                "passed": r["passed"],
                "failed": r["failed"],
                "errors": r["errors"],
                "skipped": r["skipped"],
                "exit_code": r["exit_code"],
                "output_tail": r["output_tail"],
                "output_truncated": bool(r["output_truncated"]),
                "tests": tests,
            }
        )
    return out


def mark_spoiled(slug: str, user_id: str | None = None) -> dict[str, Any]:
    """Set spoiled=1 without changing status, attempts, or solved_at."""
    with _conn(user_id) as conn:
        conn.execute(
            "INSERT INTO progress (slug, status, attempts) VALUES (?, 'todo', 0) "
            "ON CONFLICT(slug) DO NOTHING",
            (slug,),
        )
        conn.execute("UPDATE progress SET spoiled = 1 WHERE slug = ?", (slug,))
        row = conn.execute(
            "SELECT slug, status, attempts, solved_at, spoiled FROM progress "
            "WHERE slug = ?",
            (slug,),
        ).fetchone()
    return _progress_from_row(row)


def reset(slug: str, user_id: str | None = None) -> None:
    with _conn(user_id) as conn:
        conn.execute("DELETE FROM runs WHERE slug = ?", (slug,))
        conn.execute("DELETE FROM progress WHERE slug = ?", (slug,))
