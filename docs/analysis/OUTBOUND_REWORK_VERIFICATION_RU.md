# Outbound rework — план фич и журнал проверок

**Контекст:** переработка процесса **отгрузки на маркетплейс** (`marketplace_unload`), не legacy `outbound_shipment` (DEC-001).

**Источник требований:** `docs/analysis/01_normalized_process_spec.md`  
**Технический план:** `docs/analysis/02_technical_builder_plan.md` (TASK-001…018)  
**Ревью плана:** `docs/analysis/03_builder_plan_review.md`, `04_independent_review_RU.md`

**Ветка:** `feat/outbound-rework`

---

## Implementation Order (канон)

| # | TASK | Суть | Статус | Коммит / PR |
|---|------|------|--------|-------------|
| 1 | **TASK-001** | Флаг tenant «Адресное хранение» (API + настройки ФФ) | ✅ готово | backend в `908029c`; UI — отдельный коммит |
| 2 | **TASK-006** | Упаковка при create draft + sync строк | ✅ готово | `9467716` |
| 3 | **TASK-002** | Collect/pick без ячейки при выкл. флаге (DEC-005) | ✅ готово | `908029c` |
| 4 | **TASK-003** | Скрытие UI ячеек в отгрузке и приёмке | ✅ готово | см. коммит TASK-003 |
| 5 | TASK-007 | Завершение упаковки | ⏳ | — |
| 6 | TASK-008 | Gate коробов на упаковку | ⏳ | — |
| 7 | TASK-004 | Списание при collect (DEC-006) | ⏳ | — |
| 8 | TASK-009 | Batch короба | ⏳ | — |
| 9 | TASK-010 | Меню короба, remove line, delete empty | ⏳ | — |
| 10 | TASK-011 | Модалка добавления в короб | ⏳ | — |
| 11 | TASK-005 | Удаление «Начать подбор» (legacy flow) | ⏳ | — |
| 12 | TASK-013 | Счётчики + предупреждения (DEC-010) | ⏳ | — |
| 13 | TASK-012 | Вкладочный UI | ⏳ | — |
| 14 | TASK-015 | Refactor ship | ⏳ | — |
| 15 | TASK-014 | Финал + print all ШК (DEC-011) | ⏳ | — |
| 16 | TASK-016, 017 | Тесты по блокам; финальный CI | ⏳ | — |
| 17 | TASK-018 | API-контракт ТСД | ⏳ | — |

---

## TASK-001 — флаг «Адресное хранение»

**Статус:** ✅ готово

### Что сделано

- Миграция `tenants.address_storage_enabled` (default `true`, DEC-009).
- `tenant_settings_service.py`, `GET/PATCH /tenant/settings`, поле в `GET /auth/me`.
- UI: блок «Склад» на `FfSettingsScreen` (`data-testid="ff-settings-address-storage-enabled"`).
- Тесты: `test_tenant_settings.py`, `ff-address-storage-setting.spec.ts`.

### Test coverage

| TC-ID | Applies | Notes |
|-------|---------|-------|
| TC-NEW-MP-001 | Y | Given FF-admin, When toggles «Адресное хранение», Then PATCH 200, /auth/me reflects; Negative: staff → 403. |

### Проверки

| Проверка | Результат |
|----------|-----------|
| `pytest tests/test_tenant_settings.py -q` | 3 passed |
| `npx playwright test ff-address-storage-setting.spec.ts` | 1 passed |
| `npm run build` | OK |

---

## TASK-002 — условная обязательность ячеек (API)

**Статус:** ✅ готово (`908029c`)

### Что сделано

- `resolve_collect_storage_location` в `marketplace_unload_collect_service`.
- При выкл. флаге: `storage_location_id` optional, списание с агрегата.
- При вкл.: ячейка или зона сортировки; scan-порядок ячейка→товар.
- pytest: `test_marketplace_unload_address_storage.py`.

### Test coverage

| TC-ID | Applies | Notes |
|-------|---------|-------|
| TC-NEW-MP-002 | Y | Given address_storage=false, When POST box scan без location, Then 200; Given true без location, Then 422; Negative: нет остатка → 409. |

### Проверки

| Проверка | Результат |
|----------|-----------|
| `pytest tests/test_marketplace_unload_address_storage.py -q` | 2 passed |
| Регресс `test_marketplace_unload_ship_deducts_stock_by_pick_and_scan` | passed |

---

## TASK-006 — упаковка при создании черновика

**Статус:** ✅ готово (`9467716`)

- `ensure_task_for_unload` при create; sync строк упаковки; `linked_packaging_task` в detail.
- pytest: расширение `test_marketplace_unload_and_discrepancy_acts.py`.

---

## TASK-003 — скрытие UI ячеек

**Статус:** ✅ готово

### Что сделано

- Прокинут `addressStorageEnabled` из `/auth/me` в отгрузку МП и приёмку.
- Отгрузка: скрыты chip ячейки, «Начать подбор», таблица pick_allocations; scan без шага ячейки.
- Приёмка: скрыты «Распределить по ячейкам» и панель распределения.
- e2e: `ff-address-storage-mp-ui.spec.ts` (TC-NEW-MP-003).

### Проверки

| Проверка | Результат |
|----------|-----------|
| `npm run build` | OK |
| e2e address-storage (2 specs) | 2 passed |

---

## Регрессионный набор (финал ветки)

- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`
- `backend/tests/test_seller_marketplace_unload.py`
- `frontend/tests-e2e/ff-mp-ship-pick.spec.ts`
- `frontend/tests-e2e/seller-mp-unload.spec.ts`
- `frontend/tests-e2e/ff-mp-print-waybill.spec.ts`

---

## Перегруз контекста

**2026-06-27 — после TASK-003:** следующий срез — **TASK-007** (завершение упаковки) по Implementation Order.
