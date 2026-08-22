# Фича 1

# DEV · 01-wb-marking · атом 1/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: рабочее batch-чтение `POST /api/marketplace/v3/orders/meta` возвращает DTO с `decision`, `value` и `reason`; при первом `429` ждёт значение `Retry-After` и ровно один раз повторяет ту же пачку не более чем из 100 заказов; остальные `4xx/5xx` и неразбираемое тело завершаются `WildberriesClientError`, а не частичным успехом.
- Реализация и тесты атома уже сохранены в истории текущей ветки коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`. Повторная проверка `JUDGE.md` не выявила замечаний в backend-файлах или слое этого атома, поэтому необоснованный кодовый diff не создавался.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_exact_contract_and_parse` проверяет сохранение `decision`, `value` и `reason` в DTO.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_retries_429_once_after_retry_after` проверяет ожидание `Retry-After`, ровно один повтор и успешный результат повторённой пачки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_honors_retry_after_http_date` проверяет HTTP-date форму `Retry-After`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_does_not_retry_other_errors` проверяет ошибку без повтора для `400` и `500`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_rejects_malformed_response_after_single_429_retry` проверяет, что неразбираемое тело после единственного повтора возвращает `invalid_response`, а не частичный успех.
- Полностью выполнен разрешённый тестовый файл атома: 19 тестов прошли.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним оркестратором.

Backend-файлы в текущем rework не изменялись: они уже буквально соответствуют атому, а единственная находка `JUDGE.md` относится к отсутствующему живому браузерному стенду, не к backend-слою.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.06s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие браузерных снимков зон `S-03`, `S-14`, `S-15`. Она не относится к разрешённым backend-файлам и слою атома 1, поэтому backend-изменений для неё нет.
- Расписание, UI, модели, миграции, новые роуты и обращения к живому кабинету Wildberries не менялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома. Браузерная продуктовая проверка остаётся отдельным этапом согласно `JUDGE.md`.

# Фича 2

# DEV · 01-wb-marking · атом 2/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет; атом расширяет допустимые типы существующего журнала КИЗ.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: событие `EVENT_WB_ORPHANED = "wb_orphaned"` входит в `MARKING_CODE_EVENT_TYPES`.
- Существующий журнал `MarkingCodeEvent` принимает `wb_orphaned` с сохранением ссылки на исходный КИЗ и пул. Запись события сама по себе не меняет статус, пул или продуктовую привязку кода и не освобождает его.
- Код и тест атома уже сохранены в истории текущей ветки коммитами `5ae86fe8018170fc68064e87b5815f8cb8af0fd3` и `acb19c362589b5544d961eda1b75e896790a3388`.

## Миграции

- Нет. Поле `marking_code_events.event_type` уже хранится как `String(32)`, поэтому новый допустимый тип события не меняет схему данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, ссылку на КИЗ, пул, статус и продуктовую привязку после сохранения.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — реализация атома уже находится в истории ветки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — целевой тест атома уже находится в истории ветки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним процессом.

В текущем rework backend-файлы не менялись: `JUDGE.md` не содержит находок в модели, журнале или тесте этого атома, поэтому необоснованный кодовый diff не создавался.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS: `1 passed in 1.49s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Повторная и конкурентная дедупликация `wb_orphaned` не входит в этот атом: по `FEATURES.md` её покрывает следующая фича сверки без новой таблицы или миграции.
- Единственная находка `JUDGE.md` — недоступность живого UI-стенда и отсутствие браузерных снимков экранов `S-03`, `S-14`, `S-15`. Она не относится к backend-файлам или слою этого атома и не требует изменения модели либо теста.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома. Браузерная продуктовая проверка остаётся отдельным этапом согласно `JUDGE.md`.

# Фича 3

# DEV · 01-wb-marking · атом 3 · rework по JUDGE

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: уже сохранённая в истории ветки реализация безопасно применяет `metaDetails.decision`, сохраняет `reason` и сырой блок, переводит `required` без значения в `missing`, а отличающееся заполненное значение — в `replacement_required`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: сохраняет `marking_code_id` и жизненный статус КИЗ, однократно пишет `wb_orphaned`, а пропущенную строку, отсутствующий ожидаемый `kind` и неизвестное решение обрабатывает как безопасный `unknown` без ложной даты успешной проверки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — реализация атома уже сохранена в коммите `cce84fd4`; в текущем rework backend-код не менялся, потому что единственная находка `JUDGE.md` относится к недоступному живому UI-стенду.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — тесты атома уже сохранены в коммите `cce84fd4`; в текущем rework они повторно выполнены адресно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт с фактическими результатами rework.

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
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — успешно: `13 passed in 11.04s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие browser evidence — не относится к разрешённым файлам и backend-слою атома 3; backend-изменений для неё нет.
- В `CONTRACT.md` отсутствует буквально названный раздел `API и данные`; backend-спецификация атома дана в `FEATURES.md`. В текущем rework новая реализация по неполному контракту не начиналась: выполнена только адресная проверка уже сохранённого атома.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему Wildberries не добавлялись.

## Блокеры

- Backend-блокеров поведения атома нет. Целевой `mypy` остаётся не зелёным из-за четырёх ошибок в соседних импортируемых модулях вне разрешённых файлов атома.
- Product browser review остаётся заблокированным отсутствием живого стенда; это зафиксировано в `JUDGE.md` и не исправляется в роли `backend-dev`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

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

# Фича 5

# DEV · 01-wb-marking · атом 5/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых backend-роутов нет; устаревший внешний вызов `GET /api/v3/orders/{orderId}/meta` удалён ранее и на текущем `HEAD` отсутствует.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: функции `fetch_marketplace_order_meta` и её вызовов больше нет; одиночные операции записи метаданных не изменены.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: `fetch_marketplace_orders_meta_batch` через batch `POST /api/marketplace/v3/orders/meta` подтверждён как единственный путь чтения метаданных заказов.
- Находка `JUDGE.md` относится только к неподнятому живому UI-стенду; дефектов разрешённого backend-файла или слоя атома 5 в вердикте нет, поэтому необоснованный кодовый diff не создавался.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним оркестратором.

Backend-реализация атома уже сохранена в истории текущей ветки:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — удаление функции в `db5503842415145860237d989d9a403dc834c288`, очистка последнего устаревшего упоминания в `a70c4f03a622c41495c94b39ab33333455bb3343`.

## Миграции

- Нет.

## Тесты

- Новые тесты не добавлялись: новый роут или поведение не вводились, а атом удаляет мёртвую клиентскую функцию.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` — проверены импорты и действующие операции клиента, включая запись метаданных.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — проверены импорт и контракт актуального batch-чтения метаданных, включая успешный ответ, повтор 429 и ошибки ответа.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_client.py` — успешно: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `28 passed in 0.15s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && if rg -n 'fetch_marketplace_order_meta' backend/app backend/tests --glob '*.py'; then exit 1; else printf '%s\n' 'PASS: fetch_marketplace_order_meta отсутствует в backend/app и backend/tests'; fi` — успешно: определений и вызовов нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && rg -n 'fetch_marketplace_orders_meta_batch|MARKETPLACE_ORDERS_META_BULK_PATH' backend/app/services backend/tests/test_wildberries_marketplace_fbs_client.py` — успешно: batch-функция определена, вызывается сервисами и покрыта тестами.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Браузерный стенд и снимки зон `S-03`, `S-14`, `S-15` из находки `JUDGE.md` не поднимались: это Product Browser Review, а не разрешённый backend-слой атома 5.
- Новые fallback-пути, пользовательские действия, роуты, модели и миграции не добавлялись.

## Находки

- В `CONTRACT.md` нет отдельного раздела `API и данные`; rework ограничен однозначным backend-контрактом атома 5 из `FEATURES.md` и уже принятой реализацией в истории ветки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома 5.
