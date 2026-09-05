# pagination-api — JavaScript

`EventPager.page()` returns newest activity first and an opaque `nextCursor`.
New head inserts must not duplicate or skip older events already waiting below
the cursor. Run `node --test`.
