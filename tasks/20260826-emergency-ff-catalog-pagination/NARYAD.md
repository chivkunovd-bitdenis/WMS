# Наряд · 20260826-emergency-ff-catalog-pagination

**Полоса:** аварийная
**Тип:** существующий экран и API
**Статус обхода:** `EMERGENCY_BYPASS_USER_APPROVED`

## Просили дословно

> быстро делать сразу на проде правку с фронтом, чтобы оно загружалось моментально

## Экран

- `S-16` `/app/ff/products` — каталог товаров ФФ.

## Границы правки

- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `frontend/tests-e2e/ff-products.spec.ts`
- `backend/app/api/products.py`
- `backend/app/api/inventory_balances.py`
- `backend/app/services/catalog_service.py`
- `backend/app/services/inventory_service.py`
- `backend/app/services/seller_wb_catalog_service.py`
- `backend/tests/test_products_wb_catalog.py`
- `backend/tests/test_inventory_balances.py`
- `tasks/20260826-emergency-ff-catalog-pagination/*`
- `docs/evidence/20260826-emergency-ff-catalog-pagination/*`

## Аварийная граница

Меняется только скорость и корректность загрузки существующего каталога. Новые действия,
колонки и складские правила не добавляются.
