# invoice-delivery-worker

A deterministic model of concurrent workers consuming an at-least-once queue.

- `queue.py` owns claim, acknowledgement, retry, redelivery, and parking state.
- `sink.py` offers both unsafe delivery and an atomic `deliver_once` boundary.
- `worker.py` contains the orchestration defect.

The fake clock advances only when tests tell it to. Run `python -m pytest -v`.
