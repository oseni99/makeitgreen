# Solution — config-merge (JavaScript)

The merge loop confused truthiness with presence, dropping explicit `false`,
`0`, and `''` values. Once `Object.entries(overrides)` yields a key, that value
is present and must replace the default unless both sides are plain objects.

Clone both branches so callers do not share mutable arrays or nested objects
with the merged result.
