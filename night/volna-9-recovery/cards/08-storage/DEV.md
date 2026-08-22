# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx`

В `PrintAction` закреплена внутренняя таблица подписей, включая `what="накладную"`; публичный интерфейс компонента не изменён. Добавлены проверки подписей для `row` и `panel`, сохранения существующей подписи и disabled-причины.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх посторонних нарушений базовой линии в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; мои файлы их не затрагивают, базовая линия не обновлялась.
- `npx vitest run src/ui-kit/Actions.test.tsx` — не завершился в отведённое время без вывода, остановлен.
- `npm run test:unit` — не завершён: общий запуск остановлен после зависания Vitest без вывода.
- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за ограничения доступа к служебному каталогу worktree.

## Не реализовано

- Буквально не добавлялся новый член публичного типа `Printable`: `накладную` уже присутствовал в исходной ветке. Закреплена недостающая внутренняя таблица подписей и покрыт требуемый сценарий.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`

`Product` получил быстрый снимок действующего источника, времени и автора. Новая
`ProductDimensionEvent` хранит источник, аудитора, время наблюдения, размеры, объём,
основание объёма тары, fingerprint и признак действующей версии. Уникальные индексы
защищают от дублей и оставляют ровно одну действующую версию на товар.

## Миграции

- `20260822_0095_product_dimension_events` — добавляет три поля действующего источника
  в `products` и создаёт журнал `product_dimension_events` с FK, fingerprint-индексом и
  частичным уникальным индексом действующей версии.

## Гейты

- `ruff` — targeted checks новых файлов зелёные; полный `ruff check .` красный на 82
  существующих нарушениях базовой линии.
- `mypy` — красный: 21 существующая ошибка в 6 файлах; новых ошибок в изменённых моделях
  не выявлено.
- `pytest` — 32 passed, 63 ошибки и остановка полного запуска по таймауту/KeyboardInterrupt;
  ошибки относятся к существующему тестовому контуру.
- `back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py` отсутствует.
- Metadata smoke test импорта моделей — зелёный.

## Не реализовано

- Сервис записи, переключения действующей версии и API истории не реализованы: они
  относятся к атомарным кускам 3–4 и намеренно не входят в этот backend-dev проход.
- Изменение Wildberries-импорта не выполнялось: оно также относится к куску 3.
- Найденные в рабочем дереве секреты, ключи, токены и `.env` не открывались.

# Фича 3

# backend-dev · 08-storage · atom 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

Ручная запись создаёт действующее событие с источником `manual` или `container_override`, импорт WB сохраняет наблюдение и не применяет его поверх ручного события. Одинаковые отпечатки не дублируются; добавлен сервис возврата последнего полного WB-наблюдения.

## Миграции

`20260822_0095_product_dimension_events` уже был в рабочей копии и добавляет поля источника на `products` и таблицу неизменяемых наблюдений. Новых миграций для этого атома нет.

## Тесты

Существующие `backend/tests/test_wb_import_dimensions.py`: отсутствие габаритов, исправление legacy-заглушки и запрет перезаписи реального ручного значения. Тесты карточки `test_product_dimension_history.py` в рабочей копии отсутствовали, поэтому новый тестовый файл не добавлялся вне разрешённого списка.

## Гейты

- ruff (целевые файлы): PASS.
- mypy: NOT RUN — полный backend-gate запускается после ruff и остановлен из-за 80 существующих ошибок ruff вне этого атома.
- pytest (целевой файл): PASS, 3 passed.
- back_guard.py: NOT RUN — новых роутов нет.
- check_migrations.py: NOT RUN — миграции этого атома не добавлялись.

## Не реализовано

- Отдельный HTTP-роут возврата WB не добавлялся: контракт этого атома ограничивает изменения сервисами и импортом, а новый роут потребовал бы отдельного теста и API-контракта.
- Закрытые периоды не пересчитываются этой логикой: она меняет только текущую версию габаритов и события; расчёт закрытых периодов находится вне этих сервисов.

## Находки

- Исправлен `sqlite_where` условного индекса событий: строковое условие не компилировалось SQLAlchemy на тестовой SQLite-схеме.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py` — API истории, обмера тары и возврата последней WB-версии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py` — атомарное сохранение объёма тары и чтение истории.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py` — API-тест сохранения и чтения истории, включая невалидный объём.

## Гейты

- `ruff` — targeted для изменённых backend-файлов: PASS; полный `ruff check .`: FAIL на 80 существующих нарушениях вне этого куска.
- `mypy` — FAIL на 4 существующих ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы новых ошибок не добавили.
- `pytest` — PASS: `7 passed` для `tests/test_products_api.py tests/test_catalog.py`.
- `back_guard.py` — НЕ ЗАПУЩЕН: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.
- `check_migrations.py` — НЕ ЗАПУЩЕН: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.

## Миграции

Нет: схема уже подготовлена предыдущим куском `20260822_0095_product_dimension_events`.

## Не реализовано

- Полный runtime-тест роли сотрудника с правом `inventory` и запрета другой организации не добавлен в этот проход; tenant-проверка выполняется сервисом, а права — зависимостями API.
- Импорт Wildberries не изменялся: API только возвращает последнюю сохранённую WB-версию.

## Находки

- В рабочем дереве был несвязанный `night/volna-9-recovery/JOURNAL.md`; не изменялся.

# Фича 5

# Backend implementation report — 08-storage

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_statement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py

## Что реализовано

`StorageMeasurement` хранит tenant, seller, операционный склад, SKU, версию габаритов, начало и конец диапазона движений, точное количество-дни, литро-дни и статус без денежных полей.

`StorageStatement` группирует tenant, seller, склад и календарный период; уникальное ограничение запрещает второй документ для того же tenant/селлера/склада/месяца.

## Миграции

`20260822_0096` — добавляет таблицы `storage_measurements` и `storage_statements`, внешние ключи на существующие сущности и индексы; тарифы, начисления и денежные таблицы не добавляет.

## Тесты

Новых тестов не добавлял: в этой части нет эндпоинтов и сервисной логики. Импорт ORM-моделей проверен отдельной командой; миграция содержит уникальность месячного документа.

## Гейты

- ruff — FAIL на полном проекте из-за 98 существующих ошибок; новые файлы после форматирования проходят `ruff check`.
- mypy — FAIL на 4 существующих ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- pytest — прерван после 133.49 с из-за длительности полного набора: 192 passed, 3 skipped, 5 warnings; до остановки падений не было.
- back_guard.py — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Строгая проверка, что склад операционный, и проверка `InventoryMovement.warehouse_id` невозможны буквально в этой карточке: фундамент 07-A ещё не добавлен в рабочую копию и соответствующего поля в текущей модели нет. Миграция сохраняет диапазон через `movement_start_id`/`movement_end_id` и прямую ссылку на `warehouse_id`, не создавая дублирующий складской контракт.

## Блокеры

Коммит невозможен в этой sandbox-копии: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (Operation not permitted). Изменения остаются в рабочем дереве и не имеют проверенного commit SHA.

# Фича 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py` — расчёт месячного черновика по положительному остатку и доле суток.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — POST `/operations/storage/measurements/rebuild`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/background_job_service.py` — выполнение задания и сохранение последнего успешного результата при ошибке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/tasks/background_jobs.py` — Celery-задача `wms.storage_measurement_rebuild`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/main.py` — регистрация storage API.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py` — проверки прошлого месяца и валидации месяца.

## Гейты

- `ruff` — PASS для изменённых backend-файлов.
- `mypy` — FAIL на существующих ошибках зависимостей и соседних сервисов (`boto3`, `celery`, `fitz`, credentials, stock sync); после исправления собственной ошибки в новом job-коде новых ошибок в нём не осталось.
- `pytest` — PASS: `2 passed` для `backend/tests/test_storage_measurement_service.py`.
- `back_guard.py` — NOT RUN: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.
- `check_migrations.py` — NOT RUN: файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/`.

## Не реализовано

- Денежные начисления, тарифы, фиксация и печать не реализованы: они относятся к атомам 7/9 и не входят в этот кусок.
- В текущей модели `Warehouse` нет отдельного поля операционного типа; отбор ограничен tenant и активными `StorageLocation`, поэтому служебные склады без активных локаций исключаются, а явный тип склада ждёт контракта 07-A.
- Полный набор сценариев из FEATURES (нулевой месяц без движений и детальные API-ответы черновика) требует готовых связей 07-A и отдельного API-контракта; сервисный каркас не создаёт деньги и повторно использует открытый draft идемпотентно.

## Находки

- Секретные файлы, ключи, токены и `.env` не читались.

# Фича 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — атомарная фиксация черновика, проверка проблем, снимок тарифа и публикация ledger через общий billing-модуль; повторная фиксация идемпотентна.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — POST `/operations/storage/statements/{statement_id}/fix` и GET `/operations/storage/statements/{statement_id}/print`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py` — проверка обязательной зависимости общего billing-слоя.

## Гейты

- ruff — PASS для изменённых файлов.
- mypy — FAIL: отсутствует `app.models.billing`, плюс есть существующие ошибки в соседних сервисах.
- pytest — PASS: существующие `2 passed`; новый тест фиксирует отсутствие 09-A зависимости.
- back_guard.py — NOT RUN: файл отсутствует.
- check_migrations.py — NOT RUN: файл отсутствует.

## Не реализовано

- Полная публикация `BillingLedgerEntry` и повторная печать с тарифом-снимком не может быть выполнена буквально: общий модуль `app.models.billing` (09-A) отсутствует. Свой storage-тариф, storage-таблицу или второй путь счёта не добавлял.
- Тесты параллельной фиксации и A4-содержимого не добавлял без валидных 09-A billing fixtures.

## Находки

- Секретные файлы, ключи, токены, `.env` и кабинеты учётных данных не читались и не использовались.

# Фича 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения размера монолита в `src/App.tsx`, а также нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; последние файлы карточкой не менялись, базовая линия не обновлялась.
- `npm run test:unit` — красный до запуска тестов: `sh: vitest: command not found` (зависимости frontend не установлены в рабочей копии).

## Не реализовано

- Полный серверный расчёт, тарифы, история, роли и печать подключены как локальный экранный прототип: в контракте отсутствуют доступные API-контракты для этого экрана, поэтому без изменения запрещённых файлов реализован только пользовательский поток и состояния.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались и не использовались.

Коммит создать не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за ограничений доступа среды.
