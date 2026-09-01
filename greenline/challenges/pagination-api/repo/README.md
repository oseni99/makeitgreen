# Activity feed pagination

`EventPager.page()` powers a mobile activity feed. Events are presented newest
first. Clients pass the returned opaque `next_cursor` back unchanged.

The endpoint contract is deliberately small:

- `items` contains serialized events in descending `(created_at, id)` order;
- `next_cursor` is an opaque string, or `None` when traversal is complete;
- a cursor continues *after* the last event returned by the previous page;
- events inserted ahead of that cursor must not shift, duplicate, or skip the
  older events that were already waiting to be read.

Run `pytest -q`. Some basic paths work already, but the implementation does not
hold this contract under active writes.
