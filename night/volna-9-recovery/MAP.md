# MAP · Волна 9 · Карта задевания

Собрана по девяти `RAZBOR.md` из `night/volna-9/cards/`. Задача карты — до старта
работы показать, где карточки лезут в одни и те же экраны, файлы и таблицы, в каком
порядке их надо резать, чтобы не переписывать чужой diff, и какие смежные экраны
придётся перекликать, даже если сама карточка их напрямую не правит.

Работа идёт на `origin/etalon`; три задачи уже частично написаны, но лежат в
собственных ветках и на бой не уехали — их вливание в `etalon` идёт первым ходом
любой ночи, иначе свежий код сядет на конфликты по горячим файлам.

## Карта

### 01 · wb-marking — Мы не видим ответов Wildberries по маркировке

- **Тип:** домен, только бэк, UI-строки не трогаем.
- **Экраны:** `S-03` (`FfFbsOrdersScreen`, `FfFbsSupplyWorkspace`) — не правит, но
  начинает наполнять поля, из которых он рисует. `S-14` (`FbsPackagingPage`) и
  `S-15` (`PackagingPendingMarkingWorklist`) — то же: данные меняются, UI нет.
- **Файлы бэка:** `backend/app/services/wildberries_fbs_client.py`,
  `backend/app/services/fbs_marking_service.py::_sync_order_meta_from_wb`,
  `backend/app/services/fbs_autopoll_service.py::sync_marking_statuses_for_assembling_supplies`,
  `backend/app/tasks/background_jobs.py`. Мёртвый одиночный
  `GET /api/v3/orders/{id}/meta` из `wildberries_client.py:953` удаляется.
- **Таблицы:** `fbs_order_marking` (`check_status`, `meta_status`, `reason`,
  `meta_details_json`, `marking_code_id` — ссылку теперь можно снимать при
  «orphaned»); `fbs_orders` (`metadata_delivery_allowed`,
  `metadata_last_checked_at`); `marking_codes` (возврат в `available` при потере
  у WB); `marking_code_events` (новое событие `wb_orphaned`).
- **Уже написано:** ветка `fix/wb-meta-method-20260821`, два коммита
  (`bd9384f` — реальные `metaDetails`, ретрай на 429; `2453f44` — батч автополла
  до 100). В `origin/etalon` не влита. Правило «WB кода не знает» (25 заданий,
  возврат кода в пул, событие в журнал) в ветке ещё не сделано — это дописать.
- **Задевает соседей:** 02 (заполняет поля, из которых 02 рисует чипы вердикта),
  05 (пачки снимают часть нагрузки автополлера, но частоту тика режет 05).

### 02 · verdikt-screen — Экран говорит «сдавать можно», когда WB отказывает

- **Тип:** фича, бэк + фронт.
- **Экраны:** `S-03` — обе половины (`FfFbsOrdersScreen`, `FfFbsSupplyWorkspace`).
  Новых экранов нет.
- **Файлы бэка:** `fbs_marking_service.py` — `map_wb_decision_to_meta_status`
  (три пропущенных `required/optional/notRequired`), `derive_meta_status`,
  `compute_delivery_allowed` (гейт по `reason`), `_meta_details_from_wb`,
  `_apply_meta_detail_to_marking`; `fbs_shipment_service.py::_build_delivery_checks`.
- **Файлы фронта:** `FfFbsOrdersScreen.tsx::metadataProblem`,
  `FfFbsSupplyWorkspace.tsx::isOrderMarkingReady` (правится
  `MARKING_ACCEPTED_STATUSES` — убираем `pending`/`assigned` из «готово»),
  `frontend/src/screens/v2/fbsApi.ts` (тип `state.status`), новый словарь
  `frontend/src/utils/metaStatus.ts` рядом с `markingStatus.ts`.
- **Таблицы:** те же, что и у 01, только читаем — новых колонок не заводим.
- **Задевает соседей:** 01 (жёсткая зависимость по данным), 04 (шапка строки
  заказа делит место с чипом склада), 05 (частота автополла определяет, насколько
  «свежий» вердикт видит оператор), 06 (чип вердикта живёт в той же строке, что и
  колонка номера листа).

### 03 · no-distribution-mode — Режим «без распределения» не переключается после коробов

- **Тип:** «отложить» — задача уже написана и покрыта тестом, осталось влить и
  накатить миграцию.
- **Экраны:** `S-03`, вкладка «Короба» в `FfFbsSupplyWorkspace`. Новых нет.
- **Файлы бэка:** `backend/app/models/fbs_supply.py` (две новые колонки),
  `backend/app/services/fbs_packing_box_service.py` (переключатель
  `set_boxes_without_distribution` + охрана «в короба ничего не разложено»),
  `backend/app/services/fbs_workspace_service.py`,
  `backend/app/api/fbs_supplies.py` (новый роут
  `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution`),
  миграция `backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`.
- **Файлы фронта:** `FfFbsSupplyWorkspace.tsx` (условие чекбокса переехало с
  `boxes.length > 0` на `boxesAlreadyDistributed`; источник истины для шапки —
  флаг поставки), `fbsApi.ts` (`setFbsBoxesWithoutDistribution`),
  `frontend/openapi/fbs-operations.openapi.json`.
- **Таблицы:** `fbs_supplies` — `boxes_without_distribution_at`,
  `boxes_without_distribution_by_user_id`; косвенно `fbs_packing_boxes` /
  `fbs_packing_box_items` через новую охрану.
- **Уже написано:** ветка `fix/no-distribution-20260821`, коммиты `9e2808e`
  (wip) и `cbdaad9` (доделка — источник истины на поле поставки, а не скан
  коробов). Локальная, в `origin` не запушена; перед пушем проверить, что
  чужого содержимого в удалённой ветке того же имени не появилось.
- **Задевает соседей:** 06 (правит порядок строк в том же
  `fbs_workspace_service.py` и в `FfFbsSupplyWorkspace.tsx` — сливать 03 до 06),
  04 (шапка вкладки «Короба» и переключатель складов делят одну зону экрана).
- **Хвост:** после вливания текст блокировки `B-09` в `docs/blockers/S-03.md`
  переписать под новую формулировку («пока `FbsPackingBoxItem` пусто по всей
  поставке»).

### 04 · warehouse-switch — Склад мешает работать

- **Тип:** домен, широкий (модель + ручки + экраны + сканер).
- **Экраны:** `S-03` (переключатель + preflight поставки + подбор), `S-14`
  (`FbsPackagingPage` — сносим костыль
  `_try_deduct_from_alternative_sorting_location`), `S-22` (`InboundScreen`),
  `S-24` (`OutboundScreen`), `S-25` (`TransfersScreen` — сюда пишутся настоящие
  переносы X→Y при кросс-складском подборе), `S-01` (`ProductsScreen` /
  `CatalogSection` — выбор склада), `S-04` (`FfFbsStockSyncScreen`),
  `S-26`/`S-28`/`S-29` (портал селлера — `SellerDocumentsScreen`,
  `SellerInboundDraftScreen`).
- **Новый экран:** общего компонента-переключателя «Склад» в реестре сегодня нет —
  создаём как виджет рабочего места (шапка операций).
- **Файлы бэка:** `fbs_warehouse_binding_service.py`, `backend/app/api/warehouses.py`,
  `fbs_supply_service._existing_supply_issues`,
  `fbs_supply_validator_service._availability_by_order`,
  `_build_stock_location_notices`,
  `fbs_stock_availability_service.fbs_available_qty_by_product`,
  `fbs_picking_service.scan_pick_location` + `select_pick_location`,
  `fbs_packaging_integration_service._try_deduct_from_alternative_sorting_location`
  (снести, заменить `movement`).
- **Файлы фронта:** `App.tsx` (выбор склада по умолчанию — не `list[0]`, а
  `primaryWarehouseId`), `SellerApp.tsx`, `InboundScreen.tsx`, `OutboundScreen.tsx`,
  `FbsSupplyCreateDialog.tsx` (блок `preflight.notices`), `FfFbsSupplyWorkspace.tsx`,
  `FfFbsStockSyncScreen.tsx`, новый утилитный модуль
  `frontend/src/utils/fbsWarehouse.ts` (уже есть в WIP-ветке).
- **Таблицы:** `warehouses` — новое поле `barcode` для сканера штрихкода склада;
  `movements` — новые записи «перенос X→Y» при кросс-складском подборе; `fbs_orders`,
  `fbs_supplies`, `storage_locations` — только читаем и учитываем как контекст.
- **Уже написано:** ветка `fix/warehouse-single-20260821`, коммиты `206bd98` и
  `f8c6cfa`. Закрыт только «один настоящий склад + служебные подстановки». Всё
  остальное — переключатель, штрихкод склада, кросс-складской подбор с настоящим
  переносом, preflight-нотисы — открыто.
- **Задевает соседей:** 03 (та же шапка `FfFbsSupplyWorkspace`), 05 (правки
  списков FBS могут пересечься с добавлением строки-переключателя над таблицей),
  06 (порядок подбора считается по поставке — при кросс-складском подборе меняется
  набор ячеек), 08 (тариф хранения читает `warehouse_id` — «глобальный контекст
  склада» не должен уронить отчёт).

### 05 · prod-slow — Прод тормозит

- **Тип:** домен, инфра + бэк + фронт. Внутри режется на четыре подкарточки.
- **Экраны:** `S-03` (`FfFbsOrdersScreen` — `NEW_ORDERS_PAGE_LIMIT`, `setInterval`
  30 с, тик по `document.hidden`), `S-04` (тот же цикл автополла); модалка
  `FbsPrintPreviewDialog.tsx` внутри `S-03` для «сборки ленты ЧЗ»; `HonestSignScreen`
  и `HonestSignProductPage` через общий эндпоинт `/marking-codes/label-artifact-tape`.
- **Файлы бэка:** `backend/Dockerfile` и `Dockerfile.railway` (число воркеров —
  после (1), а не сейчас), `backend/app/celery_app.py` (расписание beat: лёгкий
  180 с, полный обход 30–60 мин), `backend/app/tasks/background_jobs.py`,
  `backend/app/services/wb_marketplace_orders_service.py::sync_seller_orders`
  (расщепление «лёгкий тик» / «полный обход»),
  `backend/app/services/fbs_autopoll_service.py`,
  `backend/app/services/marking_label_artifact_service.py` (в тредпул),
  `backend/app/services/marking_code_service.py::build_label_artifact_tape_pdf`,
  `backend/app/services/fbs_order_tape_print_service.py::print_fbs_order_tape`,
  `backend/app/api/marking_codes.py::/label-artifact-tape`,
  `backend/app/api/fbs_supplies.py::/order-print-tape`.
- **Файлы фронта:** `FfFbsOrdersScreen.tsx` (пагинация «Новых» 50 вместо 500,
  скрывать тик при `document.hidden`), `FfFbsSupplyWorkspace.tsx` (15-с интервал
  оставляем, но с тем же условием), `NotificationBell.tsx` (уже 60 с; добавить
  `document.hidden`).
- **Таблицы:** ни одной новой; заметно снижается частота чтения/записи
  `fbs_orders`, `fbs_supply_orders`, `marking_codes.label_artifact_pdf` (BLOB).
- **Артефакт-решение:** `docs/perf/2026-08-21-prod-slow-plan.md` (или
  `tasks/perf-prod-slow/PLAN.md`) — четыре раздела с замерами до/после, из
  которых нарезаются dev-карточки.
- **Задевает соседей:** 01 (батч автополла уже там; здесь только расписание и
  снятие `wb_seller_lock` с чтения — не переопределяем 01), 02 (частота освежения
  вердикта), 06 (сборка ленты уходит в тредпул — та же ручка `/order-print-tape`).

### 06 · picking-list-order — Единый порядок листа и ленты

- **Тип:** фича, бэк + фронт.
- **Экраны:** `S-03` — `FfFbsSupplyWorkspace`, модалка `FfFbsPickList.tsx`,
  модалка `FbsPrintPreviewDialog.tsx`. Новых нет.
- **Файлы бэка:** `fbs_supply_service.py::get_picking_list` (единый ключ
  `(article, sku_code, size, product_name)` уже есть; убедиться, что тот же ключ
  применяется к списку заказов), `fbs_order_tape_print_service.py::_orders_in_requested_order`
  (печатать в порядке единого списка + номер на наклейке),
  `fbs_workspace_service.py` (порядок `workspace.orders`),
  `backend/app/models/fbs_supply.py` — relationship `FbsSupply.orders` теперь с
  `order_by=` (стабильно по `wb_order_id`).
- **Файлы фронта:** `FfFbsPickList.tsx` (первая колонка `№` с диапазоном «12–17»),
  `FfFbsSupplyWorkspace.tsx` (кнопка печати листа отправляет `order_ids` в
  едином порядке, а не `workspace.orders.map(...)`).
- **Таблицы:** без изменений; только новый `order_by=` на relationship.
- **Задевает соседей:** 03 (тот же `FfFbsSupplyWorkspace.tsx` — если 03 не слить
  раньше, конфликты в шапке коробов и теле воркспейса), 04 (при кросс-складском
  подборе порядок ячеек может расходиться с «по артикулу» — проверить, что единый
  порядок не заставит оператора бегать между складами), 05 (сборка ленты в
  тредпуле — печать номера в макете не должна оживить синхронный путь).

### 07 · reporting — Раздел отчётности для селлера и ФФ

- **Тип:** домен, новый раздел (владелец сам помечает «список не окончательный»).
- **Экраны:** `S-nn` (`FfReportsPage` — существует, но в `screens.registry.json`
  не занесён; сегодня один разрез «Движения по товару»); портал селлера **«Отчёты» —
  создаём**. По ходу проработки — «Отчёт по складу», «Отчёт по маркетплейсу»,
  «Отчёт по операциям», «Отчёт по деньгам селлера».
- **Файлы бэка:** `backend/app/api/inventory_movements.py` (расширение),
  `backend/app/services/inventory_movement_report_service.py`, новые сервисы
  агрегаций и (при росте нагрузки) материализованных витрин.
- **Файлы фронта:** `frontend/src/screens/ff/FfReportsPage.tsx` (разбить на
  подэкраны/вкладки), `frontend/src/screens/v2/SellerDashboardScreen.tsx` (пункт
  «Отчёты» в меню селлера), `frontend/src/layouts/AuthedAppLayout.tsx` (новый
  пункт в меню).
- **Таблицы:** читает `inventory_movements`, `packaging_task`, `fbs_orders`,
  `marketplace_unload_*`, `outbound_shipment`, `seller`, `warehouse`; в первую
  волну — без новых сущностей.
- **Задевает соседей:** 08 (данные по литрам/дням/тарифу хранения — оттуда),
  09 (`billing_ledger`, счета, задолженность — оттуда), 05 (объём выборки за
  квартал может стать новым узким местом; выгрузку Excel тоже надо в тредпул).

### 08 · storage — Хранение: считать, менять габариты, брать деньги

- **Тип:** домен, новый раздел (владелец сам помечает «продумать»).
- **Экраны:** `S-11` (`/app/ff/inventory`, сегодня — `FfPlaceholderPage`); внутри
  раздела появятся «Настройка тарифа хранения», «Сколько лежит и на сколько по
  селлеру за период», «Сводная накладная за хранение», «История изменений
  габаритов», «Товары без габаритов».
- **Файлы бэка:** `backend/app/services/wildberries_product_import_service.py`
  (маркер источника вместо «пусто/stub»), `backend/app/models/product.py` (поля
  источника + связка с журналом), `backend/app/services/catalog_service.py::update_product_dimensions`
  (запись каждой правки в журнал), `backend/app/models/stock_direction.py::StockMonthlySnapshot`
  (расширить до литров + тариф-снимок), новые сервисы расчёта литро-дней и
  печати накладной.
- **Файлы фронта:** страница `S-11` (замена `FfPlaceholderPage`); блок «Источник
  габаритов + журнал» в карточке товара; пункт «Хранение» в меню ФФ.
- **Таблицы:** `products` — новые `dimensions_source`, `dimensions_updated_at`,
  `dimensions_updated_by_user_id` (по образцу пары из 03); новый журнал
  `product_dimension_events`; `stock_monthly_snapshot` — колонки литров и
  тарифа-снимка; новая `storage_tariffs` (с историей `valid_from`/`valid_to`); новая
  `storage_charges` (или строки `service='storage'` в общем `billing_ledger` из 09).
- **Задевает соседей:** 09 (тариф-снимок и `billing_ledger` — одна модель на
  двоих, проектировать вместе), 07 (данные для отчёта «Хранение»), 04
  (литро-дни считаются по `warehouse_id` — переключатель склада не должен
  ломать отчёт).

### 09 · billing — Счета и цифровой учёт работы

- **Тип:** домен, новый модуль (владелец сам помечает «продумать и проработать»).
- **Экраны:** `S-19` (`FfSettingsScreen` — добавляем вкладку «Тарифы ФФ» рядом с
  существующей вкладкой ставки упаковщика); новые: «Реквизиты селлера» (в
  карточке селлера админского портала), «Начисления за период», «Счета»; позже —
  «Мои счета» в кабинете селлера (фаза 2).
- **Файлы бэка:** `backend/app/models/seller.py` (ИНН, КПП, юр. адрес, банк),
  `backend/app/services/staff_packaging_billing_service.py` (паттерн снимка ставки —
  переиспользуем как образец); новые модели `tariffs`, `billing_ledger`, `invoices`,
  `invoice_lines`; новые сервисы биллинга; API `/billing/*`.
- **Файлы фронта:** `FfSettingsScreen.tsx` (вкладка «Тарифы ФФ»), новые экраны
  реквизитов селлера, начислений и счетов, карточка селлера в админском портале.
- **Таблицы:** новые `tariffs`, `billing_ledger`, `invoices`, `invoice_lines`;
  расширение `sellers` (ИНН, КПП, реквизиты); служебные штампы `billed_at` /
  `invoice_id` на `inbound_intakes`, `marketplace_unload`, `packaging_task`.
- **Задевает соседей:** 07 (данные показывает раздел отчётов), 08 (общий журнал
  начислений — литро-дни хранения и операции), 04 (заявки по разным складам —
  считать по фактическому `warehouse_id`), 05 (генерация PDF-счёта — сразу в
  тредпул, чтобы не повторять историю с лентой ЧЗ).

---

### Столкновения по горячим точкам

Ниже — файлы, за которые в этой волне «дерётся» больше одной карточки. Для каждого —
рекомендуемый порядок правок.

**`frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — правят 02, 03, 04, 06.** Главная
горячая точка волны. Порядок обязателен: **03 → 04-A/04-E → 02 → 06 → 04-B/04-D**.
03 идёт первым, чтобы шапка коробов и правило чекбокса встали на место; 02 меняет
чипы вердикта в строке заказа; 06 добавляет колонку `№` и порядок; 04-B/04-D
приземляют переключатель склада и кросс-складской подбор в шапку и в скан-ячейки
последними — иначе три одновременные правки одной шапки дадут конфликты.

**`frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — правят 02, 04, 05.** Безопасный
порядок: **05 → 02 → 04**. 05 меняет `NEW_ORDERS_PAGE_LIMIT` / `setInterval` /
`document.hidden` (не трогает JSX строк). 02 правит `metadataProblem` внутри ячейки.
04 добавляет строку-переключатель склада над таблицей.

**`frontend/src/screens/v2/fbsApi.ts` — правят 02, 03, 04.** Диффы соседние, не
пересекаются построчно (`state.status = 'unknown'` в 02, `boxes_without_distribution`
в 03, `setFbsBoxesWithoutDistribution` там же, тип `preflight.notices` в 04).
Порядок совпадает с общим по полосе A.

**`backend/app/services/fbs_marking_service.py` — правят 01, 02.** Строгий порядок:
**01 → 02**. 01 добавляет батчинг, возврат кода в пул при потере у WB и событие
`wb_orphaned`. 02 расширяет справочник вердиктов и гейт по `reason`. Обратный
порядок ломает 02: ему нужны данные, которых без 01 в базе нет.

**`backend/app/services/fbs_autopoll_service.py` — правят 01, 05.** Оба видят
`wb_seller_lock`. 01 переводит цикл меты на пачки. 05 расщепляет `sync_seller_orders`
на лёгкий тик и полный обход и планирует снять лок с чтения. Порядок: **01 → 05**,
конфликтов по строкам нет, конфликт по смыслу — как обходиться с локом; закрывается
допущением 05 (лок остаётся на upsert-транзакции).

**`backend/app/services/fbs_workspace_service.py` — правят 03, 06.** 03 меняет
источник истины `hasNoDistributionBoxes` (читает поле поставки). 06 добавляет
`order_by=` в формировании `workspace.orders`. Диффы соседние, но разные места
файла. Порядок: **03 → 06**.

**`backend/app/services/fbs_supply_service.py` — правят 04, 06.** 04 —
`_existing_supply_issues` и логика складов. 06 — `get_picking_list`. Функции разные,
конфликта нет.

**`backend/app/services/fbs_order_tape_print_service.py` — правят 05, 06.** Порядок:
**05 → 06**. 05 выносит PDF-слияние в тредпул (инфраструктурный слой); 06 меняет
порядок печати наклеек и добавляет номер на наклейку (логический слой сверху).

**`backend/app/api/fbs_supplies.py` — правят 03, 05, 06.** 03 добавляет новый роут
`/boxes-without-distribution`. 05 и 06 не меняют сигнатуры существующих ручек, только
внутренности `/order-print-tape`. Конфликтов нет.

**`backend/app/models/fbs_supply.py` — правят 03, 06.** 03 — две новые колонки
`boxes_without_distribution_*`. 06 — `order_by=` на relationship `orders`. Разные
места файла.

**Таблица `sellers` — расширяет 09.** 04 её только читает, конфликта нет.

**Таблица `warehouses` — расширяет 04** (новое поле `barcode` для сканера штрихкода
склада). Никто больше в волне эту таблицу не трогает.

**Таблица `products` — расширяет 08** (`dimensions_source`, штампы правки). 04
использует `warehouse_id` продукта косвенно через `product_stock`, саму `products`
не расширяет.

**Ветки, ждущие вливания:** `fix/wb-meta-method-20260821` (01),
`fix/no-distribution-20260821` (03), `fix/warehouse-single-20260821` (первый шаг 04).
Первым ходом ночи — влить эти три в `etalon` в порядке 03 → 01 → 04-A, иначе любая
свежая работа над `FfFbsSupplyWorkspace.tsx`, `fbs_marking_service.py` и `App.tsx`
сядет на конфликт.

### Смежные экраны, чьи кейсы придётся перекликать

- **`HonestSignScreen`, `HonestSignProductPage`** — ручка
  `/marking-codes/label-artifact-tape` переезжает в тредпул (05). Перепройти
  сценарии печати ленты ЧЗ и разграничения ЧЗ/ШК из `wms-print-scanner-features-plan`.
- **Мобильный ТСД (Android)** — 04 меняет семантику сканера: штрихкод склада ↔
  штрихкод ячейки. Перед правкой прочитать `mobile/docs/PROGRESS.md`; обновить
  сценарии подбора и упаковки на устройстве.
- **`FfInventorySnapshotScreen`** — 08 расширяет `StockMonthlySnapshot` литрами и
  тарифом-снимком. Ручной запуск снимка не должен сломаться; кейс проверки —
  заново.
- **`FfFbsStockSyncScreen` (S-04)** — 04 уже перевёл его на общую
  `isAutoFbsWarehouse`; при доделке переключателя повторить кейс синка остатков.
- **`SellerInboundDraftScreen` (S-28), `SellerDocumentsScreen` (S-26/29)** — 04
  убирает выбор склада у селлера при одном настоящем складе; 07 добавляет пункт
  «Отчёты» в меню селлера — сценарии портала селлера перепройти полностью.
- **`FfSettingsScreen` (S-19)** — 09 добавляет вкладку «Тарифы ФФ» рядом с уже
  живущей вкладкой ставки упаковщика. Регрессия на существующий сценарий зарплаты
  упаковщика — обязательна.
- **`FfPackagingPage` (S-14) и `PackagingPendingMarkingWorklist` (S-15)** — 01
  меняет данные меты, 04 сносит костыль
  `_try_deduct_from_alternative_sorting_location`. Кейс упаковки — целиком.
- **`FbsSupplyCreateDialog`** — 04 показывает preflight-notices; после 05 и 06 диалог
  не меняется, но нужно проверить, что предупреждения не исчезли при перерисовке.
- **`InboundScreen` (S-22), `OutboundScreen` (S-24), `TransfersScreen` (S-25)** — 04
  переключает контекст склада; кейсы приёмки, отгрузки и переносов перепройти в
  двух режимах: «один настоящий склад» и «два и более».
- **`FbsPrintPreviewDialog`** — 05 (тредпул) и 06 (номер на наклейке) правят одну
  и ту же модалку. Кейс печати ленты — после обеих правок.
- **`FfReportsPage`** — 07 переделывает его из одностраничного отчёта в раздел с
  подэкранами; существующий сценарий «Движения по товару» должен остаться живым
  как первый разрез нового раздела.

## Порядок

Три полосы. Внутри полосы порядок строгий (обратный ломает). Между полосами —
можно параллельно, столкновений по коду нет.

### Полоса A · FBS-ядро (жгучее, чинит бой)

1. **03 — слить готовую ветку `fix/no-distribution-20260821`.** Диффы минимальны,
   тест уже есть. После вливания уходит конфликт в `FfFbsSupplyWorkspace.tsx` и
   `fbs_workspace_service.py` для 04 и 06.
2. **01 — влить `fix/wb-meta-method-20260821` + дописать правило «WB кода не
   знает»** (перевод строки в `missing`, возврат `MarkingCode` в `available`,
   событие `wb_orphaned` в `marking_code_events`). Пока 01 не приземлилось,
   у 02 нет данных, из которых рисовать вердикт словами.
3. **02 — фича по вердиктам и словарю.** Расширить `map_wb_decision_to_meta_status`
   (`required`/`optional`/`notRequired`), отвязать «подтверждено» от `filled` +
   `reason`, добавить `metaStatus.ts`, показать вердикт в строке заказа и в
   `FfFbsSupplyWorkspace`, поднять гейт `compute_delivery_allowed` до «нет
   `reason`».
4. **05 — перф.** Внутри режется на четыре независимые подкарточки: (а) вынос
   PDF-слияния в тредпул, (б) расщепление `sync_seller_orders` на лёгкий тик и
   полный обход, (в) курсорная пагинация «Новых» на S-03 (50 вместо 500) +
   `document.hidden`, (г) записка владельцу про RAM/воркеры. (а) и (в) независимы
   от 02/03 и катятся одновременно; (б) удобнее после 01 (пачки уже там).
5. **06 — единый порядок листа и ленты, номера на наклейках.** После 03 (шапка
   воркспейса) и 05 (тредпул печати).

### Полоса B · Склады (широкий доменный сдвиг)

1. **04-A — влить `fix/warehouse-single-20260821`.** Уже закрывает инцидент 20.08
   и вычищает служебные подстановки; независима от полосы A.
2. **04-B — общий переключатель «Склад» как компонент.** Новый UI-элемент,
   переиспользуется в приёмке, отгрузке, переносах, поставках, упаковке.
3. **04-C — сканер понимает штрихкод склада.** Требует поле `warehouses.barcode` и
   правки мобильного клиента.
4. **04-D — снос костыля `_try_deduct_from_alternative_sorting_location`.**
   Заменяем настоящим `movement` X→Y при кросс-складском подборе
   (`fbs_picking_service.scan_pick_location` / `select_pick_location`).
5. **04-E — preflight-нотисы на создании поставки.** WIP уже есть; довести до
   рабочего вида и покрыть тестом.

Полоса B пересекается с A только по `FfFbsSupplyWorkspace.tsx`: 04-B и 04-D
приземляются в шапку и в подбор **после** того, как 02, 03, 06 из полосы A уже
влиты — иначе три параллельных правки одной шапки дадут конфликты.

### Полоса C · Новые домены (тарифы, отчёты)

1. **08 + 09 идут связкой, начинать одновременно.** Общий журнал начислений
   (`billing_ledger`) и общий паттерн «снимок тарифа» — если резать
   последовательно, вторая карточка перепишет модель первой. Продуктовое
   исследование делаем на две карточки сразу, миграцию модели — тоже одну общую.
2. **Внутри связки:** сначала реквизиты селлера + пустой каркас `billing_ledger`;
   потом тарифы (в 08 — литр-день, в 09 — за документ / за штуку); потом счёт как
   документ и печатная накладная.
3. **07 — раздел отчётности.** Идёт после 08+09 (данные — оттуда), но
   UI-исследование и продуктовые вопросы можно вести параллельно. Один разрез —
   «Движения по товару» — уже работает; переиспользуем как первый пункт нового
   раздела.

Полоса C ни в одну строку кода из A и B не лезет; катится параллельно с обеими,
блокировок по файлам нет. Единственная точка встречи — 05: массовые выборки за
квартал и Excel-выгрузка должны с самого начала жить в тредпуле, иначе новый
раздел отчётов повторит историю с лентой ЧЗ.

### Общий вывод по порядку

- Ночь начинается с **вливания трёх готовых веток** (`fix/no-distribution-20260821`,
  `fix/wb-meta-method-20260821`, `fix/warehouse-single-20260821`) в порядке
  03 → 01 → 04-A. Без этого свежие карточки на файлах `FfFbsSupplyWorkspace.tsx`,
  `fbs_marking_service.py`, `App.tsx` сядут на конфликт с первого коммита.
- Полоса A режется строго последовательно (03 → 01 → 02 → 05 → 06), потому что
  все пять карточек толпятся в одном экране `S-03` и в одном сервисе меты.
- Полоса B параллельна A до шага, когда 04 идёт в шапку `FfFbsSupplyWorkspace` и
  в кросс-складской подбор — этот шаг ставим после полосы A.
- Полоса C (07 / 08 / 09) параллельна A и B полностью; 08 и 09 проектируются
  как одна модель.
