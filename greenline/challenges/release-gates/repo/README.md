# release-gates

The existing `flags/` package stores immutable gate definitions by key and environment.
Its service currently returns the fixed default.

Create `evaluation/`, implement deterministic gate evaluation, and wire it through the
service without breaking existing callers. Run `python -m pytest -v`.
