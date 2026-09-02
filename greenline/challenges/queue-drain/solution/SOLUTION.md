# Solution — queue-drain

The loop treated a malformed message as a batch-level failure by breaking out
after quarantining it. That stranded every healthy event behind the poison
message.

Keep validation failures scoped to the current event: quarantine the ID and
continue. Validate before calling the processor rather than catching every
`ValueError`; a processor or dependency failure must still stop the drain and
trigger operational handling.

The important incident distinction is **bad data versus unavailable
processing**. Recoverable message failures advance the cursor; infrastructure
failures preserve the backlog for retry.
