"""Optional Clerk request authentication for the local API."""
from __future__ import annotations

import os
from typing import Any

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthStatus, AuthenticateRequestOptions
from starlette.requests import Request


def _secret_key() -> str | None:
    value = os.getenv("CLERK_SECRET_KEY", "").strip()
    return value or None


def auth_configured() -> bool:
    """Return whether API authentication should be enforced."""
    return _secret_key() is not None


def authorized_parties() -> list[str] | None:
    raw = os.getenv("CLERK_AUTHORIZED_PARTIES", "")
    parties = [value.strip() for value in raw.split(",") if value.strip()]
    return parties or None


def authenticate(request: Request) -> dict[str, Any] | None:
    secret = _secret_key()
    if secret is None:
        return None

    clerk_request = httpx.Request(
        request.method,
        str(request.url),
        headers=dict(request.headers),
    )
    state = Clerk(bearer_auth=secret).authenticate_request(
        clerk_request,
        AuthenticateRequestOptions(authorized_parties=authorized_parties()),
    )
    if state.status != AuthStatus.SIGNED_IN or state.payload is None:
        return None
    return state.payload
