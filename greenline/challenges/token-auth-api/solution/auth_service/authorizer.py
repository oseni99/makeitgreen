from .errors import Unauthorized

TOKENS = {
    "alice": {"token": "tok-alice", "scopes": {"reports:read", "reports:write"}},
    "bob": {"token": "tok-bob", "scopes": {"reports:read"}},
}


def authorize(token: str, required_scope: str | None = None) -> str:
    for user, record in TOKENS.items():
        if token == record["token"]:
            if required_scope is not None and required_scope not in record["scopes"]:
                raise Unauthorized("scope denied")
            return user
    raise Unauthorized("invalid token")
