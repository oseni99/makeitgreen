# Subscription renewal solution

The failures came from four independent assumptions in one orchestration path:

1. A subscription is due when `now == next_billing_at`, not only after it.
2. The contractual order is percentage discount, then account credit.
3. A successful renewal key is an idempotency key and must return its stored receipt.
4. Gateway failure must happen before subscription state is committed.

The fixed service checks for an existing receipt first, computes entirely in
integer cents, charges before saving mutations, and only consumes the credit
actually used. Zero-total renewals still advance the cycle and store a receipt,
but correctly skip the payment gateway.

In an interview, call out the remaining production boundary: a real remote
gateway and database need a durable payment-attempt/idempotency protocol because
an in-memory call followed by a database write cannot form one atomic transaction.
