# Search degradation policy

Catalog enrichment is optional. Spend at most 750 ms waiting for it. If that budget is
exhausted, return the base search result with `enrichment: unavailable`. Unexpected
dependency failures remain server errors. Capacity shedding remains a 503.
