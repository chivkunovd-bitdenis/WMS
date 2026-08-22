ФИЧ: 7

## Фичи

### 1. Разделить импорт новых заказов и часовую сверку WB

Операторские заказы продолжают появляться без изменения их статусов: частый контур читает только новые задания, а полный обход остаётся отдельной операцией, которую можно безопасно повторить после сбоя. У каждого контура есть самостоятельная проверка идемпотентного upsert, ошибки страницы и отсутствия удаления локальных данных при незавершённой сверке.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`

Зависимости: нет.

Проверка: unit-тест доказывает, что `new` не вызывает постраничный полный список, а `reconcile` проходит курсор до конца и при ошибке не помечает неполный проход успешным.

### 2. Запускать WB-контуры по отдельному расписанию без общего лока продавца

Оператор не ждёт сетевую синхронизацию: Beat ставит независимые задания `new` раз в 180 секунд и `reconcile` раз в 60 минут по каждому продавцу; повтор того же вида для того же продавца не запускается одновременно, но ручные операции не удерживаются общим `wb_seller_lock` во время чтения.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_autopoll_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`

Зависимости: 1.

Проверка: тесты вызывают оба задания отдельно, подтверждают период 180 секунд/60 минут и single-flight по `(seller_id, sync_kind)`; запуск одного вида не препятствует запуску другого и не берёт seller-wide lock на время HTTP-чтения.

### 3. Зафиксировать серверный контракт фоновой ленты ЧЗ

До нажатия печати ничего не меняется, а после запроса у WMS появляется одно переиспользуемое задание `marking_label_tape`: оно хранит только идентификатор готового артефакта, допускает повтор того же активного запроса без дубля и имеет срок доступности 12 часов для PDF-ленты `label_tape`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/fbs_print_asset.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_print_assets.py`

Зависимости: нет.

Проверка: тесты подтверждают создание одного job по ключу идемпотентности, состояния `pending/running/done/failed`, ссылку на `asset_id` вместо PDF в `result_json` и отказ в выдаче артефакта после 12 часов.

### 4. Перевести API ленты ЧЗ в очередь печати

После нажатия оператором сервер сразу возвращает `202` и идентификатор задания; один Celery worker очереди `print` последовательно собирает до 500 существующих этикеток, сохраняет готовый PDF как `label_tape` и публикует безопасный результат или ошибку. Существующая ручка получения статуса/артефакта используется для опроса, без передачи PDF через API-ответ задания.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_code_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_label_artifact_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_marking_codes.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_marking_pdf_label_artifact.py`

Зависимости: 3.

Проверка: API-тест получает `202`, повторный запрос возвращает тот же активный job, а задача worker создаёт ровно один asset; при ошибке job становится `failed`, при истечении срока старый asset не выдаётся. Отдельный нагрузочный прогон на 155 и 500 кодов одновременно с `/health` фиксирует время job и отсутствие блокировки API.

### 5. Добавить в ui-kit строку «Показать ещё» для таблиц

Внизу существующей таблицы появляется переиспользуемый `TableLoadMore`: он скрыт без следующего курсора, показывает одну кнопку «Показать ещё», на время запроса — «Загружаем…» и спиннер без повторного клика, а после ошибки сохраняет доступное действие и выводит `ErrorNotice` над ним.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`

Зависимости: нет.

Проверка: showcase вручную демонстрирует скрытое, доступное, загружаемое и ошибочное состояния; действие не вызывается повторно, пока идёт загрузка.

### 6. Пагинировать вкладку «Новые» S-03 без потери подбора

Оператор открывает `/app/ff/fbs` и получает 50 новых заказов в прежней таблице из четырёх информационных колонок. Следующая порция добавляется по `TableLoadMore`, выбор и позиция не сбрасываются; «Выбрать все» сохраняет семантику всех страниц. Видимый 30-секундный тик обновляет только первую порцию без скелета и без очистки уже догруженных строк, скрытая вкладка запросов не делает. Остальные рабочие вкладки получают максимум 100 строк без искусственной пагинации.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Зависимости: 5.

Проверка: Playwright-путь `S-03-TC-001`–`S-03-TC-007` и `S-03-TC-010`–`S-03-TC-012` проверяет скелет первой загрузки, пустой список, 50 строк, догрузку без дублей/потери выбранного, понятный повтор после ошибки и отсутствие опроса при скрытой вкладке.

### 7. Показать фоновую подготовку ленты в существующем диалоге

После запуска ленты существующий `MarkingPrintDialog` остаётся открытым и показывает «Готовим ленту…» с `StatusChip`; повторная печать блокируется. После `done` оператор сам выбирает «Открыть для печати», а после ошибки или истечения 12 часов видит понятные «Повторить» и «Закрыть» без кода задания или технических деталей. Повторное открытие тех же данных показывает состояние уже созданного job.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-separate-marking-print.spec.ts`

Зависимости: 4.

Проверка: Playwright-путь `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014` и `S-03-TC-015` проходит состояние ожидания, явное открытие готового PDF, безопасный повтор после ошибки/истечения и повторное открытие существующего активного задания.

## Порядок

Сначала независимо и параллельно выполняются 1, 3 и 5: они создают изолированные серверные и UI-фундаменты. Затем 2 зависит от 1, 4 — от 3, 6 — от 5, а 7 — от 4. Так фронтендовые пункты никогда не смешиваются с backend-пунктами в одном назначении, а каждая следующая задача получает уже проверенный контракт.

Обязательный порядок волны из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/ARCH-CROSS.md`: карточка 05 выполняется после 02 и до 06; backend-пункт 4 выполняется также после интеграции семантики маркировки карточки 01, не меняя её `metaDetails` и не освобождая КИЗ автоматически.

## Что осталось за бортом

- Выделение отдельной ноды минимум с 8 ГБ RAM, настройка production-лимитов контейнеров и стендовый замер до/после не имеют безопасного локального файла в этой карточке; боевой прод `194.87.96.144` контрактом запрещён к изменению.
- Перенос `/fbs/supplies/{supply_id}/order-print-tape` в очередь не входит в карточку: для него нет подтверждённого нагрузочного замера.
- `NotificationBell`, 15-секундный polling рабочего места поставки, WebSocket/SSE, Redis-кэш списков и пользовательские настройки частоты не входят в контракт.
- Секреты, ключи, токены, `.env`, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
