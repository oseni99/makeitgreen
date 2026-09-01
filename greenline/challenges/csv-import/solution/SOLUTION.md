# Solution

## Root cause

The worker treated decoding, schema validation, and row coercion as one operation. A BOM changed the first field name, while any bad value raised out of the whole batch.

## Repair

Decode with `utf-8-sig`, convert decode and schema failures into `ImportFormatError`, then validate each data row independently. Stable rejection records preserve the source row number and allow valid rows to continue.

## Interview talking points

- File-level corruption cannot be safely quarantined per row because the parser cannot establish the schema.
- Rejection reason stability matters for metrics, replay, and partner feedback.
- Production importers should persist accepted rows and quarantine records atomically or with an idempotent batch key.
