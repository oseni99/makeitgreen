"""Public errors for audit exports."""


class AccessDenied(PermissionError):
    pass


class ClientCancelled(RuntimeError):
    pass


class QueryFailed(RuntimeError):
    pass


class PoolExhausted(RuntimeError):
    pass
