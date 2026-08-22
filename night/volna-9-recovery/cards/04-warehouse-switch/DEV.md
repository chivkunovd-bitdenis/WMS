# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py` — активная WB→WMS-привязка отклоняет служебный склад кодом `warehouse_not_operational`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_availability_service.py` — запрос физического остатка учитывает только `Warehouse.is_operational = true`, поэтому служебные склады не попадают в доступный FBS-остаток.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py` — preflight суммирует остаток по операционным складам tenant, выбирает склад по покрытию с приоритетом текущего при равенстве и возвращает агрегированные warning/blocking строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py` — существующие проверки доступного FBS-остатка; целевой модуль проверен после изменений.

## Миграции

Нет в этом атомарном куске: признак `Warehouse.is_operational` добавлен зависимостью `04-A`.

## Гейты

- `ruff check .`: не запускался в полном объёме; `ruff check` трёх изменённых сервисов — PASS.
- `mypy .`: не запускался в полном объёме; отдельный результат предыдущего backend-прохода зафиксирован как BLOCKED существующими ошибками вне этого куска.
- `pytest`: целевой `backend/tests/test_fbs_stock_availability.py` — PASS, 6 passed.
- `back_guard.py`: недоступен в рабочей копии (`scripts/ci/back_guard.py` отсутствует).
- `check_migrations.py`: недоступен в рабочей копии (`scripts/ci/check_migrations.py` отсутствует).

## Не реализовано

- UI-предупреждения, выбор склада и визуальная разбивка не входят в backend-dev и не изменялись.
- Новая API-ручка не добавлялась: данные preflight расширены в существующем ответе.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

Нет блокеров для backend-части этого атомарного куска.
