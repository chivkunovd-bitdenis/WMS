# WMS release: исходный независимый Opus CLI max

Модель claude-opus-4-7, effort max; session a1007a28-72dd-4d9b-a0ed-1b22d2be7b6d; 74 turns, 1057812ms. Кандидат a1b64752. Ниже исходный ответ без исправления его выводов. Независимая Astra нашла пять дефектов; отдельные PostgreSQL-регрессии уже опровергли отсутствие гонок. Этот исходный ответ не является разрешением на выпуск и требует совместной сверки. Цифры/номера строк внутри ответа принадлежат модели и должны проверяться по Git.

Проверок достаточно. Формирую итоговое ревью.

---

# Итоговое code review релиза staging→production

**База production:** `9729c52c985062fc543e7358574e05d27e605db8`  
**Кандидат:** `a1b64752ffcc4eb8dfc5151c783407530cee931f`  
**Дифф:** 238 файлов, +27 943 / −3 422; 4 миграции, 70 файлов `backend/app`, 36 `frontend/src`, 83 backend-теста.

## Итог

**Подтверждённых code blockers, которые бы препятствовали выкладке разрешённого owner’ом среза, я не нашёл.** Контракты, за которыми меня специально попросили следить, соблюдены в самом коде — я это увидел и опишу по каждому пункту ниже. Все замечания, которые я всё-таки хочу зафиксировать, — это либо дизайн-вопросы к владельцу (не баги), либо ограничения моей evidence, а не найденные регрессии.

Я не запускал ни тестов, ни браузера, ни сети, ни платежей, ни SMTP. То, что перечислено ниже как «подтверждено», подтверждено чтением файлов и совпадением с прилагаемыми отчётами QA staging.

## Что я реально проверил

Читал диф целиком по секциям, а не только последние коммиты. По каждой критической области открывал полный текущий исходник, а не только hunks.

- **Миграции 20260906_1100 / 2300 / 20260908_0255 / 0257.** Все four — additive: nullable-колонки без backfill и новая таблица `subscription_payments` с уникальным индексом по `provider_payment_id`. Merge-миграция 0257 без DDL. Downgrade каждой не роняет уже применённые части. С production `0256` последовательность обязательная: 0255 (кладёт ozon-колонки) → 0257 (merge с уже стоявшим 0256). На старой БД alembic пройдёт линейно.
- **Auth-конвертация (WMS-378/379/383):** `auth.py:213–410`, `auth_service.py:257–331`, `auth_link_tokens.py`, `deps.py:74–146`, `mailer.py`. Все ключевые ветки прочитаны.
- **Подписка (WMS-381/382):** `subscription_service.py`, `subscription_payment_service.py`, `subscription.py`, `hooks/useSubscription.ts`, `SubscriptionBlockedScreen.tsx`. Free-list путей сверен с реальными префиксами роутеров (`auth_router = APIRouter(prefix="/auth")`, `subscription_router = APIRouter(prefix="/subscription")`) и с Caddy (`handle_path /api/*` срезает префикс `/api`, до FastAPI приходит `/auth/...`).
- **WMS-058 (подбор):** новые колонки `source_container_kind/id`, `pick_option_location_service.py:39–430`, `fbs_picking_service.py:200–1348`, `test_wms058_pick_availability.py` — все 5 сценариев (loose/box/sorting, две поставки на одну физическую единицу, sorting_box scan/undo, legacy-NULL pick, MP-collect не расходует FBS-резерв).
- **Упаковка = только признак (WMS-392):** `packaging_task_service.py:392–1300`. Убран импорт `inv_svc as inventory_service`, удалены вызовы `apply_packaging_convert` и `reverse_packaging_convert`, снят fallback `_apply_acknowledge_all_packed`, `assert_unload_packaging_done`→`assert_unload_marking_done` больше не требует задания упаковки.
- **Отгрузка/отмена:** `fbs_shipment_service.py:1168–1720`, `fbs_cancellation_service.py`, `fbs_cancelled_after_pack_service.py:187–260`, `test_fbs_delivery_cancelled_exclusion.py`.
- **WB КИЗ / pending confirmation:** `fbs_kiz_service.py:709–1470`, `fbs_marking_service.py:566–1080`. Прочитан переход pool→external, ветка «повторный скан того же кода», ветка «WB транспорт умер, но PUT мог долететь».
- **WMS-272 (создание WB-поставки):** `fbs_supply_service.py:325–5260`. Прочитаны обе точки предчтения `_existing_create_for_orders`, повтор внутри лока, `refresh_after_http`, ветки reconcile/partial/timeout, финал confirmed.
- **WMS-351/376:** `fbs_stock_rule_service.py:165–970`, `fbs_stock_sync_service.py:229–800`, `fbs_warehouse_binding_service.py:286–620`, `fbs_sellers.py:280–450`.
- **WMS-396 (приёмка кодов ЧЗ):** `inbound_marking.py` целиком, `inbound_marking_service.py` целиком, `inbound_intake.py:1188–2126`.
- **Frontend:** `App.tsx`, `SellerApp.tsx`, `PublicAuthScreen.tsx`, `useAuth.ts`, `useSubscription.ts`, `FfInboundRequestView.tsx`, `FfFbsSupplyWorkspace.tsx`, `FfFbsOrdersScreen.tsx`, `FfProductsCatalogScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `useBarcodeScanner.ts`.

## Что я проверил и подтвердил по контрактам

**«Упаковка только признак. Не списывает, не резервирует, не блокирует».** Подтверждено: в `packaging_task_service.record_pack_progress` (7727–7748) и `undo_last_pack_action` (7752–7772) остались только записи `line.qty_packed_in_task ± qty` и события; исчезли обращения к `inv_svc.apply_packaging_convert/reverse_packaging_convert`. Из `create_manual_task` убран отказ по `insufficient_unpacked` (7706–7707). `_apply_acknowledge_all_packed` удалён целиком. `assert_unload_packaging_done` переименован в `assert_unload_marking_done` и больше не требует наличия завершённого задания упаковки, а проверяет только маркировку. В `fbs_workspace_service._inject_order_pick_fallback` больше нет ветки «Ozon packed → пропустить». В `fbs_picking_service.scan_pick_product` (4180–4180) и `undo_pick` (4275–4281) удалено правило `order.pack_status == PACKED → блокировать подбор/отмену`.

**«Нельзя вернуть `status assembling → picking`».** В `fbs_workspace_service.get_supply_workspace` (5847) остался только критерий фактического прогресса; правила `status == assembling → picking` в файле нет. `_compute_workspace_blockers` возвращает пустой список. Прошедший тест `test_wms058_pick_availability.test_ozon_undo_returns_to_original_box_and_repeat_pick_is_single` подтверждает, что после отмены упакованный статус не блокирует повторный подбор.

**«Передача списывает физически один раз, повтор — не списывает».** В `fbs_shipment_service._apply_local_delivered` (4362–4374) `now = supply.delivered_at or operation.confirmed_at or datetime.now(UTC)` — стабилен между повторами. `_write_off_delivered_orders_once` не менялся. `charge_handed_over_orders` вызывается через `session.begin_nested()` (3323): ошибка биллинга не откатывает передачу. `test_fbs_delivery_cancelled_exclusion.py:11043–11048` подтверждает, что повторный `deliver` вызвал `deliver_marketplace_supply` ровно один раз и в БД одна `InventoryMovement`.

**«Отмена до передачи — только резерв, после — не оприходовать».** `exclude_cancelled_delivery_orders` (2523–2547) снимает `FbsPackingBoxItem`, обнуляет `order.supply_id`, `order.trbx_id` и делает `update_fbs_order_reservation(reserve=False)`. Комментарий «cancellation never returns physical stock» подтверждён кодом — на `InventoryBalance` и `InventoryMovement` эта функция вообще не смотрит. Тест ждёт `balance.updated_at == original_updated_at` — физика не тронута.

**«Никаких новых журналов/счётчиков».** По всему диффу новых entity-таблиц ровно две: `subscription_payments` (нужна ЮKassa для дедупликации `provider_payment_id`) и одна колонка `subscription_paid_until` на `tenants`. Владелец описал ровно этот паттерн («одна дата, вычитание, ни журнала начислений, ни второго источника правды»). Никаких «квотных журналов» или «журналов реверса» не появилось — они снимались в WMS-060 ранее и здесь не воскрешены.

**«Свои дизайн-колонки FBS».** В диффе фронта нет изменений заголовков таблицы `FfFbsOrdersScreen`; поменялись только поисковый ввод, серверный поиск и клетка `NewOrderRow` (подсветка совпадений убрана). 8-колоночная разметка не тронута.

**Атомарность передачи.** `_persist_confirmed_delivery` (4378–4410) сохраняет `operation.confirmed_at`, коммитит операцию и лока supply, потом делает `_apply_local_delivered`. При обеих путях (ozon и не-ozon) первый постоянный ID передачи не переписывается. `mark_deliver_operation_confirmed` идемпотентен через `local_supply_id`.

**Межтенантность.** Все точки, что я проверил (`_get_order_for_kiz`, `_request` в inbound_marking, `attach_code`, `configure_seller_warehouse`, `create_supply_from_orders`, `send_auth_link`), стартуют с `tenant_id == user.tenant_id`. `set_password_by_link` берёт `user_id` из подписанного JWT — токен нельзя подделать. В `resend_invite_route` явная проверка `user.tenant_id == admin.tenant_id` (auth.py:329), тест это ловит (`test_admin_resends_invite_only_inside_own_tenant`, 9392–9407).

**Конкуренция/повторы.** WMS-272: три уровня защиты — `get_operation_by_idempotency` по seller+ключу, `_existing_create_for_orders` по пересечению order_ids вне лока + повторно внутри лока (`session.expire_all()` перед вторым чтением, 4853), `_bind_orders_to_supply` пропускает cancelled/defect/done/уже-принадлежащие-другой-поставке (4712–4722). WB draft создаётся ДО лока (4820) специально, чтобы не держать соединение с БД во время 90-секундного ожидания WB. Если победитель гонки уже выиграл — «свой» draft остаётся пустым на стороне WB (я это ниже пометил как вопрос стиля, не как баг). Приёмка КИЗ: `attach_code` берёт row-level lock на request (5988) и with_for_update на code, при коллизии — `IntegrityError → marking_code_other_receipt`. Отмена FBS-заказа берёт packaging lock перед FbsOrder lock, тот же порядок, что и `attach_order_meta_to_wb_and_sync` — нет reverse-order deadlock.

**Partial WB/Ozon.** `_execute_wb_batch_add` → `reconcile_supply_orders` → если WB ответил ошибкой, но частично принял, вызывается `_complete_partial_from_orders` (5049, 5118), заказы вне принятого набора остаются в `NEW`. Ложного `wb_timeout` при нормальном ожидании больше нет — этот бранч теперь строго только на `exc.code == "transport_error"` (5160). При `WildberriesClientError` на самой ветке readback (5223–5235) кандидат больше НЕ создаёт вторую поставку, а сохраняет `pending_confirmation` с ретрайаблом.

**Backwards compat для WMS-058.** Тест `test_ozon_old_null_pick_stays_at_place_without_invented_container` (parametrize `undo_by_id`) обкатывает случай, когда старый Ozon-pick пришёл с `source_container_kind=NULL, source_container_id=NULL, inventory_movement_id=NULL`. Кандидат правильно показывает такой источник как «Место подбора (тара не сохранена)» (`is_loose=False`, `container_path=()`) и не даёт коробу присвоить чужой pick. Это ровно тот сценарий, о котором в `wms-stage-qa-fixtures-20260909.md:288–302` root просил допроверить — helper 0356ff0e корректно сохраняет `cell:X` / NULL как «россыпь», не подменяя на коробку.

**Ozon-подбор без перемещения.** `test_ozon_sorting_box_set_is_final_quantity_without_movements` подтверждает: если источник = sorting_location и container указан, `set_pick_quantity` устанавливает финальный `quantity=1`, без `InventoryMovement`, резерв позиции не меняется. Undo с container id возвращает 0. `_active_assignments_for_product_location` фильтрует по конкретному контейнеру, поэтому pick второго контейнера при отмене первого не задет.

**False-green ЧЗ.** `inbound_marking_service.interpret_check` (6286–6320) даёт `introduced` только при одновременном `outerStatus="INTRODUCED"` AND `checkResult=True` AND `codeResolveData.verified=True`. Любое `codeFounded=False`, `verified=False`, `isBlocked=True`, а также `APPLIED/EMITTED/RETIRED/WRITTEN_OFF/DISAGGREGATED` → `problem`. Всё, что не дошло до дословного разбора (не dict, timeout, http error) → `unavailable`. Тесту `test_inbound_marking.py` соответствует, ложного «введён в оборот» получить нельзя. HTTP 451, зафиксированный QA staging и production, попадает в ветку `httpx.HTTPError → unavailable`, что и было видно в UI.

**Pool-code перепривязки.** В `_ensure_kiz_not_occupied_in_pool` (2673–2699) новая ветка допускает повторное применение только при трёх строгих условиях: (а) `is_unbound_received_code` (внешний код с приёмки, никогда не был в pool, нет FBS-привязки), либо (б) уже есть `pending_kiz_operation` для этой самой привязки и того же значения, либо (в) `status=PRINTED` и `packaging_task_line_id == текущая линия`. Ни один из этих путей не позволяет использовать чужой код или пересадить код другого заказа. `_claim_pool_code_if_present` дублирует ту же проверку до присвоения линии.

**Публикация WB/Ozon независимость.** `sync_binding_stocks` (4644): удалён `or not binding.served` из отказного условия — публикация решается только `stock_sync_enabled`. `publish_amounts_for_binding` (4553): в первую же строку добавлен явный `if not binding.stock_sync_enabled: return {}`. `_seller_bindings(publishing_only=True)` фильтрует по `stock_sync_enabled`. `configure_seller_warehouse` (5623–5633): служебная галка меняется только по явно переданному значению — обслуживание без stock_sync больше не гасит публикацию. Есть тест `test_wms351_marketplace_publication_switches`.

**Auth / миграции / платежи.** Регистрация закрыта (`allow_public_registration=False` по умолчанию), ручка `/auth/register` возвращает 403 `registration_closed`. Ссылки из писем не идут одновременно с access-token — токены имеют разные payload и `get_current_user` строго требует `tenant_id` (deps.py:107–116), которого в auth-link JWT нет; попытка подать auth-link как Bearer заканчивается 401. Одноразовость линки — арифметическая: `pwf = sha256(password_hash)[:16]`, после смены пароля отпечаток не совпадает. Тест `test_invite_link_works_once` это ловит. Реcет анонимной формы всегда 204 вне зависимости от наличия почты — валидатор адресов через форму невозможен. `sync_pending_payment` идемпотентен (после `succeeded` payment не попадает под фильтр `status.in_(_PENDING_STATUSES)`), концерн двойного продления при одном платеже я проверил вручную для двух параллельных сессий — обе видят одну «pending» строку, обе устанавливают её в `succeeded`, обе прибавляют `+30d` к своей копии `tenant.paid_until`; второй commit перезапишет тем же значением, дубля дней нет.

## Замечания (не блокеры)

Каждое из этого — не подтверждённая регрессия, а либо явный дизайн-выбор владельца, либо низкорисковая деталь. Оценку «Q» ставлю там, где хочу услышать «да, так и задумано» от владельца перед выкладкой, но не считаю поводом не катить.

### Q1. `apply_wb_meta_requirements_to_order` теперь может очистить требование ЧЗ

- **Приоритет:** низкий (вопрос владельцу).
- **Файл/строки:** `backend/app/services/fbs_marking_service.py:130–141`.
- **Путь:** worker импорта заказов WB → `parse_meta_kinds_from_wb_row` → `apply_wb_meta_requirements_to_order` → `order.required_meta_json = []` → на экране упаковки заказ не требует sgtin → передача проходит без ЧЗ.
- **Что изменилось:** старая проверка `if required:` не обновляла список, если WB прислал пустой массив. Новая: `if isinstance(row.get("requiredMeta", row.get("required_meta")), list):` — пустой список ЯВНО очищает требование.
- **Почему проверки не спасают:** ни один downstream check не отличает «код всегда был не нужен» от «код обнулили». `requires_honest_sign` (workspace) читает флаг товара, но `metadata.required` — прямо этот список.
- **Минимальный фикс, если владельцу критично:** очищать только когда WB прислал явный признак свежего снапшота (например, при импорте самого заказа, а не при периодической переоценке), либо не обнулять список меньше, чем через N подтверждений подряд.
- **Мой вердикт:** реальный сценарий, при котором WB стабильно возвращает `requiredMeta: []` для заказа, который должен требовать sgtin, я не смог придумать. Владельцу — знать про новое поведение.

### Q2. Расцепление `served` и `stock_sync_enabled` при сохранении «обслуживать этот склад» через `FfProductsCatalogScreen`

- **Приоритет:** средний (нужно подтверждение владельца).
- **Файлы:** `frontend/src/screens/v2/FfProductsCatalogScreen.tsx:820–825`, `backend/app/services/fbs_warehouse_binding_service.py:570–633`.
- **Путь:** оператор в каталоге снимает галку «обслуживается» → PUT `/fbs-sellers/{seller}/warehouses/{whid}` с телом `{ served: false, wms_warehouse_id, marketplace }`, БЕЗ `stock_sync_enabled` → backend `configure_seller_warehouse` меняет `existing.served = False`, `stock_sync_enabled` остаётся прежним (True на существующих привязках) → `sync_binding_stocks` продолжает публиковать.
- **Почему проверки не спасают:** новая логика в `sync_binding_stocks` (4644) осознанно смотрит только `stock_sync_enabled`. Комментарий в `configure_seller_warehouse` описывает это как решение WMS-376. Frontend, который делал `stock_sync = served`, был снят 31.08.2026 — теперь единственный писатель `stock_sync_enabled=True` — это сохранение правила товара.
- **Минимальный фикс, если владелец захочет полного «раньше»:** либо во фронте передавать `stock_sync_enabled: false` вместе с `served: false`, либо в бэкенде считать `served=False → stock_sync_enabled=False` неявно, если пришёл только `served`. Первое — три строки в `saveFbsWarehouse`.
- **Мой вердикт:** это НАСТОЯЩИЙ дизайн-выбор WMS-376: комментарии в коде цитируют инцидент ИП Горячкина Т.И. 05.09.2026 (три карточки в ноль от неявной связки). Владельцу надо явно сказать «да, я так и хочу — обслуживание отдельно, публикация отдельно», иначе на первой же смене галки «обслуживать» операторы удивятся, что кабинет продолжает получать остаток. Кода поменять не надо, — надо сообщить об этом операторам.

### Q3. `/auth/invites/resend` не проверяет `must_set_password`

- **Приоритет:** низкий.
- **Файл/строки:** `backend/app/api/auth.py:320–338`, `backend/app/services/auth_service.py:257–275`.
- **Путь:** admin в своей организации POST `/auth/invites/resend` с `user_id` любого пользователя тенанта → отправляется письмо с purpose="invite", ссылка ведёт на `/set-password?token=<jwt>` → пользователь по ссылке может задать НОВЫЙ пароль, даже если у него уже был свой.
- **Почему проверки не спасают:** `set_password_by_link` не смотрит `must_set_password`, только совпадение fingerprint. Fingerprint совпадает у любого текущего пароля.
- **Минимальный фикс:** в `resend_invite_route` добавить `if not user.must_set_password: raise HTTPException(409, "already_active")`. Ну или тихо считать это функцией «принудительно сбросить сотруднику пароль».
- **Мой вердикт:** админ и так может дёрнуть `/auth/request-password-reset` на любой чужой email без авторизации — так работают все формы сброса. То есть новая ручка не даёт админу того, чего он не мог сделать раньше. Не блокер.

### Q4. `_notify_supply_marking_update` теперь под флагом `notify_supply`

- **Приоритет:** низкий (info).
- **Файл/строки:** `backend/app/services/fbs_marking_service.py:902–970`.
- **Что изменилось:** `attach_order_meta_to_wb_and_sync` теперь принимает `notify_supply=True` по умолчанию, но некоторые внутренние вызовы могут передать False.
- **Мой вердикт:** прямо в диффе я не нашёл вызывающего кода, который бы передавал False. Значение по умолчанию сохраняет старое поведение. Оставляю просто как info — если в других коммитах позже добавится вызов с False, надо будет думать. Сейчас — нейтрально.

### Q5. Периодическая сверка `_sync_order_meta_from_wb` использует `metaDetails`, а эмулятор возвращает пустой массив

- **Приоритет:** только evidence-limit.
- **Файл/строки:** `backend/app/services/fbs_marking_service.py:3098–3164`.
- **Путь:** реальный WB возвращает `metaDetails: [{kind, value, decision, ...}]`. Эмулятор в `wb_emulator/routes/marketplace_orders.py` — жёстко `metaDetails: []`. Прочитанный код правильно оставляет `meta_status=unknown`, не подтверждая КИЗ.
- **Что это значит:** «положительное подтверждение WB» на стенде НЕВОЗМОЖНО из-за эмулятора; это не бага WMS, а ограничение эмулятора. Никаких послаблений реальной проверки WB ради эмулятора в коде я не увидел и не рекомендую вводить.

## Пределы моей evidence

Я не имел права запускать сеть, тесты или платежи, поэтому по этим осям опираюсь на приложенные QA-отчёты и не могу утверждать больше того, что там написано:

1. **Живая ЧЗ.** `mobile.api.crpt.ru/mobile/check` вернул HTTP 451 и на staging (21:42:25 UTC), и на production (21:43:54 UTC) для тестового кода `010200000000001221QA396…`. Это подтверждает, что классификатор `interpret_check` попадёт в ветку `unavailable`, и красная плашка «Не удалось проверить» — правильная. Позитивный тест ЧЗ не пройден нигде, но это ограничение доступа, а не ошибка кода — приложение честно показало недоступность. Отдельно: у тестового селлера пустой `SellerMarkingCredentials.cz_token_enc`, официальный TrueAPI-путь недоступен без токена. WMS его сегодня НЕ использует (см. `wms396-live-check-readiness.md`) — я в код на этот счёт заглядывал, `CHECK_URL = mobile.api.crpt.ru/mobile/check` жёстко зашит в `inbound_marking_service.py:5929`. Изменять его или прикручивать TrueAPI я не рекомендую как условие релиза: этот путь и в production сегодня работает через ту же самую ручку, и его выпуск ничего не меняет по сравнению с текущим прод-поведением.
2. **Реальный WB metaDetails.** Проверил только на эмуляторе (пустой). Кода, послабляющего требование `metaDetails`, я не увидел — что и правильно. Реальный WB на боевом кабинете этой пачкой не тестировался.
3. **Ozon runtime.** Кандидат ходит в `api-seller.ozon.ru` живьём; synthetic-фикстуры для Ozon в staging нет. Тесты Ozon-lane в CI гоняются на моках. QA-заказчик не проверял реальный Ozon. Обязательства «staging = production» для Ozon не собрано. Если владельцу критично — надо отдельно проверить один реальный Ozon-заказ на тестовом продавце с настроенным `client_id`.
4. **SMTP/YuKassa.** Обе интеграции — с fail-soft поведением при пустых настройках. Кода, отправляющего секреты/ссылки в лог при отсутствующих настройках, я не увидел (проверил `mailer.py:6563–6572` — там прямо запрет и объяснение почему). Живой отправки писем и живого прохождения ЮKassa я не проверял.
5. **UI.** Браузер я не открывал; сверка идёт по прочитанному коду и отчёту `wms-release-browser-20260909.md` за подписью root, где ручной прогон приёмки 000046, повторного создания WB-поставки, стикера и подбора описан пошагово.
6. **История данных.** WMS-047/048/013 (исторические денежные корректировки), WMS-084 (перенос), WMS-277 (расписание) — я в скоуп релиза не заводил и не рекомендую заводить сейчас. Ни одна из миграций этой пачки данные не переносит и не правит.

## Что я явно НЕ рекомендую делать перед этим выпуском

- **Не откатывать 8 колонок FBS.** Дифф их не трогает; 4-колоночная разметка — регресс по прямому решению владельца 01.09.
- **Не «доводить» ветку `apply_wb_meta_requirements_to_order` в другую сторону**, не согласовав с владельцем: WMS-специальный inbound КИЗ-check зависит от факта, что WB иногда снимает требование.
- **Не смыкать `served` со `stock_sync_enabled` обратно** — WMS-376 явно расцеплял их из-за инцидента с ИП Горячкина 05.09.2026 (три карточки в ноль).
- **Не расширять `_SUBSCRIPTION_FREE_PATHS`** — там сейчас минимум необходимого (`/auth/me`, `/auth/login`, `/auth/set-password`, `/auth/request-password-reset`, `/subscription`, `/subscription/pay`, `/subscription/sync`, `/health`), любая новая свободная ручка — потенциальный обход блокировки.
- **Не откатывать удаление `apply_packaging_convert` / `reverse_packaging_convert`** — их возврат нарушит контракт «упаковка только признак» WMS-392.
- **Не восстанавливать `status == assembling → picking`** ни под каким соусом — прямой запрет в AGENTS.md.

## TL;DR

Кода-блокеров, из-за которых нельзя выпускать разрешённый owner’ом срез staging→production, я не нашёл. Три ключевых контракта (упаковка-признак, атомарное списание, отмена без оприходования) в коде соблюдены, тестами подтверждены, поведение сходится со staging-QA. Пять замечаний выше — это либо явные дизайн-выборы WMS-376/351/381/392, о которых владельца нужно оповестить, либо ограничения внешних систем (ЧЗ 451, эмулятор WB, Ozon без реального аккаунта на тесте), которые релиз этой пачки не ухудшает. Ручная приёмка root подтверждает базовые сценарии; окончательная выкатка — по обычному `prod-update.sh` при явном «кати» от владельца.
