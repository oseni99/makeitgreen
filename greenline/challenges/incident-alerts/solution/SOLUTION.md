# Solution — incident-alerts

The missed page is two bugs stacked. The logs name both. Read
`logs/traceback.txt` first, then the SRE replay line at the bottom of
`logs/incident-2026-08-29.log`.

## Bug 1 — naive timestamps vs aware `now`, then fail-closed

`parse_timestamp` understands the `Z` suffix (`replace("Z", "+00:00")`)
and then **throws the tzinfo away**:

```python
dt = datetime.fromisoformat(normalized)
return dt.replace(tzinfo=None)
```

`tick()` evaluates against `datetime(..., tzinfo=timezone.utc)`. Comparing
offset-naive and offset-aware datetimes raises `TypeError`. That would
have been a loud crash — except `evaluate()` catches `Exception` and
returns `None`:

```python
except Exception:
    log.exception("evaluator failed; treating as no-page")
    return None
```

The rule looks healthy. On-call sleeps. This is fail-closed alerting:
an evaluator error is treated as "threshold not crossed".

**Fix:** keep timestamps UTC-aware (treat a missing offset as UTC too —
some scrapers omit the `Z`). Delete the blanket `except`. A bad
aggregator or a tz mix-up must surface; "no page" is a claim that the
window was fine.

```python
def parse_timestamp(raw: str) -> datetime:
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
```

## Bug 2 — exclusive window drops the sample at `now`

Even after timestamps compare, `samples_in_window` uses `start <= ts < end`.
The 0.51 point is stamped `2026-08-29T03:14:00Z` — exactly the evaluation
instant. It is excluded. The remaining max is 0.44, under the 0.50
threshold. SRE's later replay in the log is this bug in plain language:
"window contained 4 of 5 samples".

**Fix:** the evaluation window is closed on the right.

```python
return [s for s in samples if start <= s.ts <= end]
```

The 0.51 sample is the only one that crosses 0.50. Drop it and the rule
cannot fire, timezone fix or not.

## Interview talking points

- Name the paging anti-pattern out loud: **fail-closed**. Alerting should
  fail *noisy* — a third state (`nodata` / `unknown`) — not "looks green".
  Datadog monitors have exactly this: OK / Alert / No Data / Warn.
- Naive vs aware datetime is the Python equivalent of "we stored UTC
  but evaluated in Eastern". Say "aware UTC in, aware UTC out" and stop.
- Inclusive vs exclusive windows: if `now` is the right edge, a scrape
  stamped `now` is in this window or the next one — pick one and document
  it. Off-by-one here is a missed page, not an off-by-one test score.
- Don't hold the "catch everything" as a reliability feature. It hid the
  TypeError for months. Catch the errors you can translate into `nodata`;
  let the rest wake someone.
