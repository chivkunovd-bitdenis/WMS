# Continuous Features — результаты проверок

Единый журнал прогона тестов и CI по фичам в режиме continuous features.

**Источник плана:** `docs/analysis/02_technical_builder_plan.md` (отгрузка на МП, TASK-001…018).

---

## Фича 1 — TASK-001: флаг «Адресное хранение» (tenant)

**Дата:** 2026-06-27  
**Статус:** ✅ готово

### Что сделано

- Колонка `tenants.address_storage_enabled` (дефолт `true`, DEC-009).
- Сервис `tenant_settings_service.py`: чтение/обновление.
- API `GET/PATCH /tenant/settings` (только `fulfillment_admin`).
- Поле `address_storage_enabled` в `GET /auth/me`.
- UI: блок «Склад» на `FfSettingsScreen` с чекбоксом (`data-testid="ff-settings-address-storage-enabled"`).
- Тесты: `backend/tests/test_tenant_settings.py`, `frontend/tests-e2e/ff-address-storage-setting.spec.ts`.

### Test coverage (PR)

| TC-ID | Title (short) | Applies | Notes |
|-------|----------------|---------|-------|
| TC-NEW-MP-001 | Admin toggles address storage | Y | Given новый FF-админ, When открывает Настройки и снимает «Адресное хранение», Then PATCH /tenant/settings 200, checkbox unchecked, /auth/me address_storage_enabled=false; When включает снова — true. Negative: staff без admin → PATCH 403. |

### Результаты проверок

| Проверка | Команда | Результат | Exit |
|----------|---------|-----------|------|
| ruff (changed) | `ruff check app/main.py app/api/tenant_settings.py …` | All checks passed | 0 |
| mypy (changed) | `mypy app/api/tenant_settings.py app/services/tenant_settings_service.py app/models/tenant.py` | Success: no issues | 0 |
| pytest (tenant) | `pytest tests/test_tenant_settings.py -q` | 3 passed in 3.46s | 0 |
| pytest (full) | `pytest -q` | 202 passed in 204s | 0 |
| frontend build | `npm run build` | ✓ built in 2s | 0 |
| e2e (feature) | `npx playwright test ff-address-storage-setting.spec.ts` | 1 passed (6.2s) | 0 |

---

## Фича 2 — TASK-002: условная обязательность ячеек в collect/pick API

**Дата:** 2026-06-27  
**Статус:** ✅ готово (`908029c`)

### Что сделано

- `resolve_collect_storage_location`; optional `storage_location_id` при выкл. флаге.
- pytest `test_marketplace_unload_address_storage.py` (2 кейса).

### Результаты проверок

| Проверка | Команда | Результат | Exit |
|----------|---------|-----------|------|
| pytest (feature) | `pytest tests/test_marketplace_unload_address_storage.py -q` | 2 passed | 0 |

---

## Фича 3 — TASK-003: скрытие UI ячеек

**Дата:** 2026-06-27  
**Статус:** ✅ готово

### Что сделано

- `FfSuppliesShipmentsPage`, `FfInboundRequestView`, `App.tsx` — флаг из `/auth/me`.
- e2e `ff-address-storage-mp-ui.spec.ts`.

### Результаты проверок

| Проверка | Команда | Результат | Exit |
|----------|---------|-----------|------|
| e2e | `npx playwright test ff-address-storage-mp-ui.spec.ts ff-address-storage-setting.spec.ts` | 2 passed | 0 |

---

## Перегруз контекста

**2026-06-27 — после TASK-003:** следующий срез — **TASK-007** (завершение упаковки) по Implementation Order.
