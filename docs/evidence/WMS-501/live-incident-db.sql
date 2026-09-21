BEGIN READ ONLY;
SET LOCAL statement_timeout='4s'; SET LOCAL lock_timeout='1s';
SELECT state,wait_event_type,wait_event,count(*) n,max(EXTRACT(epoch FROM(clock_timestamp()-xact_start))) max_xact_seconds FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() GROUP BY 1,2,3;
SELECT count(*) blocked_sessions FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid))>0;
WITH scopes AS (SELECT id AS tenant_id FROM tenants WHERE name ILIKE '%хорс%' OR name ILIKE '%hors%' UNION SELECT tenant_id FROM sellers WHERE name ILIKE '%хорс%' OR name ILIKE '%hors%') SELECT count(*) matched_tenant_scopes FROM scopes;
SELECT job_type,status,count(*) n,max(EXTRACT(epoch FROM (coalesce(finished_at,clock_timestamp())-created_at))) max_age_or_duration_s FROM background_jobs WHERE created_at>clock_timestamp()-interval '30 minutes' AND job_type ILIKE '%print%' GROUP BY 1,2;
SELECT numbackends,deadlocks,temp_files,temp_bytes FROM pg_stat_database WHERE datname=current_database();
ROLLBACK;
