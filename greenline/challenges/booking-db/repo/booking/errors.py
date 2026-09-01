class BookingError(Exception):
    """Base class for domain failures."""


class SoldOut(BookingError):
    def __init__(self, show_id: str) -> None:
        super().__init__(f"show {show_id!r} does not have enough seats")
        self.show_id = show_id


class AlreadyBooked(BookingError):
    def __init__(self, show_id: str, user_id: str) -> None:
        super().__init__(
            f"user {user_id!r} already has a booking for show {show_id!r}"
        )
        self.show_id = show_id
        self.user_id = user_id


class NotFound(BookingError):
    def __init__(self, key: object) -> None:
        super().__init__(f"not found: {key!r}")
        self.key = key
