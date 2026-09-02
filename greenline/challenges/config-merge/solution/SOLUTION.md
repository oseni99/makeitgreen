# Solution — config-merge

The merge loop used truthiness to decide whether an override was present. That
silently discarded valid values such as `False`, `0`, and `""`.

Merge based on presence of the key, not truthiness of its value. Deep-copy both
branches so callers can safely reuse their input configuration.

This distinction matters in production configuration: a disabled feature is
not the same thing as an unspecified feature, and zero often means an explicit
limit rather than a missing value.
