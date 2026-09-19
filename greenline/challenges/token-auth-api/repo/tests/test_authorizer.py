import pytest

from auth_service.authorizer import authorize
from auth_service.errors import Unauthorized


def test_exact_token_authenticates() -> None:
    assert authorize("tok-alice") == "alice"


def test_lookalike_token_is_rejected() -> None:
    with pytest.raises(Unauthorized):
        authorize("tok-ali")


def test_scope_must_match_as_a_capability() -> None:
    assert authorize("tok-alice", "reports:read") == "alice"
    with pytest.raises(Unauthorized):
        authorize("tok-alice", "reports:rea")


def test_bob_cannot_write_reports() -> None:
    with pytest.raises(Unauthorized):
        authorize("tok-bob", "reports:write")


@pytest.mark.parametrize("lookalike", ["", "tok", "alice", "ok-alice", "tok-a"])
def test_each_token_fragment_is_rejected(lookalike: str) -> None:
    with pytest.raises(Unauthorized):
        authorize(lookalike)


@pytest.mark.parametrize(
    "lookalike_scope",
    ["reports", "read", "write", "reports:", "eports:read", "ports:write"],
)
def test_each_scope_fragment_is_rejected(lookalike_scope: str) -> None:
    with pytest.raises(Unauthorized):
        authorize("tok-alice", lookalike_scope)
