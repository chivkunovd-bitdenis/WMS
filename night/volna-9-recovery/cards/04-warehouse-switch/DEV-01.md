# DEV · 04-warehouse-switch · Атом Ф-1: PATCH inbound warehouse_id

## Что реализовано

- **PATCH /operations/inbound-intake-requests/{id}** — принимает опциональное поле `warehouse_id: UUID`.
  Роутер извлекает его через `model_dump(exclude_unset=True)` и передаёт в сервис с флагом `warehouse_id_set`.
- **`InboundIntakeRequestPlannedPatch`** — добавлено поле `warehouse_id: uuid.UUID | None = None`.
- **`svc.patch_request_draft`** — принимает `warehouse_id` и `warehouse_id_set`. Если флаг установлен и UUID не None:
  1. Ищет склад через `get_warehouse(session, tenant_id, warehouse_id)`.
  2. Если не найден — `InboundIntakeError("warehouse_not_found")` → HTTP 404.
  3. Если `not wh.is_operational` — `InboundIntakeError("invalid_warehouse")` → HTTP 422.
  4. Иначе `req.warehouse_id = warehouse_id`.
  Статусная охрана `_request_plan_editable` уже поднимала `not_draft` (409) при `status != draft` — она остаётся
  первой по порядку выполнения и покрывает случай «после передачи».
- Роутер `patch_inbound_request_planned` дополнен двумя новыми ветками `except`:
  `warehouse_not_found` → 404, `invalid_warehouse` → 422.

## Изменённые файлы

- `backend/app/api/inbound_intake.py` — схема `InboundIntakeRequestPlannedPatch` + два аргумента в вызов сервиса + две ветки обработки ошибок
- `backend/app/services/inbound_intake_service.py` — сигнатура `patch_request_draft` + блок проверки склада
- `backend/tests/test_inbound_intake.py` — добавлен `import Warehouse`; три новых теста (TC-S28-001-a/b/c)

## Миграции

Нет. Атом не добавляет таблиц и колонок — поле `warehouses.is_operational` уже существует
(миграция `20260822_0094_warehouse_operational_barcode.py`).

## Тесты

Добавлены в `backend/tests/test_inbound_intake.py`:

| Имя теста | Что проверяет | Ожидаемый ответ |
|---|---|---|
| `test_patch_warehouse_id_saves_on_draft` | PATCH с `warehouse_id` второго операционного склада на черновике | 200, `warehouse_id` в теле обновлён |
| `test_patch_warehouse_id_rejected_after_submission` | PATCH с `warehouse_id` после `submit` (статус `submitted`) | 409 `not_draft` |
| `test_patch_warehouse_id_non_operational_rejected` | PATCH с `warehouse_id` склада, у которого `is_operational=False` | 422 `invalid_warehouse` |

## Гейты

| Гейт | Результат |
|---|---|
| `ruff check` (изменённые файлы) | ✅ All checks passed |
| `mypy` (изменённые файлы) | ✅ Ошибки только в нетронутых файлах (pre-existing: `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `box_import_service.py`) |
| `pytest tests/test_inbound_intake.py` | ✅ 21 passed (0 failed) |
| `pytest tests/test_inbound_intake.py -k warehouse` | ✅ 5 passed (3 новых + 2 ранее существовавших) |
| `back_guard.py` | ⚠️ Файл отсутствует в worktree (`scripts/ci/back_guard.py` не найден). Новых роутов не добавлялось — только расширена схема существующего `PATCH /{request_id}`. |
| `check_migrations.py` | ⚠️ Файл отсутствует в worktree. Миграций не добавлялось. |

## Не реализовано

Все три пункта находки 2 из REVIEW.md закрыты этим атомом:
- `InboundIntakeRequestPlannedPatch` теперь принимает `warehouse_id` ✅
- Сервис применяет склад только в статусе `draft` и при `is_operational=True` ✅
- Три теста проходят через реальный API ✅

## Находки

- Три pre-existing ошибки mypy в не-правленных файлах (`wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `box_import_service.py`) — зафиксировано, работа продолжена согласно разрешению владельца.
- В worktree отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`. Новых роутов не создавалось (только расширена схема PATCH), так что back_guard не заблокировал бы.
