# Solution — log-aggregator

## Root causes

Two independent bugs in the rollup path:

### 1. WARN counted as ERROR

`errors_in_window()` treated **WARN** as page-worthy:

```python
if event.level not in ERROR_LEVELS and event.level != "WARN":
    continue
```

On-call only wants `ERROR` in the rollup. Remove the WARN exception so only
`ERROR_LEVELS` pass the filter.

### 2. Window start is exclusive (off-by-one)

The filter used a **half-open** interval `(start, end]`:

```python
if event.ts <= start or event.ts > end:
    continue
```

Events exactly at `end - window_seconds` are dropped. The contract (and the
tests) require a **closed** window `[start, end]`:

```python
if event.ts < start or event.ts > end:
    continue
```

## Interview talking points

- Sliding windows: always clarify inclusive vs exclusive bounds — Prometheus,
  Datadog rollups, and SQL `BETWEEN` disagree; the tests are the contract.
- "Count WARN too" sounds reasonable in ops, but changes the paging SLO;
  read the spec/tests before expanding scope.
- Parser is already correct (timezone-aware ISO-8601); don't chase red herrings
  in `parser.py` unless a test points there.
- At scale you'd bucket by time slot in O(1) per ingest instead of scanning
  all events — mention as a follow-up if asked about performance.
