# S13 ARCHITECT_PLAN - BLG-D07

## Verdict

`ARCH_PLAN_READY`

This plan covers the single S12 card `BLG-D07-C1`. It is an architecture
artifact only. S13 does not change application code, create a migration, run a
worker, call WB/Ozon, access credentials, deploy, release, or touch production
data.

## Decision summary

1. Introduce one reconciliation service for every repeated WB order-status
   read. The periodic worker, manual status endpoint, and supply tracking read
   must call this service. They must not call the current
   `_apply_wb_status_to_order`, because that function can release reservations,
   reverse shipment inventory, and detach an order from a supply. Those effects
   are explicitly forbidden by S11 for BLG-D07.
2. Keep `fbs_orders.last_wb_sync_at` as the canonical per-order
   `last_success_at` storage column. Its existing writer in
   `fbs_tracking_service.py` already sets it only after a matching row. Add
   separate attempt, retry, ordering, conflict, and terminal-retention fields;
   do not overload one timestamp with cycle success.
3. Persist an append-only attempt/observation journal. A valid exact response
   row and the current projection commit in one transaction. Replay uses the
   attempt id plus an order generation, so a duplicate response is idempotent
   and an older concurrent response cannot overwrite a newer observation.
4. Replace the serial all-seller loop with a minute scheduler that enqueues one
   isolated task per due tenant/seller lane. Due orders are selected by durable
   `next_reconcile_at`, then oldest success, then order id. Successful or failed
   processing moves the selected rows forward, so a permanent cycle cap cannot
   keep the tail at the back forever.
5. Use the WB status endpoint at its current documented maximum of 1000 unique
   IDs per request. Keep the existing 100-item constant for endpoints whose
   contract is still 100; introduce a status-specific limit rather than
   widening every FBS batch accidentally.
6. Add one shared, durable seller rate budget for the documented FBS rate-limit
   family. Background status reads may reserve at most 90 of 300 units/minute;
   all local FBS traffic is capped at 270 units/minute, leaving 30 units of
   external headroom. Interactive calls have priority over the background
   allocation. Every request pre-reserves 10 units, because the current oracle
   charges every `4XX` as 10; unused units are returned after a non-`4XX`
   response, while a crash remains conservatively overcharged until expiry.
7. Do not retain batch-to-single fallback. Missing IDs are retried in a later
   scheduled batch; duplicate/foreign rows are isolated; malformed whole
   responses apply no rows. This removes the current 1-to-1000 amplification
   path and makes the S03 fallback-cap case assert zero immediate fan-out.
8. The approved operator read surface requires an API and visible table change.
   The current worklist response exposes only `status`, `wb_status`, and
   `supplier_status`; `FfFbsOrdersScreen` displays no attempt, success,
   freshness, error, retry, or conflict state. Therefore `ui_change` is a
   required impact expansion. S09/S10 must approve the `S-03` table-zone design
   before S16, and S24/S25 are required after implementation. S13 does not
   design or implement that UI.

## Resource graph

```text
Celery Beat, every 60 seconds
  -> due seller-lane scan ordered by oldest lane success
    -> one wms.fbs_order_statuses_seller task per tenant/seller
      -> seller advisory lock + lane lease
        -> due-order query by next_reconcile_at/last_success/id
          -> attempt + per-order generation committed
            -> shared seller WB rate-budget reservation
              -> POST /api/v3/orders/status, max 1000 unique IDs
                -> strict response partition
                  -> exact unique requested row
                    -> locked generation check
                      -> raw status + side-effect-free projection
                      -> per-order last_success + retry/error cleanup
                      -> append-only observation
                  -> missing/duplicate/foreign/unknown/malformed lane
                    -> safe error + bounded next retry, no false success
                -> lane cycle marker and sanitized metrics
                  -> worklist read model/API
                    -> S-03 operator freshness surface after S09/S10

All FBS callers with tenant/seller context
  -> shared wb_seller_rate_budget_service
    -> total seller bucket and background sub-budget
      -> interactive priority, 4XX x10 accounting, 429 pause

Local WB emulator
  -> deterministic status rows, lifecycle transitions and fault scripts
    -> S15 cases -> S19 runnable bindings -> S22/S23 isolated execution
```

## Existing resources to extend

- `backend/app/models/fbs_order.py`: additive per-order reconciliation fields
  and relationships. Existing raw `wb_status`, `supplier_status`, and
  `last_wb_sync_at` remain authoritative storage; no rename or destructive
  migration.
- `backend/app/models/__init__.py`: register/export the new attempt,
  observation, seller-lane, and seller-budget models for ORM/Alembic metadata.
- `backend/app/services/wb_marketplace_orders_service.py`: remove status
  polling responsibility from `sync_order_statuses` and delegate to the new
  reconciliation service. Keep import/upsert behavior separate. The existing
  `_apply_wb_status_to_order` remains only for previously approved workflows
  that intentionally own warehouse effects; BLG-D07 status reads cannot reach
  it.
- `backend/app/services/fbs_cancellation_service.py`: make
  `sync_seller_order_statuses` a compatibility facade over reconciliation,
  while `cancel_order` remains unchanged and outside the read-only worker.
- `backend/app/services/fbs_tracking_service.py`: route status reads through
  the same per-order apply path. Supply-level tracking summaries may aggregate
  per-order success, but may not write a blanket success time for missing rows.
- `backend/app/services/fbs_autopoll_service.py`: replace
  `sync_fbs_order_statuses_all_sellers` serial processing with due-lane
  dispatch and a per-seller executor. Marking and supply tracking are not
  chained inside the same status transaction.
- `backend/app/services/fbs_wb_seller_lock_service.py`: retain the PostgreSQL
  seller advisory lock as the outer same-seller exclusion. The new durable
  lane lease covers task crash/requeue; the advisory lock alone is not a retry
  journal or a rate limiter.
- `backend/app/services/wildberries_fbs_client.py`: add
  `MAX_MARKETPLACE_STATUS_BATCH = 1000`, strict typed status-row validation,
  response headers/status metadata, injected timeout, and seller budget
  context. Keep `MAX_MARKETPLACE_FBS_BATCH = 100` for stickers/meta/supply
  contracts.
- `backend/app/services/wildberries_client.py`: preserve the public compatibility
  wrapper while passing status-specific batch/base/timeout and rate context to
  the typed client. No token value is logged or persisted in budget/audit rows.
- `backend/app/celery_app.py`: keep the existing Beat entry name, change it to a
  one-minute dispatcher, add the isolated status queue route, set worker
  prefetch to one for fair seller-lane consumption, and prevent overlapping
  dispatcher leases.
- `backend/app/tasks/background_jobs.py`: add the per-seller task accepting only
  tenant id, seller id, and controller-generated lane run id. Celery native
  autoretry is disabled; retry time is durable application state.
- `backend/app/core/settings.py`: add bounded configuration listed below. No
  setting contains a credential or production endpoint override.
- `backend/app/services/fbs_worklist_service.py`: compute the five Product
  freshness states from persisted UTC facts and include the safe read model.
  `CONFLICT` has priority over age; a failed attempt never erases an older
  success.
- `backend/app/api/fbs_orders.py`: extend `FbsWorklistOrderOut` and the legacy
  `FbsOrderOut` with the reconciliation read object. The manual
  `/sync-statuses` command reuses the seller lane and returns accepted/updated/
  deferred counts rather than bypassing rate, lock, retry, or audit rules.
- `frontend/src/screens/v2/fbsApi.ts`: add a typed reconciliation object to
  `FbsWorklistOrder`; no raw body, stack trace, token, or internal exception is
  exposed.
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`: after S09/S10 only, render
  freshness and last confirmation in the existing `S-03` status cell/table
  zone. This is not a new action, bulk control, notification center, or screen.
- `frontend/screens.registry.json`: update the `S-03` table-zone resource links
  if the accepted S09 contract adds a new UI-kit component/shared file.
- `wb_emulator/routes/orders.py`, `wb_emulator/services/orders_store.py`,
  `wb_emulator/services/fault_injection.py`, and `wb_emulator/routes/admin.py`:
  implement the deterministic status/fault contract below.
- `backend/alembic/versions/<controller-allocated-next-revision>.py`: one
  additive migration. S17/S18 must resolve the actual canonical Alembic head
  immediately before allocation because other wave cards can add revisions.

## New resources

- `backend/app/models/fbs_order_status_reconciliation.py`: attempt,
  observation, seller lane, and seller rate-budget ORM models.
- `backend/app/services/fbs_order_status_reconciliation_service.py`: eligible
  selection, attempts, strict partition, mapping, conflict handling,
  idempotent apply, retry planning, terminal retention, cycle result, and
  sanitized metrics. It must not import inventory, reservation, packing, box,
  marking, shipment, supply mutation, or WB command services.
- `backend/app/services/wb_seller_rate_budget_service.py`: atomic seller-level
  total/background budget reservation, settlement, interactive priority,
  minimum interval, burst, 4XX cost, and 429 blocking.
- `backend/tests/test_fbs_status_reconciliation_unit.py`: mapping, freshness,
  error classification, retry, jitter, terminal retention, and capacity math.
- `backend/tests/test_fbs_status_reconciliation_db.py`: exact-match apply,
  journal, generation fencing, replay, locks, lane fairness, and migrations.
- `backend/tests/test_fbs_status_reconciliation_emulator.py`: all 19
  `D07-EMU-*` contracts through in-process ASGI HTTP, not `MockTransport` on
  both sides.
- `backend/tests/test_fbs_status_reconciliation_api.py`: tenant/seller read and
  command authorization, safe response schema, reload/read-back, and legacy
  compatibility.
- `frontend/tests-e2e/ff-fbs-order-freshness.spec.ts`: only after S09/S10,
  visible `NOT_SYNCED/FRESH/DELAYED/STALE/CONFLICT`, local time rendering,
  failure/retry wording, long seller/order data, and reload.

## Additive data model

### `fbs_orders` projection fields

Add nullable/defaulted columns:

- `wb_status_first_eligible_at timestamptz null`: initialized lazily when a
  nonterminal order first enters the new scheduler; migration does not pretend
  a historical eligibility timestamp is known.
- `wb_status_last_attempt_at timestamptz null`: dispatch boundary for the most
  recent request containing the order.
- existing `last_wb_sync_at timestamptz null`: canonical per-order last success
  after exactly one valid matching row is durably applied; API alias is
  `last_success_at`.
- `wb_status_next_reconcile_at timestamptz null`: fairness and normal 15-minute
  schedule, including the terminal-retention lane.
- `wb_status_next_retry_at timestamptz null`: non-null only while a bounded
  retry is scheduled; read surface may expose it.
- `wb_status_sync_error_code varchar(48) null`: allowlisted safe category such
  as `transport`, `timeout`, `upstream_5xx`, `rate_limited`, `request_invalid`,
  `access`, `payment_required`, `missing_row`, `duplicate_row`, `foreign_row`,
  `invalid_response`, `unknown_status`, or `capacity`.
- `wb_status_attempt_count integer not null default 0`: consecutive retryable
  failures since the last success; reset only by a valid exact row.
- `wb_status_sync_generation bigint not null default 0`: incremented when an
  attempt is allocated for this order.
- `wb_status_applied_generation bigint not null default 0`: fencing value of
  the newest accepted observation.
- `wb_status_terminal_observed_at timestamptz null` and
  `wb_status_reconcile_until_at timestamptz null`: bounded terminal retention.
- `wb_status_conflict_at timestamptz null` and
  `wb_status_conflict_code varchar(48) null`: unresolved conflict projection.

Freshness is not stored as a clock-dependent enum. The read service derives it
at `server_now`:

```text
CONFLICT  when conflict_at is set and unresolved
NOT_SYNCED when last_wb_sync_at is null and eligibility age <= 15 minutes
STALE     when last_wb_sync_at is null and eligibility age > 15 minutes
FRESH     when last success age <= 15 minutes
DELAYED   when 15 minutes < age <= 60 minutes
STALE     when age > 60 minutes
```

Indexes:

- `(tenant_id, seller_id, wb_status_next_reconcile_at, last_wb_sync_at, id)` for
  due-order selection;
- `(tenant_id, seller_id, wb_status_next_retry_at)` for retry dispatch;
- partial index on unresolved `wb_status_conflict_at` for operational review.

### `fbs_order_status_sync_attempts`

One row per outbound batch:

- `id`, `cycle_id`, `tenant_id`, `seller_id`, `lane_run_id`, `batch_no`;
- `started_at`, `completed_at`, `outcome`, safe `error_code`, HTTP status,
  `next_retry_at`;
- `order_count`, `request_fingerprint_sha256`, `returned_valid_count`,
  `missing_count`, `duplicate_count`, `foreign_count`;
- `rate_units_reserved`, `rate_units_charged`, and `response_class`;
- sanitized executor/queue metadata. No token, headers, URL query, raw body, WB
  response text, or operator PII.

Unique `(tenant_id, seller_id, lane_run_id, batch_no)` makes dispatcher replay
return the existing attempt. The request fingerprint hashes sorted local order
UUID/WB-ID pairs plus contract version; it is evidence, not authority to cross
tenant or seller scope.

### `fbs_order_status_observations`

Append-only per-order evidence:

- `id`, `tenant_id`, `seller_id`, `order_id`, `attempt_id`, `generation`;
- `wb_order_id`, previous/new raw `supplier_status` and `wb_status`;
- previous/proposed/final local projection;
- `observed_at`, `applied_at`, `apply_result` (`applied`, `no_change`,
  `unknown`, `conflict`, `stale_generation`, `invalid_row`), and safe reason;
- terminal/retention facts and optional `supersedes_observation_id`.

Unique `(order_id, attempt_id)` prevents duplicate history on replay. Unique
`(order_id, generation)` prevents two responses from claiming the same fence.
The observation and `fbs_orders` projection commit together under an order
`FOR UPDATE` lock.

### `wb_seller_status_sync_lanes`

One row per `(tenant_id, seller_id)`:

- next due, lease owner/until/fencing token, last cycle attempt/success;
- consecutive batch failures, circuit state (`closed`, `open`, `half_open`),
  blocked reason/until, and last safe error;
- due/processed/succeeded/failed/deferred/capacity-stale counts;
- terminal-retention and policy version.

The lane row never stores token material. Seller existence is always checked
with both tenant and seller predicates before lease acquisition.

### `wb_seller_rate_budgets`

One row per `(tenant_id, seller_id, window_started_at)` with atomic counters for
total, background, reserved, settled, and burst units plus `last_request_at`
and `blocked_until`. The service locks the current row and rejects/defers a
request before network I/O when any of these would be exceeded:

- local total: 270 units/minute;
- background status: 90 units/minute;
- minimum interval: 250 ms, stricter than the documented 200 ms;
- local burst: 15, stricter than the documented 20.

Keep 24 hours of rows for replay/incident evidence, then delete by a bounded
local maintenance job. This is operational metadata, not an order history.

## Status mapping and conflict policy

Normalize by trimming/lowercasing but always retain the original raw strings in
the observation. The side-effect-free projection is:

| WB observation | Local projection | Regular eligibility |
|---|---|---|
| `wbStatus=waiting`, `supplierStatus` null/`new` | keep current local workflow state; a new untouched order remains `new` | yes |
| `supplierStatus=confirm|complete` with nonterminal `wbStatus` | `external_processing` unless the local order already has an internal supply/workflow state that must be preserved | yes |
| `wbStatus=sorted` | `sorted` | yes |
| `ready_for_pickup`, `postponed_delivery`, `accepted_by_carrier`, `sent_to_carrier` | `external_processing`; raw value remains visible | yes |
| `sold` | `done` | terminal retention |
| `canceled`, `canceled_by_client`, `declined_by_client`, `canceled_by_carrier` | `cancelled` | terminal retention |
| `defect` | `defect` | terminal retention |
| `supplierStatus=cancel|cancel_carrier` | `cancelled` unless conflict | terminal retention |
| unknown supplier/WB value | no guessed local change | yes, attention/error |

A terminal result is a `CONFLICT`, not a local overwrite, when the order shows
physical or irreversible local progress: shipment-reversal ledger exists,
local status is `in_delivery|sorted|done`, or pick/pack is already completed.
The conflict observation stores the proposed mapping and current local state;
it does not reverse stock, release reserve, detach supply, reopen work, or call
WB. S15 must test each guard independently.

For a non-conflicting terminal row, commit the terminal projection and
`terminal_observed_at`, then keep it in a retention lane every 15 minutes for
24 hours. A repeated identical row is an idempotent `no_change` success. A
different valid row during retention creates a new observation and applies the
same conflict/order rules. After 24 hours, the order leaves regular polling;
the terminal observation and audit remain. A crash before commit leaves it due;
a crash after commit replays by attempt/generation without duplicate effects.

## Scheduling, fairness, and capacity

### Scheduler and queue

- Beat tick: 60 seconds. It performs only a due-lane DB scan and enqueue; it
  does not call WB.
- Queue: `fbs-status-reconciliation`, with environment/wave namespace in test
  and integration. Task routing is explicit; no worker may consume another
  task's isolated queue in S19/S22 fixtures.
- One task per `(tenant_id, seller_id, lane_run_id)`. Advisory lock and durable
  lease prevent manual, tracking, periodic, or duplicate Celery execution from
  running the same seller concurrently.
- Seller lanes are enqueued by `last_cycle_success_at NULLS FIRST`, then
  `next_due_at`, tenant, seller. Celery prefetch one prevents a single worker
  from reserving many seller tasks.

### Order fairness

- Normal nonterminal success sets `next_reconcile_at = success + 15 minutes`.
- New/never-synced and due retries sort first by due time, then
  `last_wb_sync_at NULLS FIRST`, then UUID.
- A seller task may issue at most 9 worst-case-charged status requests in one
  minute window. Each selected row receives a later success/retry time before
  another batch is selected. There is no scan that restarts permanently at
  `created_at_wb`.
- Selection uses `FOR UPDATE SKIP LOCKED`; the exact tenant and seller filters
  are part of the SQL predicate. The request is built from the locked snapshot,
  deduplicated by WB order ID, and duplicate local IDs become a local contract
  error before network I/O.

### 15-minute capacity proof

The guaranteed background budget assumes the worst documented cost for every
request, not the happy-path refund:

```text
90 units/min / 10 units/request = 9 requests/min
9 requests/min * 1000 orders/request * 15 min = 135,000 orders/seller/15 min
```

The worker records response latency and due count. If a seller has more than
135,000 due eligible orders, or latency/interactive pressure makes the
projected drain time exceed 15 minutes, it does not break the WB budget. It sets
safe error `capacity`, leaves orders due, emits a sanitized capacity metric,
and the read surface derives `DELAYED`/`STALE` at the approved boundaries.

## Retry, lane stop, and circuit breaker

All retries are durable schedules; the worker does not sleep while holding a
seller lock.

- Transport, DNS, timeout, and `5XX`: retry delays 15 seconds, 60 seconds, and
  5 minutes, each with deterministic jitter in `[-20%, +20%]` derived from
  attempt id. After three consecutive retries, the orders return to the normal
  15-minute lane with the historical success unchanged.
- Circuit breaker: five consecutive retryable batch failures for one seller
  open the lane for 5 minutes. Half-open sends exactly one batch; success closes
  it, failure reopens for 15 minutes. Other sellers remain runnable.
- `429`: no immediate retry and no per-ID fallback. Pause the seller until the
  later of a valid `Retry-After`, the shared budget's next availability, and a
  5-minute local default. Parse delta-seconds or HTTP-date, cap malformed input
  to the default and a valid future delay to 24 hours.
- `400`: mark request/contract failure, no same-payload retry. Open the lane for
  30 minutes and allow only one half-open probe after the payload/version has
  been rebuilt from current due rows.
- `401`/`403`: set `access` stop with no automatic status probe. Resume only
  when the existing credential configuration changes or an authorized health
  process marks access healthy. BLG-D07 performs no credential action.
- `402`: set `payment_required` stop with no automatic retry. Resume requires a
  separate operational health signal, not a payment or cabinet action here.
- Unexpected other `4XX`, invalid JSON/schema, or wrong top-level shape: no
  rows apply. Open the lane for 30 minutes and emit contract-drift evidence.
- Missing row: valid rows in the same response may apply; only the missing order
  gets `missing_row` and a 60-second retry.
- Duplicate requested ID: that ID is invalid and not applied; unambiguous rows
  may apply. Retry the duplicate ID after 5 minutes and emit contract drift.
- Foreign ID: never look it up outside the already scoped request map. Ignore
  it, count `foreign_row`, and continue applying exact unambiguous requested
  rows. The response cannot reveal whether that foreign ID exists locally.
- Unknown enum: persist the raw observation as `unknown`, keep the current local
  projection, set attention/error, and retry after 15 minutes. No irreversible
  side effect is reachable.

## Idempotency and ordering

1. The scheduler creates `lane_run_id`; each batch gets deterministic
   `(lane_run_id, batch_no)` identity. Re-dispatch finds the existing attempt.
2. Before network I/O, lock the due orders in UUID order, increment each
   generation, set attempt/next time, write the attempt, and commit. This is the
   durable inclusion fact for `last_attempt_at`.
3. Reserve shared rate units atomically, then call only the configured
   Marketplace base. A crash after reservation but before settlement cannot
   overspend; the reservation expires conservatively.
4. Strictly partition the response by requested WB ID. No `last-row-wins`, no
   bare global order lookup, and no cross-seller apply.
5. For each valid row, open a short transaction, select the order by
   `(id, tenant_id, seller_id)` with `FOR UPDATE`, and compare generation. A
   generation lower than `wb_status_applied_generation` writes
   `stale_generation` evidence but does not change projection or success time.
6. Recompute mapping and conflict under the lock. Write observation, raw fields,
   allowed projection, success timestamp, retry/error cleanup, generation, and
   terminal facts in one transaction.
7. Repeating the same attempt/order returns the existing observation. A newer
   attempt with identical WB values may advance `last_success_at` and append
   `no_change`, but cannot trigger any warehouse/marketplace side effect.
8. A seller cycle is successful only when every attempted batch is settled and
   every requested order has either a valid row or an explicit per-order
   outcome. Cycle success never updates an order's `last_wb_sync_at`.

## Tenant, seller, queue, and data isolation

- Every selection, attempt, observation, lane, budget, and apply query includes
  both `tenant_id` and `seller_id`; a UUID alone is never authority.
- One WB request contains IDs for exactly one tenant/seller lane. The token is
  resolved only after the seller-in-tenant check and never stored in job
  arguments, DB audit, logs, emulator evidence, or Git.
- Duplicate WB IDs across sellers are expected and safe because response maps
  are request-local. A foreign response ID is ignored without a DB lookup.
- API read surfaces keep `require_fbs_operator_access` plus effective-seller
  filtering. A seller user cannot request another seller by query/body and
  receives the same not-found behavior without timing/count disclosure.
- S19 fixtures allocate unique DB/schema, queue, emulator namespace, clock,
  random seed, and evidence directory. Egress is deny-by-default and allows
  only the in-process/local emulator host.
- Logs/metrics contain stable seller pseudonym, attempt id, safe category,
  counts, latency, age, and rate units. They never contain order payloads,
  tokens, Authorization, raw response bodies, barcodes, marking codes, or
  seller names.

## Local WB emulator contract

The existing emulator already supports seller-scoped status rows and omitted
IDs. Extend its test-only admin/fault state with deterministic, resettable
scripts:

- arbitrary current `supplierStatus`/`wbStatus`, including all current carrier
  values and unknown strings;
- response sequence per seller/request number;
- omit, duplicate, and foreign response IDs;
- malformed top-level/body/field types;
- status codes `400/401/402/403/404/409/429/500/502/503`, optional
  `Retry-After`, and transport delay beyond client timeout;
- crash hook after attempt commit and after N applied rows, implemented in the
  WMS harness rather than killing the emulator;
- request ledger containing seller key, method, path, requested IDs, timestamp,
  scripted response, and rate-cost class, but never WMS credentials.

Admin scripts are enabled only by the emulator admin test token and reset with
the emulator fixture. Production compose must continue to contain no emulator
service/base URL. The emulator contract allows all 19 S03 cases without WB
sandbox or production calls.

## Read surface and mandatory impact expansion

API shape added to each order:

```json
{
  "wb_reconciliation": {
    "freshness": "NOT_SYNCED|FRESH|DELAYED|STALE|CONFLICT",
    "last_attempt_at": "UTC timestamp or null",
    "last_success_at": "UTC timestamp or null",
    "next_retry_at": "UTC timestamp or null",
    "failure_category": "safe code or null",
    "conflict_code": "safe code or null"
  }
}
```

`server_now` remains the rendering clock. Backend computes the enum to avoid
client clock drift; frontend renders UTC timestamps in the operator locale.
The UI wording/layout belongs to S09. S13 limits the zone to the existing
`S-03` table status cell and forbids a new button, column-heavy redesign,
manual refresh workflow, or admin-only replacement for operator visibility.

Controller implication:

- add trait `ui_change` and stages `S09`, `S10`, `S24`, `S25`;
- return to the first missing pre-Dev UI stage before S16;
- preserve S11/S12/S13 inputs by hash unless S09 discovers a Product contract
  conflict; otherwise only the new UI receipts and dependent downstream hashes
  are added;
- S15 may define backend/emulator cases now, but the Product-before-Dev packet
  cannot pass without accepted S09/S10 evidence.

## Configuration decisions

Proposed bounded settings with validation:

- `FBS_STATUS_RECONCILIATION_ENABLED`, default false until compatibility floor;
- `FBS_STATUS_DISPATCH_INTERVAL_SEC=60`, range 30..300;
- `FBS_STATUS_FRESH_SEC=900`, fixed to Product 15 minutes unless a new Product
  contract changes it;
- `FBS_STATUS_STALE_SEC=3600`, fixed to Product 60 minutes;
- `FBS_STATUS_BATCH_SIZE=1000`, range 1..1000;
- `FBS_STATUS_REQUEST_TIMEOUT_SEC=10`, range 2..30;
- `FBS_STATUS_TERMINAL_RETENTION_SEC=86400`, range 3600..604800;
- `WB_FBS_LOCAL_TOTAL_UNITS_PER_MIN=270`, max 270;
- `WB_FBS_BACKGROUND_UNITS_PER_MIN=90`, max one third of documented capacity;
- `WB_FBS_MIN_INTERVAL_MS=250`, min 200;
- `WB_FBS_LOCAL_BURST=15`, max 15.

Settings cannot raise local limits above these safety ceilings without a new
external-contract/Product review. Lower values are allowed and automatically
feed capacity/staleness reporting.

## Implementation order and resource locks

`BLG-D07-C1` remains one Product card, but S18 executes these internal slices in
order so each boundary can be reviewed and tested:

1. **Compatibility schema and pure policy.** Lock the current Alembic head,
   `fbs_order.py`, model exports, new reconciliation models/service, migration,
   and unit/DB tests. Add nullable/defaulted schema and side-effect-free mapping
   behind a disabled worker flag.
2. **Emulator and contract runner.** Lock the four named `wb_emulator` files and
   status client tests. Implement deterministic faults/ledger and the strict
   1000-ID status client contract.
3. **Shared budget and scheduler.** Lock `wildberries_fbs_client.py`,
   `wildberries_client.py`, the new budget service, seller lock, autopoll,
   Celery, tasks, settings, and all affected FBS call sites. A shared-client
   signature change cannot be developed concurrently with another card editing
   those call sites.
4. **Unify status writers.** Lock marketplace-order, cancellation, tracking,
   and autopoll services. Remove every repeated status-read path to the
   side-effectful apply function before enabling the worker.
5. **Read API and accepted UI.** After S09/S10, lock worklist service,
   `fbs_orders.py`, `fbsApi.ts`, `FfFbsOrdersScreen.tsx`, `S-03` table zone,
   screen registry if required, and API/E2E tests.
6. **Activation evidence.** Enable only in isolated S22/S23 fixtures, run the
   full direct/breaker matrix, migration rehearsal, queue/host isolation, and
   adjacent FBS regression. No production enablement is part of S18/S23.

Exclusive logical locks:

- table/migration: `fbs_orders`, new attempt/observation/lane/budget tables,
  Alembic revision slot;
- service/external contract: WB Marketplace FBS status client and shared seller
  rate budget;
- queue: `wms.fbs_order_statuses_autopoll`, new per-seller task, isolated queue;
- process: FBS order status reconciliation and supply tracking status reads;
- screen: `S-03/table/status-cell` only after approved UX contract.

If another wave card touches the shared FBS client, seller lock, `fbs_orders`,
Celery schedule, or `S-03` status zone, the controller serializes that card with
BLG-D07. A newly found status writer or FBS rate-family caller returns to S13
for lock expansion; Atomic Dev must not patch it silently.

## Test boundaries and S15/S19 handoff

S15 must materialize all 19 research IDs unchanged and add the following direct
and breaker rows:

- exact `15:00` and `60:00` freshness boundaries using a frozen UTC clock;
- legacy row with no eligibility/success, lazy eligibility initialization, and
  no fabricated historical backfill;
- one seller with 135,000 due orders at the guaranteed capacity and 135,001 as
  visible capacity breach, using generated DB fixtures rather than HTTP bodies
  of that size;
- two sellers where one is rate-limited/access/payment/circuit-open and the
  other completes;
- two tenants and two sellers with the same WB order ID, plus a foreign response
  ID, proving zero cross-scope lookup/mutation/disclosure;
- older response arriving after a newer generation, duplicate task delivery,
  crash before response apply, and crash after N row commits;
- terminal observation retained for 24 hours, repeated terminal no-change, and
  changed late result;
- cancellation/defect/sold after pick, pack, shipment ledger, `in_delivery`,
  `sorted`, and `done`, each producing conflict and zero warehouse side effect;
- manual status sync, tracking sync, and periodic worker producing the same
  journal/read model and respecting the same seller lock/budget;
- API and reload read-back for all five freshness states and safe failure
  categories;
- static/import boundary plus behavior spies proving the reconciliation service
  cannot call reserve release, inventory movement, supply detach, packing,
  marking, shipment, cancel endpoint, stock publish, or another WB mutation;
- migration upgrade from the previous head, nullable compatibility, index/query
  plan at volume, application stop rollback, and no destructive downgrade.

S19 bindings must use:

- pure unit tests for mapping/freshness/retry/rate/capacity;
- PostgreSQL integration tests for `FOR UPDATE SKIP LOCKED`, advisory lock,
  generations, unique constraints, migration, and concurrent workers;
- Celery eager/local harness with unique queue namespace and prefetch-one
  assertions;
- in-process ASGI emulator HTTP for external contract/fault cases;
- FastAPI tests for authorization/read schema;
- Playwright only for the S09-approved visible surface;
- host guard proving every outbound status URL is the configured local emulator.

No test in S15/S18/S19/S20/S22/S23 may use live WB, WB sandbox, Ozon,
production data, credentials, or cabinets.

## S20 review gates

Code Review must return to S13/S18/S19 as typed finding if the diff:

- still calls `_apply_wb_status_to_order` from a repeated status read;
- releases reserve, reverses inventory, detaches a supply, or sends a WB command;
- treats `sorted` as terminal or drops carrier/nonterminal values;
- updates `last_wb_sync_at` from HTTP 200, cycle completion, missing, duplicate,
  foreign, malformed, unknown, wrong-seller, or stale-generation evidence;
- starts per-ID fallback, sleeps under seller lock, uses Celery autoretry, or
  retries access/payment/request errors blindly;
- maintains a status-only counter without the shared seller total budget,
  interactive priority, 4XX x10 accounting, or safety reserve;
- scans by `created_at_wb` with a permanent cap that can starve the tail;
- looks up a response order by bare WB ID or local UUID outside tenant/seller
  predicates;
- stores clock-dependent freshness instead of deriving it at read time;
- exposes raw upstream payload/error/token/header data;
- hides mandatory freshness outside the operator surface or changes `S-03`
  without S09/S10 and ui-kit provenance;
- omits an emulator/runnable binding for any applicable S15 case.

## Rollout and rollback risk

1. **Schema compatibility floor.** Apply only additive nullable/defaulted
   columns/tables/indexes. Existing readers ignore them; the worker remains
   disabled. No historical success/attempt/event is invented. Migration
   rehearsal records actual head, row counts, lock duration, and query plan.
2. **Code compatibility floor.** Deploy the unified status-read service, shared
   budget, and read schema with the worker still disabled. Manual/tracking paths
   can exercise it in the isolated environment only after S22 cases pass.
3. **Controlled enablement packet.** A future separately authorized release may
   enable seller lanes gradually and watch due age, success ratio, 4XX units,
   429s, circuit state, queue lag, conflicts, unknown enums, capacity stale,
   and attempts without matching success. BLG-D07 itself does not authorize the
   deploy or production enablement.
4. **Stop rollback.** Disable Beat dispatch and drain/stop only the isolated
   status queue. Durable due/attempt state remains replayable; no data repair is
   required to stop polling.
5. **Application rollback boundary.** After the new worker has written
   reconciliation state, do not roll back below the code compatibility floor:
   older code would resume the side-effectful apply path and exclude `sorted`.
   Roll back only to a SHA that understands the additive schema and keeps the
   old status worker disabled.
6. **Data rollback.** Observations/attempts are audit and are never deleted by
   automatic rollback. Projection correction is a new append-only observation
   after Product/review authority; schema downgrade after data exists is a
   separately approved destructive change.

Principal risks are shared-client blast radius, high-volume indexes, old status
writers bypassing generation fencing, and UI profile under-classification. The
locks, disabled-first rollout, status-writer inventory, migration rehearsal,
emulator matrix, and mandatory `ui_change` route are the corresponding gates.

## Downstream stage implications

- **S15 CASE_FACTORY:** create the full matrix above, including all 19 named
  emulator cases, the 15/60-minute states, capacity formula, conflict/no-side-
  effect proof, tenant/seller isolation, queue isolation, and migration/rollback.
- **S18 DEVELOPMENT:** one atomic card and one scoped commit set. Follow the six
  internal slices, allocate the actual migration head at implementation time,
  and keep production enablement false. Any new status writer/rate caller or UI
  zone returns to S13/S09 rather than expanding scope silently.
- **S19 TEST_AUTOMATION_BINDING:** every deterministic case gets a concrete
  pytest/Celery/emulator/API/Playwright reference, reset, frozen clock, timeout,
  expected trace, host guard, and evidence schema. Manual evidence is not valid
  for rate, retry, replay, mapping, isolation, migration, or read-back.
- **S20 CODE_REVIEW:** apply the explicit rejection list above and classify
  findings as `PLAN`, `IMPLEMENTATION`, `AUTOMATION`, or `MIGRATION` so the
  controller returns to the owning stage.
- **S23 INTEGRATION:** pin one integration SHA and immutable backend/worker/
  frontend artifacts; run migration upgrade, status queue, local emulator,
  complete FBS regression, `S-03` UI regression after approval, and verify no
  production host is reachable. Rebuild/rebase invalidates evidence.
- **S26 RELEASE_AUTHORIZATION:** release packet must state worker flag, queue,
  compatibility-floor SHA, stop command, migration head, rollback floor,
  monitoring thresholds, and that production deploy still needs separate owner
  authorization.

## Blocker and next stage

No external access, secret, fixture, owner input, or irreversible action is
needed to complete S13. The architecture is ready for `ARCH_PLAN_READY`.

The expected controller stage after S13 is `S15 CASE_FACTORY` because the
current medium-risk profile does not enable S14. However, the current task
profile is incomplete: the mandatory operator read surface is a confirmed
`ui_change`. The controller must add S09/S10 before S16 and S24/S25 downstream;
without those receipts, Product-before-Dev is blocked even if S15 cases are
otherwise complete.
