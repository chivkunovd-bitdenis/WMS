# Backend-dev · 07-reporting · атом 3 · rework

## Что реализовано

- Эндпоинты: существующие `GET /warehouses`, `POST /warehouses` и `PATCH /warehouses/{warehouse_id}` возвращают авторитетный булев признак `is_operational` из модели склада; создание даёт штатное `true`, а переименование не меняет признак, `id`, `code` и остальные поля ответа.
- Сервисы: изменений нет; существующие `list_warehouses`, `create_warehouse` и `rename_warehouse` уже сохраняют модельный признак без эвристики по имени.

## Миграции

Нет: поле `Warehouse.is_operational` уже существует и является обязательным булевым полем с default `true`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py::test_catalog_flow` — создание обычного склада и последующий `GET /warehouses` проверяют явное булево `is_operational: true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py::test_warehouse_read_model_preserves_operational_flag_after_rename` — неоперационный служебный склад переименовывается из `FBS WB Service` в `Archive`; `PATCH` и повторный `GET /warehouses` сохраняют `is_operational: false`, `id` и `code`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/warehouses.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/api/warehouses.py tests/test_catalog.py` — `All checks passed!`, код завершения 0.
- ИСХОДНО КРАСНЫЙ ВНЕ АТОМА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/api/warehouses.py tests/test_catalog.py` — обход импортов нашёл 4 существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы в списке ошибок отсутствуют, код завершения 1.
- НЕ ИСПОЛЬЗОВАН КАК ИТОГОВЫЙ ГЕЙТ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=skip app/api/warehouses.py tests/test_catalog.py` — режим `skip` лишил импортированные библиотеки типов и дал 26 ложных ошибок `Any` в двух целевых файлах, код завершения 1.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=silent app/api/warehouses.py tests/test_catalog.py` — `Success: no issues found in 2 source files`, код завершения 0; импортированные модули используются для типизации, но их посторонние ошибки не включены в результат атома.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_catalog.py` — `7 passed in 8.13s`, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся, изменён только ответ существующих маршрутов.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают полный backend-регресс на этом шаге.

## Не реализовано

- Нет: находка №4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/REVIEW.md` в части backend API и текущий атом реализованы буквально.
- Frontend-фильтрация из атомов 4 и 5, исправление загрузки из атома 6 и реестр блокировки из атома 7 намеренно не затрагивались: это соседние продуктовые задачи и не роль `backend-dev`.

## Блокеры

- Реализация и целевые проверки завершены, но сохранить атом в Git из текущего sandbox невозможно: команда `git add backend/app/api/warehouses.py backend/tests/test_catalog.py night/volna-9-recovery/cards/07-reporting/DEV.md && git commit -m "fix(warehouses): expose operational flag"` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` и завершилась с `Operation not permitted`. Изменения остаются в рабочем дереве без commit SHA; чужой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не индексировался и не изменялся этой ролью.

## Находки

- Обычный адресный `mypy` проходит по импортам и видит четыре существующие ошибки в трёх чужих сервисах; итоговая проверка целевых модулей выполнена с `--follow-imports=silent`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
