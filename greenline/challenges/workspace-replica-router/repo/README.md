# workspace-replica-router

A deterministic primary/replica routing exercise. Replication advances only through
the test-controlled `ReplicaCluster.advance_replica()` method.

Repair session consistency in `workspace_data/router.py`. Run `python -m pytest -v`.
