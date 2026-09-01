# Build stream leak

The CI dashboard's long-lived event hub keeps closed streams alive. Read the evidence
in `diagnostics/`, then repair `build_stream/stream.py` without changing the hub's
public contract or the tests.

Run `pytest -q`. The suite uses barriers and weak references, so no sleeps or network
services are required.
