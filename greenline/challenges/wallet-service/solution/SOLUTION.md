# Solution — wallet-service

## Bug 1 — Overdraft: balance checked against the wrong number

`transfer()` verified `balance >= amount` but then debited `amount + fee`.
When the balance covers the amount but not the fee, the sender goes negative.

**Fix:** check the *total* debit:

```python
if self._balances[src] < amount_cents + fee:
    raise InsufficientFunds(src)
```

This is a contract bug, not a math bug — the check and the mutation disagreed
about what "sufficient" means. In review, always compare the guard condition
against every write it protects.

## Bug 2 — Minimum fee never applied

The docstring and README both say "1% minimum 1 cent", but
`transfer_fee` returned `int(amount * 0.01)`, which truncates to 0 for
amounts under 100 cents.

**Fix:**

```python
def transfer_fee(self, amount_cents: int) -> int:
    return max(1, int(amount_cents * FEE_RATE))
```

## Interview talking points

- The failing tests *are* the spec — read assertions before reading code.
- Money in integer cents avoids float rounding, but `int()` truncation is
  still a rounding decision. Say the word "banker's rounding" and interviewers
  perk up: which direction you round fees is a business decision, not a
  technical one.
- Note the atomicity property the overdraft test also asserts: a failed
  transfer must leave balances untouched. Check-before-mutate ordering
  gives you that for free here; in a database you'd need a transaction.
