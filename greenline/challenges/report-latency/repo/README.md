# report-latency

Nightly customer spend reports over a flat order list.

- `report/models.py` — `Order` dataclass
- `report/service.py` — `build_customer_report`
- `diagnostics/` — profiler dump + SRE notes from the timeout (**read these first**)

Run tests: `python -m pytest -v`
