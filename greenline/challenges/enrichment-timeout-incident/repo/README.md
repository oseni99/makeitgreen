# Search enrichment incident

Start from the read-only incident evidence, then repair `search/service.py`. The fake
clock makes all latency behavior deterministic; there are no network calls or sleeps.

Run `python -m pytest -q` to check your work.
