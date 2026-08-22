# MAP · Волна 9 · Карта задевания

Собрана по девяти `RAZBOR.md` в `night/volna-9/cards/`. Задача карты — до старта показать,
где карточки лезут в одни и те же файлы, экраны и таблицы, и в каком порядке их надо
резать, чтобы не переписывать чужой diff.

## Карта

### 01 · wb-marking (домен, бэк-only)

- **Экраны:** `S-03` (`FfFbsOrdersScreen`, `FfFbsSupplyWorkspace`), `S-14`
  (`FbsPackagingPage`), `S-15` (`PackagingPendingMarkingWorklist`) — сам UI не правит,
  но данные, на которых эти экраны рисуют, начинает менять.
- **Файлы бэка:** `backend/app/services/wildberries_fbs_client.py`,
  `backend/app/services/fbs_marking_service.py`,
  `backend/app/services/fbs_autopoll_service.py::sync_marking_statuses_for_assembling_supplies`,
  `backend/app/tasks/background_jobs.py`. Удаляется мёртвый одиночный `GET .../meta` из
  `wildberries_client.py:953`.
- **Таблицы:** `fbs_order_marking` (`check_status`, `meta_status`, `reason`,
  `meta_details_json`, `marking_code_id` — теперь ссылку могут снимать), `fbs_orders`
  (`metadata_delivery_allowed`, `metadata_last_checked_at`), `marking_codes`
  (возврат в `available`), `marking_code_events` (новое событие `wb_orphaned`).
- **Что уже есть:** ветка `fix/wb-meta-method-20260821` (два коммита `bd9384f`, `2453f44`),
  не влита в `etalon`. Правила сверки с пулом (пункт про 25 заданий) там ещё не сделаны.
- **Задевает соседние карточки:** 02 (заполняет поля, из которых 02 рисует вердикт),
  05 (батчинг снимает часть нагрузки автополлера, но 05 отдельно режет частоту).

### 02 · verdikt-screen (фича, фронт+бэк)

- **Экраны:** `S-03` (обе половины — `FfFbsOrdersScreen`, `FfFbsSupplyWorkspace`).
- **Файлы бэка:** `fbs_marking_service.py::map_wb_decision_to_meta_status`,
  `derive_meta_status`, `compute_delivery_allowed`, `_meta_details_from_wb`,
  `_apply_meta_detail_to_marking`; `fbs_shipment_service.py::_build_delivery_checks`.
- **Файлы фронта:** `frontend/src/screens/v2/FfFbsOrdersScreen.tsx::metadataProblem`,
  `FfFbsSupplyWorkspace.tsx::isOrderMarkingReady` (правится
  `MARKING_ACCEPTED_STATUSES`), `frontend/src/screens/v2/fbsApi.ts` (тип
  `state.status`), новый словарь `frontend/src/utils/metaStatus.ts` рядом с
  `markingStatus.ts`.
- **Таблицы:** те же `fbs_order_marking` / `fbs_orders`, что и в 01 — только читаем,
  не расширяем.
- **Задевает:** 01 (жёсткая зависимость по данным), 04 (шапка строки заказа делит место
  с чипом склада/переключателем), 05 (частота автополлера меняет, насколько «свежий»
  вердикт видит оператор).

### 03 · no-distribution-mode (готово в ветке, ждёт слива)

- **Экраны:** `S-03`, вкладка «Короба» в `FfFbsSupplyWorkspace`.
- **Файлы бэка:** `backend/app/models/fbs_supply.py`,
  `backend/app/services/fbs_packing_box_service.py`,
  `backend/app/services/fbs_workspace_service.py`,
  `backend/app/api/fbs_supplies.py`, миграция
  `backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`.
- **Файлы фронта:** `FfFbsSupplyWorkspace.tsx` (условие чекбокса, шапка
  `hasNoDistributionBoxes`), `fbsApi.ts` (`setFbsBoxesWithoutDistribution`),
  `frontend/openapi/fbs-operations.openapi.json`.
- **Таблицы:** `fbs_supplies` — новые колонки `boxes_without_distribution_at`,
  `boxes_without_distribution_by_user_id`; `fbs_packing_boxes` /
  `fbs_packing_box_items` (охрана «в короба ничего не разложено»).
- **Что уже есть:** ветка `fix/no-distribution-20260821` (два коммита `9e2808e` wip +
  `cbdaad9` доделка). На `origin/etalon` нет, на бой не уехало. Тип задачи в RAZBOR —
  `отложить` (сдача уже готового, не разработка).
- **Задевает:** 06 (правит порядок в том же `fbs_workspace_service.py` и в
  `FfFbsSupplyWorkspace.tsx`, значит нужно сливать 03 до 06), 04 (правит соседний
  таб «Короба»/переключатель складов в той же шапке).

### 04 · warehouse-switch (домен, широкий)

- **Экраны:** `S-03` (переключатель + preflight поставки + подбор), `S-14` (уходит
  костыль `_try_deduct_from_alternative_sorting_location`), `S-22` (`InboundScreen`),
  `S-24` (`OutboundScreen`), `S-25` (`TransfersScreen` — сюда пишутся реальные
  переносы X→Y), `S-01` (`ProductsScreen`/`CatalogSection` — выбор склада),
  `S-04` (`FfFbsStockSyncScreen`), `S-26`/`S-28`/`S-29` (портал селлера —
  `SellerDocumentsScreen`, `SellerInboundDraftScreen`).
- **Новый экран:** общего компонента-переключателя «Склад» в реестре нет — создаём.
- **Файлы бэка:** `fbs_warehouse_binding_service.py`, `api/warehouses.py`,
  `fbs_supply_service._existing_supply_issues`,
  `fbs_supply_validator_service._availability_by_order`+`_build_stock_location_notices`,
  `fbs_stock_availability_service.fbs_available_qty_by_product`,
  `fbs_picking_service.scan_pick_location`+`select_pick_location`,
  `fbs_packaging_integration_service._try_deduct_from_alternative_sorting_location`
  (снести, заменить настоящим `movement`).
- **Файлы фронта:** `App.tsx` (выбор склада по умолчанию), `SellerApp.tsx`,
  `InboundScreen.tsx`, `OutboundScreen.tsx`, `FbsSupplyCreateDialog.tsx`,
  `FfFbsSupplyWorkspace.tsx`, `FfFbsStockSyncScreen.tsx`, новый утил
  `frontend/src/utils/fbsWarehouse.ts` (уже есть в WIP-ветке).
- **Таблицы:** `warehouses` (новое поле `barcode` для сканера), `movements`
  (новые записи «перенос X→Y» при кросс-складском подборе),
  `fbs_orders.warehouse_id`, `fbs_supplies.warehouse_id`, `storage_locations`.
- **Что уже есть:** ветка `fix/warehouse-single-20260821` (два коммита `206bd98`,
  `f8c6cfa`) — закрыт только «один настоящий склад плюс служебные подстановки». Всё
  остальное («переключатель», «сканер понимает склад», «настоящий перенос вместо
  костыля») открыто.
- **Задевает:** 03 (та же шапка `FfFbsSupplyWorkspace`), 05 (правки списков FBS
  могут пересечься с добавлением строки-переключателя над таблицей), 06 (порядок
  подбора считается по поставке, при кросс-складском подборе меняется набор ячеек),
  08 (тарификация хранения читает `warehouse_id` — если склад стал «глобальным
  контекстом», отчёт хранения этого не должен потерять).

### 05 · prod-slow (домен, инфра + бэк + фронт)

- **Экраны:** `S-03` (`FfFbsOrdersScreen` — `NEW_ORDERS_PAGE_LIMIT`, `setInterval`
  30 000 мс), `S-04` (тот же цикл автополла), «сборка ленты» — модалка
  `FbsPrintPreviewDialog.tsx` внутри `S-03`, плюс `HonestSignScreen` /
  `HonestSignProductPage` через общий эндпоинт.
- **Файлы бэка:** `backend/Dockerfile` и `Dockerfile.railway` (число воркеров),
  `backend/app/celery_app.py` (расписание beat), `backend/app/tasks/background_jobs.py`,
  `backend/app/services/wb_marketplace_orders_service.py::sync_seller_orders`
  (расщепление «лёгкий тик» / «полный обход»), `fbs_autopoll_service.py`,
  `backend/app/services/marking_label_artifact_service.py` (в тредпул),
  `backend/app/services/marking_code_service.py::build_label_artifact_tape_pdf`,
  `backend/app/services/fbs_order_tape_print_service.py::print_fbs_order_tape`,
  `backend/app/api/marking_codes.py::/label-artifact-tape`,
  `backend/app/api/fbs_supplies.py::/order-print-tape`.
- **Файлы фронта:** `FfFbsOrdersScreen.tsx` (пагинация «Новых» 50 вместо 500,
  тик 30 с при `document.hidden` — стоп), `FfFbsSupplyWorkspace.tsx` (15-с
  интервал), `NotificationBell.tsx` (60 с + `document.hidden`).
- **Таблицы:** не меняются (upsert-ы те же), но заметно снижается частота
  чтения/записи `fbs_orders`, `fbs_supply_orders`, `marking_codes.label_artifact_pdf`.
- **Артефакт:** `docs/perf/2026-08-21-prod-slow-plan.md` (или
  `tasks/perf-prod-slow/PLAN.md`) — четыре раздела с замерами до/после.
- **Задевает:** 01 (батчинг автополлера уже сделан там; расписание меняем здесь —
  но не переопределяем логику 01), 02 (частота освежения вердикта), 06 (сборка
  ленты и порядок — та же ручка `/order-print-tape`).

### 06 · picking-list-order (фича, фронт+бэк)

- **Экраны:** `S-03` — `FfFbsSupplyWorkspace`, модалка `FfFbsPickList.tsx`,
  `FbsPrintPreviewDialog.tsx` (лента наклеек).
- **Файлы бэка:** `fbs_supply_service.py::get_picking_list` (единый ключ
  сортировки), `fbs_order_tape_print_service.py::_orders_in_requested_order`
  (печать в порядке единого списка + номер на наклейке),
  `fbs_workspace_service.py` (порядок `workspace.orders`), `models/fbs_supply.py`
  (relationship `FbsSupply.orders` — добавить `order_by=`).
- **Файлы фронта:** `FfFbsPickList.tsx` (колонка `№` с диапазоном),
  `FfFbsSupplyWorkspace.tsx` (передача `order_ids` в едином порядке).
- **Таблицы:** без изменений, только новый признак сортировки на relationship.
- **Задевает:** 03 (тот же `FfFbsSupplyWorkspace.tsx` — если 03 не слить раньше,
  получим конфликты правок в шапке коробов и в теле воркспейса), 04 (при
  кросс-складском подборе порядок ячеек может отличаться от «по артикулу», нужно
  проверить, что единый порядок не заставляет оператора бегать между складами),
  05 (сборка ленты уходит в тредпул — печать номера в макете не должна оживить
  синхронный путь).

### 07 · reporting (домен, новый раздел)

- **Экраны:** `S-nn` (`FfReportsPage` — сегодня есть, в реестре не отмечен),
  портал селлера **«Отчёты» — создаём**, возможные подэкраны «Отчёт по складу»,
  «Отчёт по маркетплейсу», «Отчёт по операциям», «Отчёт по деньгам селлера».
- **Файлы бэка:** `backend/app/api/inventory_movements.py`,
  `backend/app/services/inventory_movement_report_service.py`, новые сервисы
  агрегаций и (возможно) витрин.
- **Файлы фронта:** `frontend/src/screens/ff/FfReportsPage.tsx`,
  `frontend/src/screens/v2/SellerDashboardScreen.tsx` (пункт «Отчёты» в меню
  селлера), новый пункт в `AuthedAppLayout.tsx`.
- **Таблицы:** читает `inventory_movements`, `packaging_task`, `fbs_orders`,
  `marketplace_unload_*`, `outbound_shipment`, `seller`, `warehouse`; в первую
  волну без новых сущностей, но по мере роста — материализованная витрина.
- **Задевает:** 08 (данные по литрам/дням/тарифу хранения — оттуда), 09
  (`billing_ledger`, счета, задолженность — оттуда), 05 (объём выборки за квартал
  может стать новым узким местом; выгрузку Excel тоже надо в тредпул).

### 08 · storage (домен, новый раздел)

- **Экраны:** `S-11` (`/app/ff/inventory`, сегодня `FfPlaceholderPage`), новые
  экраны «Настройка тарифа хранения», «Сколько лежит и на сколько», «Сводная
  накладная за хранение», «История изменений габаритов», «Товары без габаритов».
- **Файлы бэка:** `backend/app/services/wildberries_product_import_service.py`
  (маркер источника), `backend/app/models/product.py` (поля источника, журнал),
  `backend/app/services/catalog_service.py::update_product_dimensions` (запись в
  журнал), `backend/app/models/stock_direction.py::StockMonthlySnapshot`
  (расширение до литров), новые сервисы расчёта литро-дней и печати накладной.
- **Файлы фронта:** новая страница `S-11` (замена `FfPlaceholderPage`), пункт
  в меню ФФ; в карточке товара — блок «Источник габаритов + журнал».
- **Таблицы:** `products` (добавить `dimensions_source`, `dimensions_updated_at`,
  `dimensions_updated_by_user_id` — по образцу пары из 03), новый журнал
  `product_dimension_events`, `stock_monthly_snapshot` (расширить литрами и
  тарифом-снимком), новая таблица тарифа `storage_tariffs` (с историей),
  новая таблица `storage_charges` (или строки в общем `billing_ledger` из 09).
- **Задевает:** 09 (тариф-снимок, `billing_ledger` — одна модель на двоих),
  07 (данные для отчёта «Хранение»), 04 (объём в литро-днях считается по
  `warehouse_id` — переключатель склада не должен ломать отчёт).

### 09 · billing (домен, новый раздел)

- **Экраны:** `S-19` (`FfSettingsScreen` — добавляем вкладку «Тарифы ФФ»);
  новые: «Реквизиты селлера» (в карточке селлера админского портала),
  «Начисления за период», «Счета», позже «Мои счета» в кабинете селлера.
- **Файлы бэка:** `backend/app/models/seller.py` (ИНН/КПП/юр. адрес/банк),
  `backend/app/services/staff_packaging_billing_service.py` (паттерн снимка
  ставки — переиспользуем), новые модели `tariffs`, `billing_ledger`,
  `invoices`, `invoice_lines`; новые сервисы биллинга; API `/billing/*`.
- **Файлы фронта:** `FfSettingsScreen.tsx` (вкладка), новые экраны, карточка
  селлера в админском портале.
- **Таблицы:** новые `tariffs`, `billing_ledger`, `invoices`, `invoice_lines`;
  расширение `sellers` (ИНН, КПП, реквизиты); служебные штампы `billed_at`
  на `inbound_intakes`, `marketplace_unload`, `packaging_task`.
- **Задевает:** 07 (данные показывает раздел отчётов), 08 (общий журнал
  начислений на литро-дни хранения и на операции), 04 (заявки по разным
  складам — считать по фактическому `warehouse_id`), 05 (генерация PDF-счёта —
  в тредпул сразу, чтобы не повторять историю с лентой ЧЗ).

---

### Столкновения по горячим точкам

**Файл `FfFbsSupplyWorkspace.tsx` — правят 02, 03, 04, 06.** Это ключевая горячая точка
волны. Порядок обязателен: сначала сливаем 03 (уже готово, минимальный diff), потом
04 в тех кусках, где меняется шапка и переключатель, потом 02 (чипы вердикта), потом
06 (порядок и номера). Обратный порядок гарантированно даёт трёхсторонние конфликты
в шапке.

**Файл `FfFbsOrdersScreen.tsx` — правят 02, 04, 05.** 05 переводит «Новых» на курсорную
пагинацию (меняет `NEW_ORDERS_PAGE_LIMIT`, `setInterval`, добавляет `document.hidden`),
02 меняет `metadataProblem` и вводит словарь, 04 добавляет строку-переключатель склада
над таблицей. Порядок безопасный: 05 → 02 → 04 (05 не трогает JSX строк, 02 в ячейке,
04 над таблицей).

**Файл `fbsApi.ts` — правят 02, 03, 04.** У всех трёх свои новые клиентские функции и
типы; конфликтов данных нет, но нужно единое место для новых типов
(`state.status = 'unknown'` в 02 и поле `boxes_without_distribution` в 03 — соседние).

**Файл `fbs_marking_service.py` — правят 01, 02.** Естественная последовательность: 01
сначала (батчинг + возврат кода в пул), 02 следом (справочник вердиктов + гейт по
`reason`).

**Файл `fbs_autopoll_service.py` — правят 01, 05.** 01 переводит цикл меты на пачки, 05
рядом делит `sync_seller_orders` на лёгкий тик и полный обход. Идут параллельно,
конфликтуют только в оформлении `wb_seller_lock` — 05 планирует его снимать, 01 не
трогает.

**Файл `fbs_workspace_service.py` — правят 03, 06.** 03 меняет источник истины
`hasNoDistributionBoxes` (читает поле поставки), 06 добавляет `order_by=` в
формировании `workspace.orders`. Диффы соседние, но не пересекаются построчно.

**Файл `fbs_supply_service.py` — правят 04, 06.** 04 — `_existing_supply_issues` и
логика склада, 06 — `get_picking_list`. Функции разные, конфликта нет.

**Файл `fbs_order_tape_print_service.py` — правят 05, 06.** 05 выносит PDF-слияние в
тредпул, 06 меняет порядок печати и печатает номер на наклейке. Порядок: 05 сначала
(инфраструктурный слой), 06 сверху (логика порядка/номера).

**Файл `fbs_supplies.py` (API) — правят 03, 05, 06.** 03 добавляет новый роут
`/boxes-without-distribution`, 05 не меняет сигнатуру `/order-print-tape` (только
внутренности), 06 тоже её не меняет. Конфликтов нет.

**Модель `fbs_supply.py` — правят 03, 06.** 03 добавляет две колонки (`boxes_without_distribution_at`,
`boxes_without_distribution_by_user_id`), 06 меняет relationship (`order_by=`). Разные
места файла, конфликтов не будет.

**Таблица `sellers` — правят 04 (косвенно) и 09.** 09 добавляет ИНН/КПП/реквизиты.
04 её не расширяет, только читает — конфликта нет.

**Таблица `warehouses` — правит 04.** Добавляет физический `barcode` для сканера.
Никто больше эту таблицу в волне не трогает.

**Таблица `products` — правит 08.** Добавляет `dimensions_source` и штампы. 04
использует `warehouse_id` продукта косвенно через `product_stock`, но саму таблицу
`products` не расширяет.

**Ветки, которые уже написаны, но не влиты:** `fix/wb-meta-method-20260821` (для 01),
`fix/no-distribution-20260821` (для 03), `fix/warehouse-single-20260821` (первый шаг 04).
Первым делом ночного прогона — влить эти три в `etalon`, иначе любая свежая работа
над теми же файлами сядет на конфликт.

### Смежные экраны, чьи кейсы придётся перекликать

- **`HonestSignScreen`, `HonestSignProductPage`** — ручка `/marking-codes/label-artifact-tape`
  переезжает в тредпул (05). После правки перепройти сценарии печати ленты и
  разграничения ЧЗ/ШК из плана `wms-print-scanner-features-plan`.
- **Мобильный ТСД (Android)** — 04 меняет семантику сканера (штрихкод склада ↔
  штрихкод ячейки). Читаем `mobile/docs/PROGRESS.md` до правки и обновляем сценарии
  подбора и упаковки на устройстве.
- **`FfInventorySnapshotScreen`** — 08 расширяет `StockMonthlySnapshot` литрами и
  привязывает тариф. Ручной запуск снимка не должен сломаться; кейс проверки
  запускается заново.
- **`FfFbsStockSyncScreen` (S-04)** — 04 уже перевёл его на общую утилиту
  `isAutoFbsWarehouse`; при доделке переключателя надо повторить кейс синка остатков.
- **`SellerInboundDraftScreen` (S-28), `SellerDocumentsScreen` (S-26/29)** — 04 убирает
  выбор склада у селлера при одном настоящем складе; 07 добавляет пункт «Отчёты» в
  меню селлера — сценарии портала селлера перепройти полностью.
- **`FfSettingsScreen` (S-19)** — 09 добавляет вкладку «Тарифы ФФ» рядом с уже живущей
  вкладкой ставки упаковщика. Регрессия на существующий сценарий зарплаты упаковщика
  обязательна.
- **`FfPackagingPage` (S-14) и `PackagingPendingMarkingWorklist` (S-15)** — 01 меняет
  данные меты, 04 сносит костыль в упаковке. Кейс упаковки прогоняется целиком.
- **`FbsSupplyCreateDialog`** — 04 показывает preflight-notices; после 05 и 06 диалог не
  меняется, но нужно проверить, что предупреждения не пропали при перерисовке экрана.
- **`InboundScreen` (S-22), `OutboundScreen` (S-24), `TransfersScreen` (S-25)** — 04
  переключает контекст склада; кейсы приёмки/отгрузки/переносов перепройти под каждый
  из двух режимов («один настоящий склад» и «два+»).
- **`FbsPrintPreviewDialog`** — 05 (тредпул) и 06 (номер на наклейке) в одну и ту же
  модалку; кейс печати ленты после обеих правок.

## Порядок

Три полосы. Внутри полосы порядок строгий (справа налево ломает); между полосами —
можно параллельно, столкновений по файлам нет.

### Полоса A · FBS-ядро (жгучее, чинит бой)

1. **03 — слить.** Правки минимальные, всё уже написано и покрыто тестом. Первым
   ходом убирает конфликты в `FfFbsSupplyWorkspace.tsx` и `fbs_workspace_service.py`
   для 04, 06.
2. **01 — влить ветку `fix/wb-meta-method-20260821` + дописать правило «WB кода не
   знает».** Пока 01 не приземлилось в `etalon`, у 02 нет данных, из которых рисовать
   вердикт.
3. **02 — фича по вердиктам и словарю.** Опирается на данные из 01, правит те же
   `fbs_marking_service.py`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`.
4. **05 — перф.** Внутри режется на четыре подкарточки (тредпул PDF, лёгкий/тяжёлый
   тик, пагинация «Новых», записка про RAM). Тредпул PDF и пагинация независимы от
   02 и 03, можно двигать одновременно с 02. Разделение автополла лучше сделать
   после 01 (пачки уже там).
5. **06 — единый порядок листа и ленты.** После 03 (шапка воркспейса) и 05
   (тредпул печати), потому что правит те же куски `FfFbsSupplyWorkspace.tsx` и
   ручку `/order-print-tape`.

### Полоса B · Склады (широкий доменный сдвиг)

1. **04-A — влить ветку `fix/warehouse-single-20260821`.** Она уже закрывает
   инцидент 20.08 и вычищает служебные подстановки; независима от полосы A.
2. **04-B — переключатель склада как общий компонент.** Новый UI-элемент,
   переиспользуется в приёмке/отгрузке/переносах/поставках/упаковке.
3. **04-C — сканер понимает штрихкод склада.** Требует поле `Warehouse.barcode` и
   правки мобильного клиента.
4. **04-D — снос костыля `_try_deduct_from_alternative_sorting_location`.**
   Заменяем настоящим `movement` X→Y при кросс-складском подборе (`fbs_picking_service`).
5. **04-E — preflight-нотисы на создании поставки.** Уже частично в WIP; довести до
   рабочего вида и покрыть тестом.

Полоса B не пересекается с полосой A по файлам, кроме `FfFbsSupplyWorkspace.tsx`
(шапка, куда 04 ставит переключатель, а 02/03/06 правят её же). Значит 04-B и
04-D делать **после** того, как 02, 03, 06 из полосы A уже влиты — иначе три
одновременных правки одной шапки дадут конфликты.

### Полоса C · Новые домены (тарифы, отчёты)

1. **08 + 09 идут связкой, начинать одновременно.** Общий журнал начислений
   (`billing_ledger`) и общий паттерн «снимок тарифа» — если резать их последовательно,
   вторая карточка перепишет модель первой. Продуктовое исследование делаем на две
   карточки сразу, миграцию модели — тоже одну общую.
2. **Внутри связки: сначала реквизиты селлера + пустой каркас `billing_ledger`,
   потом тарифы (в 08 — литр-день, в 09 — за документ/за штуку), потом счёт как
   документ.**
3. **07 — раздел отчётности.** Идёт после 08+09 (данные оттуда), но UI-исследование
   и продуктовые вопросы можно вести параллельно. Один разрез — «Движения по товару»
   — уже работает, его переиспользуем как первый пункт нового раздела.

Полоса C ни в одну строку кода из A и B не лезет; её можно катить полностью
параллельно с ними, никаких блокировок по файлам нет.

### Общий вывод по порядку

- Ночь начинается с **вливания трёх готовых веток** (`fix/no-distribution-20260821`,
  `fix/wb-meta-method-20260821`, `fix/warehouse-single-20260821`). Без этого любая
  свежая карточка на файлах `FfFbsSupplyWorkspace.tsx` / `fbs_marking_service.py` /
  `App.tsx` сядет на конфликт.
- Полоса A режется строго последовательно (03 → 01 → 02 → 05 → 06), потому что все
  пять карточек толпятся в одном экране `S-03` и в одном сервисе меты.
- Полоса B параллельна A до момента, когда 04 пойдёт в шапку `FfFbsSupplyWorkspace`
  и в кросс-складской подбор — этот шаг ставим **после** полосы A.
- Полоса C (07/08/09) не задевает A и B по коду; её можно вести параллельно с обеими.
