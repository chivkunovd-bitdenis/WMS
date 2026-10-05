-- Evidence query executed 2026-10-05 through existing SSH, PostgreSQL role wms_agent_ro.
-- No writes, external provider requests, auth signatures or withdrawal creation.
SELECT m.id AS marking_id, to_json(m.value) AS exact_value_json,
       m.created_at AS marking_created_at, o.wb_order_id, o.wb_article,
       p.name AS product_name, s.name AS seller_name, s.id AS seller_id,
       sp.wb_supply_id, sp.delivered_at, o.status, o.wb_status, m.meta_status
FROM fbs_order_markings m
JOIN fbs_orders o ON o.id = m.order_id
JOIN fbs_supplies sp ON sp.id = o.supply_id
JOIN sellers s ON s.id = o.seller_id AND s.tenant_id = o.tenant_id
LEFT JOIN products p ON p.id = o.product_id AND p.tenant_id = o.tenant_id
                    AND p.seller_id = o.seller_id
WHERE m.tenant_id = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
  AND o.tenant_id = m.tenant_id
  AND o.seller_id = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd'
  AND sp.tenant_id = m.tenant_id AND sp.seller_id = o.seller_id
  AND m.kind = 'sgtin' AND m.meta_status <> 'rejected'
  AND o.marketplace = 'wb' AND sp.marketplace = 'wb'
  AND o.status NOT IN ('cancelled', 'defect') AND o.pick_status <> 'returned'
  AND o.wb_status = 'sold'
  AND sp.delivered_at IS NOT NULL AND sp.status IN ('in_delivery', 'done')
  AND (m.marking_code_id IS NULL OR EXISTS (
      SELECT 1 FROM marking_codes mc WHERE mc.id = m.marking_code_id
        AND mc.tenant_id = m.tenant_id AND mc.seller_id = o.seller_id))
  AND NOT EXISTS (
      SELECT 1 FROM fbs_shipment_reversal_ledger r WHERE r.fbs_order_id = o.id
        AND r.tenant_id = o.tenant_id AND r.reversed_at IS NOT NULL)
  AND NOT EXISTS (
      SELECT 1 FROM withdrawal_items i WHERE i.marking_id = m.id
        AND i.tenant_id = m.tenant_id AND i.seller_id = o.seller_id AND i.holds_claim)
ORDER BY sp.delivered_at ASC, m.created_at ASC, m.id
LIMIT 4;

-- До прямого поручения владельца запрос возвращал пусто. После штатного
-- автозаполнения из WB seller-info 05.10.2026 он подтверждает профиль
-- «ИП Горячкина Татьяна Ивановна», ИНН 132608771877. Политика read-only роли
-- billing_profiles.agent_ro_all равна true.
SELECT seller_id, inn FROM billing_profiles
WHERE tenant_id = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe'
  AND seller_id = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
