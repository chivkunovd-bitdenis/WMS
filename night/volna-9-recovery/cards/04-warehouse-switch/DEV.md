# DEV · 04-warehouse-switch · backend-dev · rework атома 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inventory_movements_report.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-03.md
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- Эндпоинты: новых нет; API атома 11 не расширялся.
- Сервисы: существующая атомарная пара `stock_transfer_out` / `stock_transfer_in`, идемпотентный повтор, полный undo и запрет упаковочного обхода не менялись и повторно подтверждены целевыми тестами.
- Writer теста отчётности приведён к обязательному контракту 07-A: каждое прямое создание `InventoryMovement` явно сохраняет фактические `seller_id` и `warehouse_id`, поэтому строгий `NOT NULL` для склада не ослаблен.
- Реестр блокировок S-03 дополнен шестью обязательными полями для `insufficient_sorting_stock` и `foreign_sorting_location`.

## Миграции

- Новых миграций в rework нет. Существующая `20260822_0095_inventory_movement_dimensions` не менялась: `warehouse_id` остаётся обязательным, `seller_id` nullable для обычного FF-товара без селлера.

## Тесты

- Обновлён `test_inventory_movements_summary_groups_and_period_filter`: его прямой writer теперь передаёт селлера и фактический склад для всех движений, включая второй склад.
- Повторно прогнаны `test_fbs_picking.py` и `test_fbs_packaging_integration.py`: связанная пара создаётся один раз, повтор ключа не дублирует её, undo оставляет полную обратную пару, упаковка не списывает из чужой сортировки.

## Гейты

- Воспроизведение находки: `pytest -q tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend` — до исправления `1 failed`, `NOT NULL constraint failed: inventory_movements.warehouse_id`.
- Целевой ruff: `ruff check tests/test_inventory_movements_report.py` — `All checks passed!`.
- Целевой mypy: `mypy tests/test_inventory_movements_report.py` — `Success: no issues found in 1 source file`.
- Целевой pytest: `pytest -q tests/test_fbs_picking.py tests/test_fbs_packaging_integration.py tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter` — `25 passed in 22.90s`.
- `python3 scripts/ci/back_guard.py` не запускался: rework не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: rework не добавляет и не меняет миграцию.
- `git diff --check` — пройден.
- Git-сохранение: `git add backend/tests/test_inventory_movements_report.py docs/blockers/S-03.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — не выполнено, среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки ревью №1 и №9 относятся к другим backend-атомам (`preflight` и seller inbound), поэтому в атоме 11 не менялись.
- Из находки №11 в реестр внесены две блокировки атома 11; `supply_warehouse_locked` и отсутствие операционного склада принадлежат атомам смены склада и списка, поэтому здесь не переопределялись.
- Frontend-находки №2–8 и №12 не реализовывались: роль ограничена `backend-dev`, а пользователь потребовал только атом 11.
- Строгий контракт `InventoryMovement.warehouse_id` не заменялся nullable/default: это нарушило бы обязательное решение `ARCH-CROSS.md` о неизменяемом фактическом складе движения.

## Находки

- В UI-словаре не найден отдельный человеко-понятный текст для `foreign_sorting_location`; факт записан в B-15 без изменения frontend в backend-атоме.

## Блокеры

- Локально реализовано и проверено, но не сохранено Git-коммитом: sandbox не разрешает запись в общий git-dir зарегистрированного worktree. Риск — изменения можно потерять до запуска с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
