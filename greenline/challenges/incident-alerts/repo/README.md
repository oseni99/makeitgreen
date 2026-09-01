# incident-alerts

In-process alerting for service-level metrics. Scrapers push samples;
rules evaluate a sliding window; a page fires when an aggregate crosses
its threshold.

- `alerting/ingest.py` — timestamp parse + sample wrap
- `alerting/windows.py` — sliding-window filter + aggregators
- `alerting/evaluator.py` — rule evaluation
- `alerting/service.py` — ingest / add_rule / tick
- `logs/` — the night of 2026-08-29. **Read these first.**

Rule that should have fired:

```
checkout-high-errors
  service     checkout-api
  metric      error_rate
  aggregator  max
  window      300s
  threshold   0.50   # page if max > 0.50
```

Run tests: `python -m pytest -v`
