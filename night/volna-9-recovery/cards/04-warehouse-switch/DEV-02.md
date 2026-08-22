# DEV · 04-warehouse-switch · атом 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py

## Что реализовано

- Привязка WB уже запрещает служебные склады; preflight считает только операционные склады tenant.
- Выбранный склад теперь участвует в расчёте текущего остатка и агрегированных предупреждений/блокировок.
- API-модель сохраняет `stock_preflight`, включая рекомендацию и строки дефицита.

## Миграции

Нет.

## Тесты

- Добавлен регрессионный тест `test_preflight_response_model_preserves_stock_details`.
- Изменённые backend-файлы прошли targeted ruff; focused тест прошёл: 1 passed.
- Целевой набор `test_fbs_stock_availability.py` + `test_fbs_supply_from_orders.py`: 25 passed, 1 skipped, 1 failed на календарном тесте с фиксированной датой `2026-08-15`, уже прошедшей в окружении.

## Гейты

- ruff: полный `ruff check .` не пройден из-за 80 предсуществующих ошибок вне этого diff; targeted ruff изменённых файлов — PASS.
- mypy: не пройден из-за 4 предсуществующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; новых ошибок в изменённых строках не выявлено.
- pytest: targeted набор — 25 passed, 1 skipped, 1 unrelated calendar failure; focused новый тест — PASS.
- back_guard.py: файл отсутствует в этой рабочей копии, запуск невозможен.
- check_migrations.py: файл отсутствует в этой рабочей копии, запуск невозможен.

## Не реализовано

- UI-находки ревью (переключатель, S-03/S-14/S-25 и E2E) не входят в backend-атом 2.
- Остаточные находки по picking idempotency, блокировкам supply и transfer-парам не входят в этот атом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

## Блокеры

Нет блокеров для сохранения backend-правки; общие гейты требуют исправления предсуществующих ошибок и отсутствующих guard-скриптов.
