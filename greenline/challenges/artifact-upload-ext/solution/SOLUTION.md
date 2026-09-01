# Solution

The extension stores chunk state behind the supplied repository lock, validates bytes
before mutation, and treats only byte-for-byte retries as idempotent. Finalization
requires the exact canonical sequence, then checks both total size and full digest
before handing bytes to the content-addressed store. Validation failures do not change
the active session, successful finalization clears chunks and closes it, and cancel is
an idempotent delete.
