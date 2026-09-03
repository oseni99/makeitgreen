BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 3 THEN
        RAISE EXCEPTION 'migration 004 requires schema version 3';
    END IF;
END $$;

CREATE TABLE worker_releases (
    worker_id text PRIMARY KEY,
    source_sha text NOT NULL CHECK (source_sha ~ '^[0-9a-f]{40}$'),
    python_execution_image text NOT NULL CHECK (
        python_execution_image ~ '^[^[:space:]@]+@sha256:[0-9a-f]{64}$'
    ),
    node_execution_image text NOT NULL CHECK (
        node_execution_image ~ '^[^[:space:]@]+@sha256:[0-9a-f]{64}$'
    ),
    checked_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX worker_releases_checked_at_idx ON worker_releases (checked_at);

UPDATE greenline_schema_version SET version = 4 WHERE singleton = TRUE;

COMMIT;
