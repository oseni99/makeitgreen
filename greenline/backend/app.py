"""MakeItGreen API — a Gronex-style repo-based interview practice platform."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import challenges as ch
import progress
import runner
from challenge_locks import acquire_challenge, challenge_operation
from run_jobs import jobs

app = FastAPI(title="MakeItGreen API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ch.InvalidChallengeMetadata)
async def invalid_challenge_metadata(
    _request: Request, _exc: ch.InvalidChallengeMetadata
) -> JSONResponse:
    return JSONResponse(
        status_code=500, content={"detail": "invalid challenge metadata"}
    )


@app.exception_handler(ch.InvalidChallengeFileEncoding)
async def invalid_challenge_file_encoding(
    _request: Request, _exc: ch.InvalidChallengeFileEncoding
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "challenge file is not valid UTF-8"},
    )


class FileBody(BaseModel):
    content: str = ""


class RunBody(BaseModel):
    # How long the learner has been working on this challenge (from the
    # workspace timer), in milliseconds. Optional — older clients omit it.
    session_elapsed_ms: int | None = Field(default=None, ge=0)


@app.get("/api/challenges")
def list_challenges() -> dict:
    prog = progress.get_all()
    items = []
    for meta in ch.load_all():
        p = prog.get(meta["slug"], {"status": "todo", "attempts": 0, "spoiled": False})
        items.append({**meta, "progress": p})
    return {"challenges": items}


@app.get("/api/challenges/{slug}")
def get_challenge(slug: str) -> dict:
    try:
        meta = ch.load(slug)
        tree = ch.file_tree(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    prog = progress.get_all().get(slug, {"status": "todo", "attempts": 0, "spoiled": False})
    return {**meta, "files": tree, "progress": prog}


@app.get("/api/challenges/{slug}/files/{path:path}")
def get_file(slug: str, path: str) -> dict:
    try:
        content = ch.read_file(slug, path)
    except (ch.ChallengeNotFound, FileNotFoundError):
        raise HTTPException(404, "file not found")
    except ch.InvalidPath:
        raise HTTPException(400, "invalid path")
    return {"path": path, "content": content}


@app.put("/api/challenges/{slug}/files/{path:path}")
def put_file(slug: str, path: str, body: FileBody) -> dict:
    with challenge_operation(slug):
        try:
            ch.write_file(slug, path, body.content)
        except PermissionError:
            raise HTTPException(403, "file is read-only")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "file not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True}


@app.post("/api/challenges/{slug}/files/{path:path}")
def post_file(slug: str, path: str, body: FileBody | None = None) -> dict:
    body = body or FileBody(content="")
    with challenge_operation(slug):
        try:
            ch.create_file(slug, path, body.content)
        except PermissionError:
            raise HTTPException(403, "cannot create file")
        except FileExistsError:
            raise HTTPException(409, "file already exists")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True, "path": path, "new": True}


@app.delete("/api/challenges/{slug}/files/{path:path}")
def remove_file(slug: str, path: str) -> dict:
    with challenge_operation(slug):
        try:
            ch.delete_file(slug, path)
        except PermissionError:
            raise HTTPException(403, "cannot delete original file")
        except ch.ChallengeNotFound:
            raise HTTPException(404, "file not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
    return {"ok": True}


@app.post("/api/challenges/{slug}/run")
def run(slug: str, body: RunBody | None = None) -> dict:
    body = body or RunBody()
    with challenge_operation(slug):
        try:
            ch.load(slug)
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        result = _execute_run(slug, body)
    return result


def _execute_run(
    slug: str,
    body: RunBody,
    on_output=None,
) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    result = runner.run_tests(slug) if on_output is None else runner.run_tests(slug, on_output)
    duration_ms = int((time.monotonic() - started) * 1000)
    run_meta = progress.record_run(
        slug,
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
    )
    result["run"] = run_meta
    result["duration_ms"] = duration_ms
    return result


@app.post("/api/challenges/{slug}/runs", status_code=202)
def start_run(slug: str, body: RunBody | None = None) -> dict:
    """Start a run after claiming its mutation lock; poll via /run-jobs/{id}."""
    body = body or RunBody()
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    release = acquire_challenge(slug)
    return jobs.start(
        slug,
        lambda emit: _execute_run(slug, body, emit),
        release=release,
    )


@app.get("/api/run-jobs/{job_id}")
def get_run_job(job_id: str, after: int = 0) -> dict:
    job = jobs.get(job_id, after=after)
    if job is None:
        raise HTTPException(404, "run job not found")
    return job


@app.get("/api/challenges/{slug}/runs")
def get_runs(slug: str, limit: int = 50) -> dict:
    try:
        ch.load(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    return {"runs": progress.list_runs(slug, limit=limit)}


@app.post("/api/challenges/{slug}/reset")
def reset(slug: str) -> dict:
    with challenge_operation(slug):
        try:
            ch.reset_workspace(slug)
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        except ch.InvalidPath:
            raise HTTPException(400, "invalid path")
        progress.reset(slug)
    return {"ok": True}


@app.get("/api/challenges/{slug}/search")
def search(slug: str, q: str = "", limit: int = 100) -> dict:
    try:
        ch.load(slug)
        hits = ch.search_files(slug, q, limit=limit)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "challenge not found")
    except ch.InvalidPath:
        raise HTTPException(400, "invalid query")
    return {"query": q, "hits": hits}


@app.post("/api/challenges/{slug}/spoil")
def spoil(slug: str) -> dict:
    with challenge_operation(slug):
        try:
            ch.load(slug)
        except ch.ChallengeNotFound:
            raise HTTPException(404, "challenge not found")
        updated = progress.mark_spoiled(slug)
    return {"ok": True, "progress": updated}


@app.get("/api/challenges/{slug}/solution")
def solution(slug: str) -> dict:
    try:
        return ch.solution_files(slug)
    except ch.ChallengeNotFound:
        raise HTTPException(404, "solution not found")
