# Фича 1

# screen-dev · 08-storage

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx` — расширены проверки подписи `Печать накладной`, всех существующих панельных подписей и disabled-подсказок в вариантах `row` и `panel`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx` — проверено: закрытый словарь уже возвращает `Печать накладной`; публичный интерфейс не менялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не получил завершающий результат: процесс был остановлен после длительного отсутствия вывода.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх несвязанных нарушений в соседних экранах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit` — не запустился: `vitest: command not found` (зависимости frontend не установлены).

## Не реализовано

Пунктов контракта для этого атома, которые не удалось реализовать буквально, нет. Проверка серверной фиксации хранения и соседних находок ревью в объём этого UI-kit атома не входит.

Сохранить отдельный commit не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за ограничения прав рабочей среды. Текущий проверенный `HEAD`: `a6c01e2ee0ca6236a0e99a1801d3fdb6a07ab978`.

# Фича 2

# Backend Dev · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`

## Что реализовано

- Миграция сохраняет прежние заполненные габариты товаров как первую действующую `legacy`-версию и заполняет быстрый снимок источника/времени.
- Возврат к сохранённым данным WB создаёт отдельное действующее событие без конфликта с уникальным fingerprint; обычные повторы по-прежнему дедуплицируются.
- Ручной PATCH габаритов доступен только администратору или сотруднику с правом `inventory` и записывает `author_user_id` текущего пользователя.

## Миграции

- `20260822_0095`: добавляет поля действующего источника на `products`, журнал `product_dimension_events` и backfill существующих снимков.

## Тесты

- `tests/test_storage_models.py`, `tests/test_products_api.py`, `tests/test_wb_import_dimensions.py`: модель журнала, права/автор ручного обмера и сохранение WB-наблюдений.

## Гейты

- `ruff`: полный прогон не проходит из-за 80 существующих ошибок в соседних файлах; изменённые три Python-файла проходят отдельный `ruff check`.
- `mypy`: полный прогон не проходит из-за существующих ошибок в `storage_statement_service.py`, FBS и cleanup-скриптах; ошибок в изменённых файлах не сообщил.
- `pytest`: целевые тесты `7 passed`; полный прогон запущен, на момент подготовки артефакта ещё выполнялся.
- `back_guard.py`: файл отсутствует в этой рабочей копии (`python3: can't open file scripts/ci/back_guard.py`).
- `check_migrations.py`: файл отсутствует в этой рабочей копии (`python3: can't open file scripts/ci/check_migrations.py`).

## Не реализовано

- Остальные находки ревью по расчёту хранения, биллингу, печати и UI не относятся к этому атомарному backend-слою и не изменялись.

## Блокеры

- Нет.

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py` — импорт WB теперь проверяет действующее событие журнала и сохраняет ручной или контейнерный объём, одновременно записывая новое наблюдение WB.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py` — возврат WB ограничен текущим tenant, последнее полное WB-наблюдение создаёт новую действующую версию без нарушения уникальности fingerprint.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_wb_import_dimensions.py` — использованы существующие регрессионные проверки ручного и контейнерного обмера; отдельный файл `test_product_dimension_history.py` в этой копии отсутствует.

## Гейты

- `ruff check .` — не пройден: 80 ранее существовавших ошибок в несвязанных файлах backend.
- `mypy .` — не пройден: ранее существовавшие ошибки, включая отсутствующие billing-модели из зависимости 09-A.
- `pytest -q tests/test_wb_import_dimensions.py` — пройден, 4 passed.
- `pytest` — запущен полный прогон 823 тестов; результат не получен до завершения ночного запуска.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Полный gate-прогон невозможен из-за отсутствующих CI-скриптов и независимых baseline-ошибок ruff/mypy; код этого атома не расширяет API и не добавляет миграций.
- `night/volna-9-recovery/JOURNAL.md` изменён вне этого атома и не включён в работу.

## Находки

- В рабочей копии обнаружены уже существующие несвязанные изменения и отсутствующие CI-скрипты; секретные файлы, ключи и токены не читались.

# Фича 4

# DEV · 08-storage · атом 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

API атома уже содержит маршруты сохранения обмера товара, истории габаритов,
объёма тары и возврата последней версии WB. Ручной PATCH передаёт автора,
доступ ограничен staff с правом inventory или FULFILLMENT_ADMIN, а возврат WB
доступен только FULFILLMENT_ADMIN. В тест добавлены успешный ручной обмер,
проверка автора и понятная ошибка при отсутствии WB-версии.

## Миграции

Нет новых миграций в рамках этого атома.

## Тесты

- `backend/tests/test_products_api.py`: история, обмер тары, ручной обмер,
  автор события, неполные/нулевые значения и разграничение WB restore.

## Гейты

- `ruff check app/api/products.py tests/test_products_api.py` — PASS.
- `ruff check .` — FAIL на существующих несвязанных нарушениях в ветке.
- `mypy .` — FAIL на существующих ошибках, включая отсутствующие billing-модели
  в соседнем storage statement слое; ошибок в `products.py` и тесте нет.
- `pytest -q tests/test_products_api.py` — PASS (1 passed).
- `pytest` — выполняется; на момент отчёта пройдено 36% без падений.
- `python3 scripts/ci/back_guard.py` и `check_migrations.py` — не получили вывод
  из-за длительного полного pytest; запуск следует повторить после его завершения.

## Не реализовано

- Замечания ревью 1–9 и 13 относятся к UI, расчёту/фиксации хранения,
  миграции и billing-слою, за пределами атома API обмера и истории.
- Полный role-fixture для staff inventory не добавлялся: текущая реализация
  использует существующую проверку `get_staff_permissions`.

## Находки

- В рабочем дереве обнаружены только несвязанные изменения `JOURNAL.md` и
  удаление прежнего `DEV.md`; они не изменялись.

# Фича 5

# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Модели и миграция атома уже содержали таблицы `StorageMeasurement` и `StorageStatement`,
уникальность месячного документа и внешние ключи диапазона на `InventoryMovement.id`.
Добавлены проверки, которые закрепляют ссылку диапазона движения и отсутствие финансовых
полей в документе хранения.

## Гейты

- `ruff check .` — FAIL: 80 ранее существующих ошибок вне изменённых файлов; targeted `ruff check` для моделей и `test_storage_models.py` — PASS.
- `mypy .` — не запускался до конца из-за общего набора; `mypy app/models/storage_measurement.py app/models/storage_statement.py` — PASS.
- `pytest` — targeted storage suite PASS: `7 passed`.
- `back_guard.py` — BLOCKED: файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py` — BLOCKED: файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Исправления сервисов расчёта/фиксации, биллинга, API, ролей и UI из находок 2–12 не входят в атом моделей и не выполнялись.
- Проверка `Warehouse.is_operational` и заполнение `InventoryMovement.warehouse_id` принадлежат внешнему фундаменту 07-A; в этой ветке соответствующего поля ещё нет, поэтому атом не создаёт дублирующую миграцию 07-A.
- Полная проверка миграции через guard невозможна: оба guard-скрипта отсутствуют в рабочей копии.

# Фича 6

# Backend-dev отчёт · 08-storage

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/warehouse.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0097_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`

## Гейты

- ruff: целевые файлы — PASS; полный `ruff check .` — FAIL на 80 существующих нарушениях вне этого атома.
- mypy: целевые backend-файлы — PASS.
- pytest: целевые тесты — PASS, 7 passed.
- back_guard.py: не запущен — файл отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — файл отсутствует в этой рабочей копии.

## Не реализовано

- API и фоновый контракт атома не расширялись: исправлен только расчётный слой и его модельная опора.
- Backfill старых движений в `warehouse_id` не выполнялся: это граница внешнего контракта 07-A; новая миграция добавляет поле nullable, не меняя исторические данные предположением.

## Находки

- В рабочей копии отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`; это записано как ограничение проверки, не как причина остановки работы.

# Фича 7

# DEV · 08-storage · атом 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

## Что реализовано

- Фиксация повторно использует уже опубликованный ledger для измерений и не создаёт дубли.
- Выбор тарифа детерминирован: индивидуальный тариф имеет приоритет над общим, затем берётся последняя версия, действующая на начало периода.
- Нулевой statement публикует одну нулевую ledger-строку.
- Печать ограничена измерениями конкретного tenant/seller/warehouse/month и возвращает ставку-снимок, сумму строки и единый service/source contract.

## Гейты

- ruff: PASS для изменённых `storage_statement_service.py` и `storage.py`.
- mypy: FAIL: внешний `app.models.billing` отсутствует в этой рабочей копии; также полный запуск выявляет существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- pytest: PASS, `5 passed` для `tests/test_storage_statement_service.py tests/test_storage_models.py`.
- back_guard.py: не запускался до полного backend-гейта; ожидает отсутствующий общий billing-контракт.
- check_migrations.py: не запускался, миграции атома не менялись.

## Не реализовано

- Внешние модели `BillingTariffVersion` и `BillingLedgerEntry` не добавлялись: это обязательная зависимость 09-A, а создание локальных storage-тарифов или второго ledger запрещено `ARCH-CROSS.md`.
- Тесты конкурентных API-запросов и финансового DTO не расширены: текущая ветка не содержит billing-моделей/схемы, на которой их можно выполнить.

## Находки

- В рабочем дереве отсутствует общий billing-контракт 09-A; это техническая зависимость, не секрет и не причина останавливать остальные проверки.

# Фича 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`

Экран S-11 теперь показывает прошлый календарный месяц по умолчанию, сводку селлеров и SKU, поиск по видимым строкам, роли администратора и сотрудника, нулевые значения, блокировку фиксации без габаритов, диалоги тарифа/обмера/истории и A4-предпросмотр с повторной печатью. Внутренняя таблица использует ставку снимка и отдельные поля источника, литро-дней и суммы.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх ранее существовавших нарушений в соседних файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Новых нарушений от S-11 guard не показал; базовую линию не обновлял.
- `npm run test:unit` — не запустился: в рабочей копии отсутствует команда `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Реальный API-путь, сохранение после перезагрузки и серверная фиксация начисления не реализованы в этом экранном атоме: backend-файлы не входят в разрешённый список S-11.
- `frontend/screens.registry.json` не изменён, потому что роль screen-dev разрешает править только файлы, перечисленные для карточки; обновление реестра требует отдельного согласования границ.
- Сквозной Playwright-путь с авторизацией и серверными данными не подтверждён: текущий `storage.spec.ts` содержит только локальные UI-сценарии, а unit-тесты не запускаются из-за отсутствующего `vitest`.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и персональные данные не открывались и не использовались.
