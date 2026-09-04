-- Minimal beta learning-loop report. Run against the Hosted Mode database:
-- psql "$GREENLINE_DATABASE_URL" --file scripts/product_metrics.sql

\echo '30-day learner funnel'
WITH visitors AS (
    SELECT count(DISTINCT user_id)::numeric AS total
    FROM product_events
    WHERE event_name = 'catalog_visit'
      AND occurred_at >= now() - interval '30 days'
), funnel(stage, position) AS (
    VALUES
        ('catalog_visit', 1),
        ('path_selected', 2),
        ('first_run', 3),
        ('successful_run', 4),
        ('debrief_completed', 5),
        ('return_visit', 6)
)
SELECT
    funnel.stage,
    count(DISTINCT events.user_id) AS learners,
    round(100 * count(DISTINCT events.user_id) / NULLIF(visitors.total, 0), 1)
        AS percent_of_visitors
FROM funnel
CROSS JOIN visitors
LEFT JOIN product_events AS events
    ON events.event_name = funnel.stage
   AND events.occurred_at >= now() - interval '30 days'
GROUP BY funnel.stage, funnel.position, visitors.total
ORDER BY funnel.position;

\echo 'Challenge outcomes and debrief completion (30 days)'
SELECT
    slug,
    count(DISTINCT user_id) FILTER (WHERE event_name = 'first_run') AS starters,
    count(DISTINCT user_id) FILTER (WHERE event_name = 'successful_run') AS solvers,
    count(DISTINCT user_id) FILTER (WHERE event_name = 'debrief_completed') AS debriefs
FROM product_events
WHERE occurred_at >= now() - interval '30 days'
  AND slug IS NOT NULL
GROUP BY slug
ORDER BY starters DESC, slug;

\echo 'Usefulness feedback'
SELECT
    count(*) AS responses,
    count(*) FILTER (WHERE useful) AS useful,
    round(100 * count(*) FILTER (WHERE useful) / NULLIF(count(*), 0)::numeric, 1)
        AS useful_percent,
    count(*) FILTER (WHERE feedback <> '') AS comments
FROM challenge_debriefs
WHERE updated_at >= now() - interval '30 days';

\echo 'Latest optional comments (up to 100)'
SELECT slug, useful, feedback, updated_at
FROM challenge_debriefs
WHERE feedback <> ''
ORDER BY updated_at DESC
LIMIT 100;
