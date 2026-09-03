BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 2 THEN
        RAISE EXCEPTION 'migration 003 requires schema version 2';
    END IF;
END $$;

CREATE TABLE request_rate_windows (
    user_id text NOT NULL,
    scope text NOT NULL CHECK (scope IN ('all', 'mutation', 'run')),
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0),
    rejected_count integer NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    PRIMARY KEY (user_id, scope, window_started_at)
);

CREATE INDEX request_rate_windows_expiry_idx
    ON request_rate_windows (window_started_at);

CREATE TABLE request_audit_events (
    id uuid PRIMARY KEY,
    request_id text NOT NULL,
    user_id text NOT NULL,
    action text NOT NULL,
    resource_slug text,
    method text NOT NULL,
    outcome text NOT NULL CHECK (
        outcome IN ('started', 'succeeded', 'failed', 'rate_limited')
    ),
    response_status integer CHECK (response_status BETWEEN 100 AND 599),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX request_audit_events_user_created_idx
    ON request_audit_events (user_id, created_at DESC);
CREATE INDEX request_audit_events_incomplete_idx
    ON request_audit_events (created_at) WHERE outcome = 'started';

UPDATE greenline_schema_version SET version = 3 WHERE singleton = TRUE;

COMMIT;
