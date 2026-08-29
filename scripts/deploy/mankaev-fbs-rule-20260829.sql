-- ИП Манкаев Т.Т. — перевод публикации остатков на новое правило доли.
-- Решение владельца 29.08.2026: двум товарам 20 %, Led H4-40 оставить нулём.
--
-- ЗАПУСКАТЬ ТОЛЬКО ПОСЛЕ НАКАТКИ МИГРАЦИЙ: колонок fbs_percent и
-- fbs_same_everywhere до миграции 20260828_0116 в базе не существует.
--
-- Ожидаемый результат публикации (свободный остаток посчитан 29.08.2026):
--   Led H7 A80      свободно 980 -> 20 % -> 196 шт (было 57)
--   Led H4-R4-120   свободно 478 -> 20 % ->  95 шт (было 64)
--   Led H4-40       свободно 443 ->  0 % ->   0 шт (как сейчас)

BEGIN;

UPDATE products
   SET fbs_percent = 20,
       fbs_same_everywhere = true
 WHERE id IN (
   'e67091f1-62c8-4a1c-8ae2-5bbc5d8408cf',  -- Led H7 A80
   'f023a47b-5a09-43aa-9774-a9ffc188a222'   -- Led H4-R4-120
 );

-- Осознанный ноль, а не «не настроено»: товар остаётся невыставленным.
UPDATE products
   SET fbs_percent = 0,
       fbs_same_everywhere = true
 WHERE id = 'bc44dcac-9f9f-4c35-b200-fc9bd3a3dc5a';  -- Led H4-40

-- Проверка перед фиксацией: должно быть ровно три строки с ожидаемыми долями.
SELECT coalesce(wb_vendor_code, sku_code) AS tovar,
       fbs_percent,
       fbs_same_everywhere,
       fbs_stock_sync_enabled
  FROM products
 WHERE id IN (
   'bc44dcac-9f9f-4c35-b200-fc9bd3a3dc5a',
   'e67091f1-62c8-4a1c-8ae2-5bbc5d8408cf',
   'f023a47b-5a09-43aa-9774-a9ffc188a222'
 )
 ORDER BY 1;

COMMIT;
