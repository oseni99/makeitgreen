"""Challenge discovery and file access.

A challenge lives in challenges/<slug>/ with this layout:
    challenge.json   - metadata (title, type, difficulty, blurb, ...)
    repo/            - the broken codebase presented to the user
    solution/        - reference solution: SOLUTION.md + fixed files
"""
from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
CHALLENGES_DIR = BASE_DIR / "challenges"
DATA_DIR = Path(__file__).resolve().parent / "data"
WORKSPACES_DIR = DATA_DIR / "workspaces"
VARIANT_SEPARATOR = "@"
VARIANT_ID = re.compile(r"[a-z0-9][a-z0-9-]*")

IGNORED = {"__pycache__", ".pytest_cache", ".git", ".venv"}

# These files control pytest discovery and execution independently of a
# challenge's tests/ directory. Letting a workspace overlay them would allow a
# submission to replace pytest's exit status or disable test collection.
PYTEST_CONFIG_FILES = {
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
}


class ChallengeNotFound(Exception):
    pass


class InvalidPath(Exception):
    pass


class InvalidChallengeMetadata(Exception):
    """A challenge.json file cannot be decoded into a metadata object."""


class InvalidChallengeFileEncoding(Exception):
    """A repo or solution file cannot be represented by the text-file API."""


STRING_METADATA_FIELDS = {
    "title",
    "type",
    "difficulty",
    "language",
    "blurb",
    "brief",
}
NUMBER_METADATA_FIELDS = {"minutes", "order"}
PATH_LIST_METADATA_FIELDS = {"readonly", "creatable"}
VARIANT_OVERRIDE_FIELDS = {
    "language",
    "runtime",
    "readonly",
    "creatable",
    "brief",
    "blurb",
    "minutes",
}


def _has_valid_documented_field_types(meta: dict[str, Any]) -> bool:
    for field in STRING_METADATA_FIELDS:
        if field in meta and not isinstance(meta[field], str):
            return False
    for field in NUMBER_METADATA_FIELDS:
        value = meta.get(field)
        if field in meta and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return False
    for field in PATH_LIST_METADATA_FIELDS:
        value = meta.get(field)
        if field in meta and (
            not isinstance(value, list)
            or not all(isinstance(prefix, str) and prefix for prefix in value)
        ):
            return False
    return True


def _validate_runtime(runtime: object, slug: str) -> None:
    if runtime is None:
        return
    if not isinstance(runtime, dict):
        raise InvalidChallengeMetadata(slug)
    if runtime.get("kind", "python") not in {"python", "node"}:
        raise InvalidChallengeMetadata(slug)
    command = runtime.get("command")
    if command is not None and (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise InvalidChallengeMetadata(slug)
    if runtime.get("kind") == "node" and command is None:
        raise InvalidChallengeMetadata(slug)
    default_report = "text" if runtime.get("kind") == "node" else "pytest-json"
    if runtime.get("report", default_report) not in {"pytest-json", "text"}:
        raise InvalidChallengeMetadata(slug)
    requirements = runtime.get("requirements")
    if requirements is not None and (
        not isinstance(requirements, str)
        or not requirements
        or Path(requirements).is_absolute()
        or ".." in Path(requirements).parts
    ):
        raise InvalidChallengeMetadata(slug)


def _validate_variants(variants: object, slug: str) -> None:
    if variants is None:
        return
    if not isinstance(variants, dict) or not variants:
        raise InvalidChallengeMetadata(slug)
    for variant_id, config in variants.items():
        if not isinstance(variant_id, str) or not VARIANT_ID.fullmatch(variant_id):
            raise InvalidChallengeMetadata(slug)
        if not isinstance(config, dict):
            raise InvalidChallengeMetadata(slug)
        if any(field not in VARIANT_OVERRIDE_FIELDS for field in config):
            raise InvalidChallengeMetadata(slug)
        if not isinstance(config.get("language"), str) or not config["language"].strip():
            raise InvalidChallengeMetadata(slug)
        if not _has_valid_documented_field_types(config):
            raise InvalidChallengeMetadata(slug)
        _validate_runtime(config.get("runtime"), slug)


def _load_metadata(meta_path: Path) -> dict[str, Any]:
    try:
        raw = meta_path.read_text(encoding="utf-8")
        meta = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidChallengeMetadata(meta_path.parent.name) from exc
    if not isinstance(meta, dict):
        raise InvalidChallengeMetadata(meta_path.parent.name)
    if not _has_valid_documented_field_types(meta):
        raise InvalidChallengeMetadata(meta_path.parent.name)
    _validate_runtime(meta.get("runtime"), meta_path.parent.name)
    _validate_variants(meta.get("variants"), meta_path.parent.name)
    return meta


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidChallengeFileEncoding(path) from exc


def _default_variant(meta: dict[str, Any]) -> str:
    runtime = meta.get("runtime") or {}
    return "javascript" if runtime.get("kind") == "node" else "python"


def _split_ref(ref: str) -> tuple[str, str | None]:
    if ref.count(VARIANT_SEPARATOR) > 1:
        raise ChallengeNotFound(ref)
    if VARIANT_SEPARATOR not in ref:
        return ref, None
    slug, variant = ref.split(VARIANT_SEPARATOR, 1)
    if not slug or not VARIANT_ID.fullmatch(variant):
        raise ChallengeNotFound(ref)
    return slug, variant


def _variant_descriptors(slug: str, meta: dict[str, Any]) -> list[dict[str, str]]:
    default_id = _default_variant(meta)
    descriptors = [
        {
            "id": default_id,
            "language": meta.get(
                "language",
                "JavaScript" if default_id == "javascript" else "Python",
            ),
            "slug": slug,
        }
    ]
    for variant_id, config in (meta.get("variants") or {}).items():
        if variant_id == default_id:
            raise InvalidChallengeMetadata(slug)
        descriptors.append(
            {
                "id": variant_id,
                "language": config["language"],
                "slug": f"{slug}{VARIANT_SEPARATOR}{variant_id}",
            }
        )
    return descriptors


def load_all() -> list[dict[str, Any]]:
    out = []
    for meta_path in sorted(CHALLENGES_DIR.glob("*/challenge.json")):
        out.append(load(meta_path.parent.name))
    out.sort(key=lambda m: m.get("order", 999))
    return out


def load(slug: str) -> dict[str, Any]:
    concept_slug, requested_variant = _split_ref(slug)
    meta_path = CHALLENGES_DIR / concept_slug / "challenge.json"
    if not meta_path.is_file():
        raise ChallengeNotFound(slug)
    meta = _load_metadata(meta_path)
    default_id = _default_variant(meta)
    variant_id = requested_variant or default_id
    variants = _variant_descriptors(concept_slug, meta)
    if variant_id != default_id:
        config = (meta.get("variants") or {}).get(variant_id)
        if config is None:
            raise ChallengeNotFound(slug)
        meta.update(config)
    meta["slug"] = concept_slug if variant_id == default_id else slug
    meta["concept_slug"] = concept_slug
    meta["variant"] = variant_id
    meta["variants"] = variants
    return meta


def repo_dir(slug: str) -> Path:
    meta = load(slug)
    concept = CHALLENGES_DIR / meta["concept_slug"]
    d = (
        concept / "repo"
        if meta["slug"] == meta["concept_slug"]
        else concept / "variants" / meta["variant"] / "repo"
    )
    if not d.is_dir():
        raise ChallengeNotFound(slug)
    return d


def solution_dir(slug: str) -> Path:
    meta = load(slug)
    concept = CHALLENGES_DIR / meta["concept_slug"]
    if meta["slug"] == meta["concept_slug"]:
        return concept / "solution"
    return concept / "variants" / meta["variant"] / "solution"


def _workspace_root(user_id: str | None = None) -> Path:
    if user_id is None:
        return WORKSPACES_DIR
    namespace = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return WORKSPACES_DIR / "users" / namespace


def workspace_dir(slug: str, user_id: str | None = None) -> Path:
    root = _workspace_root(user_id)
    d, _ = _safe_relpath(root, slug)
    if d == root.resolve():
        raise InvalidPath(slug)
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_overlays(slug: str, user_id: str | None = None) -> list[tuple[Path, str]]:
    """Return persisted edits only after reapplying the challenge policy.

    Workspace data survives backend restarts and can also be modified outside
    the API. A run therefore treats it as untrusted input rather than assuming
    the checks performed when the file was originally saved still hold.
    """
    meta = load(slug)
    root = repo_dir(slug)
    ws = workspace_dir(slug, user_id)
    overlays: list[tuple[Path, str]] = []
    runtime = meta.get("runtime") or {}
    requirements_path = runtime.get("requirements")
    for edited in ws.rglob("*"):
        if edited.is_symlink():
            raise InvalidPath("workspace symlinks are not allowed")
        if not edited.is_file():
            continue
        rel = edited.relative_to(ws).as_posix()
        if any(part in IGNORED for part in Path(rel).parts):
            raise InvalidPath(rel)
        repo_file, canonical_rel = _safe_relpath(root, rel)
        if is_readonly(meta, canonical_rel):
            raise InvalidPath(canonical_rel)
        if canonical_rel == requirements_path:
            raise InvalidPath(canonical_rel)
        if not repo_file.is_file() and not is_creatable(meta, canonical_rel):
            raise InvalidPath(canonical_rel)
        overlays.append((edited, canonical_rel))
    return overlays


def _safe_relpath(root: Path, rel: str) -> tuple[Path, str]:
    """Resolve rel against root and return its canonical repo-relative path."""
    resolved_root = root.resolve()
    path = (resolved_root / rel).resolve()
    if not path.is_relative_to(resolved_root):
        raise InvalidPath(rel)
    return path, path.relative_to(resolved_root).as_posix()


def _matches_prefix(rel: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    if not prefix:
        return False
    return rel == prefix or rel.startswith(f"{prefix}/")


def is_readonly(meta: dict[str, Any], rel: str) -> bool:
    path = Path(rel)
    runtime = meta.get("runtime") or {}
    if rel == runtime.get("requirements"):
        return True
    if path.name == "conftest.py" or (
        len(path.parts) == 1 and rel in PYTEST_CONFIG_FILES
    ):
        return True
    for prefix in meta.get("readonly", ["tests/"]):
        if _matches_prefix(rel, prefix):
            return True
    return False


def is_creatable(meta: dict[str, Any], rel: str) -> bool:
    """True if rel sits under a challenge.json creatable prefix."""
    for prefix in meta.get("creatable") or []:
        if isinstance(prefix, str) and _matches_prefix(rel, prefix):
            return True
    return False


def file_tree(slug: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """Flat list of repo + workspace-only files with edited/readonly/new flags."""
    meta = load(slug)
    root = repo_dir(slug)
    ws = workspace_dir(slug, user_id)
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in sorted(root.rglob("*")):
        if any(part in IGNORED for part in p.parts):
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        seen.add(rel)
        files.append(
            {
                "path": rel,
                "readonly": is_readonly(meta, rel),
                "edited": (ws / rel).is_file(),
                "new": False,
            }
        )
    if ws.is_dir():
        for p in sorted(ws.rglob("*")):
            if any(part in IGNORED for part in p.parts):
                continue
            if not p.is_file():
                continue
            rel = p.relative_to(ws).as_posix()
            if rel in seen:
                continue
            files.append(
                {
                    "path": rel,
                    "readonly": is_readonly(meta, rel),
                    "edited": True,
                    "new": True,
                }
            )
    files.sort(key=lambda f: f["path"])
    return files


def read_file(slug: str, rel: str, user_id: str | None = None) -> str:
    """Return workspace copy if user has edited the file, else the original."""
    repo_file, canonical_rel = _safe_relpath(repo_dir(slug), rel)
    ws_file, _ = _safe_relpath(workspace_dir(slug, user_id), canonical_rel)
    if ws_file.is_file():
        return _read_text_file(ws_file)
    if not repo_file.is_file():
        raise ChallengeNotFound(rel)
    return _read_text_file(repo_file)


def write_file(slug: str, rel: str, content: str, user_id: str | None = None) -> None:
    meta = load(slug)
    # Canonicalize the request path once, then use the same repo-relative path
    # for policy checks and the workspace destination.
    repo_file, canonical_rel = _safe_relpath(repo_dir(slug), rel)
    if is_readonly(meta, canonical_rel):
        raise PermissionError(rel)
    ws_file, _ = _safe_relpath(workspace_dir(slug, user_id), canonical_rel)
    # Existing repo files, or files the user created under a creatable prefix.
    if not repo_file.is_file() and not ws_file.is_file():
        raise ChallengeNotFound(rel)
    ws_file.parent.mkdir(parents=True, exist_ok=True)
    ws_file.write_text(content)


def create_file(slug: str, rel: str, content: str = "", user_id: str | None = None) -> None:
    """Create a workspace-only file under a challenge.json creatable prefix."""
    meta = load(slug)
    if not rel or rel.endswith("/"):
        raise InvalidPath(rel)
    repo_file, canonical_rel = _safe_relpath(repo_dir(slug), rel)
    if not canonical_rel or canonical_rel == ".":
        raise InvalidPath(rel)
    if is_readonly(meta, canonical_rel) or not is_creatable(meta, canonical_rel):
        raise PermissionError(rel)
    if repo_file.exists():
        raise FileExistsError(rel)
    ws_file, _ = _safe_relpath(workspace_dir(slug, user_id), canonical_rel)
    if ws_file.exists():
        raise FileExistsError(rel)
    ws_file.parent.mkdir(parents=True, exist_ok=True)
    ws_file.write_text(content)


def delete_file(slug: str, rel: str, user_id: str | None = None) -> None:
    """Remove a workspace-only user-created file. Original repo files are refused."""
    load(slug)
    repo_file, canonical_rel = _safe_relpath(repo_dir(slug), rel)
    if repo_file.exists():
        raise PermissionError(rel)
    ws_file, _ = _safe_relpath(workspace_dir(slug, user_id), canonical_rel)
    if not ws_file.is_file():
        raise ChallengeNotFound(rel)
    ws_file.unlink()


def reset_workspace(slug: str, user_id: str | None = None) -> None:
    import shutil

    root = _workspace_root(user_id)
    ws, _ = _safe_relpath(root, slug)
    if ws == root.resolve():
        raise InvalidPath(slug)
    load(slug)
    if ws.is_dir():
        shutil.rmtree(ws)


def validated_workspace_snapshot(
    slug: str, files: Mapping[str, str]
) -> dict[str, str]:
    """Validate a stored overlay snapshot against the current challenge policy."""
    meta = load(slug)
    root = repo_dir(slug)
    requirements_path = (meta.get("runtime") or {}).get("requirements")
    validated: dict[str, str] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise InvalidPath(str(path))
        repo_file, canonical = _safe_relpath(root, path)
        if (
            canonical != path
            or any(part in IGNORED for part in Path(path).parts)
            or is_readonly(meta, canonical)
            or canonical == requirements_path
            or (not repo_file.is_file() and not is_creatable(meta, canonical))
        ):
            raise InvalidPath(path)
        validated[canonical] = content
    return validated


def restore_workspace(
    slug: str, files: Mapping[str, str], user_id: str | None = None
) -> dict[str, str]:
    """Replace all learner overlays with one previously validated run snapshot."""
    validated = validated_workspace_snapshot(slug, files)
    reset_workspace(slug, user_id)
    ws = workspace_dir(slug, user_id)
    for path, content in validated.items():
        target, _ = _safe_relpath(ws, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return validated


def solution_files(slug: str) -> dict[str, Any]:
    sdir = solution_dir(slug)
    if not sdir.is_dir():
        raise ChallengeNotFound(slug)
    writeup = ""
    files = []
    for p in sorted(sdir.rglob("*")):
        if not p.is_file() or any(part in IGNORED for part in p.parts):
            continue
        rel = p.relative_to(sdir).as_posix()
        if rel == "SOLUTION.md":
            writeup = _read_text_file(p)
        else:
            original = repo_dir(slug) / rel
            files.append(
                {
                    "path": rel,
                    "content": _read_text_file(p),
                    "original": _read_text_file(original) if original.is_file() else "",
                }
            )
    return {"writeup": writeup, "files": files}
