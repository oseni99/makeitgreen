\set ON_ERROR_STOP on

SELECT current_setting('server_version') AS postgres_version;

DO $$
BEGIN
    IF (SELECT version FROM greenline_schema_version WHERE singleton = TRUE) <> 7 THEN
        RAISE EXCEPTION 'expected greenline schema version 7';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace AND NOT convalidated
    ) THEN
        RAISE EXCEPTION 'public schema contains unvalidated constraints';
    END IF;

    IF EXISTS (SELECT 1 FROM run_jobs WHERE status IN ('queued', 'running')) THEN
        RAISE EXCEPTION 'database still contains active Run Jobs';
    END IF;
END $$;

SELECT version AS greenline_schema_version
FROM greenline_schema_version
WHERE singleton = TRUE;

SELECT 'challenge_content_windows' AS table_name, count(*) AS row_count
FROM challenge_content_windows
UNION ALL SELECT 'challenge_debriefs', count(*) FROM challenge_debriefs
UNION ALL SELECT 'challenge_runs', count(*) FROM challenge_runs
UNION ALL SELECT 'greenline_schema_version', count(*) FROM greenline_schema_version
UNION ALL SELECT 'learner_challenges', count(*) FROM learner_challenges
UNION ALL SELECT 'learner_preferences', count(*) FROM learner_preferences
UNION ALL SELECT 'product_events', count(*) FROM product_events
UNION ALL SELECT 'request_audit_events', count(*) FROM request_audit_events
UNION ALL SELECT 'request_rate_windows', count(*) FROM request_rate_windows
UNION ALL SELECT 'run_jobs', count(*) FROM run_jobs
UNION ALL SELECT 'worker_releases', count(*) FROM worker_releases
UNION ALL SELECT 'workspace_files', count(*) FROM workspace_files
ORDER BY table_name;

SELECT sequencename, last_value
FROM pg_sequences
WHERE schemaname = 'public'
ORDER BY sequencename;

SELECT count(*) AS unvalidated_constraints
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace AND NOT convalidated;

SELECT count(*) AS active_run_jobs
FROM run_jobs
WHERE status IN ('queued', 'running');
