# Queue drain

Run `pytest`. Malformed input is a per-message failure; it should be
quarantined while later healthy messages continue. Processor failures are
different and must still surface.
