# Solution — wallet-service (JavaScript)

The guard checked only the transfer amount, but the mutation debited the amount
plus its fee. Check the complete debit before changing either account. The fee
calculation also needs `Math.max(1, ...)` so small transfers cannot become free.

Keeping both checks before the first mutation makes a rejected transfer atomic
in this in-memory model. A database implementation would need the equivalent
transactional conditional update.
