# MAP · Волна 9 · карта задевания

Собрано по девяти RAZBOR.md в `night/volna-9/cards/*/`. По каждой карточке
приведены: тип, задетые экраны из `frontend/screens.registry.json`, файлы
кода (бэк/фронт), таблицы БД, столкновения с соседями по волне и смежные
экраны, чьи кейсы придётся перекликать после изменений. В конце —
рекомендованный порядок и полосы, в которые карточки можно везти
параллельно, не наступая друг другу.

## Карта

### defect-01 · Мы не видим ответов Wildberries по маркировке
- **Тип:** домен (ТЗ пишется). Часть уже в ветке
  `fix/wb-meta-method-20260821` (коммиты `bd9384f`, `2453f44`), в
  `origin/etalon` не влито.
- **Экраны:** **S-03** (`FfFbsOrdersScreen`, `FfFbsSupplyWorkspace` —
  строка сдачи/статусы маркировки), **S-05** (`/app/ff/honest-sign`),
  **S-07** (`/app/ff/honest-sign/ledger` — событие сверки «WB не видит»),
  **S-08** (`/app/ff/honest-sign/pool/:poolId` — возврат КИЗ в пул),
  плюс мельком **S-13/S-30** (счётчик расхождений в шапке).
- **Файлы (backend):** `services/wildberries_fbs_client.py`
  (`MARKETPLACE_ORDERS_META_BULK_PATH`), `services/fbs_marking_service.py`
  (`_meta_details_from_wb`, `_sync_order_meta_from_wb`,
  `map_wb_decision_to_meta_status`, `_claim_pool_code_if_present`),
  `services/fbs_autopoll_service.py`
  (`sync_marking_statuses_for_assembling_supplies`,
  `MARKING_SYNC_BATCH_SIZE`), `services/fbs_workspace_service.py`
  (`_metadata_ready` — гасит опасный дефолт), новый сверочный код по
  пулу КИЗ; API-эндпоинт для отдачи пересобранного статуса на экран.
- **Файлы (frontend):** прямых правок фронта не требует, но меняет форму
  данных, которые видит `FfFbsSupplyWorkspace.tsx`/`FfFbsOrdersScreen.tsx`.
- **Модели/таблицы:** `fbs_orders` (`meta_details_json`,
  `metadata_last_checked_at`, `metadata_delivery_allowed` — снимаем
  дефолт `True`), `fbs_order_marking` (новый статус
  `META_STATUS_MISSING_AT_WB`), `marking_codes` (обратный путь
  `reserved → available` + запись в ленту).
- **Столкновения:** пересекается с **defect-02** (тот же
  `fbs_marking_service.py` — словарь `decision`, `_META_DELIVERY_OK`;
  defect-02 идёт поверх defect-01 и уже опирается на реальные
  `reason`/`decision`) и с **defect-05** (тот же
  `fbs_autopoll_service.py` — defect-05 разбивает автопулл на
  `_new` и `_full`; сверку маркировки defect-01 надо оставить
  внутри быстрого цикла).
- **Смежные экраны для перекликания:** S-03 (счётчик
  `metadata_ready` меняется — прогнать сдачу поставки), S-05 (лента
  Честного знака: новое событие), S-08 (пул: возврат КИЗ), S-07
  (лента событий пула).

### defect-02 · Экран говорит «сдавать можно», когда Wildberries отказывает
- **Тип:** фича (нужен видимый элемент — плашка вердикта +
  причина).
- **Экраны:** **S-03** (`FfFbsOrdersScreen` — все вкладки, не только
  «Просрочены»; `FfFbsSupplyWorkspace` — строка КИЗ на этапе
  упаковки).
- **Файлы (backend):** `services/wildberries_fbs_client.py` (расширить
  словарь `decision`: `required`, `optional` + логгер «новый decision»),
  `services/fbs_marking_service.py` (`map_wb_decision_to_meta_status`,
  `compute_delivery_allowed`, `derive_meta_status` — новые статусы
  `META_STATUS_ASSIGNED`, «необязательно»),
  `services/fbs_worklist_service.py` (`_build_metadata` — уже отдаёт
  `reason`, проверить формат).
- **Файлы (frontend):** `screens/v2/FfFbsOrdersScreen.tsx`
  (`metadataProblem` — плашка не только для `expired`;
  `MARKING_ACCEPTED_STATUSES` — убрать `assigned`, `pending`),
  `screens/v2/FfFbsSupplyWorkspace.tsx` (`isOrderMarkingReady` — то
  же; в строке КИЗ, стр. 1920–1993 — рендер вердикта),
  `components/fbs/FbsChips.tsx` (`FbsMarkingStatusChip`,
  `MarkingCheckStatusChip` — сегодня мёртвый код, довести и
  подключить).
- **Модели/таблицы:** `fbs_orders.meta_details_json`,
  `fbs_order_marking.reason` (уже добавлено в `bd9384f`).
- **Столкновения:** сильнейшая связка с **defect-01** — идёт строго
  после него; иначе плашка «Отклонено WB · причина» будет заполнена
  пустышками. С **defect-06** пересекается по `FfFbsSupplyWorkspace.tsx`
  (та же строка заказа), но правки в разных секциях (у defect-02 —
  вердикт над кодом, у defect-06 — сквозной номер и порядок).
- **Смежные экраны для перекликания:** S-03 сдача, все вкладки
  списка заказов (Новые/Активные/Просрочены/Отправлены); блокировка
  `marking_not_allowed` в `fbs_shipment_service._evaluate_delivery_checks`
  остаётся серверной точкой правды — проверить, что не расходится
  с UI-плашкой.

### defect-03 · Режим «без распределения» нельзя включить после создания коробов
- **Тип:** отложить. Полностью сделано на ветках
  `fix/no-distribution-20260821` (коммиты `9e2808e`, `cbdaad9`) и
  `integration/fbs-fixes-20260821` (merge `4e9b8d0`); на бой не
  выкачено.
- **Экраны:** **S-03** (`FfFbsSupplyWorkspace` — вкладка «Короба»,
  чекбокс режима, шапка счётчика; блокировка B-09 в
  `docs/blockers/S-03.md`).
- **Файлы (backend):** `services/fbs_packing_box_service.py`
  (`set_boxes_without_distribution`, `_ensure_without_distribution_flag`,
  `_boxes_without_distribution`), `api/fbs_supplies.py`
  (`POST /operations/fbs-supplies/{id}/boxes-without-distribution`,
  `FbsWorkspaceSupplyOut.boxes_without_distribution`),
  `models/fbs_supply.py` (поля `boxes_without_distribution_at`,
  `boxes_without_distribution_by_user_id`), миграция
  `alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`.
- **Файлы (frontend):** `screens/v2/FfFbsSupplyWorkspace.tsx`
  (условие `disabled` чекбокса, `hasNoDistributionBoxes`, шапка
  счётчика, Tooltip).
- **Модели/таблицы:** `fbs_supplies` (два новых поля).
- **Столкновения:** конфликтов по коду нет — правки локальные к
  коробам. Пересечение с **defect-04** (та же вкладка коробов
  workspace), но в разных функциях. При merge — убедиться, что не
  затирает изменения из полосы FBS-fixes (`f8c6cfa`, `af44363`),
  которые уже в интеграционной ветке.
- **Смежные экраны для перекликания:** только S-03 workspace, три
  сценария сдачи (уже прогнаны бэк-тестом
  `test_boxes_without_distribution_flag_survives_empty_box_list`).

### defect-04 · Склад мешает работать
- **Тип:** домен. Часть сделана на ветке
  `fix/warehouse-single-20260821` (`f8c6cfa`, WIP-родитель `206bd98`)
  и `integration/fbs-fixes-20260821`; на бой не выкачено. Костыль
  `af44363` в упаковке — на бою.
- **Экраны:** **S-03** (`FbsSupplyCreateDialog.tsx` + preflight
  notices), **S-04** (`FfFbsStockSyncScreen` — `isAutoFbsWarehouse`
  общий), **S-12** (`FfSuppliesShipmentsPage` — кросс-складская
  матчасть), **S-14** (`FfPackagingPage` — снятие костыля),
  **S-15** (ожидание маркировки — наследует остатки), **S-17**
  (`FfInboundQueuePage` — приёмка), **S-20** (`FfInboundQueuePage` —
  сортировка), **S-22** (`InboundScreen.tsx` — фильтрация
  подстановок «FBS WB …»), **S-24** (`OutboundScreen.tsx` — то же),
  **S-25** (перемещения — создание `transfer` при упаковке из
  чужой ячейки). Плюс мобильный ТСД (сканер) — экрана в реестре нет.
- **Файлы (backend):** `services/fbs_stock_availability_service.py`
  (`tenant_warehouse_ids`, `fbs_available_qty_by_product` по всем
  складам, `fbs_stock_by_warehouse_for_products`),
  `services/marketplace_unload_service.py`
  (`_outbound_reserved_by_product` суммирование по складам),
  `services/fbs_supply_validator_service.py`
  (`SupplyStockLocationNotice`, `_build_stock_location_notices`,
  `notices` в `SupplyPreflightResult`),
  `services/fbs_picking_service.py` (**новое**: снятие жёсткой
  привязки к `supply.warehouse_id`, кросс-складской подбор + путь
  `transfer`), `services/fbs_packaging_integration_service.py`
  (**новое**: удалить `_try_deduct_from_alternative_sorting_location`,
  строки 479–535 и 748–765 → заменить вызовом сервиса перемещения),
  `api/fbs_supplies.py` (Pydantic-схемы `FbsSupplyStockElsewhereOut`,
  `FbsSupplyStockLocationNoticeOut`, `notices` в
  `FbsSupplyPreflightOut`). Плюс сервис перемещений и печать метки
  склада — новые.
- **Файлы (frontend):** `utils/fbsWarehouse.ts` (новый —
  `isAutoFbsWarehouse`, `realWarehouses`, `primaryWarehouseId`),
  `App.tsx` и `apps/seller/SellerApp.tsx` (склад по умолчанию —
  первый настоящий), `screens/v2/InboundScreen.tsx`,
  `screens/v2/OutboundScreen.tsx`, `screens/v2/FfFbsStockSyncScreen.tsx`,
  `screens/v2/FbsSupplyCreateDialog.tsx` (плашка + fbsApi.ts),
  `hooks/useBarcodeScanner.ts` (распознавание штрих-кода склада),
  новый компактный переключатель «Склад → ячейка» на рабочих местах.
- **Модели/таблицы:** `warehouses` (флаг `is_auto_fbs_wms_warehouse`
  либо новый `is_auto_fbs`; штрих-код склада), `storage_locations`
  (обход по всем складам тенанта), `inventory_movements` (создание
  `transfer` в упаковке).
- **Столкновения:**
  - С **defect-05** — оба трогают `fbs_packaging_integration_service.py`
    (у defect-04 — снятие костыля, у defect-05 — offload через
    `asyncio.to_thread`). Правки в разных функциях, но одном файле.
  - С **feature-08** — оба трогают `InboundScreen.tsx` (у defect-04 —
    фильтр подстановок и переключатель, у feature-08 — команда
    «Измерить и зафиксировать» габариты); также обе полосы читают
    `InventoryBalance`/`StorageLocation`.
  - С **defect-03** — вкладка коробов workspace S-03 (разные функции).
  - Backfill/merge веток `fix/warehouse-single` +
    `fix/no-distribution` + `af44363` вместе — единый вход в бой.
- **Смежные экраны для перекликания:** S-03 сдача, S-14 упаковка
  (после снятия костыля), S-17/S-20 приёмка и сортировка (склад
  по умолчанию), S-22/S-24 (счёт складов), S-25 перемещения
  (появится transfer из упаковки), сканер на всех рабочих местах.

### defect-05 · Прод тормозит
- **Тип:** фича (инфраструктура). Не сделано.
- **Экраны:** **S-03** (`FfFbsOrdersScreen` — `NEW_ORDERS_PAGE_LIMIT`,
  polling 30 сек × 2 запроса, `Promise.all` двух `limit: 500`).
- **Файлы (backend):** `services/fbs_order_tape_print_service.py`
  (`print_fbs_order_tape` — обернуть pymupdf-работу через
  `asyncio.to_thread`; при необходимости — вынести в Celery),
  `services/marking_label_artifact_service.py` (весь `fitz` — тот же
  оффлоад), `services/fbs_autopoll_service.py`
  (`poll_fbs_orders_all_sellers` — разделить на `_new` и `_full`),
  `services/wb_marketplace_orders_service.py` (`sync_seller_orders` —
  режим «только новые» без `for _page in range(MAX_ORDERS_PAGES)`),
  `celery_app.py` (два beat-таска
  `wms.fbs_orders_autopoll_new`/`_full`),
  `core/settings.py` (`fbs_poll_new_interval_sec`,
  `fbs_poll_full_interval_sec`, `WEB_CONCURRENCY`),
  `Dockerfile.railway` (`--workers`), `api/fbs_supplies.py`
  (`POST /supplies/{id}/order-print-tape` — если пойдём в Celery,
  возвращает `job_id`), `tasks/background_jobs.py` (шаблон таска).
- **Файлы (frontend):** `screens/v2/FfFbsOrdersScreen.tsx`
  (пагинация вместо `limit: 500`, интервал polling).
- **Модели/таблицы:** прямых изменений схемы нет; косвенно — снижение
  давления на `fbs_orders` и WB-таблицы за счёт разделения циклов.
- **Столкновения:**
  - С **defect-01** — тот же `fbs_autopoll_service.py`; defect-01
    работает внутри `sync_marking_statuses_for_assembling_supplies`
    (её ставим в быстрый цикл), defect-05 меняет верхний
    `poll_fbs_orders_all_sellers`. Разные функции, но общий модуль.
  - С **defect-06** — тот же `fbs_order_tape_print_service.py`;
    defect-05 оборачивает pymupdf в поток/Celery, defect-06 меняет
    порядок и добавляет нумерацию. Правки в соседних участках, риск
    мержа умеренный.
- **Смежные экраны для перекликания:** S-03 (после смены polling
  и пагинации — прогнать все вкладки), автопулл невидим, но его
  влияние на p95 GET-ов проверять на S-03 во время цикла.

### defect-06 · Порядок в листе подбора не совпадает с порядком ленты
- **Тип:** фича.
- **Экраны:** **S-03** (`FfFbsSupplyWorkspace` — кнопки «Печать листа
  подбора» и «Печать всего», `FbsPrintPreviewDialog`, `FfFbsPickList`).
- **Файлы (backend):** `services/fbs_supply_service.py`
  (`get_picking_list` — возвращает сквозной `sequence_no`,
  сортировка по товару → `wb_order_id`),
  `services/fbs_order_tape_print_service.py`
  (`_orders_in_requested_order` — печатать по той же
  последовательности; секции с крупным номером на наклейке).
- **Файлы (frontend):** `screens/v2/FfFbsPickList.tsx` (колонка
  «№», диапазон наклеек), `screens/v2/FfFbsSupplyWorkspace.tsx`
  (`pickingRows`, `packingOrders` — единый порядок; отобразить
  `sequence_no`), `screens/v2/fbsUx.ts`
  (`buildFbsPickingListPrintHtml` — колонка/диапазон),
  `components/MarkingPrintDialog.tsx` (секции наклеек — номер над
  QR), `screens/v2/FbsPrintPreviewDialog.tsx` (то же).
- **Модели/таблицы:** прямых изменений схемы нет; в API
  `workspace.orders[*].sequence_no` — новое поле.
- **Столкновения:** с **defect-05** — тот же
  `fbs_order_tape_print_service.py`. Порядок правки: сначала
  defect-05 (offload), потом defect-06 (сортировка + номер). С
  **defect-02** — тот же `FfFbsSupplyWorkspace.tsx`, но разные
  секции строки заказа (вердикт vs номер).
- **Смежные экраны для перекликания:** S-03 workspace во всех
  сценариях печати (лист подбора, лента, перепечатка одного
  заказа).

### feature-07 · Раздел отчётности для селлера и ФФ
- **Тип:** домен. Раздела в постановочном смысле нет;
  существующий узкий отчёт ФФ живёт в `FfReportsPage.tsx`.
- **Экраны:** новый селлерский раздел «Отчёты» — **экран будет
  создан**; расширенный ФФ-раздел «Отчёты» с вкладками —
  **экран будет собран из существующего** `FfReportsPage`
  (`ff/reports`, в реестре не заведён; получит новый `S-id`). Ни
  «reports», ни «analytics» в `frontend/screens.registry.json` нет.
- **Файлы (backend):** `services/inventory_movement_report_service.py`
  (существующая агрегация — станет одним из источников),
  `api/inventory_movements.py` (`GET /operations/inventory-movements/summary`),
  новые сервисы и роуты `services/reports_*` /
  `api/reports_*` (агрегации по продавцу, складу, маркетплейсу,
  товару, операции; режимы «за период», «накопительно»,
  «сравнение»),
  `services/staff_packaging_billing_service.py` (существующий —
  войдёт в разрез «загрузка людей»).
- **Файлы (frontend):** `screens/ff/FfReportsPage.tsx` (станет
  вкладкой «Движения»), новые экраны отчётов ФФ (несколько
  вкладок) и селлера (пункт меню «Отчёты» в
  `apps/seller/SellerApp.tsx`, `apps/seller/SellerLayout.tsx`).
- **Модели/таблицы:** `inventory_movements`, `inventory_balances`,
  `packaging_tasks` (сдельщина), позже — таблицы feature-08
  (`storage_measurement_run`, `storage_charge`) и feature-09
  (`billing_work_event`, `invoice`).
- **Столкновения:**
  - С **feature-08** — финансовые/объёмные разрезы отчётов опираются
    на модели хранения; порядок: сначала feature-08, потом feature-07.
  - С **feature-09** — то же для операционных начислений; порядок:
    сначала feature-09, потом feature-07. Пока модуля счетов и
    хранения нет — feature-07 закрывает нефинансовые разрезы (штуки,
    документы, работа людей).
  - С **defect-05** — тяжёлые агрегаты не должны идти в поток
    запросов (единая политика для нового раздела: `to_thread` или
    Celery).
- **Смежные экраны для перекликания:** `ff/reports` (существующий),
  кабинет селлера (после появления пункта меню), любой экран, где
  сегодня видны счётчики — сверка «сходится ли с новым отчётом».

### feature-08 · Хранение: считать, менять габариты и брать деньги
- **Тип:** домен. Новый модуль. Прошлая ночь r04 останавливалась
  ровно на этой карточке (`docs/process/HANDOFF-PIPELINE-R04-FAILURE-RU.md`).
- **Экраны:** **S-01** (`ProductsScreen` — колонка «Габариты», команда
  «Изменить», метка источника, доступ к истории), **S-16**
  (`FfProductsCatalogScreen` — то же + массовые операции по
  недостающим), **S-22** (`InboundScreen` — команда «Измерить и
  зафиксировать» на приёмке), **S-31** (`SellerProductsStockScreen` —
  просмотр габаритов своих SKU + запрос замера у ФФ), новые: «Тарифы
  хранения» (ФФ, FF-админ), «Хранение / литр-дни / сводная накладная»
  (ФФ), «Мои накладные за хранение» (селлер) — **экраны будут
  созданы**, в реестре нет.
- **Файлы (backend):** `models/product.py` (`length_mm`, `width_mm`,
  `height_mm`, `weight_g`, `volume_liters` — уже есть),
  `services/catalog_service.py` (`volume_liters_from_mm` — есть),
  `services/wildberries_product_import_service.py`
  (`_parse_dimensions_mm`, `update` — уходит эвристика «не стаб»,
  приходит явный `source`), `api/products.py` (`POST /products`,
  `PATCH /products/{id}/dimensions` — уже есть; новый лог/история),
  новые модели `storage_tariff`, `storage_measurement_run`,
  `storage_charge`, `storage_invoice`, `product_dimension_history`,
  новые сервисы `services/storage_*` (тариф, измерение литр-дней,
  накладная), новые роуты `api/storage_*`, ежесуточная джоба в
  `backend/app/tasks/` (`storage_measurement_run` на границе суток
  МСК).
- **Файлы (frontend):** `screens/v2/ProductsScreen.tsx` (колонка,
  команда), `screens/v2/FfProductsCatalogScreen.tsx`, новые экраны
  для тарифов и накладных, `apps/seller/SellerApp.tsx` (меню «Мои
  накладные»), `screens/v2/InboundScreen.tsx` (кнопка «Измерить»).
- **Модели/таблицы:** `products` (уже с габаритами; добавить связь с
  историей), `inventory_balances` (снятие остатка в литрах на конец
  суток), `inventory_movements` (реконструкция при пропущенных
  сутках); новые: `storage_tariff`, `storage_measurement_run`,
  `storage_charge`, `storage_invoice`, `product_dimension_history`.
- **Столкновения:**
  - С **defect-04** — общий `InboundScreen.tsx` и модель складов
    (`Warehouse`, `StorageLocation`, `InventoryBalance` по всем
    складам тенанта). Идти строго после defect-04, иначе счёт
    литр-дней задвоится «FBS WB» подстановкой.
  - С **feature-09** — обе меняют `Seller` (feature-09 — реквизиты
    ИНН/КПП; feature-08 — не трогает `Seller`, но накладная требует
    реквизитов из feature-09). Порядок: реквизиты плательщика
    приходят из feature-09.
  - С **feature-07** — feature-08 отдаёт данные для разреза
    «хранение» отчёта; feature-07 после.
- **Смежные экраны для перекликания:** S-01, S-16, S-22 (после
  ввода источника и истории — не сломать существующий PATCH
  габаритов), кабинет селлера (появление меню накладных).

### feature-09 · Счета и цифровой учёт работы
- **Тип:** домен. Модуля нет.
- **Экраны:** новые — «Тарифы» (ФФ), «Работы за период» (ФФ),
  «Счета» (ФФ, кнопка «Выставить счёт», печатная форма A4), «Форма
  реквизитов» в карточке продавца — **экраны будут созданы**, в
  реестре нет.
- **Файлы (backend):** `models/seller.py` (новые поля: юр.название,
  ИНН, КПП, адрес плательщика; сегодня — только `id`, `tenant_id`,
  `name`, `created_at`), `models/user.py` (`packaging_rate_kopecks` —
  уже есть, войдёт в разрез «кто сколько собрал»),
  `services/staff_packaging_billing_service.py` (существующий —
  источник разбивки по сотрудникам),
  `services/inbound_intake_service.py`
  (`STATUS_DONE`, `primary_accepted_at` — точка фиксации факта работы
  для приёмки), `services/marketplace_unload_service.py`
  (`STATUS_SHIPPED` — точка для отгрузки), новые модели
  `billing_tariff`, `billing_work_event`, `invoice`, `invoice_line`,
  новые сервисы `services/billing_work_*`,
  `services/invoice_service.py`, новые роуты `api/billing_*`,
  `api/invoices_*`.
- **Файлы (frontend):** новые экраны (см. выше),
  `screens/ff/FfSettingsScreen.tsx` (вкладка «Сотрудники» останется
  как есть — не путать с новым разделом счетов).
- **Модели/таблицы:** `sellers` (новые поля ИНН/КПП/адрес),
  `packaging_tasks` (существует), `inbound_intakes` +
  `marketplace_unloads` (терминальные статусы — источник событий);
  новые: `billing_tariff`, `billing_work_event`, `invoice`,
  `invoice_line`.
- **Столкновения:**
  - С **feature-08** — обе меняют/читают `Seller`. feature-09
    добавляет реквизиты плательщика, которые нужны и для накладной
    хранения из feature-08; порядок: feature-09 раньше или в паре с
    feature-08 (реквизиты — общая часть).
  - С **feature-07** — feature-09 отдаёт данные о начислениях и
    счетах для отчёта; feature-07 после.
  - С **defect-05** — новые агрегаты по большому периоду должны идти
    в фон/Celery по единой политике.
- **Смежные экраны для перекликания:** карточка продавца
  (появление ИНН — все места, где показывается селлер, должны
  спокойно жить с новыми полями), приёмка (S-17, S-22) и отгрузка
  (S-12, S-24) — на терминальных статусах теперь пишется строка
  учёта работы, не сломать их сценарии.

## Порядок

Из карты видно четыре независимые полосы, которые можно везти
параллельно. Внутри полосы порядок обязателен; между полосами —
только в местах, отмеченных явно.

**Полоса A · FBS-маркировка / чтение и показ.** Одна и та же связка
модулей (`fbs_marking_service`, `wildberries_fbs_client`,
`FfFbsSupplyWorkspace.tsx`), поэтому идёт последовательно.

1. **defect-01** — сначала. Влить `fix/wb-meta-method-20260821` в
   `etalon`, поверх дописать сверку пула КИЗ и убрать опасный
   дефолт `metadata_delivery_allowed=True`. Без этого defect-02
   рисует плашки поверх пустышек.
2. **defect-02** — сразу после. Плашка вердикта в строке заказа,
   расширение словаря `decision` (`required`, `optional`), снятие
   оптимизма клиента, оживление `FbsMarkingStatusChip` /
   `MarkingCheckStatusChip`.

**Полоса B · склад и топология.** Тяжёлый домен с широким задеванием
экранов; наперёд не тянуть, но и не откладывать — костыль в упаковке
живёт на бою.

3. **defect-03** — параллельно, независимо. Одноходовое действие:
   влить `fix/no-distribution-20260821` в `etalon`, прогнать три
   сценария в браузере. Опционально — backfill
   `boxes_without_distribution_at` для старых поставок.
4. **defect-04** — большая работа. Влить
   `fix/warehouse-single-20260821`, доделать: переключатель «Склад
   → ячейка» на рабочих местах, распознавание штрих-кода склада на
   сканере, снятие костыля
   `_try_deduct_from_alternative_sorting_location` с заменой на
   настоящий `transfer`, кросс-складской подбор в
   `fbs_picking_service`, жёсткая блокировка «нигде нет». Затрагивает
   S-03, S-04, S-12, S-14, S-15, S-17, S-20, S-22, S-24, S-25 —
   кейсы этих экранов придётся перекликать полностью.

**Полоса C · производительность и печать.** Файл
`fbs_order_tape_print_service.py` общий для двух карточек, поэтому
внутри полосы порядок обязателен.

5. **defect-05** — сначала. Оффлоад pymupdf через
   `asyncio.to_thread`, разделение автопулла на `_new` и `_full`,
   `--workers 2` в `Dockerfile.railway`, пагинация на S-03. Часть
   правок в `fbs_autopoll_service.py` пересекается с полосой A
   (defect-01 живёт внутри быстрого цикла) — синхронизировать при
   переносе кода.
6. **defect-06** — после defect-05. Единый порядок и сквозная
   нумерация: сервер отдаёт `sequence_no`, лента печатает номер на
   секции, лист подбора получает диапазон номеров. Правит те же
   файлы workspace, что defect-02 — секции разные.

**Полоса D · новые доменные модули.** Отдельная от FBS, но
внутренние зависимости строгие.

7. **feature-09** — раньше, чем feature-08 и feature-07 (даёт
   реквизиты плательщика на `Seller` и модели учёта работы).
   Параллельно с полосой B возможно, но `Seller` — общая точка,
   поэтому лучше пропустить defect-04 вперёд, чтобы не путать
   миграции.
8. **feature-08** — после feature-09 (реквизиты плательщика для
   накладной), после defect-04 (единая складская модель для
   расчёта литр-дней по всем складам тенанта). Хранит габариты,
   тариф, ежесуточную джобу и печатную накладную.
9. **feature-07** — последней. Отчёты по определению живут поверх
   готовых данных: движения (существует), сдельщина (существует),
   начисления feature-09, хранение feature-08. Селлерский раздел
   создаётся в кабинете селлера; ФФ-раздел собирается вкладками
   поверх существующего `FfReportsPage`. Полагаться на defect-05
   в части фона для тяжёлых агрегатов.

**Общие перекликания.** Экран S-03 задет шестью карточками —
Playwright-набор по FBS-сценариям (сдача, короба, вердикт, печать
ленты, список поставок) прогонять после каждой полосы, не только в
конце. Приёмка (S-17, S-22) задета defect-04 и feature-08 —
проверять сдвоенно. Кабинет селлера получает изменения от
defect-04 (склад по умолчанию), feature-07 (пункт меню «Отчёты»),
feature-08 (пункт меню «Мои накладные») — не сломать существующий
`SellerLayout.tsx`.

Строка подтверждения: карта построена по девяти RAZBOR.md волны 9,
файл лежит в `night/volna-9/MAP.md`, порядок полос
A → B → C → D независим внутри и связан только там, где отмечено
явно.
