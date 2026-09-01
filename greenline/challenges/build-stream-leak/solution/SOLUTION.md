# Solution

The event hub was the retaining owner: each bound callback kept its stream alive.
`BuildStream` now owns its subscription token, swaps it to `None` exactly once while
holding the lifecycle lock, and unsubscribes on both close and failed construction.
Callbacks already copied by a concurrent publisher remain harmless because `_receive`
checks the closed flag under the same lock.
