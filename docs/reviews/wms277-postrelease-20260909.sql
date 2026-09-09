-- WMS-277: bounded read-only observation of the two prior SKU-conflict sellers.
-- Run with default_transaction_read_only=on and statement_timeout=8000.
-- Counts by timestamp are evidence of persistence, not exclusive task attribution.
WITH scope(seller_id) AS (
  VALUES ('bf8eea6b-eaa6-47ea-8dfc-289142372dab'::uuid),
         ('06b2e991-0533-4adf-83f3-d6cf21251433'::uuid)
), seller_counts AS (
  SELECT s.seller_id,
    (SELECT count(*) FROM products p WHERE p.seller_id=s.seller_id) AS products,
    (SELECT md5(string_agg(p.id::text || ':' || p.sku_code, '|' ORDER BY p.id))
       FROM products p WHERE p.seller_id=s.seller_id) AS product_id_sku_digest,
    (SELECT md5(string_agg(p.id::text || ':' || p.sku_code, '|' ORDER BY p.id))
       FROM products p WHERE p.seller_id=s.seller_id
       AND p.created_at < '2026-09-09 04:17:00+00'::timestamptz) AS pre_tick_product_id_sku_digest,
    (SELECT count(*) FROM products p WHERE p.seller_id=s.seller_id
       AND p.created_at >= '2026-09-09 04:17:00+00'::timestamptz) AS products_created_since_tick,
    (SELECT count(*) FROM seller_wildberries_imported_cards c
       WHERE c.seller_id=s.seller_id) AS card_snapshots,
    (SELECT count(*) FROM seller_wildberries_imported_cards c
       WHERE c.seller_id=s.seller_id
       AND c.updated_at >= '2026-09-09 04:17:00+00'::timestamptz) AS snapshots_updated_since_tick,
    (SELECT max(c.updated_at) FROM seller_wildberries_imported_cards c
       WHERE c.seller_id=s.seller_id) AS latest_snapshot
  FROM scope s
)
SELECT json_build_object(
  'sampled_at', clock_timestamp(),
  'transaction_read_only', current_setting('transaction_read_only'),
  'sellers', (SELECT json_agg(seller_counts ORDER BY seller_id) FROM seller_counts),
  'blocked_other_sessions', (SELECT count(*) FROM pg_stat_activity
     WHERE pid <> pg_backend_pid() AND cardinality(pg_blocking_pids(pid)) > 0),
  'other_transactions_older_than_30s', (SELECT count(*) FROM pg_stat_activity
     WHERE pid <> pg_backend_pid() AND xact_start < now() - interval '30 seconds')
);
