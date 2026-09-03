"""Production secret sources, trusted proxies, and structured security events."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


class OperationalConfigurationError(ValueError):
    """A production operational setting is absent, ambiguous, or unsafe."""


def read_secret(source: Mapping[str, str], name: str) -> str | None:
    """Read exactly one direct or mounted-file secret without logging its value."""
    direct = source.get(name, "").strip()
    file_name = source.get(f"{name}_FILE", "").strip()
    if direct and file_name:
        raise OperationalConfigurationError(
            f"{name} and {name}_FILE are mutually exclusive"
        )
    if not file_name:
        return direct or None
    path = Path(file_name)
    if not path.is_absolute():
        raise OperationalConfigurationError(f"{name}_FILE must be an absolute path")
    try:
        if not path.is_file() or path.stat().st_size > 65_536:
            raise OperationalConfigurationError(f"{name}_FILE is invalid")
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise OperationalConfigurationError(f"{name}_FILE is unreadable") from exc
    if not value:
        raise OperationalConfigurationError(f"{name}_FILE is empty")
    return value


def trusted_proxy_cidrs(source: Mapping[str, str]) -> tuple[str, ...]:
    raw = source.get("GREENLINE_TRUSTED_PROXY_CIDRS", "")
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    if not values or "*" in values:
        raise OperationalConfigurationError(
            "GREENLINE_TRUSTED_PROXY_CIDRS requires explicit IP networks"
        )
    try:
        return tuple(str(ipaddress.ip_network(value, strict=False)) for value in values)
    except ValueError as exc:
        raise OperationalConfigurationError(
            "GREENLINE_TRUSTED_PROXY_CIDRS contains an invalid network"
        ) from exc


class SecurityEventSink(Protocol):
    def emit(
        self,
        event: str,
        *,
        request_id: str | None = None,
        user_id: str | None = None,
        severity: str = "info",
        fields: Mapping[str, Any] | None = None,
    ) -> None: ...


class NullSecurityEventSink:
    def emit(self, event: str, **_values: Any) -> None:
        return None


def _security_logger() -> logging.Logger:
    logger = logging.getLogger("greenline.security")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


@dataclass(frozen=True)
class JsonSecurityEventSink:
    """Emit collector-ready JSON with stable, non-reversible learner subjects."""

    hmac_key: bytes
    logger: logging.Logger = field(default_factory=_security_logger)

    def __post_init__(self) -> None:
        if len(self.hmac_key) < 32:
            raise OperationalConfigurationError(
                "GREENLINE_LOG_HMAC_KEY must contain at least 32 bytes"
            )

    def _subject(self, user_id: str) -> str:
        return hmac.new(
            self.hmac_key,
            user_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def emit(
        self,
        event: str,
        *,
        request_id: str | None = None,
        user_id: str | None = None,
        severity: str = "info",
        fields: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"event": event}
        if request_id is not None:
            payload["request_id"] = request_id[:128]
        if user_id is not None:
            payload["subject"] = self._subject(user_id)
        if fields:
            for key, value in fields.items():
                if key not in {"event", "request_id", "subject"}:
                    payload[key] = value
        level = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }.get(severity, logging.INFO)
        self.logger.log(
            level,
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
        )
