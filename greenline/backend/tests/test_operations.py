"""Behavioral contracts for production operational configuration."""

from __future__ import annotations

import io
import json
import logging

import pytest

import operations
import serve


def test_secret_can_come_from_an_absolute_mounted_file(tmp_path) -> None:
    secret_file = tmp_path / "clerk-secret"
    secret_file.write_text("mounted-secret\n", encoding="utf-8")

    assert operations.read_secret(
        {"CLERK_SECRET_KEY_FILE": str(secret_file)},
        "CLERK_SECRET_KEY",
    ) == "mounted-secret"

    with pytest.raises(operations.OperationalConfigurationError):
        operations.read_secret(
            {
                "CLERK_SECRET_KEY": "direct-secret",
                "CLERK_SECRET_KEY_FILE": str(secret_file),
            },
            "CLERK_SECRET_KEY",
        )


def test_trusted_proxies_require_explicit_valid_networks() -> None:
    assert operations.trusted_proxy_cidrs(
        {"GREENLINE_TRUSTED_PROXY_CIDRS": "10.1.2.3/8, 127.0.0.1"}
    ) == ("10.0.0.0/8", "127.0.0.1/32")

    for unsafe in ("", "*", "not-a-network"):
        with pytest.raises(operations.OperationalConfigurationError):
            operations.trusted_proxy_cidrs(
                {"GREENLINE_TRUSTED_PROXY_CIDRS": unsafe}
            )


def test_security_events_are_json_and_pseudonymize_the_learner() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("greenline.security.contract")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    sink = operations.JsonSecurityEventSink(b"k" * 32, logger)

    sink.emit(
        "request.completed",
        request_id="request-1",
        user_id="clerk-user-secret",
        fields={"action": "challenge.run", "status_code": 202},
    )
    first = json.loads(stream.getvalue())
    stream.seek(0)
    stream.truncate(0)
    sink.emit("request.completed", user_id="clerk-user-secret")
    second = json.loads(stream.getvalue())

    assert first["event"] == "request.completed"
    assert first["action"] == "challenge.run"
    assert first["status_code"] == 202
    assert first["subject"] == second["subject"]
    assert "clerk-user-secret" not in json.dumps(first)


def test_production_launcher_trusts_only_the_configured_proxy_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: dict[str, object] = {}
    monkeypatch.setenv("GREENLINE_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,127.0.0.1")
    monkeypatch.setattr(
        serve.uvicorn,
        "run",
        lambda app, **options: started.update(app=app, **options),
    )

    serve.main()

    assert started["app"] == "app:app"
    assert started["proxy_headers"] is True
    assert started["forwarded_allow_ips"] == ["10.0.0.0/8", "127.0.0.1/32"]
    assert started["server_header"] is False
