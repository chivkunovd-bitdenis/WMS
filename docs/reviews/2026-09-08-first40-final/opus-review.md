Инструмент Write в этом контексте недоступен — не могу записать план-файл. Отдаю итоговое ревью прямо в ответе, как основной deliverable.

---

# Итоговое ревью первых сорока задач WMS перед staging

## Контекст

Проверял `.worktrees/backlog40-review-20260908` на коммите `e2ef7257`; база staging — `6afa60e7`. Список 40 задач заморожен в `docs/KANONICHESKIY_BACKLOG.md:114`. Прочитал реальный код по каждому файлу из `changed-files.txt` и трассировал сквозные пути (подбор/резервы/отмена/упаковка/передача/маркировка/печать/поиск/приёмка/биллинг/конкуренция).

Ниже — только доказанные утверждения с файлами и строками. Отделяю «сделано корректно» от «дефекты в этой пачке».

## Договор владельца соблюдён (проверено по коду)

**WMS-392 / WMS-043 — упаковка = признак**
- `backend/app/services/fbs_packaging_integration_service.py:513-635` — `record_fbs_pack_progress` больше не вызывает `apply_packaging_convert`, из сигнатуры выпилены `fail_on_insufficient_stock` и `allow_alternative_sorting_fallback`; docstring «without touching warehouse stock».
- `backend/app/services/fbs_packaging_stock_service.py` — файл удалён целиком (был путь «списать из другой ячейки сортировки»).
- `backend/app/services/fbs_picking_service.py:1036-1046, 1249-1256` — сняты блокеры `order_already_packed` в `scan_pick_product` и `pick_undo_not_allowed` в `undo_pick`. Отмена подбора после упаковки работает.
- `backend/app/services/fbs_packing_box_service.py:346-349` — снят блокер `order_not_packed` в `assign_orders`.
- `backend/app/services/fbs_ozon_packaging_service.py:89-95, 196-215` — из Ozon-пути убрана проверка `pick_status != PICKED` и «упаковочный рецепт» источника; выбор источника теперь всегда через планировщик.
- `backend/app/services/packaging_task_service.py:939-955, 1074-1097` — из `record_pack_progress` / `undo_last_pack_action` удалены `apply_packaging_convert`/`reverse_packaging_convert`; `_apply_acknowledge_all_packed` удалён.
- `backend/app/services/packaging_task_service.py:1370-1380` — `assert_unload_packaging_done` переименован в `assert_unload_marking_done`, требование «упаковка = done» снято.
- `backend/app/services/marketplace_unload_service.py:1030-1033` — на `/ship` вызывается новая функция, `packaging_not_done` больше не поднимается.
- **Regression-guard проверен:** `backend/app/services/fbs_workspace_service.py:259-265` — правило `status == assembling → picking` не восстановлено ни под каким именем.

**WMS-042** — тем же снятием блокеров и container-aware undo (см. WMS-058 ниже).

**WMS-058 — одна формула «доступно»**
- `backend/app/services/pick_option_location_service.py:115-125` — `source_available(on_hand, source_assigned, place_free, place_assigned, warehouse_ceiling)`; `min()` учитывает и точный источник, и место, и потолок склада.
- `pick_option_location_service.py:58-112` — `active_fbs_picks_by_source` считает конкретный контейнер + «безместные» Ozon-подборы отдельным consery-way.
- `pick_option_location_service.py:128-175` — единая `available_pick_source_quantity` используется и в FBS-подборе (`fbs_picking_service.py:1041-1050`), и в MP-сборе (`marketplace_unload_collect_service.py:320-329, 489-517`).
- `fbs_picking_service.py:528-546, 771-782, 1238-1330` — `set_pick_quantity` и `undo_pick` container-aware, возвращает в исходную тару; `_active_assignments_for_product_location` тянет `pick_id` для точного отката.
- Покрытие: `backend/tests/test_wms058_pick_availability.py:194-434` — параллельные WB-поставки не поделят одну единицу, Ozon undo возвращает в исходный короб, MP-сбор не съедает FBS-резерв.

**WMS-040 — конкурентная приёмка**
- `backend/app/services/inbound_intake_service.py:384-408, 1185-1195` — `complete_receiving` теперь читает `for_update=True` с `populate_existing=True` до проверки статуса.
- Покрытие: `backend/tests/test_inbound_receiving_concurrency.py`.

**WMS-045 — фоновая починка не хватает чужой WB-операции**
- `backend/app/services/fbs_supply_service.py:1389-1395, 1518-1526` — фильтр `operation_kind == OPERATION_KIND_SUPPLY_FROM_ORDERS` есть и в `_close_pending_operation_if_complete`, и в `repair_pending_supplies_for_seller`.
- Новый вид `OPERATION_KIND_ORDER_KIZ_BIND` (`backend/app/services/fbs_marking_service.py:81`) под этот ремонт не попадает, отдельная сверка в `fbs_kiz_service.pending_kiz_operation`.

**WMS-047 / WMS-046 / WMS-048** — `backend/app/cli/reconcile_fbs_shipped_stock.py` удалён, никаких новых скриптов, применяющих правки к боевым записям, в диффе нет. WMS-048 — расследование без правок исторических данных.

**WMS-010 / WMS-011 — биллинг**
- `backend/app/services/billing_configuration_service.py:22-24, 205-215` — `document` убран из допустимых единиц для `inbound`/`marketplace_outbound`, репрайсинг теперь по `entry.quantity`.
- `backend/app/services/billing_invoice_v2_service.py:317-345, 404-427` — проверка `selected_source_already_invoiced` и `SELECT ... FOR NO KEY UPDATE` на строке селлера для сериализации конкурирующих выставлений.
- Покрытие: `backend/tests/test_billing_configuration_api.py:5194-5227`, `backend/tests/test_billing_invoice_v2_duplicates.py` (целиком новый).

**WMS-013** — скрипта, создающего исторические записи, в диффе нет. Соответствует статусу `РЕШЕНИЕ ВЛАДЕЛЬЦА`.

**WMS-080 — гонка печати**
- `backend/app/services/marking_code_service.py:1338-1352` — блокировка строки задания `with_for_update().execution_options(populate_existing=True)` в `print_codes_for_packaging_line`; после ожидания чужой печати потребность перечитывается.

**WMS-082 — WB не подтвердил, код в пул не возвращается**
- `backend/app/services/fbs_kiz_service.py:1234-1293` — при `wb_transport_error`, `wb_upstream_error_408`, `wb_upstream_error_5xx` или `META_STATUS_SENDING` привязка остаётся в `META_STATUS_UNKNOWN`, заводится `FbsWbOperation(operation_kind=ORDER_KIZ_BIND, state=PENDING_CONFIRMATION)`; код в свободный пул не уходит.
- `backend/app/services/fbs_marking_service.py:685-704, 785-820` — очередная GET-сверка автоматически переводит операцию в `CONFIRMED` или `FAILED` по ответу WB.

**WMS-081 — код нанесён = STATUS_APPLIED**
- `backend/app/services/fbs_kiz_service.py:1275-1292` — на сканирование КИЗ код переводится в `STATUS_APPLIED` с `applied_at`, событие `EVENT_APPLIED` пишется до синхронного ответа WB.
- Покрытие: `backend/tests/test_fbs_kiz_applied.py` — режимы `available_pool`, `available_external`, `printed`, `printed_bound`, `reserved_bound`, `wrong_line`; переход идемпотентен, счётчики строки не двоятся.

**WMS-083 — PDF-импорт не обрезает КИЗ**
- `backend/app/services/marking_code_service.py:551-565` — `_parse_csv_rows` теперь разбивает по `[\r\n]+`, GS-разделитель не считается концом записи.
- `marking_code_service.py:960-968` — для PDF-строк `label_pdf` `cis` сохраняется как есть без `normalize_cis`.
- Новый `backend/app/services/marking_datamatrix_service.py:1-70` — реальный декод DataMatrix со страниц PDF.
- `marking_code_service.py:637-660` — `is_printable_label_artifact` считает страницу валидной по декодированному DataMatrix, а не только по видимой подписи.

**WMS-084 — отвязка КИЗ на упаковке (веб)**
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1027-1145, 2408-2430` — «Очистить ЧЗ» для выбранных заказов, диалог подтверждения, остановка на первом отказе WB, счётчик очищенных. Физический перенос кода с заказа на заказ (реассайн) в этой пачке не появляется — соответствует `ЧАСТИЧНО В ВЕТКЕ`.

**WMS-086 — вердикт WB на упаковке**
- `backend/app/services/fbs_worklist_service.py:995-1030` — `_build_metadata` показывает наблюдаемые привязки, даже когда WB не прислал требование; поле `decision` берётся из `meta_details_json`.
- `frontend/src/screens/v2/fbsUx.ts:401-434` — `fbsMarkingPresentation` красит строку по фактическому вердикту (`rejected` / `replacement_required` / `accepted` с reason → красный; `assigned`/`sending`/`pending`/`unknown`/`allowed_without_check` → нейтральный; чистый `accepted` → зелёный).
- Покрытие: `frontend/src/screens/v2/fbsUx.test.ts:32-64`.

**WMS-087 — реальные статусы ЧЗ**
- Синхронизация идёт по границе GET заказа (см. WMS-082). Отдельного пачечного GET-эндпоинта по всем кодам в этой пачке нет — соответствует статусу `ЧАСТИЧНО`.

**WMS-091 — код всегда привязан к товару + колонки ленты**
- `backend/app/services/marking_code_service.py:1193-1201, 1546-1560, 3197-3220` — везде, где выбирается доступный пул-код, добавлено `or_(MarkingCode.product_id.is_(None), MarkingCode.product_id == product.id)`.
- `marking_code_service.py:1762, 1884, 3244` — при печати и `replace_reprint_request` код получает `product_id = product.id`.
- `backend/app/api/marking_codes.py:967-985, 1024-1040` — ленту и экспорт можно смотреть только `FULFILLMENT_ADMIN`.
- `frontend/src/screens/shared/HonestSignLedgerPage.tsx:323-411` — колонки «Товар / артикул», «Тип документа / место печати», «Номер документа», «Сотрудник», «Дата и время».

**WMS-092 — «Сдать без ЧЗ» + повторная печать сохранённого кода**
- `backend/app/services/fbs_order_tape_print_service.py:150-296` — пропуск не блокирует печать уже сохранённого КИЗ, только выключает автовыдачу новых из пула.
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:948-970` — `requiresOrderHonestSign` возвращает `true` даже со снятым флагом, если у заказа привязан ЧЗ.

**WMS-095 — перевод машинных ошибок**
- `frontend/src/screens/v2/fbsUx.ts:114-208` — таблица `FBS_ERROR_TEXT` покрывает 29 машинных кодов + `wb_upstream_error_NNN`/`ozon_upstream_error_NNN` по HTTP; общий fallback для snake_case-кодов.
- Хелпер `fbsErrorText` применён во всех вызовах ошибок в `fbsApi.ts`, `FfFbsSupplyWorkspace.tsx`, `FbsSupplyCreateDialog.tsx`.

**WMS-085 — печать по товарам + доступно ЧЗ**
- `FfFbsSupplyWorkspace.tsx:1257-2100` — чекбоксы, «Выбрать всё / Снять выбор», меняющаяся кнопка «Печать выбранного / Печать всего», отдельная «Очистить ЧЗ», отображение «Доступно ЧЗ: X · нужно Y» с окраской нехватки.

**WMS-096 — восстановление обрезанных КИЗ**
- `backend/app/services/marking_code_service.py:3468-3679` — `restore_truncated_pool_cis_codes`: отдельные сессии, dry-run по умолчанию, проверка префикса/GTIN/пула/продукта/serial, отказ при неоднозначности и уже привязанных.
- CLI: `backend/app/cli/restore_truncated_marking_cis.py:1-39` — обязателен tenant.

**WMS-115 / WMS-110 — отменённые после упаковки**
- `backend/app/services/fbs_cancelled_after_pack_service.py:100-108, 187-260, 465-500` — расширенный `_assembly_trace_condition`, новые `list_cancelled_supply_orders`, `delivery_cancelled_orders`, `exclude_cancelled_delivery_orders`; поиск на списке.
- `backend/app/services/fbs_shipment_service.py:1173-1183, 2443-2447` — preflight возвращает `cancelled_orders`, перед `deliver_supply` снимаются логические связи без физического возврата остатка.
- API + фронт: `backend/app/api/fbs_supplies.py:98-117, 1261-1275`, `backend/app/api/fbs_orders.py:205-224`, `frontend/src/screens/v2/FbsCancelledAfterPackDialog.tsx:1-130`, `FfFbsOrdersScreen.tsx:1224-1230`, `FfFbsSupplyWorkspace.tsx:2577-2620` (кнопка «Передать без этих заказов»).

**WMS-123 — режим «без распределения» после раскладки**
- `backend/app/api/fbs_supplies.py:1546-1568` — новая ручка `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution`.
- `backend/app/services/fbs_packing_box_service.py:273-310` — сервис пишет флаг на поставку; локальный UI-state удалён (`FfFbsSupplyWorkspace.tsx:2094-2110`).

**WMS-272 — ограничение конкуренции создания**
- `backend/app/services/marketplace_seller_lock_service.py:32-95` — `release_connection_while_waiting=True` делает `session.rollback()` во время сна.
- `backend/app/services/fbs_supply_service.py:581-610, 940-1063` — путь `create_supply_from_orders` открывает lock с этим флагом; `_resume_from_orders_operation` делает `session.commit()` + `session.expire_all()` перед каждым HTTP-сегментом. Оговорка владельца в тексте задачи (создающий держит соединение всё время WB HTTP) соблюдена — новых блокирующих сущностей нет.

**WMS-273 — печать ленты не вешает API**
- `backend/app/services/marking_code_service.py:305-320, 3155-3175, 693-720` + `backend/app/api/marking_codes.py:1256-1275` — `asyncio.to_thread` вокруг PDF/DataMatrix, батчевая валидация `_label_artifact_flags` и `_validated_label_artifact_tape`.

**WMS-276 — полная пагинация**
- `backend/app/services/wildberries_sync_service.py:28-108` — единая `fetch_all_cards` с защитой от stall (`pagination_stalled`), rate-limit `0.6s` для контент-API и `2s` между страницами поставок. `sync_cards_list_first_page` переименована в `sync_cards_list`.
- `backend/app/services/background_job_service.py:139-220`, `backend/app/api/wildberries_integration.py:471-608`, `backend/app/services/wildberries_product_sync_service.py:27-34` — все вызовы переведены на общий проход, лимит «250 итераций» снят.
- `frontend/src/App.tsx:2381-2540` — фронтовый опрос job'а на 1s тиках, прерывается через `AbortController` при уходе с экрана.

**WMS-278 — статус ключа WB у селлеров пачкой**
- `backend/app/services/wildberries_credentials_service.py:63-90` — `list_public_marketplace_statuses` возвращает `(has_key, marketplace_scope_ok, checked_at)` без расшифровки токенов.
- `backend/app/api/sellers.py:88-118` — `GET /sellers` отдаёт три поля.
- `frontend/src/screens/v2/SellersScreen.tsx:198-232` — колонка «WB Marketplace» с 4 состояниями и временем последней проверки.

**WMS-389 — инвентаризация по выбранным товарам**
- `backend/app/api/inventory_counts.py:40-55, 692-698` и `backend/app/services/inventory_count_service.py:64-70, 311-315` — приём `product_ids`, условие `Product.id.in_(product_ids)`.
- `frontend/src/screens/ff/inventory/InventoryCreateDialog.tsx:1-135` — Autocomplete, пустой выбор сохраняет прежний охват.

**WMS-390 — серверный поиск**
- `backend/app/services/fbs_worklist_service.py:192-330` — общие `supply_number_search_clause` / `order_search_clause` через `EXISTS` (без JOIN-дубликатов), total на том же фильтре.
- `backend/app/services/fbs_supply_service.py:1207-1345` — тот же поиск на списке поставок.
- API `total` в `backend/app/api/fbs_orders.py:544-560` и `backend/app/api/fbs_supplies.py:1216-1235`.
- `FfFbsOrdersScreen.tsx:588-720, 1298-1370` — debounce 250 мс, `AbortController` через `loadSequence`, «Найдено X · показано Y».

**WMS-391 — начисление на подтверждённой передаче**
- `backend/app/services/fbs_order_billing_service.py:85-190` — `record_fbs_order_confirmed` для статуса `in_delivery` **отказывает**, если `confirmed_handover_at` не передан; момент подставляется из `supply.delivered_at` или сохранённого `operation.confirmed_at`; `charge_handed_over_orders` оборачивает вызовы в `session.begin_nested()`.
- `backend/app/services/fbs_shipment_service.py:1206-1218, 1691-1725` — вызывается из `_apply_local_delivered`; `supply.delivered_at` пере-выставляется как `supply.delivered_at or operation.confirmed_at or now` — дата не «плывёт» при поздних синках.
- Покрытие: `backend/tests/test_fbs_handover_billing.py` — 5 сценариев (`success`, `marketplace_error`, `billing_error`, `timeout`, `local_error`) + `test_handover_quantities_import_guard_and_cancellation` (импорт `in_delivery` не начисляет, отменённый не начисляет, дедуп по service_code).

**WMS-393** — уже на проде (`docs/KANONICHESKIY_BACKLOG.md:67-107`), в этой ветке `FfFbsSupplyWorkspace.tsx:558-620` содержит тот же код (`focus({ preventScroll: true })`, повторный `load(true)` при отсутствии заказа в списке, повторная прокрутка через `requestAnimationFrame`). Регрессии не вижу.

## Найденные дефекты (по приоритету)

### 🔴 БЛОКЕР — тесты MP-отгрузки ждут исчезнувший `packaging_not_done`

`backend/tests/test_marketplace_unload_and_discrepancy_acts.py:1201-1202` и `:2911-2913`.

**Триггер:** после смены `assert_unload_packaging_done` → `assert_unload_marking_done` в `marketplace_unload_service.complete_unload:1030-1033` ручка `/ship` больше не поднимает `packaging_not_done`. Первый тест кинется на `distribution_incomplete` (ни одного распределения; сервис возвращает его на строках `1035-1037`), второй тоже — коробы пустые. Ассерты `== "packaging_not_done"` завалятся.

**Влияние:** полный `pytest -n auto` на CI будет красным, staging не пройдёт technical gate.

**Минимальная правка:** сменить ожидание на `distribution_incomplete` (или довести распределение и проверить, что `/ship` теперь проходит без `packaging_not_done`, потому что упаковка перестала быть блокером). Не возвращать `packaging_not_done` в сервисе.

### 🟠 СРЕДНИЙ — мёртвый код `packaging_not_done` в маппере ошибок

`backend/app/api/marketplace_unload_requests.py:692, 730` и `frontend/src/utils/readApiErrorMessage.ts:31`.

Сервис код больше не поднимает, но обработчик и текст висят «в холостую». По правилу AGENTS «галка — это галка, не сущность» — стоит убрать.

**Правка:** удалить `"packaging_not_done"` из двух списков в `_map_pick_err`/`_map_box_err` и запись в карте фронта. Не блокер, но остаточная сущность в дизайне ошибок.

### 🟠 СРЕДНИЙ — WMS-115 покрывает только WB

`backend/app/services/fbs_cancelled_after_pack_service.py:190-193, 470` — фильтр `FbsOrder.marketplace == "wb"` в `list_cancelled_supply_orders` и в `fetch_cancelled_after_pack_page`. `FfFbsSupplyWorkspace.tsx:1310` — `cancelledDeliveryOrders = isOzonSupply ? [] : ...`. Кнопка «К вскрытию · Wildberries» показывается только при `marketplace !== 'ozon'` в `FfFbsOrdersScreen.tsx:1224-1230`.

Соответствует буквальной формулировке WMS-115 (постановка про WB), но по духу «отменённые после упаковки не должны прятаться» — для Ozon-поставок этот путь просто отсутствует. Не блокер, требует решения владельца.

### 🟠 СРЕДНИЙ — WMS-391: внешне пришедший `sorted`/`done` без нашей передачи

`backend/app/services/fbs_order_billing_service.py:95-105`.

Если WB (или Ozon autopoll) переведёт заказ сразу в `sorted`/`done` без предварительной локальной передачи (`supply.delivered_at is None`), fallback `moment = ... or order_work_moment(order)` уйдёт в `now()`. Договор владельца требует привязки к моменту передачи, а не к моменту наблюдения. Влияние ограничено — по типовому пути «наша кнопка Передать» дата берётся из `supply.delivered_at`. Не блокер, стоит спросить владельца, как обрабатывать «внешне пришло sorted, мы не передавали».

### 🟡 НИЗКИЙ — асимметрия Ozon vs WB в порядке transaction'ов передачи

`backend/app/services/fbs_shipment_service.py:1689-1725`.

WB-путь делает `_apply_local_delivered` + `mark_deliver_operation_confirmed` + `charge_handed_over_orders` в одной транзакции с последующим `session.commit()`. Ozon-путь: `mark_deliver_operation_confirmed` → `session.commit()`, потом `_apply_local_delivered` (уже включает `charge_handed_over_orders`) в новой транзакции. Если Ozon упадёт **после** commit подтверждения, но **до** локального списания/начисления, retry должен корректно достать `operation.confirmed_at` — идемпотентность `charge_handed_over_orders` по service_code этого не сломает, но тесты `test_fbs_handover_billing.py::local_error` покрывают только WB-путь. Ручная проверка Ozon-retry желательна.

### 🟢 ИНФО

- `_fetch_orders_page` считает `total` только при поиске (`fbs_worklist_service.py:325-330`). Соответствует UI-договору, не дефект.
- Статусы `ЧАСТИЧНО` / `РЕШЕНИЕ ВЛАДЕЛЬЦА` (WMS-217, 275, 084, 087, 013) в этой пачке не переведены в «done» — что и записано в бэклоге; не требую закрывать для staging.
- В `_gate_ledger_filtered_stmt` (`marking_code_service.py:2704`) для `MarkingCode.source` фильтр по `"pool"` снят — теперь лента показывает и external-коды. Это осознанное расширение под WMS-091.

## Готовность к staging

Функционально пачка соответствует договору владельца: упаковка нигде не двигает склад и не блокирует переходы; одна формула «доступно» на все пути ФБС и МП; починка WB-операций не хватает чужих; отменённые заказы показываются и логически снимаются без физического возврата; начисление привязано к подтверждённой передаче и не двоится; создание поставки не расходует пул соединений на ожидающих; печать выведена с event-loop; поиск и пагинация на сервере.

**Единственный технический блокер по коду** — два ассерта `packaging_not_done` в `test_marketplace_unload_and_discrepancy_acts.py:1202, 2913`. Их надо переписать под новое поведение до пуша в `staging`. После этого — стандартный гейт (`ruff check .`, `mypy .`, `pytest -n auto`, `tsc --noEmit`, `npm run build`), затем `./scripts/railway-staging-deploy.sh`, сверка SHA через `/openapi.json` бэкенда и ручная браузерная приёмка владельцем.

**Функциональные оговорки без блокировки, требуют явного решения владельца перед закрытием пачки:** покрытие Ozon в WMS-115/110; поведение WMS-391 при внешне пришедшем `sorted`; уборка мёртвого `packaging_not_done` из маппера ошибок.