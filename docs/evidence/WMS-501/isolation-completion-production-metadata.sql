BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SELECT n.nspname AS schema_name, c.relname AS child_table, a.attname AS child_column,
       p.relname AS parent_table, pa.attname AS parent_column
FROM pg_constraint k
JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_class p ON p.oid=k.confrelid
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.conkey[1]
JOIN pg_attribute pa ON pa.attrelid=p.oid AND pa.attnum=k.confkey[1]
WHERE k.contype='f' AND array_length(k.conkey,1)=1 AND n.nspname='public'
AND EXISTS (SELECT 1 FROM pg_attribute t WHERE t.attrelid=c.oid AND t.attname='tenant_id' AND NOT t.attisdropped)
AND EXISTS (SELECT 1 FROM pg_attribute t WHERE t.attrelid=p.oid AND t.attname='tenant_id' AND NOT t.attisdropped)
ORDER BY c.relname,a.attname;
COMMIT;
