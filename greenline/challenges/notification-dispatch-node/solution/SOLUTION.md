# Notification dispatch solution

The broken queue ranked every pending item before checking whether it was eligible.
That made an urgent future notification dispatch early and also removed it from the
queue.

The repair scans for items with `deliverAt <= now`, then compares only those candidates
by urgency and insertion sequence. Removing the selected index preserves future work,
`size()` continues to count all pending notifications, and equal urgency remains FIFO.

For a larger persistent queue, the same ordering can be represented with separate
due-time and ready-priority indexes. The semantic order stays the same: eligibility
first, ranking second.
