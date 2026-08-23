# Фича 1

# DEV · 02-verdikt-screen · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` — сохранение маркера WB в сценарии сдачи делает только `flush()` в сессии сдачи; обычные проверки продолжают фиксировать маркер отдельной короткой сессией.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py` — маршрут сдачи явно выбирает режим без `commit()` переданной транзакции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` — конкурентный тест двух `deliver` с разными ключами: второй не вызывает WB, в журнале остаётся одна подтверждённая операция.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт атома.

## Миграции

Нет.

## Тесты

- Новый конкурентный сценарий удерживает первый `deliver_marketplace_supply`, запускает второй `deliver` с другим ключом и проверяет один вызов WB и одну подтверждённую `supply_deliver`-операцию.
- `S-03-TC-016` проверяет, что поздний ответ WB не перезаписывает более свежий отказ.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`: `ruff check app/services/fbs_marking_service.py app/services/fbs_shipment_service.py tests/test_fbs_shipment_warehouse_sc.py` — `All checks passed!`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`: `mypy app/services/fbs_marking_service.py app/services/fbs_shipment_service.py` — 4 существующие ошибки в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; ошибок в двух проверяемых модулях нет.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`: `pytest -q tests/test_fbs_shipment_warehouse_sc.py -k 'second_deliver_does_not_reach_wb'` — `1 passed, 11 deselected`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`: `pytest -q tests/test_fbs_marking.py -k 'test_fbs_marking_sync_does_not_apply_stale_response'` — `2 passed, 31 deselected`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не применимы: новый роут и миграция не добавлялись.
- Сохранность Git: `git add -- backend/app/services/fbs_marking_service.py backend/app/services/fbs_shipment_service.py backend/tests/test_fbs_shipment_warehouse_sc.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не выполнен — среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Поэтому commit SHA отсутствует, результат остаётся локальным незакоммиченным diff этой рабочей копии.

## Не реализовано

Нет: реализован только атом 1 из `FEATURES.md`; соседние продуктовые задачи не затрагивались.
