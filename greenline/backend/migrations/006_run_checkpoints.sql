BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 5 THEN
        RAISE EXCEPTION 'migration 006 requires schema version 5';
    END IF;
END $$;

ALTER TABLE challenge_runs
    ADD COLUMN workspace_snapshot jsonb
    CHECK (
        workspace_snapshot IS NULL
        OR jsonb_typeof(workspace_snapshot) = 'object'
    );

WITH ranked AS (
    SELECT id, row_number() OVER (
        PARTITION BY user_id, slug ORDER BY id DESC
    ) AS position
    FROM challenge_runs
)
DELETE FROM challenge_runs
WHERE id IN (SELECT id FROM ranked WHERE position > 10);

UPDATE greenline_schema_version SET version = 6 WHERE singleton = TRUE;

COMMIT;
