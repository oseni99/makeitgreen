BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 6 THEN
        RAISE EXCEPTION 'migration 007 requires schema version 6';
    END IF;
END $$;

ALTER TABLE request_rate_windows
    DROP CONSTRAINT request_rate_windows_scope_check,
    ADD CONSTRAINT request_rate_windows_scope_check
        CHECK (scope IN ('all', 'mutation', 'run', 'content'));

CREATE TABLE challenge_content_windows (
    user_id text NOT NULL,
    slug text NOT NULL,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0),
    solution_count integer NOT NULL DEFAULT 0 CHECK (
        solution_count >= 0 AND solution_count <= request_count
    ),
    PRIMARY KEY (user_id, slug, window_started_at)
);

CREATE INDEX challenge_content_windows_expiry_idx
    ON challenge_content_windows (window_started_at);

UPDATE greenline_schema_version SET version = 7 WHERE singleton = TRUE;

COMMIT;
