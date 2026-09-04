BEGIN;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 4 THEN
        RAISE EXCEPTION 'migration 005 requires schema version 4';
    END IF;
END $$;

CREATE TABLE learner_preferences (
    user_id text PRIMARY KEY,
    prep_path text CHECK (
        prep_path IS NULL OR prep_path IN ('foundations', 'distributed', 'debugging', 'senior')
    ),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE challenge_debriefs (
    user_id text NOT NULL,
    slug text NOT NULL,
    root_cause text NOT NULL CHECK (char_length(root_cause) BETWEEN 1 AND 1000),
    fix_reasoning text NOT NULL CHECK (char_length(fix_reasoning) BETWEEN 1 AND 1000),
    tradeoff text NOT NULL CHECK (char_length(tradeoff) BETWEEN 1 AND 1000),
    useful boolean NOT NULL,
    feedback text NOT NULL DEFAULT '' CHECK (char_length(feedback) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, slug),
    FOREIGN KEY (user_id, slug) REFERENCES learner_challenges (user_id, slug)
        ON DELETE CASCADE
);

CREATE TABLE product_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    event_name text NOT NULL CHECK (event_name IN (
        'catalog_visit',
        'return_visit',
        'path_selected',
        'first_run',
        'successful_run',
        'debrief_completed',
        'feedback_submitted'
    )),
    slug text,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, dedupe_key)
);

CREATE INDEX product_events_name_time_idx
    ON product_events (event_name, occurred_at DESC);

CREATE INDEX product_events_user_time_idx
    ON product_events (user_id, occurred_at DESC);

UPDATE greenline_schema_version SET version = 5 WHERE singleton = TRUE;

COMMIT;
