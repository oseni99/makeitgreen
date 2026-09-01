from __future__ import annotations

from typing import Any

from .clients import DownstreamTimeout, EnrichmentClient


class SearchService:
    ENRICHMENT_BUDGET_MS = 750

    def __init__(self, client: EnrichmentClient, *, capacity: int = 8) -> None:
        self._client = client
        self._capacity = capacity
        self._in_flight = 0

    def health(self) -> str:
        return "saturated" if self._in_flight >= self._capacity else "ok"

    def handle(self, query: str) -> dict[str, Any]:
        if self._in_flight >= self._capacity:
            return {"status": 503, "error": "overloaded"}
        self._in_flight += 1
        try:
            labels = self._client.enrich(query, timeout_ms=self.ENRICHMENT_BUDGET_MS)
            return {
                "status": 200,
                "results": [query],
                "labels": labels,
                "enrichment": "live",
            }
        except DownstreamTimeout:
            return {
                "status": 200,
                "results": [query],
                "labels": [],
                "enrichment": "unavailable",
            }
        except Exception as exc:
            return {"status": 500, "error": str(exc)}
        finally:
            self._in_flight -= 1
