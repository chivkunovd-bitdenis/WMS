# S13 ARCHITECT_PLAN - BLG-I16

## Verdict

`ARCH_PLAN_BLOCKED`

The server architecture is implementable, and the provisional plan below fixes
the API, database, transaction, worker, idempotency, progress, recovery and
resource boundaries for `BLG-I16-C1`. It cannot honestly receive
`ARCH_PLAN_READY` on the current controller packet for two machine-contract
reasons:

1. `BLG-I16` changes runtime behavior, but its required-stage set omits S08.
   Pipeline v2 requires a versioned behavior contract or an explicit accepted
   `NO_RUNTIME_BEHAVIOR` receipt before architecture; this task is plainly not
   a no-runtime change.
2. The accepted Product result requires the existing operator surface to read
   and display accepted/running/partial/final server state. The implementation
   must replace the client mutation loop in
   `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, so `ui_change` is
   applicable. The current profile omits S09, S10, S24 and S25, and this
   architect may not perform or self-approve those BA, UX, Design or Product
   stages.

No Product decision is missing and no live environment is needed to resolve
this. The blocker is a controller impact-profile gap. S13 must remain waiting
until the profile and invalidated upstream receipts are repaired by their
owning roles.

No implementation, test run, commit, push, deployment, production data change,
secret access, live Wildberries/Ozon call, review or acceptance verdict is
performed at S13.

## Minimum closure before S13 can pass

All of the following are required:

1. A controller-owned reclassification adds the runtime S08 stage and the
   `ui_change` trait with S09, S10, S24 and S25. The controller, not a hand edit
   of `tasks/BLG-I16/state.json`, recalculates the required-stage set and
   invalidates dependent receipts.
2. `pipeline-ba` produces an S08 behavior contract covering one accepted bulk
   intent, immutable target membership, full/partial/empty/rejected/retry
   outcomes, authoritative read-back and the existing warehouse invariants.
3. S09/S10 approve the exact accepted/running/progress/partial/final states on
   screen `S-03`, using the UI kit. S11/S12 are then revalidated if their input
   hashes changed.
4. The refreshed packet returns to S13 on a pinned baseline containing the
   current FBS packaging path. This provisional artifact is rebound to those
   new input hashes before `ARCH_PLAN_READY` can be issued.

The minimum closure does not require an owner product choice, a secret, a live
marketplace call or a production fixture.

## Approved inputs and observed baseline

- `tasks/BLG-I16/S11-PRODUCT-CONTRACT.md` requires one server-accepted intent,
  immutable targets, at-most-once line effects, truthful partial results and
  recoverable read-back.
- `tasks/BLG-I16/S12-TASK-CUT.md` keeps API acceptance, persistence, worker
  processing, result reading and the existing operator surface in one vertical
  card.
- The controller baseline is
  `69c271678782d7dcfa39df97cd905cbee1678727`. The inspected current checkout is
  ahead at `a6a2a40ce02530a919d4ea979e4f3322591a6a49`, but the relevant packaging,
  API, worker and frontend files have no committed diff between those SHAs.
- `FfFbsSupplyWorkspace.packEverything` currently sends one mutating
  `POST .../lines/{line_id}/pack` per unfinished packaging line, then sends
  `POST .../{task_id}/complete`. The browser stops at the first error.
- `packaging_task_service.record_pack_progress` preserves tenant/task/line
  checks and delegates FBS units to
  `fbs_packaging_integration_service.record_fbs_pack_progress`, but the service
  commits at the route-operation boundary.
- `FbsPackagingFulfillment` already gives each packed order one active
  fulfillment and supports a per-task unit idempotency key. It is the durable
  at-most-once warehouse-effect guard to reuse, not replace.
- `BackgroundJob` is a generic polling row without request idempotency, an
  immutable target set, item results, progress counters, lease/replay semantics
  or a packaging-task uniqueness rule. Reusing it as the source of truth would
  leave the core requirements implicit; the bulk operation therefore gets a
  dedicated model.
- The screen is registry screen `S-03`, zone `модалка/панель действий`. The UI
  kit already exports `PrimaryAction`, `StatusChip` and `ErrorNotice`, which are
  sufficient primitives for the planned states. Exact composition and wording
  belong to S09/S10; S13 creates no local component exemption.

## Chosen boundary

Acceptance and deduplication are synchronous. All order mutations and final
task/supply promotion are background work except the true no-op case.

```text
one operator action + stable idempotency key
  -> POST packaging-task bulk-complete
    -> authorize + lock supply/task
      -> create/reuse one durable operation
        -> capture immutable ordered target items in the same transaction
          -> return terminal no-op OR 202 accepted
            -> enqueue operation_id only
              -> worker claims bounded item chunks
                -> existing eligibility/inventory/fulfillment primitive
                  -> durable per-item success/failure + counters
                    -> existing packaging completion/promotion guards
                      -> terminal full/partial/failed result
                        -> GET read-back after poll/reload/retry
```

There is no size heuristic that can race changing supply data:

- zero actionable targets and an already complete authoritative task can finish
  in the acceptance transaction and return `200`;
- one or more actionable targets always return `202` and run through the
  worker;
- a fast worker may be terminal by the first status read, but the API never
  holds an interactive request open while packing N rows.

This deterministic split is the S13 sync/background criterion.

## API contract

Add three tenant-scoped routes under the existing packaging router:

```text
POST /operations/packaging-tasks/{task_id}/bulk-complete
GET  /operations/packaging-tasks/{task_id}/bulk-complete
GET  /operations/packaging-tasks/{task_id}/bulk-complete/items
```

The POST body is:

```json
{"idempotency_key": "1..128 chars"}
```

The server derives supply, tenant, warehouse, seller, target rows and quantities
from authoritative database state. The client cannot submit order IDs,
quantities, a target count, success counts or a requested final status.

POST returns `BulkPackOperationOut` with HTTP `202` for
`accepted|running|retry_wait`, HTTP `200` for an already terminal operation or a
terminal no-op, and no operation row for a general rejection before acceptance.
General rejection keeps the existing authorization/not-found/conflict
non-disclosure behavior.

The operation response contains only typed, sanitized data:

```text
id, packaging_task_id, supply_id, status, retryable
target_count, pending_count, completed_now_count
already_complete_count, failed_count
finalization_error_code, last_system_error_code
accepted_at, started_at, heartbeat_at, finished_at, updated_at
```

The operation GET is the reload/recovery path. Because one packaging task owns
at most one immutable bulk intent, the browser does not need a remembered
operation ID to rediscover it. It returns `404` only when no operation exists
for that authorized task.

The items GET supports cursor pagination ordered by immutable `ordinal`, with a
bounded `limit` and optional `result=failed|completed|already_complete|pending`.
Each row returns internal `order_id`, `packaging_task_line_id`, `state` and a
stable reason code. It does not return WB payloads, CIS values, credentials or
raw exception text.

Same-key and competing-key behavior is mandatory:

- same task and same key returns the same operation and current result;
- the same key reused for a different task/request returns
  `idempotency_key_reused` without creating work;
- a different key for a task that already owns an operation returns that same
  immutable operation rather than expanding targets or starting a competitor;
- if the existing operation is terminal `failed` with pending retryable items,
  POST re-enqueues that same operation and target set; it never creates a new
  row or repeats completed effects.

Existing `POST /{task_id}/lines/{line_id}/pack` and
`POST /{task_id}/complete` remain compatible for current non-bulk consumers.
Only the FBS `Всё упаковано` action switches to the new contract in this card.

## Durable data model

Create two additive tables in one Alembic migration.

### `fbs_bulk_pack_operations`

Required columns:

```text
id UUID primary key
tenant_id, supply_id, packaging_task_id, requested_by_user_id
idempotency_key varchar(128), request_hash varchar(64), target_hash varchar(64)
status varchar(32), retryable boolean
target_count, pending_count, completed_now_count
already_complete_count, failed_count integers >= 0
attempt_count integer >= 0
lease_token UUID nullable, lease_until timestamp nullable
finalization_error_code varchar(64) nullable
last_system_error_code varchar(64) nullable
accepted_at, started_at, heartbeat_at, finished_at, updated_at timestamps
```

Constraints and indexes:

- unique `packaging_task_id`: one immutable bulk intent per task;
- unique `(tenant_id, idempotency_key)`: a key cannot identify different bulk
  requests inside one tenant;
- index `(status, lease_until)` for recovery;
- index `(tenant_id, supply_id, status)` for authorized read-back;
- check that all counters are non-negative and their sum equals
  `target_count` at every committed progress boundary.

`request_hash` covers operation kind, tenant and task path/body. It deliberately
does not re-hash live target state on retry. `target_hash` separately binds the
ordered immutable item snapshot captured on first acceptance.

Operation states are:

```text
accepted -> running -> completed
                    -> partial
                    -> failed
         -> retry_wait -> running
```

`completed`, `partial` and `failed` are terminal result states. A duplicate POST
may move a retryable `failed` operation with pending items back to `accepted`,
without changing its identity or targets.

### `fbs_bulk_pack_operation_items`

Required columns:

```text
id UUID primary key
operation_id, tenant_id, fbs_order_id
packaging_task_line_id nullable, target_product_id nullable
ordinal integer, state varchar(32), result_code varchar(64) nullable
pack_idempotency_key varchar(128)
accepted_supply_id, accepted_pick_status, accepted_pack_status
attempt_count integer >= 0
completed_at, updated_at timestamps
```

Constraints and indexes:

- unique `(operation_id, fbs_order_id)`;
- unique `(operation_id, ordinal)`;
- unique `(operation_id, pack_idempotency_key)`;
- index `(operation_id, state, ordinal)` for worker claims and result paging;
- foreign keys remain tenant-verifiable through service queries; no API reads an
  item without joining its authorized operation.

Item states are only `pending`, `completed`, `already_complete` and `failed`.
`processing` is not persisted: a database row lock and operation lease express
temporary ownership, so a crashed worker cannot strand an item in an invented
state.

The deterministic target is every non-cancelled order belonging to the supply
at acceptance, sorted by `(deadline_at, created_at_wb, wb_order_id, id)`.
Already fulfilled orders are captured as `already_complete`; unmapped or
otherwise invalid orders remain captured and receive a typed failure rather
than silently disappearing. A later order cannot join the operation.

## Acceptance transaction and idempotency

`accept_bulk_pack_operation` owns one short database transaction:

1. Require existing packaging access and load the tenant-scoped packaging task.
2. Lock its FBS supply and packaging task in canonical order. Reject a missing,
   cancelled, delivered or wrong-state shared precondition before inserting an
   operation.
3. Resolve any existing operation. Validate key/request-hash reuse and return
   it without changing targets.
4. Load and deterministically order the current active supply orders and map
   them to packaging lines. Create the operation and all items in the same
   commit; compute `target_hash` from sanitized stable IDs and accepted
   eligibility fields.
5. Derive initial counters. If the authoritative task and supply are already
   complete, finish the operation as a no-op; otherwise commit `accepted`.
6. Only after commit, make a best-effort queue dispatch. Broker failure does
   not roll back acceptance or turn it into false rejection; the recovery scan
   finds the durable accepted row.

The unique task and key constraints are the final race guard. An
`IntegrityError` is handled by rolling back the attempted insert, re-reading
the winner and applying the same request-hash rules.

Each item gets the deterministic existing fulfillment key:

```text
bulk-pack:<operation_id>:<fbs_order_id>
```

`FbsPackagingFulfillment` unique constraints and active-order uniqueness remain
the at-most-once effect guard even if a message, chunk or HTTP request is
delivered twice.

## Business mutation and transaction boundary

Extract the current FBS unit mutation into one commit-free internal primitive
used by both the old line route and the new worker. The primitive owns the
existing checks and effects; the new path must not copy their logic into a
second implementation.

For an explicit target order it must:

- re-read tenant, supply, task, line, order, active pick and active fulfillment;
- classify a matching active fulfillment as `already_complete`;
- reject moved/cancelled/unpicked/product-mismatched/inconsistent orders with a
  stable business code instead of overwriting newer state;
- preserve current marking, sticker, quantity, inventory, reserve, location,
  role and task-status checks;
- conditionally convert exactly one inventory unit and insert exactly one
  fulfillment with the deterministic key;
- update order and packaging-line progress in the same transaction.

The worker processes at most 25 ordered pending items per database transaction.
Each item runs inside a nested savepoint: a typed business failure rolls back
only that item and is recorded as `failed`; an unknown database/invariant error
rolls back the whole chunk and enters retry handling. The operation counters
are updated from the committed item transitions in that same outer transaction.

After no pending item remains, the worker calls a commit-free extraction of the
existing `complete_task` finalization. Existing marking completion,
`is_task_complete`, billing and `sync_fbs_supply_on_packaging_done` guards remain
authoritative. Full operation success is written only in the same transaction
that makes the task/supply final state durable.

Expected item failures do not stop safe independent items. Finalization that
finds failed/incomplete lines produces `partial` (or `failed` when no target
was completed/already complete) with `finalization_error_code`; it never marks
the supply `packed`. An invariant or unknown persistence error stops the chunk,
leaves uncommitted items pending and moves the operation through retry rather
than guessing a partial result.

Canonical lock order for acceptance and worker transactions is:

```text
FbsSupply -> PackagingTask -> FbsBulkPackOperation
  -> operation items by ordinal -> FbsOrder by UUID
    -> PackagingTaskLine by UUID -> InventoryBalance key
```

Existing mutation entrypoints that already lock `FbsSupply` serialize with the
bulk worker. No database lock is held while publishing a Celery message, polling
from the browser or making any external network call. This card makes no
external marketplace call at all.

## Worker ownership, retry and recovery

Add one Celery task named `wms.fbs_bulk_pack_complete`. Its payload is only the
operation UUID; tenant and all business data are loaded from the operation row.
It is registered in the existing Celery app and may run on the existing WMS
worker, but it cannot accept a generic job type or arbitrary table/tenant
payload.

Worker safety rules:

- `acks_late` and worker-loss rejection are enabled; duplicate delivery is an
  expected path;
- claim uses a short lease (`lease_token`, `lease_until`) and a conditional
  state update; duplicate workers that lose the claim exit successfully;
- item row locks plus fulfillment uniqueness remain the mutation fence if a
  stale worker survives past lease expiry;
- heartbeat and committed counters update after every chunk and at least every
  two seconds while work is active;
- typed business failures are terminal per item and are not retried;
- transient DB/broker failures use bounded exponential retry (five automatic
  attempts, 1/2/4/8/16 seconds with jitter), then leave the same operation
  `failed`, `retryable=true`, with pending items intact;
- an operator retry or recovery dispatcher re-enqueues only that same operation
  and unfinished items.

Add a recovery task `wms.fbs_bulk_pack_recover` to the existing beat schedule.
Every 15 seconds it selects bounded `accepted|retry_wait` rows and expired
`running` leases with `FOR UPDATE SKIP LOCKED`, then re-enqueues operation IDs.
The operation row itself is the durable outbox: a crash after DB commit but
before broker publish cannot lose the intent.

When no broker is configured, the API may use the existing local
`BackgroundTasks` fallback only as a best-effort development trigger. The DB
operation remains authoritative, and repeated POST/GET recovery must never
depend on the in-process task having survived. S22/S23 worker evidence runs with
an isolated real broker/queue namespace, never a live marketplace.

## Progress, result and measurable limits

The release candidate must meet all of these on the representative isolated
500-order fixture selected by S15:

- exactly one browser mutation request for the bulk intent;
- POST acceptance p95 at or below 750 ms and no request waiting for per-order
  completion;
- status-summary GET p95 at or below 250 ms;
- committed progress/heartbeat freshness at or below two seconds while running;
- a 500-order all-valid run reaches the terminal result within 30 seconds on
  the declared production-like worker profile;
- result counts equal the item-state aggregate and authoritative packaging
  task/order/fulfillment read-back after reload.

Status polling starts at one second while the workspace is visible and may
back off to three seconds after ten seconds. It stops on terminal result, close
or unmount. Reopening first performs the operation GET; it does not create a new
intent merely because browser memory was lost.

These limits are architecture/test thresholds, not production evidence. If the
500-order fixture cannot meet them without changing worker capacity, queue
topology or chunk size outside this resource graph, S18 stops and returns to
S13; it does not hide the miss with a longer spinner.

## Partial-result truth table

```text
all items completed/already + final task/supply promotion -> completed
some completed/already + any failed/incomplete            -> partial
zero completed/already + deterministic failures           -> failed, not retryable
system error + pending items after retry budget            -> failed, retryable
transient error before retry budget                         -> retry_wait
```

Stable item codes include existing service codes such as `order_not_picked`,
`order_not_in_supply`, `order_product_mismatch`, `insufficient_unpacked`,
`marking_not_done`, `packaging_incomplete` and a fail-closed
`order_pack_state_inconsistent`. Raw exception messages are never exposed.

`completed_now_count` counts fulfillments created by this operation.
`already_complete_count` counts matching authoritative effects present before
or found during replay. `failed_count` counts deterministic unfinished targets.
Pending retryable items remain `pending`; they are not relabelled as business
failures. The supply-level `packed` state is never inferred from counters; the
existing finalization service is the oracle.

## Migration, backfill, restore and rollback

The Alembic migration is expand-only: create the two new tables, constraints and
indexes after current head `20260811_0078`. It changes no existing column,
foreign key, status value or fulfillment row.

Backfill is explicitly not required. Existing packaging tasks have no accepted
bulk intent and continue on old routes until the new caller is enabled. The
pre-release compatibility proof must show:

- old API/worker binaries ignore the new tables safely;
- new binaries return `404` from bulk-operation GET when no row exists;
- old line/complete routes retain their request and response contracts;
- mixed old/new application instances cannot create two bulk operations because
  the database uniqueness rules arbitrate acceptance.

Application rollback reverts callers/API/worker to the previous compatible
binary and stops accepting new bulk operations. It does not run a destructive
down migration and does not delete operation/item audit rows. Already accepted
rows remain recoverable when the new worker is restored; completed warehouse
effects remain authoritative and are never reversed by deployment rollback.

Before release, backup/restore rehearsal restores the two tables together with
packaging tasks, FBS orders, fulfillments and inventory state, then verifies
operation/item counts, target hashes, unique constraints, counter aggregates
and final read-back. A down migration that drops non-empty operation history
requires separate owner authorization and is outside `BLG-I16`.

## UI and recovery boundary

After the profile is repaired and S09/S10 approve the exact state presentation,
the existing FBS workspace will:

- persist one `bulk-pack` idempotency key per supply/task intent using the
  existing session-storage helper, while relying on server uniqueness if
  browser storage is unavailable;
- replace the per-line mutation loop with one typed API call;
- read the operation on open/reload and poll only while non-terminal;
- refresh authoritative packaging/workspace read-back as counts change and at
  terminal state;
- use approved UI-kit actions/status/error primitives rather than local new
  buttons, chips or result cards;
- make failed orders discoverable through their existing order rows and the
  paged result contract, without introducing another manual completion flow.

The exact text, placement, focus behavior and visual composition are not
approved here. If S09 finds the current UI kit cannot express a required
progress/result state, it creates a design-system dependency; Dev may not add a
local bypass.

## Future S18 resource ownership and locks

S17 should allocate one exclusive vertical-card lock across these resources.
Names of new files are fixed by responsibility; changing the boundary requires
S13 rework.

| Resource | Planned responsibility |
| --- | --- |
| `backend/alembic/versions/<next>_fbs_bulk_pack_operations.py` (new) | Add both durable tables, constraints and indexes after `20260811_0078`; no existing-data rewrite. |
| `backend/app/models/fbs_bulk_pack_operation.py` (new) | Operation/item ORM states, relationships and constraints. |
| `backend/app/models/__init__.py` | Register the new models for Alembic metadata. |
| `backend/app/api/packaging_tasks.py` | Typed POST/GET/items contracts, existing packaging authorization and sanitized error mapping. |
| `backend/app/services/fbs_bulk_pack_service.py` (new) | Acceptance, target snapshot, idempotency, paged read-back, claim/recovery and terminal aggregation. |
| `backend/app/services/fbs_packaging_integration_service.py` | Extract/reuse commit-free explicit-order pack primitive and deterministic fulfillment identity. |
| `backend/app/services/packaging_task_service.py` | Extract commit-free completion/finalization boundary while preserving old route behavior. |
| `backend/app/tasks/background_jobs.py` | Register bulk processor and recovery Celery tasks only. |
| `backend/app/celery_app.py` | Add bounded recovery beat entry and task delivery settings. |
| `backend/tests/test_fbs_bulk_pack_operation.py` (new) | API, DB, transaction, idempotency, partial/retry/reload/isolation and performance contract. |
| Existing focused packaging/integration tests chosen by S15 | Regression for line checks, fulfillment, inventory, marking, billing and supply promotion. |
| `frontend/src/screens/v2/fbsApi.ts` | Typed bulk POST/status/items clients and response states. |
| `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` | One-request action, durable key recovery, polling/read-back and approved S09/S10 state presentation. |
| `frontend/tests-e2e/ff-fbs-full-flow.spec.ts` | Operator request-count, progress, retry, partial result and reload journey after UX approval. |

Resource locks are:

```text
screen:S-03:modal/action-panel
route:operations/packaging-tasks/bulk-complete
service:fbs-packaging-mutation
table:fbs_bulk_pack_operations
table:fbs_bulk_pack_operation_items
table:fbs_packaging_fulfillments
table:packaging_tasks
table:packaging_task_lines
table:fbs_orders
table:fbs_supplies
table:inventory_balances
worker:wms.fbs_bulk_pack_complete
worker:wms.fbs_bulk_pack_recover
process:FBS-packing-complete
```

No WB/Ozon client, credential model, print template, marking-code format,
packing-box flow, delivery route, mobile contract, secret, deploy script or
production configuration belongs to this write set. Discovery of a required
write there returns to S02/S13 before Dev expands scope.

## Implementation order after upstream closure

The card remains one vertical delivery, but S17/S18 should order its internal
work as follows:

1. Add migration and ORM constraints; prove old-binary compatibility.
2. Extract commit-free packaging primitives with all existing tests green.
3. Add operation acceptance/read service and API behavior tests.
4. Add worker claim, chunk, retry and recovery paths with crash/replay tests.
5. Add the approved S09/S10 frontend contract and remove the client mutation
   loop.
6. Bind S15 cases, then run S19/S22/S23 through the exact DB/API/worker/read-back
   chain.

No layer is independently shippable as the card result. In particular, the API
must not be enabled for the operator before durable recovery exists, and the UI
must not switch before the status/read path and worker are available.

## Required downstream proof lanes

Without writing S15 cases here, the architecture requires S15/S22 to prove at
least these boundaries from the accepted S11/S12 rows:

- one, zero and 500-order immutable target snapshots;
- exactly one browser mutation and no hidden per-line mutation sequence;
- same-key, different-key, double-click, lost-response and reload convergence;
- first/middle/last deterministic failures with other safe items retained;
- active fulfillment replay and inconsistent packed-without-fulfillment state;
- concurrent cancellation, move, manual pack and inventory depletion;
- crash before enqueue, during a 25-item chunk, after chunk commit, before final
  operation status, and after finalization commit;
- expired lease, duplicate message, broker outage and recovery scan;
- counter/item/task/order/fulfillment/inventory consistency after read-back;
- tenant, seller, warehouse, task and operation negative authorization;
- migration upgrade, no-backfill compatibility, restore rehearsal and
  application rollback with retained rows;
- the declared POST/GET/progress/500-order performance limits on isolated
  production-like resources.

All evidence is sanitized. It may contain pseudonymized UUIDs, stable reason
codes, counts, hashes, timings and queue message counts, but no raw CIS,
Authorization data, credentials or live marketplace payload.

## Stop criteria

S18 must return to the owning stage rather than improvise if:

- existing line eligibility cannot be reused through one commit-free primitive;
- full/partial result cannot be reconstructed solely from durable DB state;
- a crash can occur after a warehouse effect but before the fulfillment/item
  state that prevents its replay;
- the current migration head differs or another task owns a conflicting table,
  route, screen zone or service lock;
- queue delivery can lose an accepted operation without the recovery scan;
- a mobile, print, external-contract, tenant-scope or release resource actually
  changes outside the declared profile;
- S09/S10 require a UI-kit component that does not yet exist;
- the representative 500-order fixture misses the declared limits without a
  new capacity/topology decision.

Minimum architecture rework closure is one revised resource graph that restores
an immutable target, database-enforced operation and unit idempotency, durable
partial truth, bounded worker replay and authoritative reload read-back. A
client spinner, generic `BackgroundJob.result_json`, unbounded retry or one
transaction for the whole supply is not an acceptable substitute.

## Final verdict

`ARCH_PLAN_BLOCKED`: the provisional design establishes one durable
server-side bulk pack-complete operation with immutable targets, database and
fulfillment idempotency, bounded worker chunks, truthful partial errors,
recoverable progress and additive migration/rollback boundaries. The current
controller profile still lacks mandatory S08 and `ui_change` stages, so this
architecture may not be accepted or advanced to Dev until the minimum closure
above is completed by independent owning roles.
