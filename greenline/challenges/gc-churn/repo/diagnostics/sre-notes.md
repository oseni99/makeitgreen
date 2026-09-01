# SRE notes

Latency scales with account history even though the API limit is fixed. Database pagination is outside this exercise; the repository supplies an iterable that may be a one-pass cursor. Expanding an event into an API dictionary is the expensive allocation.
