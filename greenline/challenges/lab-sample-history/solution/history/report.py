from __future__ import annotations

import sqlite3


QUERY = """
WITH visible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY tenant_id, sample_id, aliquot_id, event_id
        ORDER BY revision DESC
    ) AS revision_rank
    FROM observations
    WHERE ingested_at <= :cutoff
), latest AS (
    SELECT * FROM visible WHERE revision_rank = 1
), compared AS (
    SELECT *, LAG(status) OVER (
        PARTITION BY tenant_id, sample_id, aliquot_id
        ORDER BY observed_at, event_id
    ) AS previous_status
    FROM latest
), marked AS (
    SELECT *, CASE WHEN previous_status IS NULL OR previous_status != status THEN 1 ELSE 0 END AS changed
    FROM compared
), numbered AS (
    SELECT *, SUM(changed) OVER (
        PARTITION BY tenant_id, sample_id, aliquot_id
        ORDER BY observed_at, event_id
    ) AS transition_number
    FROM marked
)
SELECT tenant_id, sample_id, aliquot_id, status, previous_status, transition_number
FROM numbered WHERE changed = 1
ORDER BY tenant_id, sample_id, aliquot_id, observed_at, event_id
"""


class HistoryDatabase:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            """CREATE TABLE observations (
                tenant_id TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                aliquot_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                observed_at INTEGER NOT NULL,
                ingested_at INTEGER NOT NULL,
                status TEXT NOT NULL
            )"""
        )

    def add(self, tenant: str, sample: str, aliquot: str, event: str, revision: int, observed: int, ingested: int, status: str) -> None:
        self.connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant, sample, aliquot, event, revision, observed, ingested, status),
        )
        self.connection.commit()

    def report(self, cutoff: int) -> list[tuple]:
        return self.connection.execute(QUERY, {"cutoff": cutoff}).fetchall()
