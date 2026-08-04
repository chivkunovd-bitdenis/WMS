# 01 — Анализ

## Факт из кода
- Credentials: только `content_token` + `supplies_token`.
- `TenantWbMpWarehouse` + `GET /api/v1/warehouses` — это **FBW/supplies**, не FBS seller warehouses v3.
- Intake (`wb_marketplace_orders_service`) уже использует `supplies_token` под именем marketplace.

## Модератор (сам)
1. Добавляем **`marketplace_token_encrypted`** в `seller_wildberries_credentials` + patch/get в credentials service + UI API если есть patch tokens.
2. WB: `GET /api/v3/warehouses`, `GET /api/v3/offices` на `marketplace-api` base; mock flag `e2e_mock_wb_marketplace_warehouses`.
3. Роуты в стиле репо: `/operations/fbs-sellers/{seller_id}/warehouses|offices` (не `/api/fbs/...`).
4. Auth: FF tenant staff; seller must belong to tenant; чужой seller_id → 404/403.
5. Валидация: нет marketplace_token → 403 `missing_marketplace_token` (не fallback на supplies для этих эндпоинтов — явная категория).
6. Intake: prefer marketplace_token, fallback supplies_token (обратная совместимость).
7. Кэш 1 день — **не делаем** в S (optional в TASK).
8. POST create warehouse — out of scope.
