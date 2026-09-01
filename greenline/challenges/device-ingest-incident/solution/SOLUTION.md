# Solution — device-ingest-incident

The incident was not caused merely by malformed JSON. The structural defect was the
location of the recovery boundary: one `try` wrapped the entire drain loop, so handling
the first permanent payload error also ended the worker run.

## Fix

Move `InvalidEvent` handling inside the loop. Each envelope is parsed independently;
known permanent validation failures are quarantined and processing continues with the
next envelope. Storage and other unexpected failures remain outside that narrow catch
and still reach supervision.

The state store already deduplicates by stable event ID, so a redelivered valid event
does not repeat its device update. The quarantine sink applies the same rule to a
redelivered poison event.

## Interview talking points

- Recovery scope should match the unit of work that can safely fail independently.
- Permanent data failures and transient infrastructure failures need different paths.
- Catching `Exception` would keep the loop alive by silently converting outages and
  programmer defects into data loss.
- Incident fixtures should prove both quarantine behavior and progress for healthy
  messages behind the poison event.
