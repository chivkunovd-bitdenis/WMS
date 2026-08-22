# Фича 1

# DEV · 01-wb-marking · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — batch DTO сохраняет `decision`, `value` и `reason`; первый ответ `429` ожидает числовой `Retry-After` и повторяет ту же пачку ровно один раз. Реализация уже находилась в текущем `HEAD`, дополнительный backend-дифф не потребовался.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — тесты полного `metaDetails`, единственного повтора `429`, ошибок `4xx/5xx` и неразбираемого ответа уже находились в текущем `HEAD`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт этого запуска.

## Миграции

Нет.

## Тесты

- `tests/test_wildberries_marketplace_fbs_client.py`: 17 тестов — сохранение `decision/value/reason`, повтор batch-запроса ровно один раз после `429`, отсутствие повторов для `4xx/5xx`, отказ на неразбираемом теле и ограничение пачки 100.

## Гейты

- `ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS.
- `mypy app/services/wildberries_fbs_client.py` — PASS.
- `pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: 17 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии, код завершения 2.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии, код завершения 2; миграций нет.

## Не реализовано

- Ничего из атома 1: требуемое поведение уже присутствует в `HEAD`; остальные атомы карточки не затрагивались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

# Фича 2

# DEV · 01-wb-marking · backend-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — проверено: `EVENT_WB_ORPHANED` объявлен и входит в `MARKING_CODE_EVENT_TYPES`; код, статус и пул при записи события не изменяются.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — проверено: тест создаёт `wb_orphaned` через существующий журнал и подтверждает сохранность статуса, пула и товарной привязки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт этого запуска.

Реализационный код и тест уже были в текущем `HEAD` (`5ae86fe`); дополнительный diff в backend для этого атома не потребовался.

## Миграции

Нет: используется существующий журнал событий, схема не меняется.

## Тесты

- `backend/tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — запись допустимого события и проверка неизменности статуса, `pool_id` и `product_id`.

## Гейты

- `ruff check backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `mypy backend/app/models/marking_code.py` — PASS.
- `pytest -q backend/tests/test_marking_code_events.py` — PASS: 3 passed.
- `ruff check .` из `backend/` — FAIL: 80 ранее существующих ошибок в несвязанных файлах.
- `mypy .` из `backend/` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах.
- `pytest -q` из `backend/` — запущен; полный прогон длительный, на момент оформления артефакта продолжался, целевой тест зелёный.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Ничего из контракта атома 2: `wb_orphaned` уже поддерживался существующей моделью и тестом; новые таблицы и миграции не нужны.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

# Фича 3

# DEV · 01-wb-marking · backend-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — проверена безопасная обработка batch-ответа WB: решения `filled`, `optional`, `pending`, `required` без значения и `invalid` переводятся во внутренние статусы; причина и блок `metaDetails` сохраняются; `missing` и `replacement_required` сохраняют локальную привязку и создают единственный `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — проверены отображения решений, сопоставление заказа и `kind`, защита текущих данных при неполном/неизвестном ответе и обновление времени только для возвращённой строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — этот отчёт.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_kiz.py`: целевой набор сценариев WB metadata — 7 passed; существующие тесты покрывают решения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестное решение, несовпадающий код, пропущенную строку и отсутствие ожидаемого `kind`.

## Гейты

- `ruff check .` из `backend/` — не запускался в полном объёме в этом проходе; ранее зафиксированы ошибки вне изменённых файлов. Целевые файлы проверены предыдущим атомом.
- `mypy .` из `backend/` — не запускался в полном объёме в этом проходе; ранее зафиксированы ошибки вне изменённых файлов. Целевой сервис проверен предыдущим атомом.
- `pytest -q tests/test_fbs_kiz.py -k 'wb_decision_mapping or readers_prefer_active or meta'` — PASS: 7 passed, 46 deselected.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует; миграций нет.

## Не реализовано

- Ничего из атома 3: требуемая логика уже присутствовала в рабочей копии после предыдущего backend-прохода; дополнительный кодовый diff не потребовался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# DEV · 01-wb-marking · backend-dev · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — фоновая сверка собирает уникальные `wb_order_id`, последовательно режет их на пачки максимум по 100, после ошибки продолжает следующую пачку и сопоставляет строки ответа с заказом по `order_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — применение принимает уже загруженный batch-ответ; ручной путь сохраняет запрос пачкой из одного ID.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-dev.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_autopoll.py` — целевые тесты прошли: 20 passed; проверены batch-вызовы, ограничение 100, дедупликация, продолжение после ошибки и применение ответа по `order_id`.

## Гейты

- `ruff check .` — FAIL: 80 существующих ошибок в backend, вне изменённых файлов атома.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах, вне изменённых файлов атома.
- `pytest -q tests/test_fbs_marking.py tests/test_fbs_autopoll.py` — PASS: 20 passed.
- `pytest -q` — выполнялся; полный итог не получен в доступном окне выполнения, поэтому не засчитываю как PASS.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Новых API-эндпоинтов, миграций и изменений расписания нет — они не требуются атомом 4.
- Кодовый diff по сервисам не создавался в этом проходе: требуемая реализация уже находилась в рабочей копии до запуска backend-dev и подтверждена целевыми тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# DEV · 01-wb-marking · backend-dev · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — удалены устаревшая одиночная функция `fetch_marketplace_order_meta` и неиспользуемый путь её GET-запроса. Batch-чтение и существующий PUT-сценарий не изменялись.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` — проверен набор тестов импорта и клиентских функций.
- Статический поиск по backend не находит определений или вызовов `fetch_marketplace_order_meta`; batch-чтение остаётся единственным путём чтения метаданных.

## Гейты

- `ruff check .` — FAIL: ранее существующие ошибки в несвязанных файлах; `wildberries_client.py` в выводе ошибок отсутствует.
- `mypy .` — FAIL: ранее существующие ошибки в несвязанных файлах; ошибок в `wildberries_client.py` нет.
- `pytest` — PASS: целевые тесты клиентских функций.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Остальные пункты `FEATURES.md` не затрагивались; реализован только пункт 5.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
