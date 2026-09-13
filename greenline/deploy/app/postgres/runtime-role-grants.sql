-- Apply after greenline_api and greenline_worker exist. Keep runtime roles
-- least-privileged while covering every SQL operation used by the services.
--
-- PostgreSQL checks the named conflict-target columns for this worker query:
--   INSERT ... ON CONFLICT (user_id, dedupe_key) DO NOTHING
-- INSERT alone is therefore insufficient; only those two columns are readable.

BEGIN;

GRANT SELECT (user_id, dedupe_key) ON product_events
  TO greenline_worker;

COMMIT;
