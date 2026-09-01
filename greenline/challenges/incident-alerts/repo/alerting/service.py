"""In-process alerting facade: ingest samples, register rules, tick."""
from __future__ import annotations

from datetime import datetime

from alerting.evaluator import evaluate
from alerting.ingest import ingest_sample
from alerting.models import Page, Rule, Sample


class AlertingService:
    def __init__(self) -> None:
        self.samples: list[Sample] = []
        self.rules: list[Rule] = []
        self.pages: list[Page] = []

    def ingest(self, service: str, metric: str, value: float, ts_raw: str) -> Sample:
        sample = ingest_sample(service, metric, value, ts_raw)
        self.samples.append(sample)
        return sample

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def tick(self, now: datetime) -> list[Page]:
        """Evaluate every rule at `now`. Fired pages are appended to self.pages."""
        fired: list[Page] = []
        for rule in self.rules:
            page = evaluate(rule, self.samples, now)
            if page is not None:
                self.pages.append(page)
                fired.append(page)
        return fired
