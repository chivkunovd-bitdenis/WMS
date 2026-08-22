# Фича 1

# DEV · 08-storage · атом 1 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx` — проверки `PrintAction` переведены на фактический React-рендер для вариантов `row` и `panel`, прежних подписей и disabled-пояснений.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.ts` — добавлена точка входа для теста, потому что текущий `vitest.config.ts` обнаруживает только файлы `*.test.ts` и пропускал контрактный `Actions.test.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — записан отчёт роли `screen-dev`.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx` в rework не менялся: внутреннее сопоставление `what="накладную"` → `Печать накладной` уже реализовано, публичный интерфейс компонента сохранён. В `REVIEW.md` нет находок, относящихся к `Actions.tsx`, `Actions.test.tsx` или слою этого атома.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный**, код возврата 2. Все девять ошибок находятся вне разрешённых файлов атома, в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`: две ошибки устаревшего `inputProps`, три вызова `TextCell` без `value`, два вызова `StatusChip` через неподдерживаемый `children`, один вызов `ProductCell` без `sku` и ещё один вызов `StatusChip` через `children` в диалоге истории.
- `python3 scripts/ui/ui_guard.py` из корня — **красный**, код возврата 1. Храповик сообщает три новых нарушения вне разрешённых файлов атома: `src/components/WbProductPickerDialog.tsx` (646 строк), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2498 строк), `src/screens/v2/SellerInboundDraftScreen.tsx` (1169 строк). Базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — **зелёный**: 20 файлов, 141 тест, включая 3 теста `PrintAction`.
- Целевая проверка `npm run test:unit -- src/ui-kit/Actions.test.ts` — **зелёная**: 1 файл, 3 теста.
- `git add … && git commit -m "test(storage): run PrintAction render coverage"` — **красный**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Результат остаётся в постоянном рабочем дереве, но не сохранён отдельным коммитом.

## Не реализовано

- Пунктов атома, которые не удалось реализовать буквально, нет: `what="накладную"` рендерит подпись «Печать накладной» в `row` и `panel`; четыре существующих варианта сохранили подписи; disabled-пояснение и блокировка сохранены.
- Глобальные `tsc` и `ui_guard.py` не доведены до зелёного состояния, потому что их ошибки находятся в файлах других атомов и соседних задач, которые роль `screen-dev` для этого атома менять запрещает.
- Сохранить rework отдельным Git-коммитом не удалось из-за запрета среды на запись в метаданные worktree; без коммита результат нельзя считать опубликованным или пригодным для передачи по SHA.

# Фича 2

# DEV · 08-storage · атом 2 · rework

## Что реализовано

- Эндпоинты: нет, атом не добавляет и не меняет маршруты.
- Сервис `catalog_service._record_dimension_event`: повторные WB-наблюдения по-прежнему дедуплицируются, а каждый ручной обмер `manual` / `container_override` создаёт новую неизменяемую версию и не переписывает дату или автора прежней записи.
- Модель `ProductDimensionEvent`: уникальность fingerprint ограничена источником `wb`, поэтому одинаковые осознанные ручные обмеры в разные моменты сохраняются отдельными событиями.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_product_dimension_history.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0095` — добавляет снимок действующего источника габаритов в `products` и журнал `product_dimension_events`; в rework уникальный индекс `(product_id, fingerprint)` сделан частичным для `source = 'wb'`, чтобы дедуплицировать импорт, но не терять повторные ручные обмеры.

## Тесты

- `test_repeated_manual_measurement_keeps_both_immutable_observations` — проверяет сценарий ревью: одинаковый ручной обмер после возврата к WB создаёт новую версию с новым автором, не меняет аудит первой версии и оставляет ровно одну действующую запись.
- `tests/test_product_dimension_history.py` и `tests/test_wb_import_dimensions.py` — проверяют ручную и WB-историю, единственную действующую версию, сохранность ручного значения при импорте, возврат к WB и отсутствие дублей повторного WB-наблюдения.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/product.py app/models/product_dimension_event.py app/services/catalog_service.py alembic/versions/20260822_0095_product_dimension_events.py tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/models/product.py app/models/product_dimension_event.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=skip --disable-error-code=misc --disable-error-code=no-any-return app/services/catalog_service.py` — успешно, `Success: no issues found in 1 source file`. Обычный запуск `mypy app/models/product.py app/models/product_dimension_event.py app/services/catalog_service.py` рекурсивно остановился на четырёх ранее существовавших ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; эти файлы атом не меняет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py` — успешно, `8 passed in 8.64s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не запущен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет, команда завершилась с кодом 2.
- `back_guard.py` не применим: новый маршрут не добавлялся.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — успешно, замечаний нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/alembic/versions/20260822_0095_product_dimension_events.py backend/app/models/product_dimension_event.py backend/app/services/catalog_service.py backend/tests/test_product_dimension_history.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): preserve repeated manual measurements"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки ревью №1–4 и №6–10 относятся к API списка, биллингу, writer движения, расчёту хранения и frontend; они не входят в файлы и слой атома 2.
- Миграция `0095` по обязательному порядку `ARCH-CROSS.md` продолжает внешнюю миграцию `0094` карточки 03. Файл `0094` в этой изолированной рабочей копии отсутствует, поэтому сквозной `alembic upgrade` здесь не выдаётся за выполненную проверку.
- Сохранить rework отдельным Git-коммитом не удалось из-за запрета среды на запись в метаданные worktree; результат локально реализован, но не опубликован и не может считаться сохранённым по SHA.

## Блокеры

- Интеграционная проверка цепочки миграций требует предшествующую карточку 03 и отсутствующий в checkout скрипт `scripts/ci/check_migrations.py`.
- Git-коммит заблокирован правами среды на общий каталог метаданных worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.

# Фича 3

# DEV · 08-storage · атом 3 · переделка по ревью

## Что реализовано

- Сервис расчёта хранения исключает WB-наблюдения, записанные поверх действующего ручного обмера или объёма тары, из временной шкалы применённых габаритов.
- Явный возврат к WB остаётся новой действующей версией и меняет объём только с момента возврата; завершившийся ранее период сохраняет ручной объём.
- Существующая реализация `catalog_service.py` проверена на находку ревью № 5: повторный осознанный ручной обмер создаёт новое неизменяемое событие и не переписывает автора старого события.
- Новые эндпоинты не добавлялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- Нет.

## Тесты

- Добавлен сценарий: новое WB-наблюдение после ручного обмера не меняет объём в расчёте хранения.
- Добавлен сценарий: явный возврат к последней полной WB-версии меняет открытую временную шкалу с момента возврата и не меняет завершившийся ранее период.
- Повторно проверены сценарии полного ручного обмера, объёма тары без основания и с основанием, одинакового повторного WB-импорта, WB-обновления после ручного обмера, возврата к WB и повторного ручного обмера тем же значением с сохранением старых даты и автора.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/catalog_service.py app/services/wildberries_product_import_service.py app/services/storage_measurement_service.py tests/test_product_dimension_history.py tests/test_storage_measurement_service.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/storage_measurement_service.py tests/test_storage_measurement_service.py` — пройдено, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/catalog_service.py app/services/wildberries_product_import_service.py app/services/storage_measurement_service.py tests/test_product_dimension_history.py tests/test_storage_measurement_service.py` — затронутые файлы очищены; общий граф импортов сообщает четыре ранее существовавшие ошибки вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_product_dimension_history.py tests/test_wb_import_dimensions.py tests/test_storage_measurement_service.py` — пройдено, `15 passed in 6.20s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — пройдено, замечаний нет.
- `back_guard.py` и `check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/app/services/storage_measurement_service.py backend/tests/test_storage_measurement_service.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): preserve manual dimensions in calculations"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, `Operation not permitted`.

## Не реализовано

- Нет пунктов атома 3, которые не легли буквально. Находки ревью о list API, биллинге, складских движениях, тарифах, текущем месяце, DTO фронтенда, правах маршрута и Playwright относятся к другим атомам и их файлам; в этой переделке они не затрагивались.
- Результат локально реализован, но не сохранён Git-коммитом и не опубликован: среда запрещает запись в общий каталог метаданных текущего worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.

## Блокеры

- Сохранение отдельным коммитом заблокировано правами среды на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`; код и `DEV.md` находятся только в рабочем дереве.

# Фича 4

# DEV · 08-storage · атом 4 · переделка по ревью

## Что реализовано

- `GET /products/{product_id}/dimensions/history` — ответ истории приведён к DTO живого экрана: `created_at`, `author_name`, `is_current`, источники `manual` / `wildberries` / `container`; авторы загружаются одним tenant-ограниченным запросом.
- `PATCH /products/{product_id}/dimensions` — API-тестами закреплено сохранение полного ручного обмера сотрудником с правом `inventory`, а также запрет неполных и нулевых значений без частичной записи.
- `POST /products/{product_id}/dimensions/container` — API-тестами закреплено сохранение объёма тары с основанием и отклонение нулевого объёма либо пустого основания без частичной записи.
- `POST /products/{product_id}/dimensions/restore-wb` — API-тестами закреплён запрет для сотрудника и успешный возврат последней WB-версии только администратором ФФ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- Нет.

## Тесты

- `test_inventory_staff_saves_both_measurements_and_reads_ui_history` проверяет оба способа обмера, хронологию, публичные названия источников, автора и единственную действующую версию.
- `test_invalid_measurements_and_foreign_tenant_do_not_write_history` проверяет неполные и нулевые значения, tenant-изоляцию и отсутствие частичной записи.
- `test_only_admin_can_restore_latest_wb_dimensions` проверяет право `inventory`, отказ сотруднику в возврате WB, отказ сотруднику без `inventory` в обмере и успешный возврат WB администратором.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/products.py tests/test_products_api.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/products.py tests/test_products_api.py` — изменённые файлы очищены; общий граф импортов сообщает четыре ранее существовавшие ошибки вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/products.py tests/test_products_api.py` — пройдено, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_products_api.py` — пройдено, `3 passed in 4.93s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — пройдено, замечаний нет.
- `back_guard.py` и `check_migrations.py` не запускались: переделка не добавляет маршрут или миграцию.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/app/api/products.py backend/tests/test_products_api.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m "fix(storage): align dimension history API"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки ревью № 1–7 и № 9–10 относятся к другим атомам и прямо названным файлам API хранения, сервисов, миграций либо frontend; в атоме 4 они не изменялись.
- Старые внутренние поля истории `observed_at`, `author_user_id`, `applied` намеренно больше не публикуются: утверждённый живой экран использует `created_at`, `author_name`, `is_current`.
- Результат локально реализован, но не сохранён Git-коммитом и не опубликован: среда запрещает запись в общий каталог метаданных текущего worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, Wildberries и боевой production не читались и не изменялись.

## Блокеры

- Сохранение отдельным коммитом заблокировано правами среды на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`; код, тесты и `DEV.md` находятся только в рабочем дереве.

# Фича 5

# DEV · 08-storage · атом 5 · переделка по REVIEW

## Что реализовано

- Эндпоинты: нет; атом не добавляет и не меняет HTTP-маршруты.
- Сервис `record_movement_and_adjust_balance`: каждое новое движение фиксирует `seller_id` товара и фактический `warehouse_id` ячейки в момент записи, поэтому дальнейшее изменение товара или ячейки не меняет исторический склад измерения.
- Модель `InventoryMovement`: добавлены замороженный селлер, обязательный склад и признак неполной legacy-разметки; `StorageMeasurement` продолжает ссылаться на границы этих зафиксированных движений.
- Служебные legacy-склады `FBS WB`, `FBS WB *` и склады с кодом `fbs-wb-*` помечаются `is_operational=false` и не входят в обычный состав документов хранения.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0097_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_inventory_movements_report.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0094_inventory_movement_reporting_dimensions` — после внешней ревизии карточки 03 добавляет `seller_id`, обязательный `warehouse_id` и `reporting_dimensions_legacy` в `inventory_movements`, детерминированно заполняет их через товар и ячейку и создаёт индексы отчётных срезов.
- `20260822_0095_product_dimension_events` — изменена только ссылка `down_revision`, чтобы цепочка шла после фундамента 07-A.
- `20260822_0096_storage_measurements_and_statements` — без изменений в переделке; по-прежнему добавляет только неизменяемые измерения и месячные документы без денежных таблиц.
- `20260822_0097_storage_movement_scope` — больше не дублирует `warehouse_id`; добавляет `warehouses.is_operational` и исключает legacy-склады `FBS WB` из операционного контура.

## Тесты

- `test_inventory_movement_has_frozen_storage_dimensions` — обязательность зафиксированного склада и наличие селлера/legacy-признака.
- `test_migrations_backfill_movements_and_exclude_technical_warehouses` — backfill селлера и склада, запрет неразрешённого склада и исключение служебных складов.
- `test_movement_freezes_seller_and_warehouse_at_write_time` — смена селлера товара и склада ячейки после движения не переписывает сохранённые измерения движения.
- `test_inventory_movements_report.py` адаптирован к обязательному `warehouse_id` при прямом создании тестовых движений.
- Повторно проверены пять модельных сценариев уникальности, неизменяемых ссылок и отсутствия денежных колонок из `test_storage_models.py`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/inventory_movement.py app/models/storage_measurement.py app/models/storage_statement.py app/services/inventory_service.py tests/test_storage_models.py tests/test_storage_movement_scope.py tests/test_inventory_movements_report.py alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py alembic/versions/20260822_0095_product_dimension_events.py alembic/versions/20260822_0096_storage_measurements_and_statements.py alembic/versions/20260822_0097_storage_movement_scope.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/models/inventory_movement.py app/models/storage_measurement.py app/models/storage_statement.py app/services/inventory_service.py tests/test_storage_movement_scope.py` — `Success: no issues found in 5 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_models.py tests/test_storage_movement_scope.py tests/test_inventory_movements_report.py` — `10 passed in 3.16s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не выполнен: скрипт отсутствует в этой рабочей копии (`Errno 2`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && alembic heads` — интеграционная проверка остановилась на отсутствующей внешней ревизии `20260821_0094` карточки 03. Ревизия 07-A намеренно сохраняет обязательный порядок `03 -> 07-A -> 08` из `ARCH-CROSS.md` и не подменяет соседнюю миграцию.
- `python3 scripts/ci/back_guard.py` — неприменим: новых роутов нет.
- `git add -- <файлы атома> && git commit -m 'fix(storage): freeze movement warehouse scope'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Изменения локально реализованы, но из-за ограничения sandbox не сохранены в коммите.

## Не реализовано

- Миграция `20260821_0094_fbs_supplies_boxes_without_distribution.py` карточки 03 не копировалась в этот атом: это соседняя продуктовая задача, которая должна быть влита раньше по обязательному порядку волны. До интеграции этой зависимости `alembic heads` в изолированной ветке не проходит.
- Находки REVIEW №1–2 и №4–10 относятся к API, тарифам, расчёту, истории габаритов и frontend, а не к моделям и миграциям атома 5; здесь они не менялись.
- Денежные таблицы, локальные тарифы и отдельный storage-счёт не создавались по прямой границе атома.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.

## Находки

- Данных, утечек, секретов или персональных данных в пределах просмотренных файлов не обнаружено.

## Блокеры

- Для кода атома нет. Для общей Alembic-цепочки нужна предусмотренная `ARCH-CROSS.md` предыдущая миграция карточки 03; факт отражён в гейтах и не скрыт под ложным успешным статусом.
- Сохранение результата в Git заблокировано запретом записи в Git metadata основного checkout; восстановимого commit SHA нет.

# Фича 6

# DEV · 08-storage · атом 6 · переделка по ревью

## Что реализовано

- `storage_measurement_service` — пересчёт открытого месячного черновика теперь только подготавливает изменения через `flush`, а финальную транзакцию оставляет фоновой задаче; при последующем сбое задача может откатить пересчёт и сохранить последний успешный черновик.
- `POST /operations/storage/measurements/rebuild` и `GET /operations/storage/statements` — поведение и контракты не расширялись; существующие фоновый запуск, чтение черновика и проверка будущего месяца подтверждены целевыми тестами.
- Регрессионная проверка измерений движения — исправлено ошибочное ожидание самоссылки Alembic: миграция `20260821_0094` корректно зависит от `20260821_0093`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

Нет. Миграционная цепочка не менялась; тест теперь проверяет фактическую добавляющую цепочку `20260821_0093 → 20260821_0094`.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py` добавлена проверка, что пересчёт видит новые движения внутри своей транзакции, но после отката сохраняется предыдущий успешный результат `6.000000` литро-дней.
- Существующий набор этого файла подтверждает долю суток, прошлый месяц по умолчанию, запрет будущего месяца, нулевой месяц, отсутствие габаритов, отрицательный восстановленный остаток, повтор фонового задания и исключение неоперационных складов.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_movement_scope.py` исправлена проверка `down_revision`; сценарии замороженных `seller_id` и `warehouse_id` также пройдены.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_measurement_service.py` — успешно: `11 passed in 1.82s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/storage_measurement_service.py tests/test_storage_measurement_service.py tests/test_storage_movement_scope.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/services/storage_measurement_service.py tests/test_storage_measurement_service.py tests/test_storage_movement_scope.py` — успешно: `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_measurement_service.py tests/test_storage_movement_scope.py` — успешно: `14 passed in 3.10s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — успешно, ошибок форматирования diff нет.
- `back_guard.py` не запускался: переделка не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: переделка не добавляет и не меняет миграции.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/app/services/storage_measurement_service.py backend/tests/test_storage_measurement_service.py backend/tests/test_storage_movement_scope.py night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "fix(storage): preserve draft on rebuild failure"` — не выполнено: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, получено `Operation not permitted`.

## Не реализовано

- Находка ревью про складские и индивидуальные тарифы не входит в атом 6: она требует изменения финансовой модели `BillingTariffVersion` из внешнего 09-A и тарифного API следующего атома.
- Находка ревью про арифметику печатной строки относится к фиксации и печати атома 7; печатный DTO в этой переделке не менялся.
- Лишние ORM-модели 09-B и форматирование его миграции относятся к финансовому ядру соседней карточки и не менялись.
- UI-находки про диалог тарифа и проверку роли сотрудника не входят в роль `backend-dev` и атом 6.

## Находки

- Ошибок, связанных с секретами, данными или персональными данными, в прочитанном слое атома не обнаружено.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены коммитом: песочница даёт рабочей копии доступ на запись, а служебный Git-каталог зарегистрированного worktree доступен только для чтения. Риск — незакоммиченный diff нельзя восстановить по SHA до запуска `git add`/`git commit` процессом с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`.

# Фича 7

# DEV · 08-storage · атом 7 · повторная разработка по ревью

## Что реализовано

- `GET /operations/storage/statements` — признак настроенного тарифа теперь считается по выбранным операционным складам; для администратора персональная ставка одного селлера не подменяет общую ставку склада.
- `POST /operations/storage/statements/{statement_id}/fix` — фиксация выбирает только тарифы того же склада и селлера, сохраняет эффективную ставку с достаточной точностью и по-прежнему публикует один неизменяемый набор `BillingLedgerEntry`.
- `GET /operations/storage/statements/{statement_id}/print` — A4-снимок берёт литро-дни, эффективную ставку и сумму из неизменяемого ledger, поэтому документ согласован с начислением при старте или смене тарифа внутри месяца.
- `storage_statement_service` — склад добавлен в область выбора общей и индивидуальной версии тарифа; эффективная ставка одной ledger-строки хранится с точностью 12 знаков после запятой.
- Финансовая модель 09-A очищена от преждевременных `BillingInvoice` и `BillingRunIssue`, для которых в миграции не было таблиц. Эти сущности остаются за атомом 09-B.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_billing_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0094` — в создаваемую таблицу `billing_tariff_versions` добавляет nullable `warehouse_id` с внешним ключом на `warehouses`, обязательность склада для `storage_liter_day`, раздельную уникальность общих и персональных ставок внутри склада и сохранение прежней уникальности глобальных тарифов других услуг. Точность `billing_ledger_entries.rate` увеличена до `Numeric(28, 12)` для арифметически согласованной эффективной ставки одной строки.
- Миграция остаётся добавляющей: удаления таблиц или колонок нет.

## Тесты

- `backend/tests/test_storage_statement_service.py` — проверены два одновременных запроса фиксации, единственность ledger-строки, неизменность повторной печати после нового обмера, отказ для проблемного и текущего черновика, нулевой statement, отсутствие подходящего тарифа, изоляция тарифа другого склада, неприменимость персональной ставки как общей и согласованность A4 с начисленными литро-днями при неполном тарифном месяце.
- `backend/tests/test_billing_models.py` — проверены складские и глобальные уникальные индексы тарифа, точность ledger-ставки и отсутствие преждевременных ORM-таблиц 09-B.
- `backend/tests/test_storage_movement_scope.py` — назначенный ревьюером миграционный регресс включён в целевой прогон; исправление правильного `down_revision = 20260821_0093` уже находилось в текущем HEAD.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/billing.py app/models/__init__.py app/services/storage_statement_service.py app/api/storage.py alembic/versions/20260822_0094_billing_financial_core.py tests/test_storage_statement_service.py tests/test_billing_models.py tests/test_storage_movement_scope.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/models/billing.py app/models/__init__.py app/services/storage_statement_service.py app/api/storage.py` — успешно: `Success: no issues found in 4 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_statement_service.py tests/test_billing_models.py tests/test_storage_movement_scope.py` — успешно: `14 passed in 3.64s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не запущен: в этой рабочей копии отсутствует `scripts/ci/check_migrations.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && alembic heads` — успешно: единственная голова `20260822_0097 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — успешно, ошибок пробелов нет.
- `back_guard.py` не применялся: атом не добавляет новый роут; самого файла в этой рабочей копии также нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add <файлы атома> && git commit -m "fix(storage): align fixed statements with warehouse ledger"` — среда запретила запись в общий Git-каталог: `Unable to create .../.git/worktrees/lane-2-08-storage1/index.lock: Operation not permitted`. Изменения остались в рабочей копии и не закоммичены.

Обычный целевой вызов `mypy` без `--follow-imports=silent` дополнительно был выполнен и дошёл до несвязанных импортов. Он нашёл четыре существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в четырёх затронутых модулях ошибок не показал. Полный backend-регресс не запускался по ограничению атома.

## Не реализовано

- Находки ревью 1 и 7 относятся к `frontend/` и роли `screen-dev`; backend-dev их не менял.
- API создания и изменения тарифа не добавлялся: это отдельный следующий атом и не входит в «зафиксировать документ и опубликовать ledger-строку».
- `BillingInvoice` и `BillingRunIssue` не реализованы: по `ARCH-CROSS.md` они принадлежат следующему этапу 09-B и не должны регистрироваться ORM до своей миграции.

## Находки

- В репозитории отсутствуют предписанные скрипты `scripts/ci/check_migrations.py` и `scripts/ci/back_guard.py`; цепочка миграций вместо первого дополнительно проверена безопасной командой `alembic heads` без подключения к БД.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не использовались.

## Блокеры

Функциональных блокеров кода нет. Публикация результата заблокирована файловыми правами среды на общий Git-каталог; commit и push не созданы. Отсутствие репозиторного migration-checker явно зафиксировано выше.

# Фича 8

# 08-storage · screen-dev rework по повторному ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В экран S-11 вместо тупикового сообщения добавлен диалог тарифа по макету и контракту:
операционный склад, обязательные ставка и дата начала, раскрываемая индивидуальная ставка
селлера, `PrimaryAction` «Сохранить» и `SecondaryAction` «Отмена». Ввод проверяется до
отправки; ошибка сервера остаётся в диалоге и показывается через `ErrorNotice`. Сохранение
отправляет общий тариф и, если раскрыто исключение, отдельную версию для пары
«селлер + склад» в `/operations/storage/tariffs`, после чего перечитывает экран.

В `S-11-TC-002` зафиксированы ввод ставки и даты и точное тело запроса. Для
`S-11-TC-012` восстановлен непустой сценарий сотрудника: он раскрывает SKU при настроенном
тарифе, но не видит ни изменение тарифа, ни фиксацию.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — красный только на существующих нарушениях вне файлов атома: `frontend/src/components/WbProductPickerDialog.tsx` (`0 → 646`), `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). В файлах S-11 нового нарушения нет; базовая линия не обновлялась. Скрипт также сообщает улучшение `frontend/src/App.tsx` (`3492 → 3491`), этот файл в текущем rework не менялся.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный: 20 файлов, 141 тест.
- `npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002|S-11-TC-012' --reporter=line` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — инфраструктурно красный до запуска тестов: Playwright web-server не смог открыть `127.0.0.1:18000`, `operation not permitted`.
- `npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002|S-11-TC-012' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный: найдены четыре целевых теста в одном файле, тестовый файл компилируется.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — зелёный.

## Не реализовано

- В backend этой рабочей копии отсутствует маршрут записи тарифа. Экран теперь отправляет
  `POST /operations/storage/tariffs` с `warehouse_id`, `amount`, `valid_from` и
  необязательным `seller_id`, но реальное сохранение получит 404, пока владелец backend-слоя
  не опубликует этот endpoint. Добавлять backend-файл роли `screen-dev` и списку файлов
  атома не разрешено; ложный успех через локальное состояние не создавался.
- Полный браузерный результат `S-11-TC-002` и `S-11-TC-012` не подтверждён из-за запрета
  песочницы на локальный bind. Компиляция и обнаружение целевых тестов подтверждены.
- Находки 2–6 повторного `REVIEW.md` относятся к backend-моделям, API, миграции и backend-
  тестам. Они не исправлялись ролью `screen-dev`; соседние продуктовые файлы не затрагивались.

## Находки

Секреты, ключи, токены, `.env`, персональные кабинеты и боевой production не открывались
и не использовались.
