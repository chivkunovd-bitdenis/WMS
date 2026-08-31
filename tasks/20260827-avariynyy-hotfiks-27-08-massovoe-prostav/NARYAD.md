# Наряд · 20260827-avariynyy-hotfiks-27-08-massovoe-prostav

**Полоса:** аварийная
**Тип:** экран
**Заведён:** 27.08.2026 14:41

## Просили дословно

> аварийный хотфикс 27.08: массовое проставление остатка ФБС, большая модалка выбора товара с фото и артикулами, восстановление состава поставки из WB, скан стикера в русской раскладке

## Экраны

- экраны не назначены (новый экран или не UI-задача)

## Границы правки

Разрешено трогать только эти файлы:

- `backend/app/api/fbs_sellers.py`
- `backend/app/api/fbs_supplies.py`
- `backend/app/api/products.py`
- `backend/app/services/catalog_service.py`
- `backend/app/services/fbs_autopoll_service.py`
- `backend/app/services/fbs_supply_service.py`
- `backend/app/services/wb_marketplace_orders_service.py`
- `backend/app/services/wildberries_client.py`
- `backend/tests/test_fbs_supply_repair_from_wb.py`
- `backend/tests/test_products_fbs_stock_from_balance.py`
- `frontend/src/api.ts`
- `frontend/src/screens/v2/FbsStockAllocationDialog.tsx`
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `frontend/src/screens/v2/fbsApi.ts`

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260827-avariynyy-hotfiks-27-08-massovoe-prostav/`
- [ ] влито
