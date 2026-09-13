"""Request admission, rate limiting, and durable audit controls."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

import learner_state


class AbuseControlsUnavailable(RuntimeError):
    """The Hosted Mode abuse-control dependency is unavailable."""


class RateLimitExceeded(RuntimeError):
    """A learner exceeded a configured request rate."""

    retry_after = 60

    def __init__(
        self,
        message: str,
        *,
        retry_after: int = 60,
        scope: str = "all",
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.scope = scope


class ContentScrapeDetected(RateLimitExceeded):
    """A learner crossed a bounded bulk-content access threshold."""


class RequestBodyTooLarge(ValueError):
    """A request body exceeded the configured byte limit."""


@dataclass(frozen=True)
class AbuseControlPolicy:
    max_request_bytes: int = 262_144
    requests_per_minute: int = 240
    mutations_per_minute: int = 30
    runs_per_minute: int = 6
    content_reads_per_minute: int = 120
    distinct_challenges_per_hour: int = 20
    solutions_per_hour: int = 5
    max_active_runs: int = 20
    max_active_runs_per_user: int = 1
    audit_retention_days: int = 30

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_active_runs_per_user > self.max_active_runs:
            raise ValueError(
                "max_active_runs_per_user cannot exceed max_active_runs"
            )
        if not (
            self.runs_per_minute
            <= self.mutations_per_minute
            <= self.requests_per_minute
        ):
            raise ValueError(
                "run, mutation, and total request limits must be nested"
            )


def policy_from_environment(source: Mapping[str, str]) -> AbuseControlPolicy:
    """Build the shared API/worker admission policy from deployment settings."""
    names = {
        "max_request_bytes": "GREENLINE_MAX_REQUEST_BYTES",
        "requests_per_minute": "GREENLINE_REQUESTS_PER_MINUTE",
        "mutations_per_minute": "GREENLINE_MUTATIONS_PER_MINUTE",
        "runs_per_minute": "GREENLINE_RUNS_PER_MINUTE",
        "content_reads_per_minute": "GREENLINE_CONTENT_READS_PER_MINUTE",
        "distinct_challenges_per_hour": "GREENLINE_DISTINCT_CHALLENGES_PER_HOUR",
        "solutions_per_hour": "GREENLINE_SOLUTIONS_PER_HOUR",
        "max_active_runs": "GREENLINE_MAX_ACTIVE_RUNS",
        "max_active_runs_per_user": "GREENLINE_MAX_ACTIVE_RUNS_PER_USER",
        "audit_retention_days": "GREENLINE_AUDIT_RETENTION_DAYS",
    }
    defaults = AbuseControlPolicy()
    values = {
        field: int(source.get(environment_name, str(getattr(defaults, field))))
        for field, environment_name in names.items()
    }
    return AbuseControlPolicy(**values)


@dataclass(frozen=True)
class RequestClassification:
    action: str
    slug: str | None
    mutation: bool
    run: bool
    content: bool
    solution: bool


@dataclass(frozen=True)
class RequestAdmission:
    audit_id: UUID | None
    limit: int | None = None
    remaining: int | None = None


class AbuseControlAdapter(Protocol):
    policy: AbuseControlPolicy

    def check_ready(self) -> None: ...
    def begin_request(
        self,
        user_id: str,
        method: str,
        path: str,
        request_id: str,
    ) -> RequestAdmission: ...
    def finish_request(self, admission: RequestAdmission, status_code: int) -> None: ...
    def list_audit_events(
        self, user_id: str, limit: int = 100
    ) -> list[dict[str, Any]]: ...


def classify_request(method: str, path: str) -> RequestClassification:
    """Map concrete paths to a bounded, non-sensitive audit vocabulary."""
    normalized_method = method.upper()
    parts = [part for part in path.split("/") if part]
    slug = parts[2] if len(parts) > 2 and parts[:2] == ["api", "challenges"] else None
    mutation = normalized_method in {"POST", "PUT", "PATCH", "DELETE"}
    run = bool(
        mutation
        and normalized_method == "POST"
        and slug
        and len(parts) == 4
        and parts[3] in {"run", "runs"}
    )
    solution = bool(
        normalized_method == "GET"
        and slug
        and len(parts) == 4
        and parts[3] == "solution"
    )
    content = bool(
        normalized_method == "GET"
        and slug
        and (
            len(parts) == 3
            or (len(parts) >= 4 and parts[3] in {"files", "solution"})
        )
    )
    if run:
        action = "challenge.run"
    elif slug and "files" in parts and mutation:
        action = "challenge.file.mutate"
    elif slug and parts[-1:] == ["reset"]:
        action = "challenge.reset"
    elif slug and parts[-1:] == ["spoil"]:
        action = "challenge.spoil"
    elif solution:
        action = "challenge.solution.read"
    elif content:
        action = "challenge.content.read"
    elif mutation:
        action = "api.mutate"
    else:
        action = "api.read"
    return RequestClassification(action, slug, mutation, run, content, solution)


class LocalAbuseControlAdapter:
    """Preserve the unrestricted trusted Local Mode workflow."""

    def __init__(self) -> None:
        self.policy = AbuseControlPolicy()

    def check_ready(self) -> None:
        return None

    def begin_request(
        self,
        user_id: str,
        method: str,
        path: str,
        request_id: str,
    ) -> RequestAdmission:
        return RequestAdmission(None)

    def finish_request(self, admission: RequestAdmission, status_code: int) -> None:
        return None

    def list_audit_events(
        self, user_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        return []


class PostgresAbuseControlAdapter:
    """Atomically rate-limit requests and persist their audit lifecycle."""

    def __init__(self, pool: Any, policy: AbuseControlPolicy | None = None) -> None:
        self._pool = pool
        self.policy = policy or AbuseControlPolicy()

    @classmethod
    def connect(
        cls, dsn: str, policy: AbuseControlPolicy | None = None
    ) -> "PostgresAbuseControlAdapter":
        pool = None
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
            adapter = cls(pool, policy)
            adapter.check_ready()
            return adapter
        except Exception as exc:
            if pool is not None:
                pool.close()
            raise AbuseControlsUnavailable("abuse controls are unavailable") from exc

    def close(self) -> None:
        self._pool.close()

    def check_ready(self) -> None:
        try:
            with self._pool.connection(timeout=3) as conn:
                row = conn.execute(
                    "SELECT version FROM greenline_schema_version WHERE singleton = TRUE"
                ).fetchone()
        except Exception as exc:
            raise AbuseControlsUnavailable("abuse controls are unavailable") from exc
        if row is None or row["version"] != learner_state.SCHEMA_VERSION:
            raise AbuseControlsUnavailable("abuse-control schema migration is required")

    @contextmanager
    def _connection(self):
        try:
            with self._pool.connection() as conn:
                yield conn
        except (RateLimitExceeded, AbuseControlsUnavailable):
            raise
        except Exception as exc:
            raise AbuseControlsUnavailable("abuse controls are unavailable") from exc

    @staticmethod
    def _consume(conn: Any, user_id: str, scope: str, limit: int) -> int | None:
        row = conn.execute(
            "INSERT INTO request_rate_windows "
            "(user_id, scope, window_started_at, request_count) "
            "VALUES (%s, %s, date_trunc('minute', now()), 1) "
            "ON CONFLICT (user_id, scope, window_started_at) DO UPDATE "
            "SET request_count = request_rate_windows.request_count + 1 "
            "WHERE request_rate_windows.request_count < %s "
            "RETURNING request_count",
            (user_id, scope, limit),
        ).fetchone()
        return None if row is None else int(row["request_count"])

    @staticmethod
    def _record_rejection(conn: Any, user_id: str, scope: str) -> bool:
        row = conn.execute(
            "UPDATE request_rate_windows SET rejected_count = rejected_count + 1 "
            "WHERE user_id = %s AND scope = %s "
            "AND window_started_at = date_trunc('minute', now()) "
            "RETURNING rejected_count",
            (user_id, scope),
        ).fetchone()
        return row is not None and row["rejected_count"] == 1

    @staticmethod
    def _record_content_access(
        conn: Any,
        user_id: str,
        slug: str,
        *,
        solution: bool,
    ) -> dict[str, int]:
        conn.execute(
            "INSERT INTO challenge_content_windows "
            "(user_id, slug, window_started_at, request_count, solution_count) "
            "VALUES (%s, %s, date_trunc('hour', now()), 1, %s) "
            "ON CONFLICT (user_id, slug, window_started_at) DO UPDATE SET "
            "request_count = challenge_content_windows.request_count + 1, "
            "solution_count = challenge_content_windows.solution_count + EXCLUDED.solution_count",
            (user_id, slug, 1 if solution else 0),
        )
        row = conn.execute(
            "SELECT count(*) AS distinct_challenges, "
            "coalesce(sum(request_count), 0) AS content_reads, "
            "coalesce(sum(solution_count), 0) AS solutions "
            "FROM challenge_content_windows WHERE user_id = %s "
            "AND window_started_at = date_trunc('hour', now())",
            (user_id,),
        ).fetchone()
        return {
            "distinct_challenges": int(row["distinct_challenges"]),
            "content_reads": int(row["content_reads"]),
            "solutions": int(row["solutions"]),
        }

    def begin_request(
        self,
        user_id: str,
        method: str,
        path: str,
        request_id: str,
    ) -> RequestAdmission:
        classification = classify_request(method, path)
        scopes = [("all", self.policy.requests_per_minute)]
        if classification.mutation:
            scopes.append(("mutation", self.policy.mutations_per_minute))
        if classification.run:
            scopes.append(("run", self.policy.runs_per_minute))
        if classification.content:
            scopes.append(("content", self.policy.content_reads_per_minute))

        audit_id = uuid4()
        limited = False
        limited_scope: str | None = None
        effective_limit = self.policy.requests_per_minute
        effective_remaining = effective_limit
        retry_after = 60
        with self._connection() as conn:
            for scope, limit in scopes:
                count = self._consume(conn, user_id, scope, limit)
                if count is None:
                    limited = True
                    limited_scope = scope
                    effective_limit = limit
                    effective_remaining = 0
                    break
                if limit <= effective_limit:
                    effective_limit = limit
                    effective_remaining = max(0, limit - count)
            if not limited and classification.content and classification.slug:
                content = self._record_content_access(
                    conn,
                    user_id,
                    classification.slug,
                    solution=classification.solution,
                )
                if (
                    content["distinct_challenges"]
                    > self.policy.distinct_challenges_per_hour
                ):
                    limited = True
                    limited_scope = "content_distinct_hour"
                    effective_limit = self.policy.distinct_challenges_per_hour
                    retry_after = 3600
                elif content["solutions"] > self.policy.solutions_per_hour:
                    limited = True
                    limited_scope = "content_solution_hour"
                    effective_limit = self.policy.solutions_per_hour
                    retry_after = 3600
            should_audit = (
                classification.mutation
                if not limited
                else (
                    True
                    if (limited_scope or "").startswith("content_")
                    else self._record_rejection(conn, user_id, limited_scope or "all")
                )
            )
            if should_audit:
                conn.execute(
                    "INSERT INTO request_audit_events "
                    "(id, request_id, user_id, action, resource_slug, method, outcome) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        audit_id,
                        request_id[:128],
                        user_id,
                        classification.action,
                        classification.slug,
                        method.upper()[:10],
                        "rate_limited" if limited else "started",
                    ),
                )
            conn.execute(
                "DELETE FROM request_rate_windows WHERE (user_id, scope, window_started_at) "
                "IN (SELECT user_id, scope, window_started_at FROM request_rate_windows "
                "WHERE window_started_at < date_trunc('minute', now()) - interval '1 day' "
                "ORDER BY window_started_at LIMIT 100)"
            )
            conn.execute(
                "DELETE FROM challenge_content_windows WHERE (user_id, slug, window_started_at) "
                "IN (SELECT user_id, slug, window_started_at FROM challenge_content_windows "
                "WHERE window_started_at < date_trunc('hour', now()) - interval '1 day' "
                "ORDER BY window_started_at LIMIT 100)"
            )
            conn.execute(
                "DELETE FROM request_audit_events WHERE id IN "
                "(SELECT id FROM request_audit_events WHERE created_at < now() - "
                "(%s * interval '1 day') ORDER BY created_at LIMIT 100)",
                (self.policy.audit_retention_days,),
            )
        if limited:
            if (limited_scope or "").startswith("content"):
                raise ContentScrapeDetected(
                    "bulk challenge content access detected",
                    retry_after=retry_after,
                    scope=limited_scope or "content",
                )
            raise RateLimitExceeded(
                "request rate limit exceeded",
                retry_after=retry_after,
                scope=limited_scope or "all",
            )
        return RequestAdmission(
            audit_id if should_audit else None,
            effective_limit,
            effective_remaining,
        )

    def finish_request(self, admission: RequestAdmission, status_code: int) -> None:
        if admission.audit_id is None:
            return
        with self._connection() as conn:
            conn.execute(
                "UPDATE request_audit_events SET outcome = %s, response_status = %s, "
                "completed_at = now() WHERE id = %s AND outcome = 'started'",
                (
                    "succeeded" if status_code < 400 else "failed",
                    int(status_code),
                    admission.audit_id,
                ),
            )

    def list_audit_events(
        self, user_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 500))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT request_id, action, resource_slug, method, outcome, "
                "response_status, created_at, completed_at FROM request_audit_events "
                "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, bounded),
            ).fetchall()
        return [dict(row) for row in rows]


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP bodies before authentication or request parsing."""

    def __init__(self, app: Any, max_bytes: int, security_events: Any = None) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.security_events = security_events

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError:
                declared = self.max_bytes + 1
            if declared > self.max_bytes or declared < 0:
                if self.security_events is not None:
                    self.security_events.emit(
                        "request.body_rejected",
                        severity="warning",
                        fields={"declared_bytes": max(0, declared)},
                    )
                await self._reject(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    if self.security_events is not None:
                        self.security_events.emit(
                            "request.body_rejected",
                            severity="warning",
                            fields={"received_bytes": received},
                        )
                    raise RequestBodyTooLarge("request body too large")
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(scope: dict, receive: Any, send: Any) -> None:
        from starlette.responses import JSONResponse

        await JSONResponse(
            {"detail": "request body too large"},
            status_code=413,
        )(scope, receive, send)
