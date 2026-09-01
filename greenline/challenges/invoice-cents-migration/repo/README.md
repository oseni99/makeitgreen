# invoice-cents-migration

An online SQLite data migration from legacy decimal-string totals to integer cents.

The schema expansion has already happened. Repair the application writer and bounded
backfill in `billing/service.py`. Run `python -m pytest -v`.
