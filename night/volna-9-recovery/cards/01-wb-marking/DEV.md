# Фича 1

# DEV · 01-wb-marking · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — batch DTO сохраняет `decision`, `value`, `reason`; первый ответ `429` ожидает числовой `Retry-After` и повторяет ту же пачку ровно один раз.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — проверки полного `metaDetails`, единственного повтора `429`, ошибок `4xx/5xx` и неразбираемого ответа.

## Миграции

Нет.

## Тесты

- `test_fetch_orders_meta_batch_exact_contract_and_parse` проверяет сохранение `decision`, `value`, `reason`.
- `test_fetch_orders_meta_batch_retries_429_once_after_retry_after` проверяет ровно два запроса и ожидание `Retry-After`.
- Проверки ошибок подтверждают, что неуспешный или неразбираемый ответ не превращается в DTO-успех.

## Гейты

- `ruff check .` — FAIL: в полном backend есть ранее существующие ошибки в несвязанных файлах; целевые файлы проходят (`All checks passed`).
- `mypy .` — FAIL/не пройден в полном backend из-за ранее существующих ошибок; целевой `app/services/wildberries_fbs_client.py` проходит (`Success: no issues found`).
- `pytest` — релевантный набор PASS: 17 passed; полный suite не запускался.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Остальные атомы карточки не затрагивались: `wb_orphaned`, применение ответа к локальной привязке, автополлер пачек и удаление устаревшего одиночного чтения.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 2

# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — проверено: `EVENT_WB_ORPHANED` уже входит в допустимые типы событий журнала.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — проверено: тест создаёт событие через существующий журнал и подтверждает сохранность статуса, пула и привязки к товару.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-dev.

Реализационный код и тест уже были в `HEAD`; дополнительный diff в backend для этой атомарной фичи не требуется.

## Гейты

- `ruff check .` — FAIL: 80 существующих ошибок в несвязанных файлах backend.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах.
- `pytest` — полный прогон начат, но остановлен после прохождения 6% из-за длительного выполнения; целевой `tests/test_marking_code_events.py` прошёл: 3 теста.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Ничего из контракта этой атомарной фичи: `wb_orphaned` и проверка записи в существующий журнал уже присутствуют в исходном `HEAD`; новые таблицы и миграции не нужны.

## Блокеры

- Полный набор гейтов не зелёный из-за ранее существующих ошибок и отсутствующих CI-скриптов; исправления вне атомарной карточки не вносились.

# Фича 3

# DEV · 01-wb-marking · backend-dev · feature 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — при наличии строки заказа WB, но отсутствии ожидаемого `kind`, применение ответа теперь немедленно фиксирует `unknown` и не позволяет несвязанному статусу значения обновить локальную жизненную ветку.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — существующие тесты отображения `filled`, `optional`, `pending`, `required`, `invalid` и неизвестного решения, а также применения batch-ответа; релевантный запуск прошёл: 6 passed.

## Гейты

- `ruff check app/services/fbs_marking_service.py tests/test_fbs_kiz.py` — PASS.
- `mypy .` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах; изменённый сервис в ошибках не указан.
- `pytest` — прерван после частичного запуска полного набора (827 тестов); релевантный `tests/test_fbs_kiz.py -k 'wb_decision_mapping or readers_prefer_active'` — PASS, 6 passed.
- `python3 scripts/ci/back_guard.py` — FAIL: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — FAIL: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Новых тестовых сценариев в `test_fbs_kiz.py` не добавлялось: требуемые базовые отображения и сценарии batch-применения уже были в рабочей копии; изменён только безопасный приоритет `unknown` для неполного `kind`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# DEV · 01-wb-marking · backend-dev · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — фоновая сверка уникальных заказов активных собираемых поставок режет ID на последовательные batch-пачки до 100, продолжает цикл после ошибки пачки и сопоставляет ответ с заказом по `order_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — применение принимает заранее загруженный batch-ответ, сохраняя одиночный ручной путь с пачкой из одного ID.

## Миграции

Нет.

## Тесты

- Существующие backend-тесты маркировки и автополлера покрывают batch-вызовы, ограничение размера пачки, продолжение после локальной ошибки и применение ответа к конкретному заказу.

## Гейты

- `ruff` — PASS для целевых сервисов и тестов.
- `mypy` — PASS для целевых файлов; полный backend не проходит из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`, вне этой фичи.
- `pytest` — PASS: 20 тестов в `tests/test_fbs_marking.py` и `tests/test_fbs_autopoll.py`.
- `back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Новых API-эндпоинтов и миграций нет; расписание и ручной путь не менялись.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# DEV · 01-wb-marking · backend-dev · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — удалены устаревшая одиночная функция `fetch_marketplace_order_meta` и неиспользуемый путь её GET-запроса. Batch-чтение и существующий PUT-сценарий не изменялись.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` — проверен набор тестов импорта и клиентских функций.
- Статический поиск по `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` не находит определений или вызовов `fetch_marketplace_order_meta`.

## Гейты

- `ruff check .` — FAIL: 81 ранее существующая ошибка в несвязанных файлах; изменённый `app/services/wildberries_client.py` в выводе ошибок отсутствует.
- `mypy .` — FAIL: 22 ошибки в 7 несвязанных файлах; после восстановления общей константы ошибок в `wildberries_client.py` нет.
- `pytest` — PASS: 26 тестов клиентских функций (`tests/test_wildberries_marketplace_fbs_client.py`, `tests/test_wildberries_client.py`).
- `back_guard.py` — недоступен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — недоступен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует; миграций нет.

## Не реализовано

- Остальные пункты `FEATURES.md` не затрагивались; реализован только пункт 5.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
