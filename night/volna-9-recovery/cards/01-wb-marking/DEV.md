# Фича 1

# DEV · 01-wb-marking · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch-чтение `metaDetails` сохраняет `key`, `value`, `decision` и `reason`; при `429` один раз ожидает `Retry-After` (число или HTTP-дата) и повторяет ту же пачку не более 100 заказов.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: ответы 4xx/5xx и неразбираемое тело возвращают ошибку без частичного успешного результата.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: полный DTO `decision`/`value`/`reason`, один повтор после `429`, числовой и HTTP-date `Retry-After`, ошибки 400/500 и неразбираемый успешный ответ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: адресная регрессия вызывающего контура.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Backend-код атома уже сохранён в текущей ветке коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`; повторная проверка `JUDGE.md` не выявила замечаний в файлах и слое этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.06s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 0.96s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не применим: роуты не добавлялись и не менялись.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не применим: миграции не добавлялись.
- `git add night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "night(01-wb-marking): verify atom 1 rework" -- night/volna-9-recovery/cards/01-wb-marking/DEV.md` — FAIL до изменения индекса: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Замечание `JUDGE.md` о недоступном живом UI относится к browser-product-review экранов S-03, S-14 и S-15. Этот backend-атом не меняет UI, поэтому исправлений в его файлах и слое нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-код атома сохранён в Git-коммите `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`, но обновлённый `DEV.md` остаётся незакоммиченным из-за read-only доступа sandbox к общему Git metadata. Browser-product-review остаётся отдельной проверкой живого UI.

# Фича 2

# DEV · 01-wb-marking · атом 2/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет; атом расширяет допустимые типы существующего журнала КИЗ.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: константа `EVENT_WB_ORPHANED = "wb_orphaned"` включена в `MARKING_CODE_EVENT_TYPES`.
- Существующий журнал `MarkingCodeEvent` принимает событие `wb_orphaned` со ссылками на исходный код и пул. Создание события само по себе не меняет статус, пул или продуктовую привязку КИЗ и не освобождает код.
- Backend-реализация атома уже сохранена в истории текущей ветки: основной код и тест — `5ae86fe8018170fc68064e87b5815f8cb8af0fd3`, дополнительные проверки ссылок события — `acb19c362589b5544d961eda1b75e896790a3388`.

## Миграции

Нет. `marking_code_events.event_type` уже является строковым полем `String(32)`, поэтому добавление нового допустимого значения не меняет схему данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, ссылку на КИЗ, пул, статус и продуктовую привязку после сохранения.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

В текущем rework backend-файлы не менялись: `JUDGE.md` не содержит находок в модели, журнале или тесте этого атома. Обязательный отчёт `DEV.md` восстановлен после удаления внешним оркестратором.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS: `1 passed in 0.96s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Повторная и конкурентная дедупликация `wb_orphaned` не входит в этот атом: по `FEATURES.md` её покрывает следующая фича сверки без новой таблицы или миграции.
- Единственная находка `JUDGE.md` — недоступность живого UI-стенда и отсутствие браузерных снимков экранов `S-03`, `S-14`, `S-15`. Она не относится к backend-файлам или слою этого атома и не требует изменения модели либо теста.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

Нет для backend-атома. Браузерная продуктовая проверка остаётся отдельным заблокированным этапом согласно `JUDGE.md`.

# Фича 3

# DEV · 01-wb-marking · атом 3 · rework по JUDGE

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: применяет `metaDetails.decision` к существующей привязке КИЗ, сохраняет `reason` и сырой блок, переводит `required` без значения в `missing`, а отличающееся заполненное значение — в `replacement_required`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: сохраняет `marking_code_id` и жизненный статус КИЗ, однократно пишет `wb_orphaned`, а пропущенную строку, отсутствующий ожидаемый `kind` и неизвестное решение обрабатывает как безопасный `unknown` без ложной даты успешной проверки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — реализация атома уже сохранена в истории текущей ветки; по находке `JUDGE.md` дополнительная backend-правка не потребовалась.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — целевые сценарии атома уже сохранены в истории текущей ветки; в rework повторно проверены адресно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — обновлён отчёт rework с фактическими результатами гейтов.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail` — отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего кода; сохранение причины и сырого блока.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time` — отсутствие ожидаемого `kind` даёт `unknown`, не стирает прежние детали КИЗ и не ставит дату успешной проверки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only` — пропущенный `order_id` не меняет привязку, жизненный статус КИЗ, прежнюю причину, сырой блок и время последней успешной проверки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — повторные и конкурентные `missing` / `replacement_required` оставляют один аудит-факт `wb_orphaned`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && ruff check backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py` — код выхода 1 из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `app/services/fbs_warehouse_binding_service.py:291`; в файле атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — успешно: `13 passed in 10.25s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие browser evidence — не относится к файлам и backend-слою атома 3; backend-изменений для неё нет.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему Wildberries не добавлялись.

## Блокеры

- Backend-блокеров атома нет. Целевой `mypy` остаётся не зелёным только из-за четырёх ошибок в соседних импортируемых модулях вне разрешённых файлов этого атома.
- Новый отчёт `DEV.md` локально записан, но не сохранён отдельным коммитом: `git commit` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` из-за запрета записи sandbox (`Operation not permitted`). Реализация и тесты атома уже находятся в истории текущей ветки.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

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

# Фича 5

# DEV · 01-wb-marking · атом 5 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: подтверждено отсутствие устаревшего одиночного чтения `GET /api/v3/orders/{orderId}/meta` и функции `fetch_marketplace_order_meta`; актуальное batch-чтение через `fetch_marketplace_orders_meta_batch` остаётся единственным путём чтения метаданных.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — записан отчёт повторной проверки атома.

Backend-код в текущем `HEAD` уже буквально соответствует атому 5, поэтому необоснованный кодовый diff не создавался. Находка из `JUDGE.md` относится только к отсутствующему живому браузерному стенду и не указывает дефектов backend-файла или слоя этого атома.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` — проверены импорты и поведение публичных функций клиента, включая запись метаданных.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — проверено актуальное batch-чтение метаданных и остальные импорты клиентских функций этого модуля.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_client.py` — успешно: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `28 passed in 0.15s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ! rg -n 'fetch_marketplace_order_meta' app tests --glob '*.py' && ! rg -n 'async def fetch_marketplace_order_meta|def fetch_marketplace_order_meta' app --glob '*.py'` — успешно: определений и вызовов нет.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Браузерный стенд и снимки зон `S-03`, `S-14`, `S-15` из находки `JUDGE.md` не поднимались: это Product Browser Review, а не разрешённый backend-слой атома 5.
- Новые fallback-пути, пользовательские действия, роуты, модели и миграции не добавлялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома 5.
