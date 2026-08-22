# Фича 1

# DEV · 01-wb-marking · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch-чтение сохраняет `key`, `value`, `decision` и `reason`; после `429` ровно один раз ждёт полный `Retry-After`, включая HTTP-дату, и повторяет ту же пачку.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: штатная E2E-заглушка теперь возвращает записанную маркировку через рабочий `meta_details`, а не через устаревшее поле `meta`.

## Миграции

- Нет.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` сохранена проверка полного DTO `metaDetails` с `decision`, `value` и `reason`.
- Числовой `Retry-After: 3600` проверяется без искусственного ограничения; HTTP-дата проверяется отдельным тестом; оба сценария подтверждают ровно один повтор пачки.
- Добавлена проверка штатного mock-пути `PUT` → batch `POST`: сеть не вызывается, DTO содержит `meta_details`, legacy `meta` отсутствует.
- Существующие проверки подтверждают ошибку для `400`, `500` и неразбираемого тела вместо частичного успеха.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.09s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 1.02s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git diff --check` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git add -- backend/app/services/wildberries_fbs_client.py backend/tests/test_wildberries_marketplace_fbs_client.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "fix(wb-marking): honor batch retry metadata"` — BLOCKED средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Находки 1 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/REVIEW.md` относятся к атомам применения ответа и фоновой сверки в `fbs_marking_service.py`, `fbs_autopoll_service.py`, `test_fbs_kiz.py` и `test_fbs_marking.py`; по прямому ограничению текущего задания их реализация не менялась.
- Полный backend-регресс не запускался: он прямо запрещён для этого атомарного шага.

## Находки

- В `CONTRACT.md` нет отдельного заголовка «API и данные»; однозначная backend-семантика текущего атома задана разделом 1 `FEATURES.md`, а rework — находками 2 и 4 `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-изменения локально реализованы и проверены, но не сохранены коммитом: Git-метаданные зарегистрированного worktree находятся вне разрешённой для записи области песочницы. Для сохранения нужно выполнить указанную в разделе «Гейты» команду процессом с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

# Фича 2

# DEV · 01-wb-marking · атом 2/5

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис: новых и изменённых сервисов нет; атом расширяет существующий журнал КИЗ на уровне модели.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: тип события `wb_orphaned` включён в допустимый набор `MARKING_CODE_EVENT_TYPES`.
- Журнал КИЗ принимает событие `wb_orphaned`, связанное с исходным `MarkingCode`; создание события не меняет жизненный статус кода, его пул и продуктовую привязку.

## Миграции

Нет: `event_type` уже хранится в строковом поле существующей таблицы журнала, поэтому новый допустимый тип не требует изменения схемы базы данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`: `test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, связь `code_id`, прежние статус, пул и продуктовую привязку КИЗ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS, `1 passed in 4.95s`.
- `back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Конкурентная и повторная дедупликация `wb_orphaned` не реализовывалась в этом атоме: `FEATURES.md` прямо относит повторную запись для той же привязки к следующей фиче сверки и запрещает ради неё новую таблицу или миграцию.
- Находки 1–3 из `REVIEW.md` относятся к `/backend/app/services/fbs_marking_service.py` и тестам следующего сервисного атома, а не к модели и журналу атома 2.
- Находка 4 из `REVIEW.md` требует конкурентного сценария сервиса сверки в `/backend/tests/test_fbs_kiz.py`; этот файл и поведение находятся за границей текущего атома 2.

## Находки

- В `CONTRACT.md` нет отдельного заголовка `API и данные`; backend-граница атома буквально задана в `FEATURES.md` и подтверждена `ARCH-CROSS.md`: карточка 01 владеет семантикой `metaDetails` и не освобождает КИЗ автоматически.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-изменения атома сохранены в достижимых коммитах: основная модель и тест — `5ae86fe8018170fc68064e87b5815f8cb8af0fd3`, дополнительные проверки связи события после ревью — `acb19c362589b5544d961eda1b75e896790a3388`.
- Обновлённый обязательный отчёт `DEV.md` создан локально, но сохранить его отдельным коммитом в этой сессии невозможно: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock`, потому что метаданные worktree находятся вне разрешённой для записи области песочницы (`Operation not permitted`).

# Фича 3

# DEV · 01-wb-marking · атом 3 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `fbs_marking_service._sync_order_meta_from_wb`: пропущенная строка заказа и строка без ожидаемого `kind` безопасно снимают устаревший положительный вердикт в `unknown`, не меняя привязку КИЗ, жизненный статус кода, прежние `reason`/сырой блок и время последней успешной проверки.
- Сервис `fbs_marking_service._sync_order_meta_from_wb`: любое заполненное значение WB, отличающееся от локального, получает `replacement_required`, в том числе при `invalid`; первый переход создаёт один `wb_orphaned`.
- Сервис `fbs_autopoll_service.sync_marking_statuses_for_assembling_supplies`: пропущенный из успешной пачки `order_id` передаётся в безопасное применение, но не учитывается как успешная сверка и не запускает производное обновление поставки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Миграции

- Нет.

## Тесты

- Расширен параметризованный тест отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего значения; `invalid` с чужим КИЗ теперь закреплён как `replacement_required`.
- Добавлен тест пропущенной строки WB: статус сверки становится `unknown`, но ссылка на КИЗ, статус `reserved`, причина, сырой блок и прежнее время успешной проверки сохраняются.
- Сохранён отдельный тест отсутствующего ожидаемого `kind`: свежая дата не появляется, локальные данные КИЗ не стираются.
- Тест однократного аудита расширен на конкурентные и повторные `missing` и `replacement_required`: в каждом варианте остаётся один `wb_orphaned`.
- Регрессия автополлера проверяет применение пропущенного `order_id` без счётчика успеха и уведомления, а упавшая пачка остаётся без изменений.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py tests/test_fbs_kiz.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` — целевой запуск выполнен; остановлен двумя ранее существующими ошибками в импортируемых соседних файлах: `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`. В изменённых строках ошибок не показано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy --follow-imports=skip app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` — диагностический запуск выполнен; из-за пропуска типов импортов показал 16 прежних `no-any-return` в этих модулях и не является зелёным гейтом.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches` — успешно: `14 passed in 14.44s`.
- Первый пробный `pytest` был запущен из `backend/` с ошибочным префиксом `backend/tests/...` и завершился `file or directory not found`; исправленная точная команда выше зелёная.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git add -- backend/app/services/fbs_marking_service.py backend/app/services/fbs_autopoll_service.py backend/tests/test_fbs_kiz.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git diff --cached --check && git status --short && git commit -m "fix(wb-marking): safely apply partial metadata"` — не выполнено средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).
- `python3 scripts/ci/back_guard.py` — не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Находки ревью 2 и 4 относятся к `wildberries_fbs_client.py`, mock-контракту и `Retry-After` атома 1; в атом 3 не включались.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему WB не добавлялись.

## Находки

- Целевой `mypy` загрязнён двумя ошибками соседних импортируемых сервисов, перечисленными в разделе «Гейты»; текущий атом эти файлы не меняет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Локальная реализация и артефакт не сохранены commit: песочница разрешает менять файлы рабочей копии, но запрещает запись в Git-метаданные зарегистрированного worktree за её пределами. Для сохранения требуется повторить указанную в «Гейтах» команду в процессе с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

# Фича 4

# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `sync_marking_statuses_for_assembling_supplies`: подтверждена последовательная обработка уникальных `wb_order_id` пачками не более 100, применение ответа по `order_id`, перевод пропущенного в успешной пачке заказа в безопасный `unknown` без свежего времени проверки и продолжение после локализованной ошибки пачки.
- Сервис `_sync_order_meta_from_wb`: подтверждено, что любое отличающееся заполненное значение WB, включая решение `invalid`, даёт `replacement_required`, не освобождает локальный КИЗ и сохраняет аудит `wb_orphaned`.
- Сервис `fetch_marketplace_orders_meta_batch`: подтверждено, что встроенный mock возвращает рабочий `metaDetails`, а единственный повтор после 429 соблюдает числовой `Retry-After` и HTTP-дату без искусственного ограничения одной секундой.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — исправление применения пропущенного `order_id` уже сохранено в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасный `unknown` и общее правило расхождения заполненных значений уже сохранены в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — рабочий mock `metaDetails` и корректный `Retry-After` уже сохранены в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — пакетная последовательность, частичный ответ и продолжение после ошибки уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — частичный ответ и `invalid` с чужим КИЗ уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — mock batch-контракт и обе формы `Retry-After` уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — обновлённый отчёт rework по атому 4.

## Миграции

- Нет.

## Тесты

- `test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается последовательными пачками `100/100/1`; строки сопоставляются по `order_id`; пропущенный заказ становится `unknown`; ошибка средней пачки не меняет её локальные данные и не останавливает последнюю пачку.
- `test_fbs_marking_sync_updates_check_status`: существующий ручной путь одного заказа остаётся допустимой пачкой из одного ID.
- `test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail`: среди параметров проверен `invalid` с отличающимся заполненным значением, результат — `replacement_required`.
- `test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time`: неполный ответ сбрасывает прежний положительный статус в `unknown`, не проставляя свежую дату успешной проверки.
- `test_fetch_orders_meta_batch_mock_returns_meta_details`: встроенная заглушка возвращает данные в `metaDetails`, а не в устаревшем `row.meta`.
- `test_fetch_orders_meta_batch_retries_429_once_after_retry_after` и `test_fetch_orders_meta_batch_honors_retry_after_http_date`: повтор после 429 ждёт переданное число секунд или интервал до HTTP-даты.

## Гейты

- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_retries_429_once_after_retry_after tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_honors_retry_after_http_date tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_mock_returns_meta_details` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `15 passed in 9.81s`.
- `ruff check app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py app/services/wildberries_fbs_client.py tests/test_fbs_marking.py tests/test_fbs_kiz.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py app/services/wildberries_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — в трёх целевых модулях ошибок нет; команда завершилась кодом 1 из-за четырёх существующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.
- `git diff --check -- night/volna-9-recovery/cards/01-wb-marking/DEV.md` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено.
- `git add -- night/volna-9-recovery/cards/01-wb-marking/DEV.md && git diff --cached --check && git commit -m "docs(wb-marking): record atom 4 rework validation"` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — не выполнено ограниченной средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Нет. Все четыре относящиеся к backend-слою находки `REVIEW.md` исправлены в текущей ветке и подтверждены адресными тестами; соседние продуктовые задачи не затрагивались.

## Находки

- Формального раздела «API и данные» в `CONTRACT.md` нет; работа выполнена по явно заданному backend-атому 4 из `FEATURES.md` и обязательному rework-вердикту `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-реализация находок уже сохранена в текущей ветке на `ce46191f` и предшествующих атомарных коммитах, но обновлённый обязательный `DEV.md` остаётся незакоммиченным: песочница разрешает запись в рабочую копию, но запрещает запись в Git-метаданные зарегистрированного worktree за её пределами. Для сохранения отчёта нужен повтор указанной в «Гейтах» команды процессом с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

# Фича 5

# DEV · 01-wb-marking · атом 5 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; устаревший одиночный `GET /api/v3/orders/{orderId}/meta` отсутствует.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: удалённая ранее функция `fetch_marketplace_order_meta` и её вызовы отсутствуют; комментарий mock-хранилища очищен от упоминания удалённого одиночного `GET`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch `POST /api/marketplace/v3/orders/meta` подтверждён как единственный путь чтения метаданных.
- Находки `REVIEW.md`: четыре исправления соседних атомов присутствуют в текущей ветке и повторно подтверждены названными ревью-сценариями; дополнительного изменения их файлов в атоме 5 не потребовалось.

## Миграции

- Нет.

## Тесты

- Новые тесты не добавлялись: атом удаляет мёртвое чтение, а существующие клиентские тесты полностью покрывают разрешённые операции записи/удаления и batch-чтение.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: подтверждены клиентские контракты, включая batch-чтение `metaDetails`.
- Адресные тесты из `REVIEW.md`: подтверждены полный сырой снимок, контрактный `check_status`, отсутствие legacy fallback и конкурентная однократность `wb_orphaned`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/wildberries_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `Success: no issues found in 1 source file`.
- `pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `26 passed in 0.24s`.
- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_missing` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `13 passed in 22.69s`.
- `if rg -n 'fetch_marketplace_order_meta' backend/app backend/tests; then exit 1; else printf '%s\\n' 'PASS: fetch_marketplace_order_meta отсутствует в backend/app и backend/tests'; fi` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: определений и вызовов нет.
- `rg -n 'fetch_marketplace_orders_meta_batch|MARKETPLACE_ORDERS_META_BULK_PATH' backend/app/services backend/tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: batch-функция определена, вызывается сервисами и покрыта тестами.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.

## Не реализовано

- Нет: атом 5 выполнен буквально; новый fallback и новое пользовательское действие не добавлялись.

## Находки

- В `CONTRACT.md` нет отдельного раздела `API и данные`; для rework использованы однозначные backend-границы атома 5 из `FEATURES.md`, решения `ARCH.md` и проверяемые требования `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет.
