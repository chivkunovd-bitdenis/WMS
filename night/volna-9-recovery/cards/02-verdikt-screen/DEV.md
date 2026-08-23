# Фича 1

# DEV · 02-verdikt-screen · атом 1/1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` — сценарий конкурентной сдачи теперь наблюдает начало и завершение второго `UPDATE` стартового WB-маркера через `before_cursor_execute`/`after_cursor_execute`. До освобождения первого вызова WB второй `UPDATE` обязан оставаться незавершённым; отдельно перехвачен преждевременный `AsyncSession.commit()` до первого вызова WB.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_shipment_warehouse_sc.py::test_fbs_shipment_second_deliver_does_not_reach_wb_while_first_holds_supply_lock` → `1 passed`.
- Негативная проверка: временно добавленный `await session.commit()` сразу после `await session.flush()` в `_record_wb_sync_started` сделал тот же сценарий красным: `assert premature_commit_count == 0`, фактически `1 == 0`. Временная мутация удалена; рабочего кода она не изменила.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_shipment_warehouse_sc.py` → `12 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check --no-cache tests/test_fbs_shipment_warehouse_sc.py` → `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy tests/test_fbs_shipment_warehouse_sc.py` → не прошёл с 9 существующими диагностическими ошибками: 4 в зависимостях сервисов и 5 в старых строках теста (153, 231, 897, 898, 1014). В изменённом фрагменте новых ошибок нет.
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет роутов или миграций.

## Не реализовано

- Нет: атом буквально ограничен доказательным регрессионным тестом; API, сервисы, модели и миграции не менялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
