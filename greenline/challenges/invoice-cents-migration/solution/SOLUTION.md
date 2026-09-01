# Solution — invoice-cents-migration

The repair treats the migration as a compatibility window, not a one-off script.

## Forward-compatible writes

New invoices compute cent fields with `Decimal` and write the legacy and expanded
representations in one transaction. This prevents fresh traffic from extending the
backfill indefinitely and keeps old application versions readable during rollout.

## Stable, atomic backfill

The batch uses immutable invoice IDs rather than an offset over the shrinking set of
unmigrated rows. Updates and checkpoint movement share `BEGIN IMMEDIATE`; an exception
rolls both back. Row updates also require `total_cents IS NULL`, making retries safe.

A checkpoint is only a scan hint. When no row exists above it, the runner checks the
actual null predicate and wraps to any remaining older row. Completion is stored only
after the database confirms that no invoice remains unmigrated.

## Interview talking points

- Online migrations separate expand, dual-write, backfill, verify, and contract.
- Offset pagination is unstable when processed rows leave the queried set.
- Money conversion requires decimal arithmetic and a reconciliation invariant.
- Progress metadata accelerates work; it must never replace verification of the data.
