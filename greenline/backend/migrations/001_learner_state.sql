BEGIN;

CREATE TABLE greenline_schema_version (
    singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    version integer NOT NULL
);

INSERT INTO greenline_schema_version (singleton, version) VALUES (TRUE, 1);

CREATE TABLE learner_challenges (
    user_id text NOT NULL,
    slug text NOT NULL,
    workspace_revision bigint NOT NULL DEFAULT 0 CHECK (workspace_revision >= 0),
    status text NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'attempted', 'solved')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    solved_at timestamptz,
    spoiled boolean NOT NULL DEFAULT FALSE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, slug)
);

CREATE TABLE workspace_files (
    user_id text NOT NULL,
    slug text NOT NULL,
    path text NOT NULL,
    content text NOT NULL,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, slug, path),
    FOREIGN KEY (user_id, slug) REFERENCES learner_challenges (user_id, slug)
        ON DELETE CASCADE
);

CREATE TABLE challenge_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    slug text NOT NULL,
    started_at timestamptz NOT NULL,
    duration_ms integer NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    session_elapsed_ms integer CHECK (session_elapsed_ms >= 0),
    green boolean NOT NULL DEFAULT FALSE,
    passed integer NOT NULL DEFAULT 0 CHECK (passed >= 0),
    failed integer NOT NULL DEFAULT 0 CHECK (failed >= 0),
    errors integer NOT NULL DEFAULT 0 CHECK (errors >= 0),
    skipped integer NOT NULL DEFAULT 0 CHECK (skipped >= 0),
    exit_code integer NOT NULL DEFAULT 0,
    output_tail text NOT NULL DEFAULT '',
    output_truncated boolean NOT NULL DEFAULT FALSE,
    tests jsonb NOT NULL DEFAULT '[]'::jsonb,
    FOREIGN KEY (user_id, slug) REFERENCES learner_challenges (user_id, slug)
        ON DELETE CASCADE
);

CREATE INDEX challenge_runs_scope_id_idx
    ON challenge_runs (user_id, slug, id DESC);

COMMIT;
