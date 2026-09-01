# booking-db

SQLite-backed ticket booth for live shows. Integer seat counts — no floats.

- `booking/db.py` — connection + schema
- `booking/service.py` — create shows, book, cancel
- `booking/errors.py` — domain exceptions

Run tests: `python -m pytest -v`
