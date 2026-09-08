"""Learner Challenge State Interface and Local/PostgreSQL Adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

import challenges
import progress


SCHEMA_VERSION = 6
PREP_PATHS = frozenset({"foundations", "distributed", "debugging", "senior"})


class LearnerStateUnavailable(RuntimeError):
    """The durable Learner Challenge State dependency is unavailable."""


class LearnerIdentityRequired(ValueError):
    """Durable Learner Challenge State requires a verified learner identity."""


class LearnerChallengeBusy(RuntimeError):
    """A live operation lease currently owns this Learner Challenge State."""

    retry_after = 2


class DebriefRequiresSolved(RuntimeError):
    """A learner may debrief only after completing the Challenge Run."""


class RunNotFound(LookupError):
    """The requested run does not belong to this learner and challenge."""


class RunSnapshotUnavailable(RuntimeError):
    """The run predates durable workspace snapshots and cannot be restored."""


def _validated_debrief(values: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for field in ("root_cause", "fix_reasoning", "tradeoff"):
        value = values.get(field)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 1000:
            raise ValueError(f"{field} must contain 1 to 1000 characters")
        cleaned[field] = value.strip()
    feedback = values.get("feedback", "")
    if not isinstance(feedback, str) or len(feedback.strip()) > 1000:
        raise ValueError("feedback must contain at most 1000 characters")
    useful = values.get("useful")
    if not isinstance(useful, bool):
        raise ValueError("useful must be a boolean")
    cleaned["useful"] = useful
    cleaned["feedback"] = feedback.strip()
    return cleaned


@dataclass(frozen=True)
class WorkspaceSnapshot:
    revision: int
    files: Mapping[str, str]


class LearnerStateAdapter(Protocol):
    def check_ready(self) -> None: ...

    def get_all(self, user_id: str | None) -> dict[str, dict[str, Any]]: ...
    def file_tree(self, slug: str, user_id: str | None) -> list[dict[str, Any]]: ...
    def read_file(self, slug: str, path: str, user_id: str | None) -> str: ...
    def write_file(self, slug: str, path: str, content: str, user_id: str | None) -> None: ...
    def create_file(self, slug: str, path: str, content: str, user_id: str | None) -> None: ...
    def delete_file(self, slug: str, path: str, user_id: str | None) -> None: ...
    def search_files(
        self, slug: str, query: str, limit: int, user_id: str | None
    ) -> list[dict[str, Any]]: ...
    def snapshot(self, slug: str, user_id: str | None) -> WorkspaceSnapshot: ...
    def record_run(self, slug: str, user_id: str | None, **values: Any) -> dict[str, Any]: ...
    def list_runs(self, slug: str, limit: int, user_id: str | None) -> list[dict[str, Any]]: ...
    def restore_run(
        self, slug: str, run_id: int, user_id: str | None
    ) -> WorkspaceSnapshot: ...
    def mark_spoiled(self, slug: str, user_id: str | None) -> dict[str, Any]: ...
    def reset(self, slug: str, user_id: str | None) -> None: ...
    def get_preferences(self, user_id: str | None) -> dict[str, Any]: ...
    def set_prep_path(self, user_id: str | None, prep_path: str) -> dict[str, Any]: ...
    def record_visit(self, user_id: str | None, visited_at: datetime | None = None) -> None: ...
    def get_debrief(self, slug: str, user_id: str | None) -> dict[str, Any] | None: ...
    def save_debrief(self, slug: str, user_id: str | None, **values: Any) -> dict[str, Any]: ...
    def list_product_events(self, user_id: str | None) -> list[dict[str, Any]]: ...


class LocalLearnerStateAdapter:
    """Preserve filesystem and SQLite behavior for trusted Local Mode."""

    def check_ready(self) -> None:
        return None

    def get_all(self, user_id: str | None) -> dict[str, dict[str, Any]]:
        return progress.get_all(user_id)

    def file_tree(self, slug: str, user_id: str | None) -> list[dict[str, Any]]:
        return challenges.file_tree(slug, user_id)

    def read_file(self, slug: str, path: str, user_id: str | None) -> str:
        return challenges.read_file(slug, path, user_id)

    def write_file(
        self, slug: str, path: str, content: str, user_id: str | None
    ) -> None:
        challenges.write_file(slug, path, content, user_id)

    def create_file(
        self, slug: str, path: str, content: str, user_id: str | None
    ) -> None:
        challenges.create_file(slug, path, content, user_id)

    def delete_file(self, slug: str, path: str, user_id: str | None) -> None:
        challenges.delete_file(slug, path, user_id)

    def search_files(
        self, slug: str, query: str, limit: int, user_id: str | None
    ) -> list[dict[str, Any]]:
        return challenges.search_files(slug, query, limit=limit, user_id=user_id)

    def snapshot(self, slug: str, user_id: str | None) -> WorkspaceSnapshot:
        files = {
            relative: path.read_text(encoding="utf-8")
            for path, relative in challenges.workspace_overlays(slug, user_id)
        }
        return WorkspaceSnapshot(revision=0, files=files)

    def record_run(
        self, slug: str, user_id: str | None, **values: Any
    ) -> dict[str, Any]:
        return progress.record_run(slug, user_id=user_id, **values)

    def list_runs(
        self, slug: str, limit: int, user_id: str | None
    ) -> list[dict[str, Any]]:
        return progress.list_runs(slug, limit=limit, user_id=user_id)

    def restore_run(
        self, slug: str, run_id: int, user_id: str | None
    ) -> WorkspaceSnapshot:
        try:
            workspace = progress.run_workspace(slug, run_id, user_id=user_id)
        except KeyError as exc:
            raise RunNotFound(run_id) from exc
        except ValueError as exc:
            raise RunSnapshotUnavailable(str(exc)) from exc
        restored = challenges.restore_workspace(slug, workspace, user_id)
        return WorkspaceSnapshot(revision=0, files=restored)

    def mark_spoiled(self, slug: str, user_id: str | None) -> dict[str, Any]:
        return progress.mark_spoiled(slug, user_id=user_id)

    def reset(self, slug: str, user_id: str | None) -> None:
        challenges.reset_workspace(slug, user_id)
        progress.reset(slug, user_id=user_id)

    def get_preferences(self, user_id: str | None) -> dict[str, Any]:
        return progress.get_preferences(user_id)

    def set_prep_path(
        self, user_id: str | None, prep_path: str
    ) -> dict[str, Any]:
        if prep_path not in PREP_PATHS:
            raise ValueError("unknown prep path")
        return progress.set_prep_path(prep_path, user_id)

    def record_visit(
        self, user_id: str | None, visited_at: datetime | None = None
    ) -> None:
        progress.record_visit(user_id, visited_at)

    def get_debrief(
        self, slug: str, user_id: str | None
    ) -> dict[str, Any] | None:
        return progress.get_debrief(slug, user_id)

    def save_debrief(
        self, slug: str, user_id: str | None, **values: Any
    ) -> dict[str, Any]:
        values = _validated_debrief(values)
        try:
            return progress.save_debrief(slug, user_id=user_id, **values)
        except RuntimeError as exc:
            raise DebriefRequiresSolved(str(exc)) from exc

    def list_product_events(
        self, user_id: str | None
    ) -> list[dict[str, Any]]:
        return progress.list_product_events(user_id)


class PostgresLearnerStateAdapter:
    """Store each tenant-scoped Learner Challenge State transactionally."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    def connect(cls, dsn: str) -> "PostgresLearnerStateAdapter":
        if not dsn.strip():
            raise LearnerStateUnavailable("database configuration is missing")
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=10,
                open=True,
                kwargs={"row_factory": dict_row},
            )
            adapter = cls(pool)
            adapter.check_ready()
            return adapter
        except Exception as exc:
            raise LearnerStateUnavailable(
                "durable learner state is unavailable"
            ) from exc

    def close(self) -> None:
        self._pool.close()

    def check_ready(self) -> None:
        try:
            with self._pool.connection(timeout=3) as conn:
                row = conn.execute(
                    "SELECT version FROM greenline_schema_version WHERE singleton = TRUE"
                ).fetchone()
        except Exception as exc:
            raise LearnerStateUnavailable(
                "durable learner state is unavailable"
            ) from exc
        if row is None or row["version"] != SCHEMA_VERSION:
            raise LearnerStateUnavailable("learner state schema migration is required")

    @staticmethod
    def _user(user_id: str | None) -> str:
        if not user_id:
            raise LearnerIdentityRequired("verified learner identity is required")
        return user_id

    @staticmethod
    def _progress(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": row["status"],
            "attempts": row["attempts"],
            "solved_at": row["solved_at"].isoformat() if row["solved_at"] else None,
            "spoiled": row["spoiled"],
        }

    def _workspace_snapshot(
        self, slug: str, user_id: str | None
    ) -> WorkspaceSnapshot:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT state.workspace_revision, files.path, files.content "
                "FROM learner_challenges AS state "
                "LEFT JOIN workspace_files AS files "
                "ON files.user_id = state.user_id AND files.slug = state.slug "
                "WHERE state.user_id = %s AND state.slug = %s "
                "ORDER BY files.path",
                (user, slug),
            ).fetchall()
        if not rows:
            return WorkspaceSnapshot(revision=0, files={})
        return WorkspaceSnapshot(
            revision=rows[0]["workspace_revision"],
            files={row["path"]: row["content"] for row in rows if row["path"]},
        )

    def _workspace(self, slug: str, user_id: str | None) -> dict[str, str]:
        return dict(self._workspace_snapshot(slug, user_id).files)

    @staticmethod
    def _validated_path(slug: str, path: str) -> tuple[dict[str, Any], Path, str]:
        meta = challenges.load(slug)
        repo_file, canonical = challenges._safe_relpath(challenges.repo_dir(slug), path)
        return meta, repo_file, canonical

    def get_all(self, user_id: str | None) -> dict[str, dict[str, Any]]:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT slug, status, attempts, solved_at, spoiled "
                "FROM learner_challenges WHERE user_id = %s",
                (user,),
            ).fetchall()
        return {row["slug"]: self._progress(row) for row in rows}

    def file_tree(self, slug: str, user_id: str | None) -> list[dict[str, Any]]:
        meta = challenges.load(slug)
        root = challenges.repo_dir(slug)
        overlays = self._workspace(slug, user_id)
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in sorted(root.rglob("*")):
            if any(part in challenges.IGNORED for part in path.parts) or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            files.append(
                {
                    "path": relative,
                    "readonly": challenges.is_readonly(meta, relative),
                    "edited": relative in overlays,
                    "new": False,
                }
            )
        for relative in sorted(overlays.keys() - seen):
            files.append(
                {
                    "path": relative,
                    "readonly": challenges.is_readonly(meta, relative),
                    "edited": True,
                    "new": True,
                }
            )
        return sorted(files, key=lambda item: item["path"])

    def read_file(self, slug: str, path: str, user_id: str | None) -> str:
        _, repo_file, canonical = self._validated_path(slug, path)
        overlays = self._workspace(slug, user_id)
        if canonical in overlays:
            return overlays[canonical]
        if not repo_file.is_file():
            raise challenges.ChallengeNotFound(path)
        return challenges._read_text_file(repo_file)

    def _ensure_state(self, conn: Any, user: str, slug: str) -> None:
        conn.execute(
            "INSERT INTO learner_challenges (user_id, slug) VALUES (%s, %s) "
            "ON CONFLICT (user_id, slug) DO NOTHING",
            (user, slug),
        )

    @staticmethod
    def _record_product_event(
        conn: Any,
        user: str,
        event_name: str,
        *,
        slug: str | None = None,
        properties: Mapping[str, Any] | None = None,
        dedupe_key: str | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        row = conn.execute(
            "INSERT INTO product_events "
            "(user_id, event_name, slug, properties, dedupe_key, occurred_at) "
            "VALUES (%s, %s, %s, %s::jsonb, %s, %s) "
            "ON CONFLICT (user_id, dedupe_key) DO NOTHING RETURNING id",
            (
                user,
                event_name,
                slug,
                json.dumps(dict(properties or {}), sort_keys=True),
                dedupe_key,
                occurred_at or datetime.now(timezone.utc),
            ),
        ).fetchone()
        return row is not None

    def _begin_mutation(self, conn: Any, user: str, slug: str) -> None:
        """Lock one aggregate and refuse or retire its existing run lease."""
        self._ensure_state(conn, user, slug)
        row = conn.execute(
            "SELECT lease_job_id, lease_expires_at > now() AS lease_live "
            "FROM learner_challenges WHERE user_id = %s AND slug = %s FOR UPDATE",
            (user, slug),
        ).fetchone()
        if row["lease_job_id"] is None:
            return
        if row["lease_live"]:
            raise LearnerChallengeBusy("challenge operation already in progress")
        conn.execute(
            "UPDATE run_jobs SET status = 'failed', error = 'operation lease expired', "
            "completed_at = now(), terminal_expires_at = now() + interval '1 hour' "
            "WHERE id = %s AND status IN ('queued', 'running')",
            (row["lease_job_id"],),
        )
        conn.execute(
            "UPDATE learner_challenges SET lease_job_id = NULL, lease_expires_at = NULL "
            "WHERE user_id = %s AND slug = %s",
            (user, slug),
        )

    def write_file(
        self, slug: str, path: str, content: str, user_id: str | None
    ) -> None:
        user = self._user(user_id)
        meta, repo_file, canonical = self._validated_path(slug, path)
        if challenges.is_readonly(meta, canonical):
            raise PermissionError(path)
        existing = canonical in self._workspace(slug, user)
        if not repo_file.is_file() and not existing:
            raise challenges.ChallengeNotFound(path)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            conn.execute(
                "INSERT INTO workspace_files (user_id, slug, path, content) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (user_id, slug, path) DO UPDATE "
                "SET content = EXCLUDED.content, revision = workspace_files.revision + 1, "
                "updated_at = now()",
                (user, slug, canonical, content),
            )
            conn.execute(
                "UPDATE learner_challenges SET workspace_revision = workspace_revision + 1, "
                "updated_at = now() WHERE user_id = %s AND slug = %s",
                (user, slug),
            )

    def create_file(
        self, slug: str, path: str, content: str, user_id: str | None
    ) -> None:
        user = self._user(user_id)
        meta, repo_file, canonical = self._validated_path(slug, path)
        if (
            not canonical
            or canonical == "."
            or challenges.is_readonly(meta, canonical)
            or not challenges.is_creatable(meta, canonical)
        ):
            raise PermissionError(path)
        if repo_file.exists():
            raise FileExistsError(path)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            inserted = conn.execute(
                "INSERT INTO workspace_files (user_id, slug, path, content) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING path",
                (user, slug, canonical, content),
            ).fetchone()
            if inserted is None:
                raise FileExistsError(path)
            conn.execute(
                "UPDATE learner_challenges SET workspace_revision = workspace_revision + 1, "
                "updated_at = now() WHERE user_id = %s AND slug = %s",
                (user, slug),
            )

    def delete_file(self, slug: str, path: str, user_id: str | None) -> None:
        user = self._user(user_id)
        _, repo_file, canonical = self._validated_path(slug, path)
        if repo_file.exists():
            raise PermissionError(path)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            deleted = conn.execute(
                "DELETE FROM workspace_files WHERE user_id = %s AND slug = %s "
                "AND path = %s RETURNING path",
                (user, slug, canonical),
            ).fetchone()
            if deleted is None:
                raise challenges.ChallengeNotFound(path)
            conn.execute(
                "UPDATE learner_challenges SET workspace_revision = workspace_revision + 1, "
                "updated_at = now() WHERE user_id = %s AND slug = %s",
                (user, slug),
            )

    def search_files(
        self, slug: str, query: str, limit: int, user_id: str | None
    ) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        if not needle:
            return []
        if len(needle) > 200:
            raise challenges.InvalidPath("query too long")
        bounded_limit = max(1, min(int(limit), 200))
        hits: list[dict[str, Any]] = []
        for entry in self.file_tree(slug, user_id):
            text = self.read_file(slug, entry["path"], user_id)
            for line_number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    hits.append(
                        {"path": entry["path"], "line": line_number, "text": line[:240]}
                    )
                    if len(hits) >= bounded_limit:
                        return hits
        return hits

    def snapshot(self, slug: str, user_id: str | None) -> WorkspaceSnapshot:
        self._user(user_id)
        meta = challenges.load(slug)
        root = challenges.repo_dir(slug)
        snapshot = self._workspace_snapshot(slug, user_id)
        files = snapshot.files
        requirements = (meta.get("runtime") or {}).get("requirements")
        for path in files:
            repo_file, canonical = challenges._safe_relpath(root, path)
            if (
                canonical != path
                or any(part in challenges.IGNORED for part in Path(path).parts)
                or challenges.is_readonly(meta, canonical)
                or canonical == requirements
                or (not repo_file.is_file() and not challenges.is_creatable(meta, canonical))
            ):
                raise challenges.InvalidPath(path)
        return snapshot

    def record_run(
        self, slug: str, user_id: str | None, **values: Any
    ) -> dict[str, Any]:
        user = self._user(user_id)
        now = datetime.now(timezone.utc)
        started_at = values.get("started_at") or now.isoformat()
        green = bool(values.get("green"))
        duration_ms = max(0, int(values.get("duration_ms", 0)))
        elapsed = values.get("session_elapsed_ms")
        output = str(values.get("output", ""))
        output_tail = output[-progress.OUTPUT_TAIL_LIMIT :]
        output_truncated = bool(values.get("output_truncated")) or len(output) > len(
            output_tail
        )
        workspace = values.get("workspace")
        workspace_json = (
            None
            if workspace is None
            else json.dumps(dict(workspace), sort_keys=True)
        )
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            conn.execute(
                "UPDATE learner_challenges SET attempts = attempts + 1, "
                "status = CASE WHEN status = 'solved' OR %s THEN 'solved' "
                "ELSE 'attempted' END, solved_at = CASE WHEN %s "
                "THEN COALESCE(solved_at, %s) ELSE solved_at END, updated_at = now() "
                "WHERE user_id = %s AND slug = %s",
                (green, green, now, user, slug),
            )
            row = conn.execute(
                "INSERT INTO challenge_runs (user_id, slug, started_at, duration_ms, "
                "session_elapsed_ms, green, passed, failed, errors, skipped, exit_code, "
                "output_tail, output_truncated, tests, workspace_snapshot) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "RETURNING id",
                (
                    user,
                    slug,
                    started_at,
                    duration_ms,
                    None if elapsed is None else max(0, int(elapsed)),
                    green,
                    int(values.get("passed", 0)),
                    int(values.get("failed", 0)),
                    int(values.get("errors", 0)),
                    int(values.get("skipped", 0)),
                    int(values.get("exit_code", 0)),
                    output_tail,
                    output_truncated,
                    json.dumps(values.get("tests") or []),
                    workspace_json,
                ),
            ).fetchone()
            conn.execute(
                "DELETE FROM challenge_runs WHERE user_id = %s AND slug = %s "
                "AND id NOT IN (SELECT id FROM challenge_runs WHERE user_id = %s "
                "AND slug = %s ORDER BY id DESC LIMIT %s)",
                (user, slug, user, slug, progress.RUN_HISTORY_LIMIT),
            )
            self._record_product_event(
                conn,
                user,
                "first_run",
                slug=slug,
                dedupe_key=f"first_run:{slug}",
            )
            if green:
                self._record_product_event(
                    conn,
                    user,
                    "successful_run",
                    slug=slug,
                    dedupe_key=f"successful_run:{slug}",
                )
        return {
            "id": row["id"],
            "slug": slug,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "session_elapsed_ms": elapsed,
            "green": green,
            "passed": int(values.get("passed", 0)),
            "failed": int(values.get("failed", 0)),
            "errors": int(values.get("errors", 0)),
            "skipped": int(values.get("skipped", 0)),
            "exit_code": int(values.get("exit_code", 0)),
        }

    def list_runs(
        self, slug: str, limit: int, user_id: str | None
    ) -> list[dict[str, Any]]:
        user = self._user(user_id)
        bounded = max(1, min(int(limit), progress.RUN_HISTORY_LIMIT))
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, slug, started_at, duration_ms, session_elapsed_ms, green, "
                "passed, failed, errors, skipped, exit_code, output_tail, "
                "output_truncated, tests, "
                "(workspace_snapshot IS NOT NULL) AS snapshot_available "
                "FROM challenge_runs "
                "WHERE user_id = %s AND slug = %s ORDER BY id DESC LIMIT %s",
                (user, slug, bounded),
            ).fetchall()
        return [
            {
                **dict(row),
                "started_at": row["started_at"].isoformat(),
                "tests": row["tests"] if isinstance(row["tests"], list) else [],
            }
            for row in rows
        ]

    def restore_run(
        self, slug: str, run_id: int, user_id: str | None
    ) -> WorkspaceSnapshot:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            row = conn.execute(
                "SELECT workspace_snapshot FROM challenge_runs "
                "WHERE user_id = %s AND slug = %s AND id = %s",
                (user, slug, run_id),
            ).fetchone()
            if row is None:
                raise RunNotFound(run_id)
            workspace = row["workspace_snapshot"]
            if workspace is None:
                raise RunSnapshotUnavailable(
                    "run does not have a workspace snapshot"
                )
            if not isinstance(workspace, dict):
                raise RunSnapshotUnavailable("run workspace snapshot is invalid")
            try:
                validated = challenges.validated_workspace_snapshot(slug, workspace)
            except challenges.InvalidPath as exc:
                raise RunSnapshotUnavailable(
                    "run workspace snapshot is no longer compatible"
                ) from exc
            conn.execute(
                "DELETE FROM workspace_files WHERE user_id = %s AND slug = %s",
                (user, slug),
            )
            for path, content in validated.items():
                conn.execute(
                    "INSERT INTO workspace_files (user_id, slug, path, content) "
                    "VALUES (%s, %s, %s, %s)",
                    (user, slug, path, content),
                )
            revision = conn.execute(
                "UPDATE learner_challenges SET workspace_revision = workspace_revision + 1, "
                "updated_at = now() WHERE user_id = %s AND slug = %s "
                "RETURNING workspace_revision",
                (user, slug),
            ).fetchone()["workspace_revision"]
        return WorkspaceSnapshot(revision=revision, files=validated)

    def mark_spoiled(self, slug: str, user_id: str | None) -> dict[str, Any]:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            row = conn.execute(
                "UPDATE learner_challenges SET spoiled = TRUE, updated_at = now() "
                "WHERE user_id = %s AND slug = %s "
                "RETURNING status, attempts, solved_at, spoiled",
                (user, slug),
            ).fetchone()
        return self._progress(row)

    def reset(self, slug: str, user_id: str | None) -> None:
        user = self._user(user_id)
        challenges.load(slug)
        with self._pool.connection() as conn:
            self._begin_mutation(conn, user, slug)
            conn.execute(
                "DELETE FROM learner_challenges WHERE user_id = %s AND slug = %s",
                (user, slug),
            )

    def get_preferences(self, user_id: str | None) -> dict[str, Any]:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT prep_path FROM learner_preferences WHERE user_id = %s",
                (user,),
            ).fetchone()
        return {"prep_path": row["prep_path"] if row else None}

    def set_prep_path(
        self, user_id: str | None, prep_path: str
    ) -> dict[str, Any]:
        if prep_path not in PREP_PATHS:
            raise ValueError("unknown prep path")
        user = self._user(user_id)
        with self._pool.connection() as conn:
            previous = conn.execute(
                "SELECT prep_path FROM learner_preferences WHERE user_id = %s FOR UPDATE",
                (user,),
            ).fetchone()
            conn.execute(
                "INSERT INTO learner_preferences (user_id, prep_path) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET prep_path = EXCLUDED.prep_path, "
                "updated_at = now()",
                (user, prep_path),
            )
            if previous is None or previous["prep_path"] != prep_path:
                self._record_product_event(
                    conn,
                    user,
                    "path_selected",
                    properties={"prep_path": prep_path},
                )
        return {"prep_path": prep_path}

    def record_visit(
        self, user_id: str | None, visited_at: datetime | None = None
    ) -> None:
        user = self._user(user_id)
        visit = (visited_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        day_start = visit.replace(hour=0, minute=0, second=0, microsecond=0)
        day = visit.date().isoformat()
        with self._pool.connection() as conn:
            prior = conn.execute(
                "SELECT 1 FROM product_events WHERE user_id = %s "
                "AND event_name = 'catalog_visit' AND occurred_at < %s LIMIT 1",
                (user, day_start),
            ).fetchone()
            inserted = self._record_product_event(
                conn,
                user,
                "catalog_visit",
                dedupe_key=f"catalog_visit:{day}",
                occurred_at=visit,
            )
            if inserted and prior is not None:
                self._record_product_event(
                    conn,
                    user,
                    "return_visit",
                    dedupe_key=f"return_visit:{day}",
                    occurred_at=visit,
                )

    @staticmethod
    def _debrief(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "root_cause": row["root_cause"],
            "fix_reasoning": row["fix_reasoning"],
            "tradeoff": row["tradeoff"],
            "useful": row["useful"],
            "feedback": row["feedback"],
            "updated_at": row["updated_at"].isoformat(),
        }

    def get_debrief(
        self, slug: str, user_id: str | None
    ) -> dict[str, Any] | None:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT root_cause, fix_reasoning, tradeoff, useful, feedback, updated_at "
                "FROM challenge_debriefs WHERE user_id = %s AND slug = %s",
                (user, slug),
            ).fetchone()
        return None if row is None else self._debrief(row)

    def save_debrief(
        self, slug: str, user_id: str | None, **values: Any
    ) -> dict[str, Any]:
        user = self._user(user_id)
        values = _validated_debrief(values)
        with self._pool.connection() as conn:
            state = conn.execute(
                "SELECT status FROM learner_challenges "
                "WHERE user_id = %s AND slug = %s FOR UPDATE",
                (user, slug),
            ).fetchone()
            if state is None or state["status"] != "solved":
                raise DebriefRequiresSolved("debrief requires a solved challenge")
            row = conn.execute(
                "INSERT INTO challenge_debriefs "
                "(user_id, slug, root_cause, fix_reasoning, tradeoff, useful, feedback) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id, slug) DO UPDATE SET "
                "root_cause = EXCLUDED.root_cause, fix_reasoning = EXCLUDED.fix_reasoning, "
                "tradeoff = EXCLUDED.tradeoff, useful = EXCLUDED.useful, "
                "feedback = EXCLUDED.feedback, updated_at = now() "
                "RETURNING root_cause, fix_reasoning, tradeoff, useful, feedback, updated_at",
                (
                    user,
                    slug,
                    values["root_cause"],
                    values["fix_reasoning"],
                    values["tradeoff"],
                    values["useful"],
                    values.get("feedback", ""),
                ),
            ).fetchone()
            self._record_product_event(
                conn,
                user,
                "debrief_completed",
                slug=slug,
                dedupe_key=f"debrief_completed:{slug}",
            )
            self._record_product_event(
                conn,
                user,
                "feedback_submitted",
                slug=slug,
                dedupe_key=f"feedback_submitted:{slug}",
            )
        return self._debrief(row)

    def list_product_events(
        self, user_id: str | None
    ) -> list[dict[str, Any]]:
        user = self._user(user_id)
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT event_name, slug, properties, occurred_at FROM product_events "
                "WHERE user_id = %s ORDER BY id",
                (user,),
            ).fetchall()
        return [
            {
                "event_name": row["event_name"],
                "slug": row["slug"],
                "properties": row["properties"],
                "occurred_at": row["occurred_at"].isoformat(),
            }
            for row in rows
        ]
