from __future__ import annotations

import csv
import io
from dataclasses import dataclass


class ImportFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    accepted: tuple[dict[str, object], ...]
    rejected: tuple[dict[str, object], ...]


def import_customers(payload: bytes) -> ImportResult:
    """Parse a partner export into normalized customer rows."""
    text = payload.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    accepted: list[dict[str, object]] = []
    for row in reader:
        accepted.append(
            {
                "external_id": row["external_id"].strip(),
                "email": row["email"].strip().lower(),
                "age": int(row["age"]),
            }
        )
    return ImportResult(tuple(accepted), ())
