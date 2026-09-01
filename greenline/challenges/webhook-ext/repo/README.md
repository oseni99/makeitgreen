# webhook-ext

In-process event bus for domain events. Product is adding outbound webhooks.

- `events/models.py` — `Event` dataclass
- `events/bus.py` — subscribe / publish to in-process handlers
- `webhooks/` — **you create this** (see the challenge brief)

Run tests: `python -m pytest -v`
