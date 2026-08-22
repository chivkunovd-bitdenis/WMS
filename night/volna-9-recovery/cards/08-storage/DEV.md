# Фича 1

# screen-dev · 08-storage · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx` — тест закрепляет «Печать накладной» для `row` и `panel`, а также сохранение прежних подписей и disabled-подсказок в обоих размещениях.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx` — проверен в рамках атома: закрытый словарь `PrintAction` уже содержит внутреннее правило `накладную → накладной`; публичный интерфейс компонента не изменён.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — артефакт выполнения атома.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `python3 ../scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.

## Не реализовано

Пунктов контракта, которые не удалось реализовать буквально в этом атоме, нет. Находки `REVIEW.md` относятся к серверному хранению и экрану S-11; они не затрагивают разрешённые файлы UI-kit атома 1.

Git-коммит не создан: среда запрещает Git создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Поэтому результат реализован локально, но не сохранён коммитом.

# Фича 2

# DEV · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py` — цепочка миграций продолжена от обязательной `20260821_0094`; журнал наблюдений и снимок действующего источника остаются добавляющей миграцией.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_wb_import_dimensions.py` — добавлена проверка совместного хранения ручной и WB-версий, единственной активной записи и их аудиторского контекста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/product.py app/models/product_dimension_event.py alembic/versions/20260822_0095_product_dimension_events.py tests/test_wb_import_dimensions.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/models/product.py app/models/product_dimension_event.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_wb_import_dimensions.py` — успешно, `5 passed in 3.99s`.
- `back_guard.py` не применим: в атоме нет нового маршрута.
- `check_migrations.py` не применим: атом исправляет существующую миграцию, но не добавляет новую.
- `git commit -m "fix(storage): linearize dimensions migration"` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — не выполнен: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).

## Не реализовано

- Находка ревью №9 о синхронизации `dimensions_updated_at` и `dimensions_updated_by_user_id` при WB-импорте и возврате к WB лежит в сервисах `catalog_service.py` и `wildberries_product_import_service.py`, которые буквально принадлежат следующему атому 3. В рамках атома 2 они не изменялись.
- Находки ревью №1–8 и №11–12 относятся к UI, API, расчётам хранения, биллингу, движению и следующим атомам; этот атом их не затрагивает.
- Изменения реализованы локально, но не сохранены Git-коммитом из-за запрета на создание Git lock-файла.

# Фича 3

# DEV · 08-storage · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py` — при возврате к последнему полному наблюдению WB обновляет быстрый снимок времени и очищает автора ручного обмера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py` — применённое наблюдение WB обновляет быстрый снимок времени и автора; тип входной карточки уточнён для mypy.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_product_dimension_history.py` — TC-NEW-003: полный ручной обмер, тара без основания и с основанием, повтор WB-наблюдения, сохранение ручного объёма и создание новой действующей версии при возврате к WB.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/catalog_service.py app/services/wildberries_product_import_service.py tests/test_product_dimension_history.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py` — пройдено, `7 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/catalog_service.py app/services/wildberries_product_import_service.py tests/test_product_dimension_history.py` — не пройдено из-за четырёх существующих ошибок в не затронутых данным атомом модулях: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`. Ошибок в изменённых файлах нет.
- `back_guard.py` и `check_migrations.py` не применимы: этот атом не добавляет маршрут или миграцию.

## Не реализовано

- Нет. Пересчёт или изменение закрытых периодов этим атомом не вызываются и не изменяются.

## Находки

- Секреты, токены, `.env` и кабинеты учётных данных не читались.

# Фича 4

# DEV · 08-storage · атом 4 · переделка после ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py` — ручной PATCH габаритов доступен только `FULFILLMENT_ADMIN` и staff с правом `inventory`; `ProductOut` теперь возвращает источник, время и автора действующих габаритов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py` — проверены поля снимка действующих габаритов и корректная ошибка `404 wb_dimensions_not_found`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_catalog.py` — проверено, что reception и shift lead не могут менять габариты, а inventory может; проверка невалидных размеров выполняется под разрешённой ролью inventory.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/products.py tests/test_products_api.py tests/test_catalog.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/products.py` — не пройдено из-за 4 существующих ошибок в не затронутых модулях: `app/services/wildberries_credentials_service.py`, `app/services/fbs_stock_sync_service.py`, `app/services/fbs_warehouse_binding_service.py`. В `products.py` ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_products_api.py tests/test_catalog.py::test_only_inventory_staff_can_update_product_dimensions tests/test_catalog.py::test_staff_product_dimensions_validation_rejects_zero_and_partial_body` — пройдено: `3 passed`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: в переделке не добавлялся маршрут или миграция.
- `git add … && git commit -m 'fix(storage): restrict dimension measurement access'` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и не сохранены коммитом.

## Не реализовано

- Находки ревью №1–7 и №10–12 относятся к frontend, storage statement/measurement, billing и миграциям других атомов; этот атом их не изменяет.
- В `wildberries_product_import_service.py` и `catalog_service.py` из находки №9 время и автор WB-версии уже обновляются. Исправлена недостающая часть этой находки в слое атома: эти поля возвращаются через `ProductOut`.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 5

# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py` — добавлена уникальность измерения по tenant, селлеру, операционному складу, SKU и месяцу; это защищает повторный rebuild от дублей.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py` — миграция создаёт тот же уникальный ключ; существующие ограничения отформатированы по лимиту ruff.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py` — проверяет состав нового ключа и отсутствие изменяемой ссылки на ячейку вместо диапазона зафиксированных движений.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому.

## Миграции

- `20260822_0096_storage_measurements_and_statements` — добавляет `uq_storage_measurements_tenant_seller_warehouse_product_period`; отдельная таблица денег, локальный тариф или счёт не добавлялись.

## Тесты

- `test_measurement_is_unique_for_tenant_seller_warehouse_sku_and_month` — состав ключа идемпотентности monthly measurement.
- `test_measurement_keeps_immutable_movement_boundary_references` — измерение не содержит `storage_location_id` и хранит только FK на границы `InventoryMovement`.

## Гейты

- `ruff check backend/app/models/storage_measurement.py backend/app/models/storage_statement.py backend/tests/test_storage_models.py backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py` — `All checks passed!`
- `cd backend && mypy -m app.models.storage_measurement -m app.models.storage_statement` — `Success: no issues found in 2 source files`.
- `cd backend && pytest -q tests/test_storage_models.py` — `5 passed`.
- `git diff --check` — пройден без вывода.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- Эквивалентная проверка `cd backend && alembic heads` — обнаружила отсутствующую внешнюю ревизию `20260821_0094`, на которую ссылается уже существующая `20260822_0095`; изменения атома 5 эту внешнюю цепочку не меняют.
- `python3 scripts/ci/back_guard.py` неприменим: новых роутов в атоме нет.
- `git add … && git commit -m 'night(08-storage): enforce measurement idempotency'` — не выполнен: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`. Изменения остаются в рабочем дереве и требуют коммита из среды с доступом к Git metadata.

## Не реализовано

- Из вердикта ревью №3 не менялся контракт `InventoryMovement.seller_id/warehouse_id`, backfill и writers: это единоличная зона внешнего фундамента 07-A по `ARCH-CROSS.md`, не слой атома 5.
- Денежная фиксация statement, выбор тарифа, печатный DTO и API из находок №2 и №5–9 не менялись: этот атом создаёт только неизменяемые модели и миграцию без финансовых таблиц или новых роутов.
- Нахождение внешней отсутствующей миграции `20260821_0094` записано выше как факт проверки; секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 6

# DEV · 08-storage · атом 6 · исправления ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py` — расчёт теперь режет положительный остаток также в момент смены версии габаритов; поздний обмер не применяется к более раннему остатку, а любой положительный интервал без объёма остаётся проблемой.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — запрос rebuild сразу отклоняет неполную пару года и месяца, несуществующий и будущий месяц; при отсутствии периода по-прежнему передаётся предыдущий календарный месяц МСК.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py` — добавлены проверки разбиения непрерывного остатка сменой габаритов и запрета ретроактивного применения позднего обмера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — обязательный отчёт backend-dev по текущему атому.

## Миграции

Нет.

## Тесты

- `test_volume_segments_split_continuous_stock_at_dimension_change` — литро-дни используют прежний объём до даты новой версии и новый после неё.
- `test_volume_segments_do_not_apply_later_measurement_to_earlier_stock` — отсутствие исторического объёма до первого обмера не подменяется текущим значением товара.

## Гейты

- `cd backend && ruff check app/services/storage_measurement_service.py app/api/storage.py tests/test_storage_measurement_service.py` — `All checks passed!`.
- `cd backend && pytest -q tests/test_storage_measurement_service.py` — `5 passed in 0.02s`.
- `cd backend && mypy app/services/storage_measurement_service.py app/api/storage.py` — не прошёл из-за 48 уже существующих ошибок вне расчёта: отсутствует внешний `app.models.billing` (находка ревью о зависимости 09-A), а также существующие типовые ошибки `storage_statement_service` и его зависимостей.
- `cd backend && mypy --follow-imports=skip app/services/storage_measurement_service.py app/api/storage.py` — не прошёл из-за 7 существующих типовых ошибок API-модуля: FastAPI/Pydantic импортируются как `Any` в этом режиме и у старого `_statement_out` нет полной аннотации.
- `git diff --check` — пройден без вывода.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся, исправлена валидация существующего `/operations/storage/measurements/rebuild`.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграции не добавлялись и не изменялись.

## Не реализовано

- Находка ревью №3 о `InventoryMovement.seller_id/warehouse_id`, backfill и writer-контракте не изменялась: это внешний фундамент 07-A, прямо исключённый границей атома 6.
- Находки №2 и №5–9 о фиксации, тарифах, ledger, печатном DTO и API габаритов относятся к другим атомам и финансовому фундаменту 09-A; в этом атоме деньги не создаются.
- Находки по секретам, ключам, токенам, `.env` и кабинетам учётных данных отсутствуют: они не читались и не использовались.

# Фича 7

# DEV · 08-storage · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — публикация использует контракт общего `BillingLedgerEntry` из 09-A (`tariff_version_id`, `rate`, `source`); нулевой statement получает единственный уникальный source id самого документа, а выборка ledger ограничена source ids именно этого statement.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — фиксированный и повторно печатаемый расчёт отдаёт имя селлера и склада, SKU, артикул, объём, источник габаритов, литро-дни, снимок ставки, сумму и дату фиксации; нулевой документ возвращает пустой состав SKU вместо ошибки `zip(..., strict=True)`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py` — целевые проверки уникального source id нулевого statement, источников обычных строк и безопасной повторной печати нулевого документа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт атома.

## Гейты

- `ruff check backend/app/services/storage_statement_service.py backend/app/api/storage.py backend/tests/test_storage_statement_service.py` — успешно: `All checks passed!`.
- `cd backend && pytest -q tests/test_storage_statement_service.py` — успешно: `3 passed in 0.01s`.
- `cd backend && mypy app/services/storage_statement_service.py app/api/storage.py` — не пройден: в этой рабочей копии отсутствует обязательный внешний модуль `app.models.billing` из 09-A; также mypy сообщает три существующие ошибки вне атома в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `python3 scripts/ci/back_guard.py` — неприменимо: атом не добавляет новый маршрут; файла `scripts/ci/back_guard.py` в данной рабочей копии также нет.
- `python3 scripts/ci/check_migrations.py` — неприменимо: атом не добавляет миграцию; файла `scripts/ci/check_migrations.py` в данной рабочей копии также нет.
- `git diff --check` — успешно, пробеловых ошибок нет.

## Не реализовано

- Разбиение одного агрегированного `StorageMeasurement.liter_days` между несколькими тарифными интервалами внутри месяца: текущая модель измерения не хранит посуточное или интервальное распределение литро-дней, поэтому точный расчёт новой ставки с середины месяца невозможно получить из этого агрегата без изменения контракта измерений. Текущий сервис использует действующую на начало периода версию общего тарифа 09-A.
- Полный интеграционный сценарий фиксации и конкурентных запросов не запускается до появления в этой ветке обязательных моделей 09-A `BillingTariffVersion` и `BillingLedgerEntry`. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не использовались.

# Фича 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Экран S-11 больше не показывает захардкоженные локальные расчёты. Сводка, формирование, ручной обмер, история, фиксация и повторная печать обращаются к API с авторизацией; при недоступности API экран показывает штатную ошибку, а не вымышленные финансовые данные. Добавлены e2e-сценарии `S-11-TC-001`, `003`—`015`, `017`, `020` с пользовательскими действиями и видимыми результатами.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `npx playwright test tests-e2e/storage.spec.ts --reporter=line` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage`: красный до правок S-11 и вне разрешённых файлов этого атома: новые нарушения в `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `git diff --check`: зелёный.

## Не реализовано

- Буквальное сохранение тарифа не реализовано: необходимый API единого биллинга (владение карточки 09-A по `ARCH-CROSS.md`) в этой рабочей копии не опубликован. Диалог не подменяет сохранение локальным состоянием и явно сообщает о границе.
- Полная загрузка сводки требует `GET /operations/storage/statements`; в доступном backend есть только rebuild/fix/print, поэтому на фактическом текущем сервере этот запрос перейдёт в предусмотренное контрактом состояние ошибки загрузки. Экран и e2e уже используют этот контракт, но добавить backend-маршрут запрещено границами роли `screen-dev` и списком файлов S-11.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались и не использовались.
