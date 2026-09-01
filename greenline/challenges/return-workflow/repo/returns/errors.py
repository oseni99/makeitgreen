"""Public errors raised by the returns service."""


class ReturnNotFound(LookupError):
    pass


class DuplicateReturn(ValueError):
    pass


class InvalidTransition(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move return from {current} to {target}")
        self.current = current
        self.target = target
