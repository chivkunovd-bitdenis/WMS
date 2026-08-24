# Ozon в WMS: архитектура семантического переиспользования

**Call ID:** `17-ozon-semantic-reuse-contract-rework`

**Дата:** 24 августа 2026 года

**Исходный baseline commit:** `2af800d5846d351904cab050860356038b6d282e`

**Live baseline:** `docs/evidence/ozon-module-20260824/baseline-current-product/`

**Binding product contract:** `tasks/ozon-module-20260824/S0R_REWORK_CONTRACT.md`

**Machine-readable map:** `tasks/ozon-module-20260824/REUSE_MAP.json`
**Статус:** architecture rework; production и prototype code не разрешены и не изменяются

SHA `309e85d666f377e23e670d0ae0044f12ca4449cd` отклонён владельцем. Файловое переиспользование внутри существующего React-файла не является продуктовым переиспользованием, если query переключает whole screen/workspace/modal, оператор видит второй процесс или WB semantics протекают в Ozon.

## 1. Архитектурное решение

Выбран additive marketplace domain с adapters/capabilities и проекцией в существующие operator surfaces:

- FBS остаётся `/app/ff/fbs`, `FfFbsOrdersScreen` и тем же `FfFbsSupplyWorkspace` с четырьмя текущими стадиями;
- FBO остаётся `/app/ff/mp-shipments` и тем же `MarketplaceUnloadRequest` modal с тремя текущими стадиями;
- return остаётся `/app/ff/reception` и тем же `InboundIntakeRequest(operation_type="return")` modal;
- mapping остаётся в action-zone текущей таблицы `/app/ff/products`; current create dialog сохраняет WMS identity;
- connection остаётся соседней card на `/seller/settings` и использует тот же credentials-dialog pattern.

Target добавляет **0** routes, screens/pages, tabs, documents, workspaces, modals, navigation items и лишних operator steps. Conditional Ozon payload разрешён только внутри текущих header/cell/stage/action zones. Whole-screen early return, Ozon-only modal, replacement workspace, fixed decorative tabs и синонимичные действия запрещены независимо от имени файла.

WB — неизменяемый observable baseline. Ozon — conditional delta. В первой программе существующие WB models/tables/services не переименовываются и не мигрируют.

## 2. Primary user и его работа

Primary user — оператор фулфилмент-склада. Он должен в одной очереди выбрать совместимую работу, доказанно подобрать физические единицы, выполнить требования маркетплейса, упаковать, нанести актуальную этикетку и передать груз без ложного внешнего завершения.

- Marketplace filter предотвращает смешение WB/Ozon labels и handover.
- Multi-line totals показывают реальное количество физической работы в одном Ozon posting.
- Единая формула progress не позволяет упаковать больше подобранного.
- Unit requirements отделяют локальный скан от проверки Ozon, чтобы отклонённый код можно было исправить до ship.
- Package/cargo/TGM links не называют WMS box внешним контейнером без доказательства.
- Local handover и Ozon confirmation показаны отдельно, чтобы следующая смена не повторила mutation.
- Per-unit return inspection не даёт вернуть повреждённый или чужой товар в продажу.

Seller admin подключает account; FF admin подтверждает product mapping; бригадир ведёт FBO и discrepancies; сотрудник приёмки осматривает return. Все остаются на текущих страницах.

## 3. Нормальный процесс end to end

### 3.1 Account и catalog

1. Seller admin вводит `Client-Id` и `API-ключ` в existing credentials dialog. Неполная pair сохраняет draft и не вызывает внешнюю систему.
2. Discovery получает external identity, roles, expiry и capabilities. Card говорит `Подключение проверено` либо понятную причину; secret не возвращается в UI.
3. Import-only sync загружает products/nodes/references. Partial result сохраняет last confirmed data и checkpoint.
4. FF admin в current catalog row раскрывает `Связь с Ozon`, отвергает ambiguous candidate или подтверждает exact account offer. WMS SKU остаётся primary identity.
5. Seller warehouse ↔ WMS warehouse и return point ↔ safe holding location являются разными bindings. Delivery method выбирается в FBS preflight, destination/route — в current FBO header.

### 3.2 FBS

1. Push ускоряет intake; `/v4/posting/fbs/unfulfilled/list` polling и entity detail восстанавливают пропуски.
2. Один posting становится одним `FbsWorkItemView` с lines/quantities, blockers и provider-specific copy в current cells.
3. Homogeneous selection создаёт local work batch и открывает same modal. Это не Ozon supply/carriage.
4. `Состав` показывает full lines; `Подбор` использует existing location/product scans; `Упаковка и маркировка` показывает only required per-unit fields/packages; `Короба` связывает WMS box/package/label and capability-derived handover.
5. One-by-one mode не создаёт обязательную carriage. Local handover показывает `Передано со склада. Подтверждение Ozon ещё не получено.` до authoritative Ozon state.

### 3.3 FBO

1. Current create block receives one marketplace select. WB path remains unchanged.
2. Same document header conditionally receives Ozon account/destination/route/interval and inline operation state.
3. Existing `Товары` owns local plan/reserve; `Подбор` owns WMS allocations; `Упаковка` owns PackagingTask/WMS boxes.
4. Ozon cargo/TGM and their labels are children linked after closed boxes in the same packaging panel, not replacements.
5. Same document keeps local shipped, Ozon accepted/rejected and act-agreed as separate facts.

### 3.4 Return

1. `/v1/returns/list` upserts account-scoped return and idempotently links one existing inbound return document.
2. Same queue row/modal shows source/identifiers and receives unit into a non-saleable location.
3. Identity and condition are recorded per unit. Only completed inspection plus `Вернуть в продажу` may let the existing inbound posting create available inventory.

## 4. Ошибки и partial states

| State | Operator copy | Safe next action | Machine invariant |
|---|---|---|---|
| incomplete credentials | `Укажите Client-Id и API-ключ` | `Изменить подключение` | external requests = 0 |
| partial sync | `Синхронизация выполнена частично. Последние подтверждённые данные сохранены.` | `Продолжить синхронизацию` | committed checkpoint does not advance past failed page |
| unmapped line | `Товар не связан с каталогом WMS` | `Перейти к товару` | reserve/pick disabled |
| external state unknown | `Требуется проверка состояния в Ozon` | `Проверить состояние` | no blind retry/new intent |
| exemplar rejected | `Ozon отклонил код: …` | `Исправить код` | unit cannot enter completed package |
| label not ready | `Этикетка готовится` | wait or `Проверить состояние` | print current-ready asset only |
| partial package | `Упаковано 2 из 3` | finish or supported split | posting not complete; packed≤picked |
| timeout after send | `Состояние не подтверждено. Проверьте его перед повтором.` | `Проверить состояние` | one active intent fingerprint |
| partial FBO acceptance | `План 10 · принято 9 · отклонено 1` | inspect line reasons/act | accepted+rejected≤planned |
| return not inspected | `Осмотр не выполнен` | complete identity/condition | restock forbidden |

Operator UI uses the exact Russian copy in `S0R_REWORK_CONTRACT.md` §13. Terms `fixture`, `projection`, `provider API`, `readback`, `pending`, `uncertain`, `exemplar`, `QUARANTINE`, `mapped`, `local workspace` and WB copy inside Ozon roots are forbidden visible text.

## 5. Responsibility boundary

### WMS

WMS owns tenant/seller/account authorization, WMS product/warehouse/location, inventory/reservation/movement, local plan/pick/pack, work batches, unload/inbound documents, boxes, audit, secret/asset storage, operation ledger and truthful projection of the last confirmed external fact.

### Ozon

Ozon owns identity/roles, external products/nodes, posting lines/actions, exemplar validation, package restrictions/labels, FBS confirmation, FBO route/timeslot/supply/cargo/TGM/acceptance, returns and provider errors/limits. HTTP success is not business confirmation.

### Manual work

Physical scan/pick/pack/label/handover, return inspection/disposition, discrepancy review and portal fallback remain manual. WMS records actor/time/result but never forges Ozon confirmation.

## 6. Alternatives and price

### A. Put Ozon into existing WB models

Estimate 6–9 weeks. Faster first demo, but loses lines/quantities/packages, forces one-by-one postings into false supplies and risks inventory. Rejected.

### B. Additive Ozon aggregates + adapters/capabilities + current surfaces

Estimate 12–18 engineering weeks, 8–12 atomic slices including migrations, fixtures, WB characterization, print and browser gates. Selected: semantic fidelity with limited UI blast radius.

### C. Migrate WB and Ozon immediately to one canonical marketplace domain

Estimate 20–30+ weeks. Requires WB backfill and simultaneous lifecycle switch. Clean long-term but too risky now. Deferred; projection interfaces from B create a future seam.

## 7. Data model

Names are target contracts, not production code.

### Integration spine

- `marketplace_accounts`: tenant, seller, marketplace, auth mode, encrypted credential refs, external identity, roles/capabilities, expiry, health timestamps.
- `marketplace_product_mappings`: account + offer/product/sku/barcodes + WMS product + state/history.
- `marketplace_nodes`/`marketplace_node_bindings`: provider resource kind/id/raw; WMS warehouse/location target. Warehouse, delivery method, destination and return point remain distinct.
- `marketplace_sync_checkpoints`: account/resource/API-version/filter fingerprint and committed cursor/last-id/window.
- `marketplace_event_inbox`: external event identity/hash and idempotent processing.
- `marketplace_operations`: immutable intent fingerprint, entity/action, external task id, local technical state, last authoritative check/error, actor.
- `marketplace_assets`: kind/entity/source/version/task/checksum/content type/dimensions/status/supersession/applied audit.

### Ozon FBS

- posting: account, posting number, raw status/substatus/actions, dates/delivery, cancellation, local workflow;
- line: stable external key, offer/product/sku snapshot, WMS mapping, ordered/picked/packed;
- unit: line/ordinal, required data, masked identifiers, local/external validation;
- package + package-line quantity; sum per line cannot exceed ordered;
- local work batch membership; it has no Ozon supply/carriage identity.

`FbsWorkItemView` and `FbsWorkspaceView` are provider-neutral projection contracts. Ozon conditional payloads are lines/requirements/packages/assets/handover modes. WB adapter wraps current models and must reproduce current output/behavior.

### Ozon FBO and return

`MarketplaceUnloadRequest` gains account/provider/external-operation snapshots. Child links represent supply order, route/interval, cargo, cargo↔WMS-box, transport cargo, labels, acceptance lines and act under the same document.

`marketplace_returns` links one external return to one existing inbound request. `marketplace_return_inspections` record unit identity/condition/disposition/actor/time. Import/receive alone never increases available stock.

## 8. API and adapters

Additive backend APIs do not create new operator routes:

- account list/save/discovery/sync under `/integrations/marketplaces/self/accounts...`; existing `/integrations/wildberries/*` remains;
- mappings in additive `/products/ff-catalog` data and product-scoped mapping command;
- marketplace/account filter and additive fields on existing `/operations/fbs-orders/...` and `/operations/fbs-supplies/...`;
- Ozon FBO children under existing `/operations/marketplace-unload-requests/{id}/...`;
- inspection under existing `/operations/inbound-intake-requests/{id}/lines/{line_id}/return-inspection`.

Server resolves provider/account from authorized stored entity; client cannot choose another seller's account. Adapter returns normalized capabilities/actions plus sanitized raw snapshots and never changes inventory directly.

Ozon mutating actions require all three: discovered capability, project allowlist and entity `available_actions`. Unknown/absent value disables that action only. A retry first checks operation/entity state. Product publication and `/v2/products/stocks` are absent as client method, route, job, capability and UI action.

## 9. Reusable WMS parts

Reuse unchanged or behind narrow facade: `Tenant`, `Seller`, `Product` as WMS identity, `Warehouse`, `StorageLocation`, inventory services, `PackagingTask`, `MarketplaceUnloadRequest`, inbound flow/boxes, `BackgroundJob`, role/effective-seller checks, audit, binary print storage, current route/render/dialog/stage systems and scan interactions.

Do not reuse as generic truth: `FbsOrder.wb_*`, `FbsSupply.wb_supply_id`, `FbsTrbx`, WB status maps/publisher, `Product.wb_*`, marking `mp_api_key`, WB sticker/trbx/supply QR taxonomy or one universal pagination/retry scheme.

## 10. Semantic surface contract

The full binding side-by-side table is `S0R_REWORK_CONTRACT.md` §12 and machine rows are `REUSE_MAP.json.surface_contracts`. Every touched row contains:

1. exact baseline screenshots/copy/action/state/geometry;
2. one minimal Ozon delta in the same surface;
3. research-backed necessity;
4. WB observable regression invariant;
5. executable assertion.

Required roots stay identical: `fbs-orders-screen`, `fbs-workspace`, `ff-supplies-create-actions`, `ff-supplies-doc-dialog`, `ff-reception-page`, `ff-doc-dialog`, `ff-products-list`, `seller-settings-root`. Identity means same current component tree and stage engine, not copied markup with the same test id.

## 11. Machine/browser gates

### Surface and copy

- Fail any added application route/nav/screen/page/tab/document/workspace/modal.
- AST/self-tests fail query-conditional whole-screen return, Ozon-named replacement component and Ozon-only modal.
- Visible Ozon-root copy fails on WB terms and forbidden jargon from §4.
- Every control has a semantic `data-action-intent`; per zone+intent count≤1, eliminating duplicated/synonymous opens.

### Progress and returns

One selector produces UI and command preflight: integer `plan≥0`, `0≤packed≤picked≤plan`, `remaining=plan-picked`. It runs after mount and every action. Auto-pass requires visible reason and `picked=plan`; stage remains readonly.

Restock requires completed per-unit identity+condition inspection and explicit disposition. Browser asserts disabled state; direct handler/API negative test asserts rejection and zero inventory delta.

### Zero-network fixture

The only fixture URLs and exact clicks are enumerated in `S0R_REWORK_CONTRACT.md` §14.1. Existing screen effects receive a local data/command adapter before scheduling. Harness boots the static shell, arms request record+abort, mounts fixture URL through history API and fails on **any** request from fixture mount through all clicks. Counter must be zero; no allowlist.

### Geometry and WB

Playwright measures fields from `BASELINE_GEOMETRY.json`. Existing overflow may not increase; FBS modal narrow remains 369px without internal horizontal overflow, FBO/return modal 433px, catalog table≤1283.99px narrow, settings body≤1084px narrow. Side-by-side screenshot filenames are binding in contract §15.

WB replay without fixture compares visible copy/action intents/enabled state/stage transitions, request method/path/payload snapshots and geometry. Shared adapter/UI cannot ship until baseline equality passes.

## 12. Async operations, sync and print

Technical operation states are internal: intent created → sent → awaiting authoritative state → confirmed/failed/unknown/manual. Operator sees only approved Russian states. Network timeout after send is unknown, not failure; same fingerprint blocks a new send. Confirmed failure permits a new intent only after cause changes or safe explicit retry.

Push inbox deduplicates and schedules the same detail read used by polling. Checkpoint commits only after full page transaction. Pagination form belongs to resource/API-version, not a generic page counter.

Asset taxonomy keeps product barcode, marking data, FBS posting/package label, posting barcode, carriage act, FBO cargo label, transport-cargo label, acceptance act and return-giveout barcode distinct. Only ready, current, checksum-verified asset is printable; dimensions are not guessed.

## 13. Delivery slices

Each slice returns through BA → Product Before Dev → Atomic Dev → Code Review → live Product Browser Review. Early slices do not mean the module is complete.

1. S0R clickable semantic-reuse prototype and negative gates on the six existing URLs.
2. Account/discovery/isolation in settings.
3. Import-only catalog/mapping and node bindings.
4. Reliability spine: checkpoints, inbox, operation ledger, assets.
5. FBS intake/projection/reserve.
6. FBS pick and unit requirements.
7. FBS packages/labels/handover/cancellation recovery.
8. FBO route/supply async in current document.
9. FBO pick/pack/cargo/TGM/labels.
10. FBO handover/acceptance/act reconciliation.
11. Returns/inbound inspection.
12. Full account isolation, load/backfill, WB regression and live integration hardening.

## 14. Conscious non-goals

- No standalone Ozon UI surface or redesign of current WB flows.
- No production/prototype code in this architecture call.
- No WB table migration/rename in the first program.
- No Ozon product publication or stock write.
- No automatic split/cancel/retry/restock/act acceptance.
- No guessed account capability, label size/format, cargo rule, interval, quota or idempotency guarantee.
- No other marketplace research/implementation.
- No release/deploy/browser approval implied by documents or tests.

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| semantic replacement hidden in current file | AST negative patterns + render-root/stage identity + live side-by-side evidence |
| multi-line posting flattened | additive lines/units/packages; one posting→one work item |
| WB regression | untouched WB models + characterization + request/DOM/geometry/browser replay |
| account leak | tenant→seller→account authorization and account on every external key |
| packed exceeds picked | one selector/preflight and transition property tests |
| duplicate mutation | intent fingerprint and authoritative state check before retry |
| stale/wrong label | distinct asset kinds, version/checksum/supersession |
| false delivered/accepted | local and external facts stored/rendered separately |
| early restock | per-unit inspection and server-side disposition gate |
| API drift | versioned fixtures, raw enum tolerance, capability off by default |
| narrow geometry regression | numeric non-worsening gates and named desktop/narrow pairs |

## 16. Вопросы владельцу

**Вопросов владельцу: 0.** Owner override fixes the product boundary. Unknown auth mode, account capabilities, label formats, cargo rules and return policy remain unknown and resolve to a hidden/disabled action plus truthful Russian reason; they are not guessed.

## 17. Exact handoff to clickable React prototype

The developer follows `S0R_REWORK_CONTRACT.md` §§13–16 verbatim:

- starts from `2af800d5846d351904cab050860356038b6d282e` and removes rejected semantics rather than copying them;
- changes only current components/data seams and test-only local adapters;
- implements the six enumerated URLs through the same render trees, exact Russian copy/action intents and exact click traces;
- enforces progress, mandatory inspection, zero requests, duplicate-action and geometry gates with negative self-tests;
- captures all named desktop/narrow baseline→Ozon screenshot pairs and replays WB baseline;
- performs no backend/provider/stock request, DB/data mutation, secret access, deployment or production implementation.

Architecture is not `PRODUCT_APPROVED_FOR_DEV` and not `PRODUCT_BROWSER_APPROVED`. Next work requires its own isolated product gate.
