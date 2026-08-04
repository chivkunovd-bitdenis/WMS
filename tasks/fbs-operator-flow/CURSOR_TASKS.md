# Cursor queue — FBS operator flow

**integration_branch:** `feat/fbs-stock-sync`

> **Cursor делает backend, WB client, migrations, emulator и backend/integration tests. Frontend делает Codex.**  
> Перед началом прочитать `README.md`, `BACKEND_CONTRACT.md`, разделы 1–2 `FRONTEND_TASKS.md` с binding wire-format, `TEST_CASES.md`, корневой `AGENTS.md`, `.dev/PROCESS.md` и текущий `tasks/fbs-stock-sync/HANDOFF.md`.

## Жёсткие правила

1. Работать только в `/Users/deniscivkunov/Desktop/WMS `.
2. Dirty tree пользователя не чистить, не stash/pop, не добавлять посторонние untracked-файлы.
3. Одна задача — один небольшой commit с ID.
4. Перед task зафиксировать baseline; существующий красный gate записать отдельно, не чинить соседние модули.
5. Frontend-код не менять: его реализует Codex после backend handoff.
6. Не возвращать прежний `localStorage`-процесс через другой API.
7. Не добавлять новую упаковочную сущность параллельно `PackagingTask`.
8. Не реализовывать обязательное распределение order → trbx.
9. Не считать HTTP timeout / 409 / неизвестный ответ WB успехом.
10. Не выдавать frontend локальные пути файлов.
11. Все query по worklist/workspace — batch, без N+1.
12. Cursor не пишет финальный `APPROVE`; `05-review.md` заполняет независимый reviewer.

## Порядок

| ID | depends_on | lane | Краткая цель |
|---|---|---|---|
| FBSFLOW-000 | — | baseline | Зафиксировать фактический baseline и конфликтующие старые контракты |
| FBSFLOW-010 | 000 | model | Модель per-order операций, печатных активов и WB operation audit |
| FBSFLOW-020 | 010 | wb-client | Обновить WB client до актуальных batch/meta/trbx contracts |
| FBSFLOW-030 | 010 | read-api | Enriched worklist и workspace без N+1 |
| FBSFLOW-040 | 020,030 | supply | Preflight и атомарное создание поставки из массива заказов |
| FBSFLOW-050 | 010,030 | picking | Серверный подбор сканами и движение в сортировку |
| FBSFLOW-060 | 050 | packaging | Связать существующую упаковку с конкретным FBS-заказом |
| FBSFLOW-070 | 020,060 | marking | requiredMeta/optionalMeta, скан и автоматическая проверка WB |
| FBSFLOW-080 | 010,020 | print | Исправить хранение и выдачу стикеров/QR как binary assets |
| FBSFLOW-090 | 020,080 | pvz | Грузоместа без ручного распределения заказов |
| FBSFLOW-100 | 040,060,070,080,090 | delivery | Свежий preflight и безопасная передача в доставку |
| FBSFLOW-110 | 020,100 | tracking | Статусы после передачи и частичный отказ |
| FBSFLOW-120 | 040,050,070,080,090,110 | emulator | Полноценные три селлера и печатаемые assets в эмуляторе |
| FBSFLOW-130 | 030,040,050,060,070,080,090,100,110 | contract | OpenAPI, error catalog, permanent test cases |
| FBSFLOW-140 | 120,130 | e2e | Backend/compose full-flow gate и handoff фронту |

---

## FBSFLOW-000 — baseline и карта расхождений

**ownership:** только диагностика и новый `tasks/fbs-operator-flow/00-baseline.md`.

### Сделать

1. Записать branch, HEAD, status, worktrees, alembic head.
2. Прогнать целевые существующие тесты FBS, packaging, emulator без правок.
3. Для каждого текущего FBS endpoint сопоставить фактический контракт с `BACKEND_CONTRACT.md`.
4. Явно зафиксировать устаревшее:
   - add one order вместо batch;
   - `sticker_file` как путь;
   - локальные pick flags;
   - ручной bind order → trbx;
   - отсутствие requiredMeta/optionalMeta;
   - отсутствие per-order связи упаковки.
5. Не менять код.

### Gate

`00-baseline.md` содержит факты, команды и точный список красных baseline tests.

---

## FBSFLOW-010 — модели и миграция

**ownership:**

- `backend/app/models/fbs_order.py`
- `backend/app/models/fbs_supply.py`
- новые `backend/app/models/fbs_*operation*.py`, `fbs_*asset*.py` при необходимости
- `backend/app/models/packaging_task.py` только FK/relationship для per-order unit
- новая alembic migration
- новые model/migration tests

### Сделать

1. Сохранить отдельно внешний статус WB и внутренние статусы pick / pack / sticker / metadata.
2. Ввести 1:1 активный pick record на заказ с source location, sorting location, user, timestamps и undo audit.
3. Ввести связь физически упакованной единицы `PackagingTask` с конкретным `FbsOrder`; одна упаковочная единица не может закрыть два заказа.
4. Сохранить required/optional metadata и последний фактический `metaDetails` без потери причин.
5. Ввести печатный asset с kind, content type, path/blob key, checksum, WB fetched_at; внутренний путь не является API-полем.
6. Ввести журнал внешней операции: seller, operation kind, idempotency key, request hash, WB object id, state `pending|confirmed|failed|pending_confirmation`, safe error code, timestamps.
7. Добавить audit подтверждения нанесения стикера/QR.
8. Индексы: tenant/seller/status/deadline/supply; unique idempotency; unique active pick per order; unique fulfilled FBS order per packaging unit.
9. Миграция не угадывает новые состояния старых данных: backfill только доказуемых значений, остальное `unknown`/`pending`.

### Tests / gate

- чистый PostgreSQL upgrade → head → downgrade migration → upgrade;
- constraints реально ловят повторный pick, повторный fulfillment и duplicate idempotency;
- старые FBS rows читаются после migration.

---

## FBSFLOW-020 — актуальный WB FBS client

**ownership:**

- `backend/app/services/wildberries_client.py`
- новый/существующий typed FBS client module
- client contract tests

### Сделать

1. Сверить официальный OpenAPI в день реализации и сохранить дату/ссылку в тесте/доке.
2. Реализовать typed методы:
   - new/orders/status;
   - create supply;
   - batch add/move ≤100 orders;
   - supply details/order IDs;
   - stickers ≤100, PNG 58×40;
   - get/put/delete metadata + parse `metaDetails`;
   - create/list/delete trbx;
   - trbx stickers;
   - deliver;
   - supply barcode/status.
3. Строго отличать 204, JSON и binary/base64 responses.
4. 409 сохранять как typed business error с безопасным code; `MetaValidationFail` парсить по заказам.
5. Rate limit: bounded retry/backoff только для retryable 429/transport; один 409 учитывается WB как 10 запросов — не retry loop.
6. Токен и response body с потенциальными секретами не логировать.

### Tests / gate

`httpx.MockTransport` проверяет exact URL/method/query/body, chunk boundaries 100, 204, malformed JSON, base64, timeout, 409 MetaValidationFail, 429.

---

## FBSFLOW-030 — worklist и workspace read model

**ownership:**

- `backend/app/api/fbs_orders.py`
- `backend/app/api/fbs_supplies.py`
- новый `backend/app/services/fbs_worklist_service.py`
- новый `backend/app/services/fbs_workspace_service.py`
- query-count tests

### Сделать

1. Реализовать `GET /worklist` и `GET /{id}/workspace` строго по контракту.
2. Enrichment: seller, WB warehouse binding, WMS warehouse, product, WB image, size, barcodes, storage locations, available unpacked, metadata, sticker/pick/pack state.
3. `selection_blockers` рассчитываются сервером единым validator service, который потом переиспользует preflight.
4. `server_now` возвращается для корректного live timer.
5. Workspace рассчитывает stage/progress/blockers, а не просит frontend вывести бизнес-статус из сырых полей.
6. Старые GET можно сохранить совместимо, но новый frontend использует только новые read models.

### Tests / gate

- 500 заказов не создают N+1; query-count bounded;
- три seller на одном WMS warehouse не смешивают данные;
- unavailable/missing mapping/expired/cancelled видны как конкретные blockers;
- timezone-aware deadline от `created_at_wb`.

---

## FBSFLOW-040 — совместимость и атомарное создание поставки

**ownership:**

- `backend/app/services/fbs_supply_service.py`
- новый validator/reconcile service
- `backend/app/api/fbs_supplies.py`
- supply tests

### Сделать

1. Один validator для UI selection, preflight и create-under-lock.
2. Проверить все правила из `BACKEND_CONTRACT.md`, включая buyer type и `can_pvz`.
3. Создавать supply + batch add orders одной прикладной командой `from-orders`.
4. DB row locks не допускают параллельно добавить один заказ в две поставки.
5. Сетевую частичность обрабатывать operation journal + reconcile, не второй поставкой.
6. `start-work` идемпотентно создаёт существующий PackagingTask и не замораживает состав без основания WB.
7. Старый create + N add path оставить только как deprecated internal/test path либо удалить после миграции callers.

### Tests / gate

- TC-01, 02, 03, 04, 05, 06;
- parallel create одного order → одна подтверждённая поставка;
- WB create success + batch timeout → pending_confirmation, retry не создаёт дубль;
- add failure не выдаёт frontend false success.

---

## FBSFLOW-050 — серверный подбор

**ownership:**

- новый `backend/app/services/fbs_picking_service.py`
- новые pick endpoints в `fbs_supplies.py`
- `inventory_service.py` только переиспользуемые batch/transfer операции
- pick tests

### Сделать

1. Реализовать scan location → scan product.
2. Перемещать unpacked stock из ячейки в `__SORTING__`, не списывать его из WMS.
3. Сохранять конкретный order record; одинаковые SKU назначать по ближайшему дедлайну.
4. Сохранять user/time/source location/scanned barcode/idempotency.
5. Undo до упаковки возвращает единицу в исходную ячейку.
6. Прогресс доступен сразу всем клиентам через workspace; polling достаточно, WebSocket не обязателен.
7. Сообщение недостатка содержит order, product, location, requested, available и рекомендуемое действие.

### Tests / gate

- TC-07, 08, 09;
- два параллельных scan при stock=1 → один успех;
- два клиента читают одинаковый progress;
- refresh не теряет progress;
- cross-seller stock использовать нельзя.

---

## FBSFLOW-060 — существующая упаковка на конкретный заказ

**ownership:**

- `backend/app/services/fbs_packaging_integration_service.py`
- `backend/app/services/packaging_task_service.py`
- `backend/app/api/packaging_tasks.py`
- packaging model только в рамках принятой migration 010
- FBS packaging tests

### Сделать

1. `PackagingTask` остаётся единственным документом.
2. Lines агрегируют SKU, physical units связывают каждое увеличение done с одним picked FbsOrder.
3. Нельзя pack order без pick; нельзя pack дважды.
4. Для одинаковых SKU auto-assign по ближайшему дедлайну, explicit `order_id` поддержать.
5. После pack stock в sorting переводится unpacked → packed существующим inventory service.
6. Supply packed только когда все активные orders имеют physical pack, а required metadata допускает продолжение.
7. Отмена / повторная упаковка сохраняет аудит и корректно возвращает inventory state.
8. Удалить логику, где aggregate qty сама по себе объявляет все orders packed без per-order evidence.

### Tests / gate

- TC-10, 11;
- два одинаковых SKU закрывают два разных WB order;
- third pack rejected;
- real inventory in source cell → pick → sorting unpacked → pack → sorting packed → final write-off exactly once.

---

## FBSFLOW-070 — WB metadata и Честный знак

**ownership:**

- `fbs_marking_service.py`, `fbs_marking.py`
- marking pool service только через существующие публичные функции
- metadata sync tests

### Сделать

1. Intake/sync сохраняет `requiredMeta` и `optionalMeta` каждого order.
2. Убрать `Product.requires_honest_sign` как единственный WB delivery gate; он остаётся локальной подсказкой, но authoritative — requiredMeta + фактический WB meta status.
3. Scanner path сохраняет GS separators; UI manual input не является основным API.
4. Код из пула выбирается только для seller + product, резервируется атомарно, связывается с order/packaging unit.
5. После подтверждения физической пары автоматически PUT в WB, затем meta read/sync.
6. Маппинг состояний: missing, assigned, sending, pending, accepted, allowed_without_check, rejected, replacement_required.
7. 409 причины возвращать оператору по конкретному типу и заказу.

### Tests / gate

- TC-12, 13, 14;
- duplicate KIZ rejected;
- KIZ другого seller rejected;
- GS roundtrip byte-for-byte;
- required rejected blocks, WB allowed intermediate does not self-block.

---

## FBSFLOW-080 — печать без пустых страниц

**ownership:**

- `fbs_supply_service.py`, shipment/pvz services
- новый print asset service/API
- storage path validation
- print tests

### Сделать

1. Мигрировать `sticker_file`/`barcode_file` к asset abstraction или строго спрятать paths за binary endpoint.
2. Никогда не возвращать relative path как base64.
3. Проверять decode, content type, non-empty bytes, checksum и безопасный путь.
4. One/selected/all/retry-missing с chunk ≤100.
5. Batch result не падает целиком из-за одного missing sticker; возвращает per-order status.
6. Серверное подтверждение print-opened и applied не смешивать.
7. Размер стикера заказа 58×40, scale metadata 100%, no margins.

### Tests / gate

- TC-15, 16;
- реальный PNG magic bytes и ненулевые dimensions;
- missing file не выдаёт ready;
- cross-tenant asset 404;
- traversal path rejected.

---

## FBSFLOW-090 — грузоместа ПВЗ

**ownership:**

- `fbs_shipment_pvz_service.py`, `fbs_supplies.py`, `fbs_trbx.py`
- WB client trbx methods из 020
- PVZ tests

### Сделать

1. Создание только по count, не по order mapping.
2. GET reconcile списка trbx после create; retry идемпотентен через operation journal.
3. Удалить ручную bind-orders операцию из рабочего gate; endpoint deprecated/410 после миграции caller.
4. `packaging_box_id` optional и никогда не delivery blocker.
5. Проверки размеров/веса/объёма и count ≤ items+1.
6. Если данных нет — explicit manual confirmation с audit, не выдуманный ноль.
7. QR каждого trbx через print asset service; applied confirmation per cargo place.

### Tests / gate

- TC-17, 18;
- 2 boxes create + GET reconcile + 2 valid QR;
- no order→trbx mapping and delivery remains possible;
- >60 side, sum>140, >5kg, total>1m3 yield exact blockers.

---

## FBSFLOW-100 — delivery preflight и deliver

**ownership:**

- `fbs_shipment_service.py`, `fbs_supplies.py`
- status/metadata sync services
- operation journal
- delivery tests

### Сделать

1. Preflight всегда делает fresh WB status/meta sync и version token.
2. Полный checklist по общим + route-specific правилам.
3. Deliver принимает idempotency key и preflight version.
4. Локальный status только после WB success/reconcile.
5. timeout/connection loss → pending_confirmation.
6. 409 MetaValidationFail → order/type/reason; status не меняется.
7. warehouse/sc после success получает QR supply; pvz до success требует ready cargo place QR.

### Tests / gate

- TC-19, 20, 21;
- timeout after request + retry → one WB close;
- cancelled order found by fresh sync blocks;
- stale preflight rejected;
- QR route differs correctly.

---

## FBSFLOW-110 — tracking после передачи

**ownership:** status sync/autopoll services, background jobs, workspace read model, tests.

### Сделать

1. Sync active in-delivery supplies and their orders.
2. Normalize accepted/sorted/partially_rejected/cancelled/retry_required/done without hiding raw WB status.
3. Partial rejection returns exact orders, safe reason and remaining deadline.
4. Sync is idempotent, tenant/seller isolated, bounded by WB rate limits.
5. UI-visible `last_wb_sync_at` and stale warning.

### Tests / gate

- TC-22;
- mixed accepted/rejected orders preserved;
- repeated sync no duplicate events;
- one seller failure does not stop others.

---

## FBSFLOW-120 — эмулятор и нормальные данные

**ownership:** `wb_emulator/**`, seed helpers, emulator tests, compose docs.

### Сделать

1. Три токена/селлера, один общий physical WMS warehouse, отдельные products/stocks/KIZ/supplies.
2. ≥13 осмысленных orders: normal, required KIZ, manufacturer KIZ, pool KIZ, B2C, B2B, can_pvz true/false, multiple PVZ, warehouse/sc, rejected metadata, cancelled, near deadline, different cargo type.
3. Order JSON: requiredMeta/optionalMeta, warehouseId отдельно от officeId, actual createdAt.
4. Настоящий PNG для order sticker, cargo QR, supply QR; не строка-заглушка.
5. Script/setup создаёт реальный WMS inventory в конкретных locations и seller-scoped marking pool.
6. Fault injection: timeout, 409, MetaValidationFail, incomplete stickers, delayed QR, partial status.

### Tests / gate

- TC-23;
- restart persistence;
- token isolation;
- every returned PNG decodes and has dimensions;
- seed setup can be repeated without duplicates.

---

## FBSFLOW-130 — OpenAPI и error catalog

**ownership:** API schema/docs/test case catalog only.

### Сделать

1. Обновить OpenAPI новым contract.
2. Добавить стабильный RU error catalog и `retryable` semantics.
3. Перенести TC из `TEST_CASES.md` в canonical product scenario catalog с final IDs.
4. Удалить/пометить deprecated старые assumptions в `tasks/fbs-frontend-*` и старом SPEC, не стирая исторические документы.
5. Обновить `docs/MVP_DECISIONS_RU.md`: FBS full-cycle является осознанным исключением из старого общего решения «WB import-only»; иначе два источника правды продолжат конфликтовать.

### Gate

OpenAPI generation green; documented examples validate against schemas; grep не находит новый frontend contract с `sticker_file` path или обязательным trbx order binding.

---

## FBSFLOW-140 — backend full-flow handoff

**ownership:** compose/e2e setup, backend integration tests, `tasks/fbs-operator-flow/HANDOFF.md`.

### Сделать

1. Fresh PostgreSQL + migrations + queue + emulator.
2. Seed 3 sellers + physical inventory.
3. Пройти API full flows PVZ и warehouse/sc, негативы timeout/409.
4. Записать exact commands, counts, timings, failures and limitations.
5. Сохранить для Codex current endpoint examples и реальные response fixtures для последующей frontend-реализации.

### Gate

Все TC, не требующие браузера, зелёные. Handoff не объявляет WB compatibility доказанной без отдельного live smoke.

## Что Cursor не делает

- не меняет frontend-код;
- не меняет согласованные имена методов и JSON-форматы из `BACKEND_CONTRACT.md` и `FRONTEND_TASKS.md`;
- не возвращает цену в основной worklist;
- не добавляет обязательный выбор конкретного ПВЗ;
- не добавляет кнопку ручной отправки КИЗ как основной сценарий;
- не делает внутренний `WHB-*` короб обязательным для WB;
- не выполняет deploy/merge в main без отдельной команды пользователя.
