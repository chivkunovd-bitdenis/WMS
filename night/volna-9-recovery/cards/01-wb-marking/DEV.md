# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`: заказы активных собираемых поставок выбираются для одного tenant и селлера, их уникальные `wb_order_id` последовательно отправляются в Wildberries пачками не более 100; ошибка одной пачки журналируется локально и не останавливает следующую.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: готовая строка batch-ответа передаётся в применение по `order_id`, независимо от позиции в ответе; существующий ручной путь остаётся пачкой из одного ID.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Backend-код и тест атома уже находятся в текущем `HEAD`; повторная проверка не выявила относящихся к backend находок из `JUDGE.md`, поэтому необоснованный кодовый diff не создавался.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается последовательными пачками `100/100/1`; ID внутри пачек уникальны; ответ в обратном порядке сопоставляется по `order_id`; ошибка средней пачки сохраняет её локальные статусы и не останавливает последнюю пачку; пропущенная строка не считается успешной.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: ручная сверка одного заказа использует batch-клиент с единственным ID и применяет ответ.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py` — код выхода 1: четыре ранее существующие ошибки в импортируемых соседних модулях `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `app/services/fbs_warehouse_binding_service.py:291`; в двух проверяемых модулях атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — успешно: `2 passed in 2.09s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — отсутствие живого UI-стенда и browser evidence для зон `S-03`, `S-14`, `S-15` — не относится к backend-файлам и слою атома 4; backend-изменений для неё нет.
- Новые маршруты, миграции, изменение расписания автополлера, UI и обращения к живому кабинету Wildberries не добавлялись.

## Находки

- Целевой `mypy` затрагивает импортируемые соседние модули и обнаруживает в них четыре ошибки, перечисленные в разделе «Гейты»; файлы находятся вне разрешённого слоя атома и не изменялись.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-блокеров атома 4 нет.
- Новый `DEV.md` локально записан, но не сохранён отдельным коммитом: `git add night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "night(01-wb-marking): verify atom 4 rework"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` из-за запрета записи файловой системы (`Operation not permitted`). Код реализации и тест атома уже находятся в истории текущей ветки.
