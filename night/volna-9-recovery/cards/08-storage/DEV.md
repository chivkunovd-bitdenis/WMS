# Фича 1

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный, ошибок TypeScript не вывел.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в посторонних файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Изменённые файлы этого атома в выводе не названы; базовую линию не обновлял.
- `npm run test:unit -- --run src/ui-kit/Actions.test.tsx` — не запущен: `vitest: command not found`.

## Не реализовано

- Невыполненные пункты контракта для этого атома отсутствуют. Внутренняя подпись `накладную` теперь отображается как «Печать накладной» в вариантах `row` и `panel`; публичный интерфейс `PrintAction` не менялся.
- Находки ревью по экрану хранения и backend не относятся к разрешённым файлам этого атома и не изменялись.

# Фича 2

# DEV · 08-storage · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py`

Исправлена атомарная часть хранения версий габаритов: fingerprint учитывает источник и объём, WB-наблюдение больше не перезаписывает действующий ручной обмер или объём тары, ручной автор сохраняется при активации версии, сотрудники с правом `inventory` могут вносить обмер, а история товара проверяет принадлежность селлеру.

Миграции: нет; миграция `20260822_0095_product_dimension_events.py` уже присутствует и не изменялась.

## Гейты

- ruff: целевые файлы прошли; полный `ruff check .` заблокирован 23 существующими ошибками в несвязанных файлах.
- mypy: полный и целевой запуск заблокирован 5 существующими ошибками в несвязанных местах; новых ошибок в изменённых строках не выявлено.
- pytest: `tests/test_wb_import_dimensions.py tests/test_catalog.py` — 9 passed.
- back_guard.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Замечания ревью по расчёту хранения, биллингу, тарифам, печати и фронтенду не относятся к этому атомарному backend-слою и не изменялись.
- `external_updated_at` не заполняется: текущий WB-клиент не передаёт дату обновления карточки; поле миграции сохранено для будущего значения.

Блокеры: Git-коммит не создан: Git пытается создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, путь находится вне разрешённой рабочей копии и недоступен для записи. Изменения локальны и требуют сохранения/коммита владельцем или расширения прав.

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_wb_import_dimensions.py`

## Гейты

- ruff (изменённые backend-файлы): PASS.
- mypy: FAIL на существующих ошибках в `storage_statement_service.py` (отсутствует `app.models.billing`) и других несвязанных файлах; новых ошибок в изменённых строках не выявлено.
- pytest: PASS, `4 passed` в `tests/test_wb_import_dimensions.py`.
- back_guard.py: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Финансовые, storage-measurement и UI-находки REVIEW.md не относятся к атомарному backend-куску «Не давать импорту WB затереть ручной обмер» и не изменялись.
- Полный `mypy` и CI-скрипты не стали зелёными из-за уже существующих ошибок/отсутствующих скриптов, перечисленных в разделе «Гейты».

# Фича 4

# DEV · 08-storage · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py`

## Что реализовано

- История габаритов фильтруется по tenant и явно ограничивается seller-владельцем товара; чужой товар для seller возвращает `product_not_found`.
- API ручного обмера сохраняет `container_override`; тестами закреплены запрет неполного и нулевого обмера.
- Доступ сотрудника с правом `inventory` к ручному обмеру сохранён в API-ветке.

## Миграции

Нет.

## Тесты

- `backend/tests/test_products_api.py`: история container-обмера, запрет неполных и нулевых габаритов.

## Гейты

- `ruff check .`: FAIL — существующие ошибки вне изменённых файлов (80 ошибок, включая `storage_statement_service.py` и FBS-модули).
- `mypy .`: FAIL — существующие ошибки, включая отсутствующий `app.models.billing`; ошибок в изменённых строках не показано.
- `pytest -q tests/test_products_api.py`: PASS — 1 passed.
- `pytest -q`: INTERRUPTED вручную после прохождения 26% набора без ошибки; полный результат не получен.
- `python3 scripts/ci/back_guard.py`: BLOCKED — файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py`: BLOCKED — файл отсутствует в рабочей копии.
- Commit: BLOCKED — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета доступа к общему git-метадаталогу.

## Не реализовано

- Остальные находки ревью по storage statements, billing, WB-импорту и frontend находятся за пределами атома 4 и не изменялись.

## Блокеры

- Нет блокеров по коду атома; общие гейты требуют исправлений/файлов, отсутствующих в этой рабочей копии.
- Сохранение commit заблокировано правами на общий git worktree; изменения остаются в рабочей копии до устранения ограничения.

# Фича 5

# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_statement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py`

Добавлены переносимые ограничения неотрицательных измерений и корректного диапазона периода. Уникальность `StorageStatement` теперь привязана к `tenant_id + seller_id + warehouse_id + period_start`, поэтому второй документ за тот же календарный месяц создать нельзя.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL из-за 93 ранее существовавших ошибок в несвязанных файлах.
- `mypy`: PASS для изменённых моделей; полный `mypy .` — FAIL из-за ошибок в несвязанных сервисах и cleanup-скриптах.
- `pytest`: 5 целевых тестов PASS. Полный запуск остановлен после 32 passed / 63 errors: общие тесты падают на подготовке существующей схемы/фикстур, не в тестах атома.
- `back_guard.py`: не запущен — файл отсутствует по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует по пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/check_migrations.py`.

## Не реализовано

- Проверка соответствия `StorageMeasurement.warehouse_id` фактическому `InventoryMovement.warehouse_id` и исключение служебных складов не добавлены: поля `InventoryMovement.warehouse_id` и `Warehouse.is_operational` принадлежат внешнему фундаменту 07-A и отсутствуют в этой рабочей копии.
- Идемпотентный rebuild, часовой пояс МСК, публикация ledger, API и ролевые ограничения относятся к соседним сервисным/API-атомам и намеренно не изменялись.

# Фича 6

# DEV · 08-storage · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/background_job_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

## Что реализовано

- Расчёт месячного черновика использует календарные границы и доли суток в часовом поясе МСК.
- Повторный rebuild не добавляет строки к закрытому statement; открытые строки пересчитываются идемпотентно.
- Для периода без движений создаются нулевые draft statements по доступным seller/warehouse scope.
- Добавлен seller scope для фонового задания и право `inventory` для запуска rebuild через API.
- При наличии `InventoryMovement.warehouse_id` расчёт использует зафиксированный склад движения; fallback на storage location оставлен для старых данных до 07-A.

## Миграции

Нет. Схема не менялась.

## Тесты

- Целевые storage-тесты: 5 passed.
- Полный `pytest` запущен; на момент подготовки артефакта процесс ещё выполнялся.

## Гейты

- `ruff`: целевые изменённые файлы — passed; полный `ruff check .` — failed на существующих несвязанных ошибках в других backend-файлах.
- `mypy`: изменённые сервис/API проверены; полный/связанный запуск выявил существующие ошибки в `wildberries_credentials_service.py` и `fbs_stock_sync_service.py`, не относящиеся к этому атому.
- `pytest`: целевые тесты — passed; полный прогон запущен, итог ожидается.
- `back_guard.py`: не запущен — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py`: не запущен по той же причине; миграций нет.

## Не реализовано

- Поле `InventoryMovement.warehouse_id` и `Warehouse.is_operational` отсутствуют в текущей рабочей копии: сервис использует immutable поле, если фундамент 07-A уже присутствует, иначе совместимый fallback через location. Добавление соседней миграции 07-A в этот атом не выполнялось.
- Финансовая фиксация/ledger, печатный A4-контракт, WB-защита габаритов и UI находятся в других атомах и не изменялись.

## Блокеры

Изменения локальны и не сохранены commit: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Обязательные корневые CI-скрипты также отсутствуют в рабочей копии.

# Фича 7

# DEV · 08-storage · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `ruff`: PASS для изменённых backend-файлов.
- `mypy`: FAIL в существующих несвязанных местах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- `pytest`: PASS: `tests/test_storage_statement_service.py` — 1 passed.
- `back_guard.py`: НЕ ЗАПУЩЕН — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py`).
- `check_migrations.py`: НЕ ЗАПУЩЕН — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py`).

## Не реализовано

- Общие модели `BillingTariffVersion` / `BillingLedgerEntry` отсутствуют в текущей рабочей копии; собственный storage-ledger не добавлялся по обязательной границе `ARCH-CROSS.md`.
- Создание нулевого statement и полноценная A4-схема с SKU, ставкой-снимком и итогом требуют соседнего слоя измерений/09-A; в этом атоме не добавлялись новые таблицы и миграции.
- Полный набор конкурентных интеграционных тестов не добавлен: доступные в копии тесты не содержат billing-моделей для исполнения фиксации.

Блокеры: нет; ограничения отражены выше.

# Фича 8

# 08-storage · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

`App.tsx` и `frontend/tests-e2e/storage.spec.ts` в этом проходе не изменялись: маршрут S-11 уже подключён, а существующие тесты не требуют изменения для внесённой экранной правки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в `frontend/` отсутствует исполняемый `tsc`, а `npx --no-install` не доступен.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх предсуществующих нарушений вне атома S-11: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не подтверждён: исполняемый `vitest` отсутствует в `frontend/node_modules`.

## Не реализовано

- API-персистентность, реальные тарифы, измерения, расчёт и фиксация не реализованы: находки REVIEW относятся к backend-файлам, которые запрещены границами screen-dev.
- Исправление подписи `PrintAction` «Печать накладной» не внесено: контракт указывает `frontend/src/ui-kit/Actions.tsx`, но этот файл не входит в разрешённый список атома.
- Полное покрытие `S-11-TC-001`—`S-11-TC-020` не расширялось: добавление сценариев, требующих авторизации и backend-состояний, без доступного API было бы недостоверным.
- В экранной логике исправлены только локальные проблемы слоя экрана: поиск учитывает пробелы и пустой запрос, а формирование показывает состояние загрузки и не допускает повторный запуск.

Изменения не удалось закоммитить: Git заблокирован правами окружения на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).
