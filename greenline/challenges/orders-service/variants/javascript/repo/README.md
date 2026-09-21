# Flash-sale checkout — JavaScript

This repository contains the asynchronous checkout path for a flash-sale service.
`OrderService` owns order validation, pricing, lifecycle transitions, retries, and
cancellation. `Inventory` owns stock reservation and release across overlapping
requests.

The service must preserve these externally visible rules:

- orders require a non-blank SKU, a positive quantity, and a positive unit price;
- discounts are deterministic and may be applied repeatedly without compounding;
- a reservation never consumes unavailable stock or accepts a non-positive quantity;
- overlapping reservations for one SKU never oversell it;
- independent SKUs must still reach authorization concurrently;
- retrying one completed or rejected order must not repeat inventory effects;
- an unexpected authorization error leaves the order retryable and stock unchanged;
- only completed orders can be cancelled, and their stock is returned exactly once.

The tests coordinate promise interleavings without timing sleeps. Remember that
single-threaded JavaScript can still have races when an `await` splits a read-modify-
write sequence. Preserve the public methods and do not serialize unrelated products.

Run the suite with:

```bash
node --test
```
