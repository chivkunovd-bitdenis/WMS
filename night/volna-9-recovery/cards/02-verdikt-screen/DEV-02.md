# DEV · 02-verdikt-screen · фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` — конкурентный сценарий `deliver` ожидает фактический вход второго запроса в `_get_supply_for_update` через `asyncio.Event`, а не фиксированную паузу.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт по атомарной фиче 2.

## Эндпоинты и сервисы

- Эндпоинты: нет изменений.
- Сервисы: нет изменений; тест инструментирует существующий `fbs_shipment_service._get_supply_for_update` только на время сценария.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py::test_fbs_shipment_second_deliver_does_not_reach_wb_while_first_holds_supply_lock` — второй запрос отмечает вход в границу `SELECT ... FOR UPDATE` до освобождения первого вызова WB; затем подтверждаются один вызов WB, одна `confirmed`-операция и ответ `supply_bad_status` у второго запроса.
- Весь `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` — регрессия слоя сдачи поставки.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check tests/test_fbs_shipment_warehouse_sc.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy tests/test_fbs_shipment_warehouse_sc.py` — не пройден: 9 существующих диагностик, включая 4 в импортируемых не изменённых модулях и 5 в прежних строках этого теста (`153`, `231`, `843`, `844`, `960`); новых диагностик для изменённого сценария нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_shipment_warehouse_sc.py::test_fbs_shipment_second_deliver_does_not_reach_wb_while_first_holds_supply_lock` — успешно: `1 passed in 1.17s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_shipment_warehouse_sc.py` — успешно: `12 passed in 11.48s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` и `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` не запускались: атом не добавляет роут или миграцию.

## Не реализовано

Нет: реализован только второй атом из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/FEATURES.md`. Продуктовый сервис `fbs_shipment_service.py`, соседние задачи и первый атом не менялись.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
