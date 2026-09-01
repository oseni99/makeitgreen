# cache-ext

`catalog.repository.ProductRepository` is a small, working repository over an
in-memory backing store. Its `storage_reads` counter represents an expensive
database read and makes cache behavior observable without timing benchmarks.

Product wants an optional TTL cache:

- create the generic implementation under `cache/`;
- inject time so tests never sleep;
- wire through the repository constructor;
- invalidate writes and deletes.

Existing callers that construct `ProductRepository()` must behave exactly as
before. Run `python -m pytest -v`.
