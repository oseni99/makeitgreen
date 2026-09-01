# audit-export-pool

A deterministic model of an audit export service and its database connection pool.

Start with `diagnostics/`, then run `python -m pytest -v`. The pool exposes lifecycle
events so transaction ordering can be tested without a real database server.
