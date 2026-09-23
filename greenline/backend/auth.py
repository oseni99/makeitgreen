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


def create_client(secret_key: str) -> Clerk:
    """Create the process-scoped Clerk client used by request authentication."""
    return Clerk(bearer_auth=secret_key)


def is_pem_public_key(value: str) -> bool:
    """Return whether a configured JWT key has the expected PEM envelope."""
    stripped = value.strip()
    return (
        stripped.startswith("-----BEGIN PUBLIC KEY-----")
        and stripped.endswith("-----END PUBLIC KEY-----")
    )


def authenticate(
    request: Request,
    *,
    secret_key: str | None = None,
    jwt_key: str | None = None,
    parties: list[str] | None = None,
    client: Clerk | None = None,
) -> dict[str, Any] | None:
    secret = secret_key or _secret_key()
    if secret is None:
        return None

    clerk_request = httpx.Request(
        request.method,
        str(request.url),
        headers=dict(request.headers),
    )
    sdk = client or create_client(secret)
    state = sdk.authenticate_request(
        clerk_request,
        AuthenticateRequestOptions(
            authorized_parties=parties if parties is not None else authorized_parties(),
            jwt_key=jwt_key,
        ),
    )
    if state.status != AuthStatus.SIGNED_IN or state.payload is None:
        return None
    return state.payload
