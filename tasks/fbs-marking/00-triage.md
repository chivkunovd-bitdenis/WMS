# 00–04 — fbs-marking (модераторский пакет)

## Триаж
feature / M; зависит от intake + supply ✅

## Модераторский MVP
1. Модель `FbsOrderMarking` уже есть (intake) — не дублировать; при необходимости unique (order_id, kind, value).
2. WB client: `PUT /api/v3/orders/{id}/meta/{sgtin|uin|imei|gtin}`, `GET /api/v3/orders/{id}/meta` (+ optional DELETE).
3. Service `fbs_marking_service.py` + API `/operations/fbs-orders/{order_id}/markings` GET list, PUT `.../markings/{kind}` body `{value}`.
4. Allowed order statuses for write: `new`, `in_supply`, `assembling`, `packed`. Block: `in_delivery`, `cancelled`, `done` → `order_marking_frozen`.
5. kind whitelist: sgtin|uin|imei|gtin; empty value → 400.
6. ЧЗ link: for `sgtin` lookup `MarkingCode` by `(tenant_id, cis_code=value)` (and seller match if present); set `marking_code_id` if found. **Do not create** new MarkingCode without pool (too heavy) — if not found, leave null + still push WB.
7. Sync: function `sync_order_marking_statuses` + job type OR endpoint `POST .../markings/sync`. Background job optional via existing background_jobs pattern. Mock `e2e_mock_wb_marketplace_marking`.
8. Map WB meta statuses → check_status new|checking|ok|error|no_check (best-effort normalize).

## Out
Physical print; ЧЗ API validation; jewelry uniqueness; packaging_task; deliver gate UI.

## Tests TC-NEW-FBS-MARK-001..004
`tests/test_fbs_marking.py`

## Ок на код
