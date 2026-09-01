# Digest scheduler

Repair the leased job store in `scheduler/core.py`. Tests use barriers and an injected
integer clock; they do not rely on sleeps.
