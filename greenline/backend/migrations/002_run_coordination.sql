BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 1 THEN
        RAISE EXCEPTION 'migration 002 requires schema version 1';
    END IF;
END $$;

ALTER TABLE learner_challenges
    ADD COLUMN operation_fence bigint NOT NULL DEFAULT 0 CHECK (operation_fence >= 0),
    ADD COLUMN lease_job_id uuid,
    ADD COLUMN lease_expires_at timestamptz,
    ADD CONSTRAINT learner_challenges_lease_pair CHECK (
        (lease_job_id IS NULL) = (lease_expires_at IS NULL)
    );

CREATE TABLE run_jobs (
    id uuid PRIMARY KEY,
    user_id text NOT NULL,
    slug text NOT NULL,
    session_elapsed_ms integer CHECK (session_elapsed_ms >= 0),
    workspace_revision bigint NOT NULL CHECK (workspace_revision >= 0),
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    fence bigint NOT NULL CHECK (fence > 0),
    claim_token uuid,
    worker_id text,
    claim_expires_at timestamptz,
    claim_attempts integer NOT NULL DEFAULT 0 CHECK (claim_attempts >= 0),
    output text NOT NULL DEFAULT '' CHECK (char_length(output) <= 20000),
    output_base bigint NOT NULL DEFAULT 0 CHECK (output_base >= 0),
    result jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    heartbeat_at timestamptz,
    completed_at timestamptz,
    terminal_expires_at timestamptz,
    FOREIGN KEY (user_id, slug) REFERENCES learner_challenges (user_id, slug)
        ON DELETE CASCADE,
    CHECK (
        (status = 'running' AND claim_token IS NOT NULL AND worker_id IS NOT NULL
            AND claim_expires_at IS NOT NULL)
        OR status <> 'running'
    )
);

CREATE UNIQUE INDEX run_jobs_one_active_scope_idx
    ON run_jobs (user_id, slug) WHERE status IN ('queued', 'running');
CREATE INDEX run_jobs_claim_idx ON run_jobs (status, created_at);
CREATE INDEX run_jobs_terminal_expiry_idx ON run_jobs (terminal_expires_at)
    WHERE terminal_expires_at IS NOT NULL;

UPDATE greenline_schema_version SET version = 2 WHERE singleton = TRUE;

COMMIT;
