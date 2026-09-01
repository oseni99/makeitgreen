# Solution — booking-db

Three integrity bugs, all of the "check and mutate disagreed" family — but
this time the mutations live in SQLite, so the fix is a **transaction** (and
a constraint), not a reordered `if`.

## Bug 1 — Cancel drops the booking and forgets the seats

`cancel()` deleted the row and returned. Inventory never came back.

**Fix:** restore `seats_left` in the same write transaction as the delete:

```python
self.conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
self.conn.execute(
    "UPDATE shows SET seats_left = seats_left + ? WHERE id = ?",
    (seats, show_id),
)
```

If either statement fails, roll back both. Partial cancel is how you invent
ghost inventory (or permanently lose seats).

## Bug 2 — No uniqueness on `(show_id, user_id)`

Nothing stopped Alice from booking Hamlet twice. The schema is part of the
API: if the business rule is "one booking per fan per show", enforce it with
`UNIQUE (show_id, user_id)` and map `IntegrityError` → `AlreadyBooked`.

App-level "select then insert" is not enough under concurrency — the unique
index is.

## Bug 3 — Last-seat race (lost update / write skew)

Broken `book()` did:

1. `SELECT seats_left`
2. `INSERT` booking
3. `UPDATE seats_left = seats_left - n`

Each statement auto-committed. Two threads both observe `seats_left = 1`,
both insert, both decrement → two winners and `seats_left = -1`.

**Fix:** take the write lock *before* the read:

```python
self.conn.execute("BEGIN IMMEDIATE")
# SELECT / INSERT / UPDATE ...
self.conn.execute("COMMIT")
```

`BEGIN IMMEDIATE` (not deferred `BEGIN`) is the SQLite-shaped answer to
"SELECT FOR UPDATE". Deferred transactions only grab the write lock at the
first write — too late; another connection can already have read the same
`seats_left`.

Defense in depth: `CHECK (seats_left >= 0)` so a missed transaction still
fails closed instead of inventing negative inventory.

## Interview talking points

- Name the anomaly: this is a classic **lost update** / check-then-act race.
  In Postgres you'd say `SELECT … FOR UPDATE` inside a transaction; in SQLite
  you say `BEGIN IMMEDIATE`.
- Constraints are product rules. Prefer `UNIQUE` / `CHECK` over hoping every
  call site remembers the invariant.
- Atomicity cuts both ways: a failed `book` must leave *zero* residue
  (rollback), and a successful `cancel` must move seats and rows together.
- WAL + a shared file DB is why the concurrent test uses `tmp_path` instead
  of `:memory:` — each `:memory:` connection is its own database.
