# Solution — webhook-ext

This is an **Architecture Extension**: the existing bus stays small; the new
capability lives in a new package, then gets plugged in at the boundary.

## What to create

Under `webhooks/` (the creatable prefix):

- `webhooks/__init__.py`
- `webhooks/dispatcher.py` — `WebhookDispatcher(transport=...)`

`WebhookDispatcher` responsibilities:

1. `register(url, secret)` — store endpoints
2. `deliver(event)` — JSON-encode `{id, type, payload}`, HMAC-SHA256 the **raw
   body bytes**, set `X-Signature: sha256=<hex>` + `Content-Type: application/json`,
   POST via the injected transport
3. If the transport returns status ≥ 500, **retry that endpoint once**
4. Do not retry on 4xx

Use stable JSON (`sort_keys=True`, compact separators) so the signature matches
what the receiver will recompute over the same bytes.

## How to wire the bus

Extend `EventBus.__init__` with an optional `webhooks=` argument. After in-process
handlers run, call `webhooks.deliver(event)` when present:

```python
def publish(self, event: Event) -> None:
    for handler in self._handlers:
        handler(event)
    if self._webhooks is not None:
        self._webhooks.deliver(event)
```

Keep HTTP out of `events/` — the bus only knows a narrow collaborator. That is
the architectural point of the exercise.

## Interview talking points

- **Dependency inversion:** tests inject `FakeTransport`; production would inject
  an HTTP client. The dispatcher never imports `urllib`/`httpx` in the happy path
  the tests care about.
- **Sign the bytes on the wire**, not a Python dict. Canonical JSON matters.
- **Retry policy is a product decision.** Blindly retrying 4xx amplifies bad
  payloads; retrying 5xx once is a common first cut before backoff/queues.
- Extension vs. edit-in-place: stuffing `requests.post` into `EventBus.publish`
  would green the tests today and make the next feature (async delivery, DLQ,
  per-endpoint filters) painful. New package + constructor injection scales.
