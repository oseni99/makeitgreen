# Flash-sale checkout

This repository contains the in-memory checkout path for a flash-sale service.
`OrderService` owns order validation, pricing, lifecycle transitions, retries, and
cancellation. `Inventory` owns stock reservation and release across checkout worker
threads.

The service must preserve these externally visible rules:

- orders require a non-blank SKU, a positive quantity, and a positive unit price;
- discounts are deterministic and may be applied repeatedly without compounding;
- a reservation never consumes unavailable stock or accepts a non-positive quantity;
- concurrent reservations for one SKU never oversell it;
- independent SKUs must still reach authorization concurrently;
- retrying one completed or rejected order must not repeat inventory effects;
- an unexpected authorization error leaves the order retryable and stock unchanged;
- only completed orders can be cancelled, and their stock is returned exactly once.

Tests use injected barriers rather than timing sleeps, so concurrency failures are
reproducible. Preserve the public methods and do not replace per-product concurrency
with one global checkout lock.

Run the suite with:

```bash
python -m pytest -v
```
