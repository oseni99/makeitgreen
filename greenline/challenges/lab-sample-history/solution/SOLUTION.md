# Lab sample history solution

Every window must use the full physical identity. Revision selection now partitions by
tenant, sample, aliquot, and event ID, so corrected payloads replace the same observation
without crossing tenant boundaries. Transition comparison and numbering partition by
tenant, sample, and aliquot.

The query first chooses the latest revision visible at the cutoff, then compares stable
`(observed_at, event_id)` order, removes consecutive duplicate statuses, and numbers
only meaningful transitions. Payload status is never used as revision identity.
