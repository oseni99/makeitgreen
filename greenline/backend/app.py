"""MakeItGreen API — a Gronex-style repo-based interview practice platform."""
from __future__ import annotations

import os
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

import challenges as ch
import abuse_controls
import auth
import learner_state
import operations
import progress
import run_coordination
import runner
from challenge_locks import acquire_challenge, challenge_operation
from run_jobs import RunJobStore, jobs

LOCAL_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
execution_adapter: runner.ExecutionAdapter = runner.LocalSubprocessAdapter()
learner_state_adapter: learner_state.LearnerStateAdapter = (
    learner_state.LocalLearnerStateAdapter()
)
abuse_control_adapter: abuse_controls.AbuseControlAdapter = (
    abuse_controls.LocalAbuseControlAdapter()
)


class RuntimeMode(StrEnum):
    LOCAL = "local"
    HOSTED = "hosted"


@dataclass(frozen=True)
class CompositionViolation:
    code: str
    message: str


class CompositionError(RuntimeError):
    def __init__(self, violations: list[CompositionViolation]) -> None:
        self.violations = tuple(violations)
        super().__init__("; ".join(violation.message for violation in violations))


@dataclass(frozen=True)
class _RuntimeSettings:
    mode: RuntimeMode
    clerk_secret: str | None
    authorized_parties: tuple[str, ...]
    execution_adapter: runner.ExecutionAdapter
    learner_state_adapter: learner_state.LearnerStateAdapter
    run_jobs_adapter: RunJobStore | run_coordination.PostgresRunJobAdapter
    abuse_control_adapter: abuse_controls.AbuseControlAdapter
    trusted_proxy_cidrs: tuple[str, ...]
    security_events: operations.SecurityEventSink
    release_sha: str


@dataclass(frozen=True)
class HostedAdapters:
    """Production control-plane Adapters supplied at the composition seam."""

    learner_state: learner_state.PostgresLearnerStateAdapter | None = None
    run_jobs: run_coordination.PostgresRunJobAdapter | None = None
    abuse_controls: abuse_controls.PostgresAbuseControlAdapter | None = None


class _SinglePageApplication(StaticFiles):
    """Serve browser routes from index.html without hiding missing assets."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            headers = Headers(scope=scope)
            browser_navigation = (
                exc.status_code == 404
                and scope["method"] in {"GET", "HEAD"}
                and "text/html" in headers.get("accept", "")
                and "." not in Path(path).name
            )
            if not browser_navigation:
                raise
            return await super().get_response("index.html", scope)


def _configured_learner_state(
    dsn: str | None,
) -> learner_state.PostgresLearnerStateAdapter | None:
    if not dsn:
        return None
    return learner_state.PostgresLearnerStateAdapter.connect(dsn)


def _configured_run_jobs(
    dsn: str | None, policy: abuse_controls.AbuseControlPolicy
) -> run_coordination.PostgresRunJobAdapter | None:
    if not dsn:
        return None
    return run_coordination.PostgresRunJobAdapter.connect(
        dsn,
        run_coordination.RunAdmissionPolicy(
            max_active_runs=policy.max_active_runs,
            max_active_runs_per_user=policy.max_active_runs_per_user,
        ),
    )


def _configured_abuse_controls(
    dsn: str | None, policy: abuse_controls.AbuseControlPolicy
) -> abuse_controls.PostgresAbuseControlAdapter | None:
    if not dsn:
        return None
    return abuse_controls.PostgresAbuseControlAdapter.connect(dsn, policy)


def _read_settings(
    environment: Mapping[str, str] | None,
    hosted_adapters: HostedAdapters | object | None,
) -> _RuntimeSettings:
    source = os.environ if environment is None else environment
    violations: list[CompositionViolation] = []
    raw_mode = source.get("GREENLINE_MODE")
    if not raw_mode:
        violations.append(
            CompositionViolation(
                "missing_runtime_mode",
                "GREENLINE_MODE is required and must be 'local' or 'hosted'",
            )
        )
        mode = None
    else:
        try:
            mode = RuntimeMode(raw_mode)
        except ValueError:
            violations.append(
                CompositionViolation(
                    "invalid_runtime_mode",
                    "GREENLINE_MODE must be exactly 'local' or 'hosted'",
                )
            )
            mode = None

    secret_values: dict[str, str | None] = {}
    for secret_name in (
        "CLERK_SECRET_KEY",
        "GREENLINE_DATABASE_URL",
        "GREENLINE_LOG_HMAC_KEY",
    ):
        try:
            secret_values[secret_name] = operations.read_secret(source, secret_name)
        except operations.OperationalConfigurationError:
            secret_values[secret_name] = None
            if not any(
                violation.code == "invalid_secret_configuration"
                for violation in violations
            ):
                violations.append(
                    CompositionViolation(
                        "invalid_secret_configuration",
                        "secret values must use one valid direct or absolute file source",
                    )
                )
    secret = secret_values["CLERK_SECRET_KEY"]
    database_url = secret_values["GREENLINE_DATABASE_URL"]
    log_hmac_key = secret_values["GREENLINE_LOG_HMAC_KEY"]
    parties = tuple(
        value.strip()
        for value in source.get("CLERK_AUTHORIZED_PARTIES", "").split(",")
        if value.strip()
    )
    selected_execution: runner.ExecutionAdapter = execution_adapter
    selected_learner_state: learner_state.LearnerStateAdapter = learner_state_adapter
    selected_run_jobs: RunJobStore | run_coordination.PostgresRunJobAdapter = jobs
    selected_abuse_controls: abuse_controls.AbuseControlAdapter = abuse_control_adapter
    selected_security_events: operations.SecurityEventSink = (
        operations.NullSecurityEventSink()
    )
    proxies: tuple[str, ...] = ()
    durable_state: learner_state.PostgresLearnerStateAdapter | None = None
    durable_run_jobs: run_coordination.PostgresRunJobAdapter | None = None
    durable_abuse_controls: abuse_controls.PostgresAbuseControlAdapter | None = None
    owns_durable_state = False
    owns_durable_run_jobs = False
    owns_durable_abuse_controls = False
    try:
        policy = abuse_controls.policy_from_environment(source)
    except (TypeError, ValueError):
        policy = abuse_controls.AbuseControlPolicy()
        if mode is RuntimeMode.HOSTED:
            violations.append(
                CompositionViolation(
                    "invalid_abuse_configuration",
                    "Hosted Mode abuse-control limits must be positive integers",
                )
            )
    if mode is RuntimeMode.HOSTED:
        release_sha = source.get("GREENLINE_RELEASE_SHA", "").strip()
        if len(release_sha) != 40 or any(
            character not in "0123456789abcdef" for character in release_sha
        ):
            violations.append(
                CompositionViolation(
                    "release_identity_required",
                    "Hosted Mode requires GREENLINE_RELEASE_SHA as a full lowercase commit SHA",
                )
            )
        if source.get("GREENLINE_PROCESS_ROLE") != "api":
            violations.append(
                CompositionViolation(
                    "api_process_role_required",
                    "Hosted API must use the supported API process launcher",
                )
            )
        try:
            proxies = operations.trusted_proxy_cidrs(source)
        except operations.OperationalConfigurationError:
            violations.append(
                CompositionViolation(
                    "trusted_proxy_required",
                    "Hosted Mode requires explicit trusted proxy IP networks",
                )
            )
        if source.get("GREENLINE_PROXY_HEADERS_CONFIGURED") != "1":
            violations.append(
                CompositionViolation(
                    "trusted_proxy_launcher_required",
                    "Hosted Mode must use the trusted-proxy production launcher",
                )
            )
        if log_hmac_key is None:
            violations.append(
                CompositionViolation(
                    "security_logging_required",
                    "Hosted Mode requires GREENLINE_LOG_HMAC_KEY or its file source",
                )
            )
        else:
            try:
                selected_security_events = operations.JsonSecurityEventSink(
                    log_hmac_key.encode("utf-8")
                )
            except operations.OperationalConfigurationError:
                violations.append(
                    CompositionViolation(
                        "invalid_security_logging_configuration",
                        "Hosted Mode security-log HMAC key must contain at least 32 bytes",
                    )
                )
        if secret is None:
            violations.append(
                CompositionViolation(
                    "clerk_secret_required",
                    "Hosted Mode requires CLERK_SECRET_KEY",
                )
            )
        if not parties:
            violations.append(
                CompositionViolation(
                    "authorized_parties_required",
                    "Hosted Mode requires a non-empty CLERK_AUTHORIZED_PARTIES allowlist",
                )
            )
        selected_execution = runner.DisabledExecutionAdapter()
        durable_state = (
            hosted_adapters.learner_state
            if (
                isinstance(hosted_adapters, HostedAdapters)
                and type(hosted_adapters.learner_state)
                is learner_state.PostgresLearnerStateAdapter
            )
            else None
        )
        if durable_state is None:
            try:
                durable_state = _configured_learner_state(database_url)
                owns_durable_state = durable_state is not None
            except learner_state.LearnerStateUnavailable:
                violations.append(
                    CompositionViolation(
                        "durable_state_unavailable",
                        "Hosted Mode PostgreSQL learner state is unavailable",
                    )
                )
        if durable_state is not None:
            try:
                durable_state.check_ready()
            except learner_state.LearnerStateUnavailable:
                violations.append(
                    CompositionViolation(
                        "durable_state_unavailable",
                        "Hosted Mode PostgreSQL learner state is unavailable",
                    )
                )
                if owns_durable_state:
                    durable_state.close()
                    owns_durable_state = False
                durable_state = None
        if durable_state is None:
            violations.append(
                CompositionViolation(
                    "durable_state_required",
                    "Hosted Mode requires the PostgreSQL Learner State Adapter",
                )
            )
        else:
            selected_learner_state = durable_state
        durable_run_jobs = (
            hosted_adapters.run_jobs
            if (
                isinstance(hosted_adapters, HostedAdapters)
                and type(hosted_adapters.run_jobs)
                is run_coordination.PostgresRunJobAdapter
            )
            else None
        )
        if durable_run_jobs is None:
            try:
                durable_run_jobs = _configured_run_jobs(database_url, policy)
                owns_durable_run_jobs = durable_run_jobs is not None
            except run_coordination.RunJobsUnavailable:
                violations.append(
                    CompositionViolation(
                        "distributed_coordination_unavailable",
                        "Hosted Mode durable Run Jobs are unavailable",
                    )
                )
        if durable_run_jobs is not None:
            try:
                durable_run_jobs.check_ready()
            except run_coordination.RunJobsUnavailable:
                violations.append(
                    CompositionViolation(
                        "distributed_coordination_unavailable",
                        "Hosted Mode durable Run Jobs are unavailable",
                    )
                )
                if owns_durable_run_jobs:
                    durable_run_jobs.close()
                    owns_durable_run_jobs = False
                durable_run_jobs = None
        if durable_run_jobs is None:
            violations.append(
                CompositionViolation(
                    "distributed_coordination_required",
                    "Hosted Mode requires durable Run Jobs and cross-replica leases",
                )
            )
        else:
            selected_run_jobs = durable_run_jobs
        expected_run_policy = run_coordination.RunAdmissionPolicy(
            max_active_runs=policy.max_active_runs,
            max_active_runs_per_user=policy.max_active_runs_per_user,
        )
        if (
            durable_run_jobs is not None
            and durable_run_jobs.admission_policy != expected_run_policy
        ):
            violations.append(
                CompositionViolation(
                    "invalid_abuse_configuration",
                    "Hosted Mode Run Job limits must match the abuse-control policy",
                )
            )
        durable_abuse_controls = (
            hosted_adapters.abuse_controls
            if (
                isinstance(hosted_adapters, HostedAdapters)
                and type(hosted_adapters.abuse_controls)
                is abuse_controls.PostgresAbuseControlAdapter
            )
            else None
        )
        if durable_abuse_controls is None:
            try:
                durable_abuse_controls = _configured_abuse_controls(database_url, policy)
                owns_durable_abuse_controls = durable_abuse_controls is not None
            except abuse_controls.AbuseControlsUnavailable:
                violations.append(
                    CompositionViolation(
                        "abuse_controls_unavailable",
                        "Hosted Mode abuse controls are unavailable",
                    )
                )
        if durable_abuse_controls is not None:
            try:
                durable_abuse_controls.check_ready()
            except abuse_controls.AbuseControlsUnavailable:
                violations.append(
                    CompositionViolation(
                        "abuse_controls_unavailable",
                        "Hosted Mode abuse controls are unavailable",
                    )
                )
                if owns_durable_abuse_controls:
                    durable_abuse_controls.close()
                    owns_durable_abuse_controls = False
                durable_abuse_controls = None
        if durable_abuse_controls is None:
            violations.append(
                CompositionViolation(
                    "abuse_controls_required",
                    "Hosted Mode requires PostgreSQL rate limits and audit records",
                )
            )
        elif durable_abuse_controls.policy != policy:
            violations.append(
                CompositionViolation(
                    "invalid_abuse_configuration",
                    "Hosted Mode abuse-control Adapter policy must match configuration",
                )
            )
        else:
            selected_abuse_controls = durable_abuse_controls

    if violations:
        if owns_durable_state and durable_state is not None:
            durable_state.close()
        if owns_durable_run_jobs and durable_run_jobs is not None:
            durable_run_jobs.close()
        if owns_durable_abuse_controls and durable_abuse_controls is not None:
            durable_abuse_controls.close()
        raise CompositionError(violations)
    assert mode is not None
    release_sha = source.get("GREENLINE_RELEASE_SHA", "").strip() or "development"
    return _RuntimeSettings(
        mode,
        secret,
        parties,
        selected_execution,
        selected_learner_state,
        selected_run_jobs,
        selected_abuse_controls,
        proxies,
        selected_security_events,
        release_sha,
    )


def _application_lifespan(
    settings: _RuntimeSettings,
):
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            application.state.ready = True
            yield
        finally:
            application.state.ready = False
            if type(settings.run_jobs_adapter) is run_coordination.PostgresRunJobAdapter:
                settings.run_jobs_adapter.close()
            if (
                type(settings.learner_state_adapter)
                is learner_state.PostgresLearnerStateAdapter
            ):
                settings.learner_state_adapter.close()
            if (
                type(settings.abuse_control_adapter)
                is abuse_controls.PostgresAbuseControlAdapter
            ):
                settings.abuse_control_adapter.close()

    return lifespan


router = APIRouter()


def request_user_id(request: Request | None) -> str | None:
    if request is None:
        return None
    payload = getattr(request.state, "clerk_payload", None)
    return payload.get("sub") if isinstance(payload, dict) and isinstance(payload.get("sub"), str) else None


def request_execution_adapter(request: Request | None) -> runner.ExecutionAdapter:
    if request is None:
        return execution_adapter
    return request.app.state.execution_adapter


def request_learner_state(
    request: Request | None,
) -> learner_state.LearnerStateAdapter:
    if request is None:
        return learner_state_adapter
    return request.app.state.learner_state_adapter


def request_run_jobs(
    request: Request | None,
) -> RunJobStore | run_coordination.PostgresRunJobAdapter:
    if request is None:
        return jobs
    if request.app.state.runtime_settings.mode is RuntimeMode.LOCAL:
        return jobs
    return request.app.state.run_jobs_adapter


async def clerk_authentication(request: Request, call_next):
    settings: _RuntimeSettings = request.app.state.runtime_settings
    if request.url.path.startswith("/api/") and settings.clerk_secret is not None:
        try:
            payload = auth.authenticate(
                request,
                secret_key=settings.clerk_secret,
                parties=list(settings.authorized_parties) or None,
            )
        except Exception:
            payload = None
        if payload is None:
            return JSONResponse(status_code=401, content={"detail": "authentication required"})
        request.state.clerk_payload = payload
    return await call_next(request)


async def enforce_abuse_controls(request: Request, call_next):
    settings: _RuntimeSettings = request.app.state.runtime_settings
    if settings.mode is not RuntimeMode.HOSTED or not request.url.path.startswith(
        "/api/"
    ):
        return await call_next(request)
    user_id = request_user_id(request)
    if user_id is None:
        return JSONResponse(status_code=401, content={"detail": "authentication required"})
    request_id = uuid4().hex
    request.state.request_id = request_id
    request_started = time.monotonic()
    classification = abuse_controls.classify_request(
        request.method, request.url.path
    )
    try:
        admission = settings.abuse_control_adapter.begin_request(
            user_id,
            request.method,
            request.url.path,
            request_id,
        )
    except abuse_controls.RateLimitExceeded as exc:
        settings.security_events.emit(
            "request.rate_limited",
            request_id=request_id,
            user_id=user_id,
            severity="warning",
            fields={"action": classification.action},
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(exc.retry_after), "X-Request-ID": request_id},
            content={"detail": "request rate limit exceeded"},
        )
    except abuse_controls.AbuseControlsUnavailable:
        settings.security_events.emit(
            "request.admission_unavailable",
            request_id=request_id,
            user_id=user_id,
            severity="error",
            fields={"action": classification.action},
        )
        return JSONResponse(
            status_code=503,
            headers={"X-Request-ID": request_id},
            content={"detail": "request admission is temporarily unavailable"},
        )
    try:
        response = await call_next(request)
    except Exception:
        try:
            settings.abuse_control_adapter.finish_request(admission, 500)
        except abuse_controls.AbuseControlsUnavailable:
            pass
        raise
    try:
        settings.abuse_control_adapter.finish_request(admission, response.status_code)
    except abuse_controls.AbuseControlsUnavailable:
        response.headers["X-Audit-Status"] = "pending"
        settings.security_events.emit(
            "request.audit_pending",
            request_id=request_id,
            user_id=user_id,
            severity="error",
            fields={"action": classification.action},
        )
    settings.security_events.emit(
        "request.completed",
        request_id=request_id,
        user_id=user_id,
        severity="info" if response.status_code < 400 else "warning",
        fields={
            "action": classification.action,
            "status_code": response.status_code,
            "duration_ms": int((time.monotonic() - request_started) * 1000),
        },
    )
    response.headers["X-Request-ID"] = request_id
    if admission.limit is not None:
        response.headers["X-RateLimit-Limit"] = str(admission.limit)
        response.headers["X-RateLimit-Remaining"] = str(admission.remaining)
    return response


async def invalid_challenge_metadata(
    _request: Request, _exc: ch.InvalidChallengeMetadata
) -> JSONResponse:
    return JSONResponse(
        status_code=500, content={"detail": "invalid challenge metadata"}
    )


async def invalid_challenge_file_encoding(
    _request: Request, _exc: ch.InvalidChallengeFileEncoding
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "challenge file is not valid UTF-8"},
    )


async def execution_unavailable(
    _request: Request, _exc: runner.ExecutionUnavailable
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "challenge execution is temporarily unavailable"},
    )


async def unsupported_container_runtime(
    _request: Request, _exc: runner.UnsupportedContainerRuntime
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "challenge runtime is unavailable in Hosted Mode"},
    )


async def learner_state_unavailable(
    _request: Request, _exc: learner_state.LearnerStateUnavailable
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "learner state is temporarily unavailable"},
    )


async def learner_challenge_busy(
    _request: Request, exc: learner_state.LearnerChallengeBusy
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        headers={"Retry-After": str(exc.retry_after)},
        content={"detail": "challenge operation already in progress"},
    )


async def run_jobs_unavailable(
    _request: Request, _exc: run_coordination.RunJobsUnavailable
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "run jobs are temporarily unavailable"},
    )


async def run_capacity_exceeded(
    request: Request, exc: run_coordination.RunCapacityExceeded
) -> JSONResponse:
    settings: _RuntimeSettings = request.app.state.runtime_settings
    settings.security_events.emit(
        "run.capacity_exceeded",
        request_id=getattr(request.state, "request_id", None),
        user_id=request_user_id(request),
        severity="warning",
    )
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(exc.retry_after)},
        content={"detail": "Run Job capacity exceeded"},
    )


async def request_body_too_large(
    request: Request, _exc: abuse_controls.RequestBodyTooLarge
) -> JSONResponse:
    settings: _RuntimeSettings = request.app.state.runtime_settings
    settings.security_events.emit(
        "request.body_rejected",
        severity="warning",
    )
    return JSONResponse(
        status_code=413,
        content={"detail": "request body too large"},
    )


class FileBody(BaseModel):
    content: str = ""


class RunBody(BaseModel):
    # How long the learner has been working on this challenge (from the
    # workspace timer), in milliseconds. Optional — older clients omit it.
    session_elapsed_ms: int | None = Field(default=None, ge=0)


class PrepPath(StrEnum):
    FOUNDATIONS = "foundations"
    DISTRIBUTED = "distributed"
    DEBUGGING = "debugging"
    SENIOR = "senior"


class PreferencesBody(BaseModel):
    prep_path: PrepPath


class DebriefBody(BaseModel):
    root_cause: str = Field(min_length=1, max_length=1000)
    fix_reasoning: str = Field(min_length=1, max_length=1000)
    tradeoff: str = Field(min_length=1, max_length=1000)
    useful: bool
    feedback: str = Field(default="", max_length=1000)

    @field_validator("root_cause", "fix_reasoning", "tradeoff")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("feedback")
    @classmethod
    def trim_feedback(cls, value: str) -> str:
        return value.strip()


@router.get("/api/me/preferences")
def get_preferences(request: Request) -> dict:
    return request_learner_state(request).get_preferences(request_user_id(request))


@router.put("/api/me/preferences")
def put_preferences(body: PreferencesBody, request: Request) -> dict:
    return request_learner_state(request).set_prep_path(
        request_user_id(request), body.prep_path.value
    )


@router.post("/api/me/visits")
def record_visit(request: Request) -> dict:
    request_learner_state(request).record_visit(request_user_id(request))
    return {"ok": True}


@router.get("/api/me/activity")
def get_solve_activity(request: Request) -> dict:
    events = request_learner_state(request).list_product_events(
        request_user_id(request)
    )
    return {
        "solves": [
            {"slug": event["slug"], "solved_at": event["occurred_at"]}
            for event in events
            if event["event_name"] == "successful_run" and event["slug"]
        ]
    }


@router.get("/api/challenges/{slug}/debrief")
def get_debrief(slug: str, request: Request) -> dict:
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    debrief = request_learner_state(request).get_debrief(
        slug, request_user_id(request)
    )
    return {"debrief": debrief}


@router.put("/api/challenges/{slug}/debrief")
def put_debrief(slug: str, body: DebriefBody, request: Request) -> dict:
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    try:
        debrief = request_learner_state(request).save_debrief(
            slug,
            request_user_id(request),
            **body.model_dump(),
        )
    except learner_state.DebriefRequiresSolved:
        raise HTTPException(409, "debrief requires a solved challenge")
    return {"debrief": debrief}


def _empty_progress() -> dict:
    return {"status": "todo", "attempts": 0, "spoiled": False}


def _catalog_progress(variants: list[dict]) -> dict:
    progress_items = [variant["progress"] for variant in variants]
    if any(item["status"] == "solved" for item in progress_items):
        status = "solved"
    elif any(item["status"] == "attempted" for item in progress_items):
        status = "attempted"
    else:
        status = "todo"
    return {
        "status": status,
        "attempts": sum(item.get("attempts", 0) for item in progress_items),
        "spoiled": any(item.get("spoiled", False) for item in progress_items),
    }


def _with_variant_progress(meta: dict, progress: dict[str, dict]) -> dict:
    variants = [
        {**variant, "progress": progress.get(variant["slug"], _empty_progress())}
        for variant in meta["variants"]
    ]
    selected = progress.get(meta["slug"], _empty_progress())
    return {**meta, "variants": variants, "progress": selected}


@router.get("/api/challenges")
def list_challenges(request: Request) -> dict:
    prog = request_learner_state(request).get_all(request_user_id(request))
    items = []
    for meta in ch.load_all():
        item = _with_variant_progress(meta, prog)
        item["progress"] = _catalog_progress(item["variants"])
        items.append(item)
    return {"challenges": items}


@router.get("/api/challenges/{slug}")
def get_challenge(slug: str, request: Request) -> dict:
    try:
        meta = ch.load(slug)
        state = request_learner_state(request)
        user_id = request_user_id(request)
        tree = state.file_tree(slug, user_id)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    item = _with_variant_progress(meta, state.get_all(user_id))
    return {**item, "files": tree}


@router.get("/api/challenges/{slug}/files/{path:path}")
def get_file(slug: str, path: str, request: Request) -> dict:
    try:
        content = request_learner_state(request).read_file(
            slug, path, request_user_id(request)
        )
    except (ch.ChallengeNotFound, FileNotFoundError):
        raise HTTPException(404, "file not found")
    except ch.InvalidPath:
        raise HTTPException(400, "invalid path")
    return {"path": path, "content": content}


@router.put("/api/challenges/{slug}/files/{path:path}")
def put_file(slug: str, path: str, body: FileBody, request: Request = None) -> dict:  # type: ignore[assignment]
    with challenge_operation(slug):
        try:
            request_learner_state(request).write_file(
                slug, path, body.content, request_user_id(request)
            )
        except PermissionError:
            raise HTTPException(403, "file is read-only")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "file not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True}


@router.post("/api/challenges/{slug}/files/{path:path}")
def post_file(slug: str, path: str, body: FileBody | None = None, request: Request = None) -> dict:  # type: ignore[assignment]
    body = body or FileBody(content="")
    with challenge_operation(slug):
        try:
            request_learner_state(request).create_file(
                slug, path, body.content, request_user_id(request)
            )
        except PermissionError:
            raise HTTPException(403, "cannot create file")
        except FileExistsError:
            raise HTTPException(409, "file already exists")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True, "path": path, "new": True}


@router.delete("/api/challenges/{slug}/files/{path:path}")
def remove_file(slug: str, path: str, request: Request = None) -> dict:  # type: ignore[assignment]
    with challenge_operation(slug):
        try:
            request_learner_state(request).delete_file(
                slug, path, request_user_id(request)
            )
        except PermissionError:
            raise HTTPException(403, "cannot delete original file")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "file not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True}


@router.post("/api/challenges/{slug}/run")
def run(slug: str, body: RunBody | None = None, request: Request = None) -> dict:  # type: ignore[assignment]
    body = body or RunBody()
    if type(request_run_jobs(request)) is run_coordination.PostgresRunJobAdapter:
        raise HTTPException(
            409,
            "synchronous runs are unavailable in Hosted Mode; use /runs",
        )
    with challenge_operation(slug):
        try:
            ch.load(slug)
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        result = _execute_run(
            slug,
            body,
            request_execution_adapter(request),
            request_learner_state(request),
            request_user_id(request),
        )
    return result


def _execute_run(
    slug: str,
    body: RunBody,
    adapter: runner.ExecutionAdapter,
    state: learner_state.LearnerStateAdapter,
    user_id: str | None = None,
    on_output=None,
) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    workspace = state.snapshot(slug, user_id)
    result = adapter.execute(
        runner.ChallengeRun(
            slug=slug,
            user_id=user_id,
            workspace=workspace.files,
        ),
        on_output=on_output,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    run_meta = state.record_run(
        slug,
        user_id,
        green=result["green"],
        duration_ms=duration_ms,
        session_elapsed_ms=body.session_elapsed_ms,
        passed=result.get("passed", 0),
        failed=result.get("failed", 0),
        errors=result.get("errors", 0),
        skipped=result.get("skipped", 0),
        exit_code=result.get("exit_code", 0),
        output=result.get("output", ""),
        tests=result.get("tests"),
        started_at=started_at,
        output_truncated=result.get("output_truncated", False),
        workspace=dict(workspace.files),
    )
    result["run"] = run_meta
    result["duration_ms"] = duration_ms
    return result


@router.post("/api/challenges/{slug}/runs", status_code=202)
def start_run(slug: str, body: RunBody | None = None, request: Request = None) -> dict:  # type: ignore[assignment]
    """Start a run after claiming its mutation lock; poll via /run-jobs/{id}."""
    body = body or RunBody()
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    job_adapter = request_run_jobs(request)
    user_id = request_user_id(request)
    if type(job_adapter) is run_coordination.PostgresRunJobAdapter:
        if user_id is None:
            raise learner_state.LearnerIdentityRequired(
                "verified learner identity is required"
            )
        return job_adapter.enqueue(
            run_coordination.RunJobRequest(
                user_id=user_id,
                slug=slug,
                session_elapsed_ms=body.session_elapsed_ms,
            )
        )
    release = acquire_challenge(slug)
    adapter = request_execution_adapter(request)
    state = request_learner_state(request)
    job_kwargs = {"release": release}
    if user_id is not None:
        job_kwargs["user_id"] = user_id
    return job_adapter.start(
        slug,
        lambda emit: _execute_run(slug, body, adapter, state, user_id, emit),
        **job_kwargs,
    )


@router.get("/api/run-jobs/{job_id}")
def get_run_job(job_id: str, after: int = 0, request: Request = None) -> dict:  # type: ignore[assignment]
    user_id = request_user_id(request)
    job_adapter = request_run_jobs(request)
    job = job_adapter.get(
        job_id,
        after=after,
        **({"user_id": user_id} if user_id is not None else {}),
    )
    if job is None:
        raise HTTPException(404, "run job not found")
    return job


@router.get("/api/challenges/{slug}/runs")
def get_runs(slug: str, limit: int = progress.RUN_HISTORY_LIMIT, request: Request = None) -> dict:  # type: ignore[assignment]
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    return {
        "runs": request_learner_state(request).list_runs(
            slug, limit, request_user_id(request)
        )
    }


@router.post("/api/challenges/{slug}/runs/{run_id}/restore")
def restore_run(slug: str, run_id: int, request: Request = None) -> dict:  # type: ignore[assignment]
    with challenge_operation(slug):
        try:
            ch.load(slug)
            snapshot = request_learner_state(request).restore_run(
                slug, run_id, request_user_id(request)
            )
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        except learner_state.RunNotFound:
            raise HTTPException(404, "run not found")
        except learner_state.RunSnapshotUnavailable:
            raise HTTPException(409, "code snapshot unavailable for this run")
        except ch.InvalidPath:
            raise HTTPException(409, "code snapshot is no longer compatible")
    return {"ok": True, "run_id": run_id, "files_restored": len(snapshot.files)}


@router.post("/api/challenges/{slug}/reset")
def reset(slug: str, request: Request = None) -> dict:  # type: ignore[assignment]
    with challenge_operation(slug):
        try:
            request_learner_state(request).reset(slug, request_user_id(request))
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True}


@router.get("/api/challenges/{slug}/search")
def search(slug: str, q: str = "", limit: int = 100, request: Request = None) -> dict:  # type: ignore[assignment]
    try:
        ch.load(slug)
        hits = request_learner_state(request).search_files(
            slug, q, limit, request_user_id(request)
        )
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    except ch.InvalidPath:
        raise HTTPException(400, "invalid query")
    return {"query": q, "hits": hits}


@router.post("/api/challenges/{slug}/spoil")
def spoil(slug: str, request: Request = None) -> dict:  # type: ignore[assignment]
    with challenge_operation(slug):
        try:
            ch.load(slug)
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        updated = request_learner_state(request).mark_spoiled(
            slug, request_user_id(request)
        )
    return {"ok": True, "progress": updated}


@router.get("/api/challenges/{slug}/solution")
def solution(slug: str) -> dict:
    try:
        return ch.solution_files(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "solution not found")


def create_application(
    environment: Mapping[str, str] | None = None,
    *,
    hosted_adapters: HostedAdapters | object | None = None,
) -> FastAPI:
    """Return a fully composed application or fail before it can serve traffic."""
    settings = _read_settings(environment, hosted_adapters)
    application = FastAPI(
        title="MakeItGreen API",
        lifespan=_application_lifespan(settings),
    )
    application.state.ready = False
    application.state.runtime_settings = settings
    application.state.execution_adapter = settings.execution_adapter
    application.state.learner_state_adapter = settings.learner_state_adapter
    application.state.run_jobs_adapter = settings.run_jobs_adapter
    application.state.abuse_control_adapter = settings.abuse_control_adapter
    application.state.security_events = settings.security_events
    application.state.readiness_failed = False
    allowed_origins = settings.authorized_parties or LOCAL_ORIGINS
    application.middleware("http")(enforce_abuse_controls)
    application.middleware("http")(clerk_authentication)
    if settings.mode is RuntimeMode.HOSTED:
        application.add_middleware(
            abuse_controls.RequestBodyLimitMiddleware,
            max_bytes=settings.abuse_control_adapter.policy.max_request_bytes,
            security_events=settings.security_events,
        )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(
        ch.InvalidChallengeMetadata, invalid_challenge_metadata
    )
    application.add_exception_handler(
        ch.InvalidChallengeFileEncoding, invalid_challenge_file_encoding
    )
    application.add_exception_handler(
        runner.ExecutionUnavailable, execution_unavailable
    )
    application.add_exception_handler(
        runner.UnsupportedContainerRuntime, unsupported_container_runtime
    )
    application.add_exception_handler(
        learner_state.LearnerStateUnavailable, learner_state_unavailable
    )
    application.add_exception_handler(
        learner_state.LearnerChallengeBusy, learner_challenge_busy
    )
    application.add_exception_handler(
        run_coordination.RunJobsUnavailable, run_jobs_unavailable
    )
    application.add_exception_handler(
        run_coordination.RunCapacityExceeded, run_capacity_exceeded
    )
    application.add_exception_handler(
        abuse_controls.RequestBodyTooLarge, request_body_too_large
    )
    application.include_router(router)

    async def live() -> dict[str, str]:
        return {"status": "live", "mode": settings.mode.value}

    def current_readiness() -> bool:
        is_ready = bool(application.state.ready)
        if is_ready and settings.mode is RuntimeMode.HOSTED:
            try:
                settings.learner_state_adapter.check_ready()
                settings.run_jobs_adapter.check_ready()
                settings.abuse_control_adapter.check_ready()
            except (
                learner_state.LearnerStateUnavailable,
                run_coordination.RunJobsUnavailable,
                abuse_controls.AbuseControlsUnavailable,
            ):
                is_ready = False
        if not is_ready and not application.state.readiness_failed:
            settings.security_events.emit(
                "runtime.not_ready",
                severity="error",
            )
        elif is_ready and application.state.readiness_failed:
            settings.security_events.emit("runtime.ready_recovered")
        application.state.readiness_failed = not is_ready
        return is_ready

    def ready() -> JSONResponse:
        is_ready = current_readiness()
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "mode": settings.mode.value,
            },
        )

    def release() -> JSONResponse:
        is_ready = current_readiness()
        worker_release = None
        if is_ready and settings.mode is RuntimeMode.HOSTED:
            try:
                worker_release = settings.run_jobs_adapter.worker_release_status(
                    settings.release_sha
                )
                is_ready = worker_release.ready
            except run_coordination.RunJobsUnavailable:
                is_ready = False
        content = {
            "status": "ready" if is_ready else "not_ready",
            "source_sha": settings.release_sha,
        }
        if worker_release is not None:
            content["worker"] = {
                "status": "ready" if worker_release.ready else "not_ready",
                "live_workers": worker_release.live_workers,
                "matching_workers": worker_release.matching_workers,
                "source_sha": settings.release_sha,
                "python_execution_image": worker_release.python_execution_image,
                "node_execution_image": worker_release.node_execution_image,
            }
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content=content,
        )

    application.add_api_route("/health/live", live, methods=["GET"])
    application.add_api_route("/health/ready", ready, methods=["GET"])
    application.add_api_route("/health/release", release, methods=["GET"])
    source = os.environ if environment is None else environment
    frontend_dist = source.get("GREENLINE_FRONTEND_DIST", "").strip()
    if frontend_dist:
        application.mount(
            "/",
            _SinglePageApplication(directory=frontend_dist, html=True),
            name="frontend",
        )
    return application


app = create_application()
