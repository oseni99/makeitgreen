# orders-service — JavaScript

Order processing for a flash-sale commerce platform.

- `src/inventory.js` — SKU stock tracking and asynchronous reservation
- `src/service.js` — order creation, discounts, and checkout flow

Run tests with `node --test`.

The checkout API is asynchronous because authorization may yield to other
requests. Preserve concurrency between different SKUs while ensuring limited
stock cannot be sold more than once.
