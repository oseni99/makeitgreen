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
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError("file is not valid UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    required = {"external_id", "email", "age"}
    present = set(reader.fieldnames or ())
    missing = sorted(required - present)
    if missing:
        raise ImportFormatError(f"missing columns: {', '.join(missing)}")

    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for row_number, row in enumerate(reader, start=2):
        external_id = (row.get("external_id") or "").strip()
        email = (row.get("email") or "").strip().lower()
        age_text = (row.get("age") or "").strip()
        if not external_id:
            rejected.append({"row": row_number, "reason": "missing_external_id"})
            continue
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            rejected.append({"row": row_number, "reason": "invalid_email"})
            continue
        try:
            age = int(age_text)
        except ValueError:
            rejected.append({"row": row_number, "reason": "invalid_age"})
            continue
        if age < 0:
            rejected.append({"row": row_number, "reason": "invalid_age"})
            continue
        accepted.append({"external_id": external_id, "email": email, "age": age})
    return ImportResult(tuple(accepted), tuple(rejected))
