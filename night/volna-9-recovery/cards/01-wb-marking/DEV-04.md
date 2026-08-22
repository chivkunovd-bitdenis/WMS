# DEV · 01-wb-marking · атом 4/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`: фоновая сверка выбирает заказы собираемых поставок одного tenant и селлера, дедуплицирует `wb_order_id` с сохранением порядка и последовательно читает Wildberries пачками не более 100 ID; ошибка одной пачки журналируется и не останавливает следующую пачку.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`: строки успешного batch-ответа индексируются по `order_id`, поэтому позиция строки в ответе не влияет на выбор локального заказа; ошибочная пачка не увеличивает счётчик успеха и не меняет локальные данные своих заказов.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: применение принимает уже полученную строку batch-ответа, а существующий ручной путь продолжает вызывать тот же batch-клиент с единственным `wb_order_id`.
- Реализация и тест атома уже сохранены в истории текущей ветки; повторная проверка `JUDGE.md` не выявила замечаний к backend-файлам или слою атома, поэтому необоснованный новый кодовый diff не создавался.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним оркестратором.

Backend-файлы атома уже присутствуют в текущем `HEAD` и адресно проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py`

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается строго последовательными пачками `100/100/1`; каждая пачка содержит не более 100 уникальных ID; перевёрнутый ответ применяется по `order_id`; ошибка второй пачки сохраняет её исходные `check_status` и `meta_status`, после чего третья пачка выполняется; пропущенная строка не засчитывается как успешная сверка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: существующая ручная сверка одного заказа использует batch-клиент с пачкой из одного ID и применяет ответ.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py` — код выхода 1: четыре ранее существующие ошибки в импортируемых соседних модулях `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `app/services/fbs_warehouse_binding_service.py:291`; в двух проверяемых модулях атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — успешно: `2 passed in 1.89s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет маршруты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие браузерных снимков зон `S-03`, `S-14` и `S-15`. Она не относится к разрешённым backend-файлам и слою атома 4, поэтому backend-изменений для неё нет.
- Новые маршруты, миграции, изменение расписания автополлера, UI и обращения к живому кабинету Wildberries не добавлялись.

## Находки

- Целевой `mypy` обнаруживает четыре ошибки в импортируемых соседних сервисах, перечисленные в разделе «Гейты»; эти файлы находятся вне границ атома и не изменялись.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома 4. Браузерная продуктовая проверка остаётся отдельным этапом согласно `JUDGE.md`.
