BEGIN READ ONLY;
SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='1s';
SELECT product_id IS NULL AS unlinked,count(*) AS codes,sum(octet_length(label_artifact_pdf)) AS pdf_bytes FROM marking_codes GROUP BY product_id IS NULL;
SELECT max(n) AS largest_linked_product_codes,max(bytes) AS largest_linked_product_pdf_bytes FROM (SELECT product_id,count(*) n,sum(octet_length(label_artifact_pdf)) bytes FROM marking_codes WHERE product_id IS NOT NULL GROUP BY product_id) q;
SELECT deadlocks,temp_files,temp_bytes,numbackends FROM pg_stat_database WHERE datname=current_database();
SELECT state,count(*),max(EXTRACT(epoch FROM (clock_timestamp()-xact_start))) AS max_transaction_age_seconds FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() GROUP BY state;
ROLLBACK;
