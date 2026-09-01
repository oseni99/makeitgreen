# Subscription renewal

`RenewalService` bills seat-based subscriptions. Prices are integer cents. A
percentage discount is applied to the seat subtotal first, then account credit
reduces the discounted amount. The gateway and repository are deterministic
in-memory collaborators so failures are reproducible.

Renewal keys identify one logical billing command. Retrying a successful key
must return its original receipt without another gateway call. A declined
charge is not a successful renewal and must leave the subscription unchanged.
