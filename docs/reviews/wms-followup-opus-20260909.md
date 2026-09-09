# WMS-277 / WMS-394 / WMS-395 / WMS-396 / WMS-401 / WMS-403 / WMS-404 — Opus final review

CLI session: e4e0a5b1-2d0b-42bc-8dd9-3b919ef15f6b; requested effort max. Frozen application SHA7259d630af123df0fe57e74824e99324e564190d against054897e270533d3e0fc65b651d420b3af8332fce. Review is read-only; external acceptance limitations below remain explicit.

Финальное read-only ревью остатка релиза поверх уже согласованной части TrueAPI. HEAD фрозен-чекаута я взял из задачи — `7259d630`, продакшн-точка `054897e2`. Оба SHA заявлены задачей; git не запускал (условие только Read/Grep/Glob), поэтому оперирую ими как объявленными.

## Итог

**Reviewed frozen candidate: `7259d630` (`.worktrees/wms396-staging-release`). Сравнение против прод `054897e2`. Ветка TrueAPI (e574) уже проверена и присутствует здесь без изменений — не перечитывал.**

Новых блокеров в коде я не нашёл. Все остальные правки (WMS-277 hourly каталог, WMS-401 optional `order_id`, WMS-394/395/403/404 UI + правки Astra) поверх TrueAPI выглядят корректными и совместимыми. Реальная приёмка на стенде/бою для нескольких кусков остаётся невыполненной — это отдельный от кода блокер, о нём ниже.

## Что проверено в остатке диффа

### WMS-401 — optional `order_id` в существующем `/pick/scan`

- Поле `order_id: uuid.UUID | None = None` только пробрасывается вниз (`backend/app/api/fbs_supplies.py:230,1311`, `backend/app/services/fbs_picking_service.py:624,786,925`).
- Все прежние проверки сохранены: `_load_supply` даёт поставку строго по tenant; `_eligible_orders_for_product`/`_eligible_positions_for_product` (`fbs_picking_service.py:1693-1716`) не пропускают отменённые/уже подобранные/чужие; при `order_id` вне eligible выдаётся 409 `product_not_in_supply` (`fbs_picking_service.py:1035-1062`); отменённый заказ с валидной привязкой к поставке → 409 `order_cancelled` через `order_belonged_to_supply` (`fbs_cancelled_after_pack_service.py:113`, проверяет `tenant_id` и `seller_id`); контейнерная валидация (`invalid_container_reference`) не обходится — `test_wms397_pick_scan_order.py:251-264`.
- Idempotency: `_find_pick_by_scan_idempotency` первым делом возвращает существующий workspace (`fbs_picking_service.py:930-932`); повтор с тем же ключом даже при новом `order_id` не создаёт второй подбор — покрыто `test_replay_keeps_original_order_and_new_key_rejects_already_picked`.
- Cross-tenant/cross-supply/чужой товар доказаны в `test_foreign_tenant_order_product_and_supply_are_not_pickable`.
- Складского эффекта нет: тесты сверяют `warehouse_snapshot == before` для отменённых/невалидных путей и для Ozon-ветки.

Замечаний нет. Поле добросовестно опционально и не открывает нового обхода валидаций.

### WMS-277 — часовой импорт WB-каталога

- Beat: `crontab(minute=17)` каждый час (`backend/app/celery_app.py:28-31`), тонкая обёртка `run_wb_catalog_hourly_sync_task` вызывает `run_wb_products_sync_all_sellers` (`backend/app/tasks/background_jobs.py:35-40`). Тест `test_hourly_schedule_uses_existing_task_executor` фиксирует и минуту, и все 24 часа.
- Выборка селлеров — только WB Content: `SellerWildberriesCredentials.content_token_encrypted.isnot(None)` **и** `!= ""` (`wildberries_product_sync_service.py:117-120`); Marketplace scope и складская публикация как условие не используются, Ozon не затронут.
- HTTP вне DB: `_sync_scheduled_seller` явно закрывает `SessionLocal` до `fetch_all_wb_cards` и открывает вторую сессию только для сохранения (`wildberries_product_sync_service.py:82-105`); тест `test_connected_sellers_isolated_and_http_has_no_open_read_session` через `tracked_session` фиксирует `opened == 0` в момент HTTP.
- Проверка селлера/токена после HTTP: если `content_token_encrypted` очищен/подменён во время fetch — ответ выбрасывается c `content_token_changed` (`wildberries_product_sync_service.py:100-104`, покрыто `test_disconnect_during_http_discards_response`).
- Ошибка одного селлера не рушит обход: `except WildberriesSyncError` c per-code группировкой и `except Exception` в общем цикле (`wildberries_product_sync_service.py:138-174`); тест `test_connected_sellers_isolated_and_http_has_no_open_read_session` подтверждает 2 ok / 1 failed.
- Дедуп с ручным путём: `select(BackgroundJob.id).where(job_type == "wildberries_cards_sync", status in pending/running, payload_json['seller_id'] == seller_id)` (`wildberries_product_sync_service.py:83-89`). Продавец пропускается с `manual_sync_active`. Тест `test_active_manual_job_skipped_then_terminal_job_allows_import` проверяет обе стороны.
- Каталог не пишет в склад/остаток/резерв: `_save_wb_cards` вызывает только `upsert_imported_cards` и `upsert_products_from_wb_cards`; `test_connected_sellers_isolated_and_http_has_no_open_read_session:101-102` сверяет `count(InventoryBalance)=0` и `count(InventoryMovement)=0`; `test_wildberries_products_full_sync.py:78,109` дублирует эту гарантию на 205-карточной пагинации и последующем реальном импорте заказа с одним резервом.

**Явно принятые ограничения по этому куску, зафиксированы в `docs/reviews/wms277-catalog-hourly-20260909.md:48-63` и в коде честно оставлены:**

1. **Дедуп охватывает только `BackgroundJob`**. Синхронная кнопка селлера `/integrations/wildberries/self/sync-products` (`backend/app/api/wildberries_integration.py:578`) не создаёт `BackgroundJob` и не попадает под фильтр. Одновременный ручной клик + часовой запуск могут вызвать `IntegrityError` на `uq_wb_imported_card_seller_nm` (`backend/app/models/seller_wildberries_imported_card.py:21`) — один из двух импортёров этого селлера упадёт, следующий часовой прогон вернёт согласованность. `upsert_products_from_wb_cards` (`wildberries_product_import_service.py:268-278`) сам ловит IntegrityError и делает rollback+lookup, так что коллизия по Products не считается ошибкой. Данные не портятся, ложных остатков не возникает; это UX-шум.
2. **Между двумя параллельными часовыми запусками общего замка нет**. Два worker-процесса Celery получат из beat очереди две задачи и оба сядут на общий список селлеров, каждый со своим `_PACING`-неотносящимся к этому куску. То же поведение по коллизиям.
3. **Атомарной отмены многошагового сохранения нет.** `_save_wb_cards` делает `upsert_imported_cards.commit()`, затем продолжает `upsert_products_from_wb_cards`; исключение на второй половине оставит уже сохранённые snapshots — они догоняются штатно следующим запуском. Транзакционность целого каталога в задачу WMS-277 не заявлялась.

Ни один из этих трёх пунктов не даёт ложного «пересобрать»/«отгрузить» и не трогает склад. Как блокер релиза не квалифицирую.

**Не проверено:** живой запуск часового scheduler на стенде — `wms277-catalog-hourly-20260909.md:88-94` явно фиксирует «не проверен и не выложен», синтетический Content transport для приёмки не подключался. Это внешний блокер приёмки, не блокер кода.

### WMS-394/395/403/404 — точечный UI

- Сброс активного заказа: `dropKizScanActive` (`frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:686-697`) очищает только UI-состояние сканера (`kizScanActive`, `kizSelectedStickerRef`, значение, ошибки, подсказки, notice, debug, оба confirm-стейта) и возвращает фокус. Никаких HTTP/склада.
- Триггеры сброса: явная кнопка «Сбросить» (`FfFbsSupplyWorkspace.tsx:1943-1946`, `data-testid="fbs-kiz-scan-reset"`), Escape в input при активном заказе (`FfFbsSupplyWorkspace.tsx:702-707` — `event.stopPropagation()` не даёт Escape закрыть внешний Dialog), и повторный скан того же стикера (`FfFbsSupplyWorkspace.tsx:712-715`).
- Правило совпадения стикера — `fbsSameStickerScan` (`frontend/src/screens/v2/fbsUx.ts:428-447`): нормализует пробелы/BOM/`\u001c-\u001f`, только для строк с кириллицей/`№` строит альтернативный кандидат через раскладку. Пары раскладок посимвольно совпадают с backend-`_KEYBOARD_LAYOUT_PAIRS` в `backend/app/services/fbs_kiz_service.py:130-146`. Регистр латиницы сохраняется, чужой заказ или ЧЗ отличаются — покрыто `fbsUx.test.ts:64-79`.
- Правка Astra по Escape на кнопке: внешний `Dialog.onClose` перехватывает `reason === 'escapeKeyDown'` и, если активен скан или идёт запрос, вместо закрытия зовёт `dropKizScanActive` (не зовёт при `kizScanBusy` — операция в полёте не прерывается) (`FfFbsSupplyWorkspace.tsx:1559-1565`). Escape без активного скана прежним путём закрывает окно — не сломано.
- Правка Astra по контрасту: фон ошибочной строки `alpha(theme.palette.error.main, 0.08)` вместо `error.light` (`FfFbsSupplyWorkspace.tsx:2041-2042`). Текст остаётся `error.main` (`FfFbsSupplyWorkspace.tsx:2027-2028`), бордер слева `error.main` — читаемость улучшена, ошибочная строка визуально не теряется.
- Значок ошибки с подсказкой рядом со статусом (`FfFbsSupplyWorkspace.tsx:2078-2083`): `ErrorOutlineIcon` внутри `Tooltip`, aria-label и tabIndex=0 — доступно с клавиатуры и скринридера.
- Вердикт после сохранения: `load` теперь возвращает свежий workspace (`FfFbsSupplyWorkspace.tsx:388`); в `scanKizCode` для WB подбирается `savedOrder.metadata.states.find(kind === 'sgtin')` и `fbsMarkingPresentation` даёт tone/label/reason (`FfFbsSupplyWorkspace.tsx:658-667`). Для WB backend кладёт ровно одну текущую sgtin-запись на kind в `build_order_metadata` (`backend/app/services/fbs_marking_service.py:462-479`) — неоднозначности порядка нет. Успешное сохранение не подменяет отрицательный вердикт WB.
- Inline «Отменить КИЗ»: строго `!isOzonSupply && hasOperatorKiz(order, true)` (`FfFbsSupplyWorkspace.tsx:2127-2132`), открывает прежний confirm `kizUndoOrderId` (`FfFbsSupplyWorkspace.tsx:2593-2618`), который зовёт существующий `deleteFbsOrderKiz` → `DELETE /operations/fbs-orders/{order_id}/kiz` → `cancel_order_kiz` (`backend/app/api/fbs_kiz.py:216-232`, `backend/app/services/fbs_kiz_service.py:1187-1241`). Серверный `_current_sgtin_marking_for_update` уже вызывается с `include_rejected=True` в `cancel_order_kiz:1197`, backend не менялся.
- Меню «Перепечатать»: `hasOperatorKiz(reprintOrder, !isOzonSupply)` (`FfFbsSupplyWorkspace.tsx:2634`) — для Ozon `includeRejected=false` (прежнее поведение сохранено), для WB расширяется до отклонённых. **Никакой новой поверхности для непроверенной Ozon-отмены** не открывается; `_delete_sgtin_from_wb` (`fbs_kiz_service.py:1077-1099`) явно ранним `return` пропускает удалённое удаление в чужой WB-кабинет по синтезированному номеру Ozon.
- Навигация вкладок не менялась; складских эффектов, блокеров вкладок, редизайна — нет. Правки только в `FfFbsSupplyWorkspace.tsx` и `fbsUx.ts`.

## Мелкие наблюдения (не блокеры)

- `stickerKeyboardMap` во фронте включает identity-пары (напр. русская «.» → английская «/», пары с «"», «;», «:», «?», «/» → «@#$^&|»). Для чисто латинского стикера гейт `/[\u0400-\u04ff№]/.test(char)` не срабатывает, репаир не создаётся — семантика идентична backend `_KEYBOARD_LAYOUT_MAP` (там ещё явно отфильтрованы точные equal-пары, но у нас таких нет). Ничего не ломается.
- `_sync_scheduled_seller` бросает `SessionLocal` дважды на один цикл продавца. На больших нагрузках это удваивает соединения на короткий момент по сравнению с прежним ручным путём `sync_wb_products_for_seller`, но это сознательный компромисс за «нет DB-сессии во время HTTP». Не блокер.
- Дедупный `select(BackgroundJob.id).where(payload_json['seller_id'] == …)` — по полю JSON без индекса, вычисляется после отсечения по `tenant_id`-индексу. При большой истории `BackgroundJob` даёт последовательное сканирование срезки тенанта. Не критично.
- Синхронный `/self/sync-products` (`wildberries_integration.py:578-620`) держит FastAPI-сессию поверх HTTP-пагинации; это **прежний** тех.долг, не относится к WMS-277 и в диффе не менялся. Просто фиксирую, чтобы не путать с сегодняшним scheduler.
- Escape во время `kizScanBusy` при фокусе на input — тихо игнорируется без визуальной реакции. Фон-клик закрывает диалог как и прежде. Асимметрия минимальна, интеграционный ущерб — нулевой.

## Что не проверено (внешние границы приёмки, не блокеры кода)

- **Живая приёмка hourly WB catalog** на стенде под настоящим Content-токеном не проводилась (`wms277-catalog-hourly-20260909.md:88-94`). До неё нельзя утверждать, что часовой прогон реально совместим с фактическим ответом WB Content API `/content/v2/get/cards/list` в тех кабинетах, где живёт стенд.
- **Настоящий круговорот `deleteFbsOrderKiz` против живого WB API** для отклонённого КИЗ не подтверждён — в браузерной сессии Root DELETE-ответ подменялся синтетикой (`wms394-395-403-404-ui-20260909.md:39-47`). Кодовая логика корректна, но факт удаления в живом WB для rejected KIZ впервые пройдёт только на стенде/бою.
- **Живая позитивная проверка TrueAPI** — из ранее уже принятого раздела остаётся открытой (`wms396-live-check-readiness.md:31-37`): у QA-селлера нет `cz_token_enc`. Не меняется этим релизом.
- **Общий межпроцессный лимит частоты TrueAPI** и **межпроцессный dedup WMS-277** — принятые ограничения, зафиксированные в отчётах Astra и координатора.

## Финальный вердикт

- **Reviewed SHA: `7259d630`** против прод `054897e2`. Ветка TrueAPI e574 включена целиком без изменений и повторно не читалась.
- **Блокеров в коде остатка релиза не вижу.** WMS-401 — минимальное безопасное расширение существующего сканера, все прежние валидации сохранены. WMS-277 — тонкая обёртка существующего импорта, HTTP вне DB, per-seller изоляция, никаких складских эффектов; принятые ограничения на дедуп/атомарность честно отражены в коде и в отчёте. WMS-394/395/403/404 UI — локальный сброс без HTTP, WB-only inline-крестик, Ozon-меню не расширяется, правки Astra по Escape и контрасту приняты корректно.
- **Открытые границы приёмки, требующие живой проверки перед production**, а не правки кода:
  1. Живой прогон часового scheduler на стенде на настоящем WB Content-токене с проверкой конкретного нового товара в каталоге и последующего обычного FBS-импорта заказа.
  2. Живое DELETE отклонённого КИЗ через `/operations/fbs-orders/{order_id}/kiz` в WB-кабинете стенда.
  3. Ранее объявленный живой позитивный вызов TrueAPI (`cises/info`+`cises/check`) с реальным JWT участника.
- **Явно принятые ограничения**, о которых договорились и которые я не переопределяю в блокер: process-local pacing TrueAPI, отсутствие межпроцессного dedup WMS-277 против synchronous seller-button, отсутствие транзакционной отмены многошагового каталогового сохранения при отключении во время сохранения.

Живьём в браузере и вживую в WB/CRPT/Ozon API эту ветку я не проверял и это специально не выдаю за проверенное.
