# Customer CSV import incident

An overnight migration is stuck retrying the same file. Read the incident evidence before changing `customer_import.py`.

Run `python -m pytest -q`. Keep parsing dependency-free and do not silently accept a file that lacks the required schema.
