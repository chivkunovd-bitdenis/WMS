-- marking_shape
SELECT
    status,
    source,
    (printed_at IS NOT NULL) AS has_printed_at,
    (product_id IS NOT NULL) AS has_product_id,
    COUNT(*) AS code_count
FROM marking_codes
GROUP BY
    status,
    source,
    (printed_at IS NOT NULL),
    (product_id IS NOT NULL)
ORDER BY status, source, has_printed_at, has_product_id;

-- reserved_age
SELECT
    CASE
        WHEN reserved_at IS NULL THEN 'reserved_at_null'
        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '15 minutes' THEN 'under_15m'
        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN '15m_to_1h'
        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN '1h_to_24h'
        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN '1d_to_7d'
        ELSE 'over_7d'
    END AS reserved_age,
    (reserved_by_user_id IS NOT NULL) AS has_reserving_user,
    COUNT(*) AS code_count
FROM marking_codes
WHERE status = 'reserved'
GROUP BY reserved_age, (reserved_by_user_id IS NOT NULL)
ORDER BY reserved_age, has_reserving_user;

-- printed_product_invariant
SELECT
    status,
    COUNT(*) FILTER (WHERE printed_at IS NOT NULL AND product_id IS NULL) AS printed_without_product,
    COUNT(*) FILTER (WHERE printed_at IS NULL AND product_id IS NOT NULL) AS product_without_print_time,
    COUNT(*) AS total_in_status
FROM marking_codes
WHERE status IN ('printed', 'applied', 'introduced', 'shipped', 'transferred')
GROUP BY status
ORDER BY status;

-- recovery_shape
SELECT
    status,
    char_length(cis_code) AS stored_length,
    (right(cis_code, 1) = chr(29)) AS ends_with_group_separator,
    (label_artifact_pdf IS NOT NULL) AS has_own_pdf_artifact,
    COUNT(*) AS code_count
FROM marking_codes
WHERE source = 'pool'
  AND import_batch_id IS NOT NULL
GROUP BY
    status,
    char_length(cis_code),
    (right(cis_code, 1) = chr(29)),
    (label_artifact_pdf IS NOT NULL)
ORDER BY status, stored_length, ends_with_group_separator, has_own_pdf_artifact;
