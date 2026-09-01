# Vendor catalog reconciliation solution

The broken importer conflated source-record identity with product identity, discarded a
configured field, and used arrival order for conflicts. The repair maps every configured
field, builds normalized GTIN/SKU keys, and merges every product whose key set intersects
the incoming row. A bridge row can therefore unify two earlier records.

Every source identifier is retained. Field values carry `(updated_at, source)` versions,
providing explicit recency and deterministic ties. Replaying the same feeds changes
nothing and output sorting is stable.

Real identity resolution may require reviewed match confidence rather than exact keys,
but it should still remain separate from field mapping and conflict policy.
