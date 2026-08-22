ФИЧ: 8

## Фичи

### 1. Расширить подпись PrintAction для расчёта хранения

Оператор видит в строке зафиксированного расчёта хранения привычное действие «Печать накладной»; публичный интерфейс компонента не меняется, а новая подпись остаётся внутренним правилом `PrintAction`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx`

Зависимости: нет. Это единственная необходимая работа UI-kit из раздела «Нехватка ui-kit» контракта.

Проверка: рендер `PrintAction` с `what="накладную"` в вариантах `row` и `panel` показывает «Печать накладной», а существующие варианты печати сохраняют свои подписи и disabled-подсказки.

### 2. Сохранить версии источника и габаритов товара

Система хранит неизменяемую историю наблюдений WB и ручных обмеров вместе с действующей версией, автором, временем, объёмом и основанием для объёма тары; текущие поля товара остаются быстрым снимком действующего значения.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/product_dimension_event.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`

Зависимости: нет.

Проверка: миграция создаёт поля действующего источника на `products` и журнал событий; в тестовой БД можно записать ручную и WB-версии одного товара, при этом действующей остаётся ровно одна версия с полным аудиторским контекстом.

### 3. Не давать импорту WB затереть ручной обмер

При ручной правке оператор создаёт новую действующую версию `manual` либо `container_override`, а импорт WB сохраняет изменившееся наблюдение, но не меняет ручной действующий объём. Повтор одинакового наблюдения не создаёт дубль; возврат к последней полной версии WB создаёт новую действующую версию.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/wildberries_product_import_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_product_dimension_history.py`

Зависимости: 2.

Проверка: тесты покрывают полный ручной обмер, объём тары без и с комментарием, повтор WB-импорта и WB-обновление после ручного обмера; после возврата к WB действующим становится последнее полное WB-наблюдение, а закрытые периоды не пересчитываются этим действием.

### 4. Открыть API обмера и истории габаритов товара

Сотрудник с правом `inventory` может через API сохранить допустимый обмер и прочитать историю товара, а только `FULFILLMENT_ADMIN` может вернуть последнюю WB-версию. Недопустимые габариты, тара без основания и доступ не своей организации получают понятную ошибку без частичной записи.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/products.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_products_api.py`

Зависимости: 3.

Проверка: API-тесты подтверждают чтение хронологии, сохранение каждого из двух способов обмера, запрет неполных/нулевых значений и разграничение прав для возврата WB-версии.

### 5. Завести неизменяемые измерения и документы хранения

Система получает таблицы `StorageMeasurement` и `StorageStatement`: измерение связано с tenant, селлером, операционным складом, SKU, версией объёма и диапазоном движений; документ группирует один месяц и один склад. Денежных таблиц, локальных тарифов и отдельного счёта эта фича не создаёт.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_measurement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/storage_statement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0096_storage_measurements_and_statements.py`

Зависимости: внешний фундамент 07-A из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/ARCH-CROSS.md`; фичи 2–3.

Проверка: миграция запрещает дубли документа для одного tenant/селлера/операционного склада/месяца и сохраняет ссылку измерения только на зафиксированный `InventoryMovement.warehouse_id`; служебный склад не проходит в состав документа.

### 6. Сформировать и показать черновик хранения за месяц

По запросу оператора фоновая задача строит или безопасно пересчитывает только открытые черновики выбранного календарного месяца МСК. Она интегрирует положительный физический остаток по времени, применяет версию габаритов, показывает SKU без объёма как проблему, оставляет последний успешный черновик при ошибке и не создаёт денег.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/tasks/background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`

Зависимости: 5 и внешний контракт 07-A.

Проверка: сервисные и API-тесты проверяют формулу с долей суток, прошлый месяц по умолчанию, запрет будущего месяца, нулевой месяц, отсутствие габаритов, отрицательный восстановленный остаток, идемпотентный повтор задания и исключение неоперационных складов.

### 7. Зафиксировать документ и опубликовать единственную ledger-строку

Администратор фиксирует только черновик без проблем. В одной транзакции неизменяемый `StorageStatement` публикует строки общего биллинга `BillingLedgerEntry` с `service_code='storage_liter_day'`, `unit='liter_day'` и `source_type='storage_measurement'`, в том числе для нулевого документа; затем API отдаёт A4-представление только зафиксированного расчёта.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py`

Зависимости: 6 и внешний 09-A — модели `BillingTariffVersion` / `BillingLedgerEntry` и единица `liter_day` должны уже существовать. Это обязательная граница `ARCH-CROSS.md`: свои `storage_tariffs`, `storage_charges` либо второй путь счёта не допускаются.

Проверка: два одновременных запроса создают один statement и один набор ledger-строк; проблемный черновик не фиксируется, зафиксированный не меняется при новом обмере, а повторная печать возвращает тот же состав SKU, ставку-снимок, итог и дату фиксации.

### 8. Заменить заглушку S-11 рабочим экраном «Хранение»

Оператор на `/app/ff/inventory` видит только операционные склады, прошлый месяц, сводку по селлерам и раскрытие одного селлера до SKU. Экран даёт сформировать черновик, внести обмер и открыть историю; администратор также меняет тариф, фиксирует расчёт и печатает его. Состояния загрузки, пустого тарифа, ошибки, проблемных габаритов и нулевого месяца следуют контракту без новых страниц или изменения соседней навигации.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`

Зависимости: 1, 4, 6 и 7.

Проверка: Playwright проходит UI-путь администратора «открыть прошлый месяц → сформировать → раскрыть селлера → внести обмер → зафиксировать → увидеть A4-предпросмотр», а отдельные сценарии подтверждают ограничение сотрудника без кнопок тарифа/фиксации, отсутствие габаритов с блокировкой, нулевой месяц, поиск только по видимым строкам и повторную печать. Тесты помечаются `S-11-TC-001`—`S-11-TC-020` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/CASES.md`.

## Порядок

Сначала выполнить 1 и 2 параллельно: они не зависят друг от друга. Затем последовательно 3 → 4, чтобы пользовательский API опирался на версионирование, и 5 → 6, чтобы расчёт имел неизменяемое хранилище. Фича 5 начинается только после готовности 07-A, поскольку ей нужен фактический склад из `InventoryMovement.warehouse_id`.

После 6 выполнить 7; она дополнительно ждёт 09-A и использует только его общий тарифно-биллинговый контракт. В завершение выполнить 8: экран опирается на готовый UI-kit, API габаритов, черновик и фиксацию. Независимая пара 1 и 2 может идти параллельно с внешними 07-A и 09-A, но не заменяет их.

## Что осталось за бортом

- Паллето-дни, бесплатные периоды, минимальная сумма, сезонные коэффициенты и категории товара не входят в контракт первой версии.
- Бухгалтерский акт, счёт-фактура, НДС, ЭДО, оплата и интеграция с 1С остаются задачей общего биллинга, а не хранения.
- Онлайн-кабинет селлера, посуточная детализация, запись ручных габаритов в Wildberries и прогноз хранения не создаются этой карточкой.
- Фича 7 блокируется только отсутствием внешнего 09-A; вместо собственной финансовой схемы 08 обязана ждать общий контракт.
