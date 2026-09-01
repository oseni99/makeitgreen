# Solution

## Root cause

Compaction used the fastest acknowledgement, so one consumer could delete changes still required by another. Acknowledgements were also accepted without proving the slot had received that sequence.

## Repair

Track delivered and acknowledged positions per slot. Reject backwards or beyond-delivered acknowledgements, and compact only through the minimum acknowledgement of all active slots. Removing a slot removes its retention claim explicitly.

## Interview talking points

- Real databases update slot progress transactionally and persist it across restarts.
- Slow slots create storage pressure; monitoring and an explicit administrative drop policy are safer than silently violating delivery.
- Delivery position and acknowledgement position are different states and should not be conflated.
