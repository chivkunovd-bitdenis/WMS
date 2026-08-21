# S13 ARCHITECT_PLAN - BLG-I02

## Verdict

`ARCH_PLAN_READY`

BLG-I02 remains one atomic critical vertical card. The implementation is acceptable only when a
current WB preflight is durably preserved, a server-side fail-closed gate controls the existing FBS
deliver path, the deliver result is durably preserved, and the operator result is read back from
that evidence. A migration without the gate, a UI-only disabled button, mutable order flags without
history, or a gate that treats missing evidence as success is not a partial completion.

This stage changes no application code or schema. It authorizes no development, release, deploy,
production data operation, secret access, live WB/Ozon call, or direct Chestny ZNAK call.

## Accepted inputs and non-bypassable dependencies

- External contract: `tasks/BLG-I02/S03-EXTERNAL-CONTRACT.md`, independently accepted at S04.
- Product contract: `tasks/BLG-I02/S11-PRODUCT-CONTRACT.md`.
- Atomic card: `tasks/BLG-I02/S12-TASK-CUT.md`.
- Current implementation baseline: the existing FBS marking, shipment, workspace, WB typed-client,
  operation-journal, API and two operator surfaces inspected at S13.
- `BLG-I01` owns the accepted `POST /api/marketplace/v3/orders/meta` transport, response envelope,
  deterministic batching, polling and rate-limit behavior. BLG-I02 consumes that boundary and must
  not add a second WB client or fallback endpoint.
- `BLG-D03` owns the Product/legal applicability oracle for `requiredMeta`, `optionalMeta` and the
  concrete item situation. BLG-I02 stores raw WB `optional`, but must classify it
  `UNKNOWN_BLOCKED` until the D03 oracle explicitly allows that key and situation.

Controller truth at planning time is that both dependencies are open: BLG-I01 is `WAITING` at S03
on `BLK-RESEARCH-001`, and BLG-D03 is `WAITING` at S04 on `BLK-PROD-001`. This does not block S13,
S14 or S15 because every unresolved branch is designed fail-closed. It does block S16 and S18 as
specified below. No local mapping, mock green state, feature flag, manual database write or copied
contract may resolve either edge.

## Current baseline and unsafe authority to retire

The existing code already provides useful pieces, but none is sufficient evidence for BLG-I02:

1. `fbs_order_markings` and mutable `fbs_orders.meta_details_json`,
   `metadata_delivery_allowed`, and `metadata_last_checked_at` overwrite the latest interpretation.
   They do not preserve every WB call, omissions, response ordering, raw decisions, HTTP outcome or
   the marking-set revision that was checked.
2. `fbs_marking_service._sync_order_meta_from_wb()` requests one order and folds details into a
   dictionary keyed by kind. Repeated/conflicting rows are lost, absent rows do not become an
   explicit incomplete result, and legacy `check_status` can still derive an optimistic mutable
   status. This path may remain a compatibility display path, but it cannot authorize dispatch.
3. `fbs_shipment_service._build_delivery_checks()` currently reads mutable marking state and
   computes `can_deliver`; the existing `delivery-preflight` response is not a durable WB evidence
   projection.
4. `FbsWbOperation` is the correct idempotency/reconciliation journal for the deliver side effect,
   but its mutable state and summary JSON do not provide one immutable transport outcome plus the
   `0..N` exact WB verdict rows for every preflight and deliver call.
5. `FfFbsSupplyWorkspace` exposes `Передать в WB` without a persisted WB-verdict read model, while
   `FfFbsSupplyDrawer` relies on the existing local `canDeliver` calculation. The backend must
   enforce the same gate even for stale or old clients.
6. `fbs_workspace_service` currently returns `delivery_preflight: null`; after restart the operator
   cannot read the last relevant WB evidence state from the normal workspace response.

Therefore all legacy booleans and summaries become compatibility-only inputs. They may explain an
old screen during rollout, but they never satisfy the new dispatch gate and are not backfilled as WB
evidence.

## Architecture decision

### Resource graph

```text
tenant + seller + warehouse + FBS supply
  -> tenant-owned supply orders + required/optional metadata + current marking values
  -> canonical marking_scope_fingerprint
  -> validation run (one operator/dispatch check over one exact scope)
       -> 1..N preflight attempts (one per actual <=100-order I01 call)
            -> exactly one terminal outcome per attempt
            -> 0..N verdict rows actually returned by WB
       -> deterministic completeness/classification
       -> current dispatch projection (rebuildable, not evidence)
  -> server-side dispatch gate under supply lock
  -> existing FbsWbOperation deliver intent/idempotency journal
       -> one deliver attempt
            -> exactly one terminal outcome
            -> 0..N real rows from partial 409 only
  -> workspace/API read-back
  -> existing FBS operator surfaces

pending/deadlineExceeded only
  -> bounded tenant/seller/supply-scoped recheck job
  -> a new validation run, never an automatic deliver job
```

The evidence chain is append-only. The current projection is a disposable index: it may be replaced
or rebuilt only from committed runs, attempts, outcomes and verdict rows. It cannot repair history
and it cannot be used without rechecking the current marking fingerprint.

### Canonical scope and fingerprint

The service loads the supply with an exclusive row lock and verifies `tenant_id`, `seller_id`,
`warehouse_id`, supply membership and every local order before constructing the scope. The canonical
scope is stable JSON containing:

- tenant, seller, warehouse, local supply and WB supply identities;
- ordered local-order/WB-order identity pairs;
- for every order, sorted applicable metadata keys from the accepted D03 oracle;
- for every present identifier, the kind plus a SHA-256 hash of the exact preserved value;
- a version/hash of the I01 external-contract adapter and D03 oracle used;
- the local supply/order composition version inputs needed to detect membership changes.

The `marking_scope_fingerprint` is SHA-256 over that canonical representation. Full KIZ values are
not included in logs, idempotency keys, public errors or operator JSON. Any order membership,
warehouse, seller, applicable key or identifier-value change produces a different fingerprint and
immediately makes an older positive projection unusable. A timestamp or TTL alone never proves
freshness.

### Additive evidence schema

S18 creates new additive tables; it does not repurpose mutable order fields.

#### `fbs_wb_validation_runs`

One append-only parent for an exact preflight scope:

- `id`, `tenant_id`, `seller_id`, `warehouse_id`, `supply_id`, `wb_supply_id`;
- `purpose=dispatch_preflight|operator_recheck|worker_recheck`;
- `marking_scope_fingerprint`, protected canonical scope or protected durable reference, scope hash,
  expected order count, expected batch count;
- I01 contract adapter hash, D03 oracle hash, `created_at_utc`, actor/request identity;
- no mutable business verdict column.

An index on `(tenant_id, seller_id, warehouse_id, supply_id, created_at_utc)` supports scoped
read-back. A run is never reused for a different fingerprint or retried in place.

#### `fbs_wb_validation_attempts`

One immutable identity/request row is committed before every actual external call:

- `id`, nullable `run_id`, `tenant_id`, `seller_id`, `warehouse_id`, `supply_id`;
- `source_operation=orders_meta_preflight|supply_deliver`;
- batch ordinal, exact ordered request-scope hash, request payload hash, contract snapshot hash;
- nullable `fbs_wb_operation_id` for deliver reconciliation, unique call/idempotency identity,
  `started_at_utc` and recovery lease/fencing identity;
- protected request scope or protected durable reference, never ordinary raw logging.

The attempt row proves that a call was intended and identifies exactly one call. It is inserted and
committed before network I/O, so a process crash cannot erase the fact that the call may have
started. A retry gets a new attempt row unless the existing deliver operation must first be
reconciled.

#### `fbs_wb_validation_outcomes`

Exactly zero or one immutable terminal row is allowed per attempt through a unique `attempt_id`.
Normal execution inserts it immediately after receiving or failing the call; recovery inserts an
honest `PROCESS_INTERRUPTED_UNKNOWN` outcome for an expired attempt whose response cannot be
reconstructed. It contains:

- transport outcome, nullable HTTP status, nullable exact WB error code and local attempt result;
- WMS `observed_at_utc`, explicitly not a WB or Chestny ZNAK event time;
- response-body-present flag, response hash, protected encrypted raw response or durable reference;
- WB request/correlation ID and rate-limit headers when present;
- parse/completeness diagnostics that never invent verdict rows.

The unique constraint makes terminalization idempotent. A second conflicting outcome is an
integrity error and keeps dispatch blocked. Final outcome rows are never updated or deleted.

#### `fbs_wb_validation_verdicts`

`0..N` append-only rows under one outcome, and only for real `metaDetails[]` elements:

- `tenant_id`, `attempt_id`, `outcome_id`, local order identity if resolvable, exact WB order ID;
- order and metadata ordinals, exact key, encrypted value plus value hash;
- case-sensitive `decision_raw`, normalized class, safe reason code and safe Russian reason;
- no synthetic row for an omitted order/key, bodyless response or transport failure.

A uniqueness key over `(outcome_id, order_ordinal, meta_ordinal)` preserves duplicate/conflicting
rows instead of collapsing them. Completeness is computed against the run scope, not inferred from
row count or dictionary keys.

#### `fbs_wb_dispatch_projection`

One mutable, rebuildable row per `(tenant_id, supply_id)` contains the latest evaluated run ID,
fingerprint, state (`POSITIVE_CONFIRMED`, `NEGATIVE_CONFIRMED`, `WAITING_BLOCKED`,
`UNKNOWN_BLOCKED`), completeness, safe reason summary and evaluation time. Updating it requires a
compare-and-swap on the previous projection version while the supply is locked. It stores no raw WB
body and no full KIZ.

The projection is never primary evidence. Missing projection, a rebuild failure, an absent source
row, a fingerprint mismatch or an oracle/contract hash mismatch evaluates to `UNKNOWN_BLOCKED`.

### Protected payload retention

Raw request scopes, response bodies and identifier values use an application-level encrypted text
envelope through the repository's existing integration Fernet facility, with hashes stored
separately for comparison. BLG-I02 consumes the configured encryption facility but does not create,
read, rotate or replace its key. Encryption unavailability blocks persistence and therefore blocks
dispatch; plaintext fallback is forbidden.

Ordinary logs contain only attempt/run IDs, tenant-safe local IDs, HTTP/result class, hashes and safe
reason codes. API and UI never return encrypted blobs or full KIZ. Raw evidence is readable only by
an explicit support/audit service boundary with tenant authorization; no such operator route is part
of this card. Retention is time-based and implemented later as a separately authorized purge policy:
until that policy exists, evidence remains retained. Purge, if introduced, must remove protected
payload only after its audit requirement while preserving hashes and non-sensitive outcome metadata;
it is not part of S18.

## Result semantics and projection rules

### `200 orders/meta`

Each I01 batch call gets an attempt, one outcome and every real row. The run becomes complete only
when all expected attempts have successful `200` outcomes, every requested order is represented,
every D03-applicable key has an unambiguous row for the exact current value hash, and no unknown,
missing or conflicting duplicate exists. Only the S11-approved raw positive set may normalize to
`CONFIRMED_ALLOW`; unapproved `optional` stays `UNKNOWN_BLOCK`.

All batches are persisted in one local terminalization transaction per returned batch; the final run
evaluation occurs only after all batch outcomes are committed. A partial run is blocked and remains
auditable. A later retry creates a new run rather than filling old missing evidence.

### Bodyless `204 supply/deliver`

The deliver attempt receives one outcome with `http_status=204`,
`attempt_result=DELIVER_ACCEPTED`, `response_body_present=false`, and zero verdict rows. The existing
`FbsWbOperation` is marked confirmed and the local supply transition is committed in the same local
transaction as that outcome. No synthetic positive per-order/key rows are created, and the 204 does
not repair an incomplete preflight.

### `409 MetaValidationFail`

The deliver attempt receives `DELIVER_REJECTED_PARTIAL`, the protected raw response and only the
problem/pending rows WB actually returned, preserving empty `orders[]` honestly. It is a negative
result for that deliver attempt, supersedes the current projection to `NEGATIVE_CONFIRMED` or a more
conservative blocked state, and never replaces the complete preflight run or makes omitted rows
positive.

### Every other `4XX`

`400`, `401`, `402`, `403`, `404`, `429` and future `4XX` values receive an honest attempt outcome,
available body/hash and only real parseable rows. All classify `UNKNOWN_BLOCKED`; none authorizes a
deliver call. Rate-limit accounting treats every `4XX` as ten requests under the accepted contract,
while `429` additionally preserves and obeys actual retry/reset headers. Authentication errors do
not trigger secret lookup or credential management from this card.

### `5XX`, timeout, connection and malformed response

Each receives its exact transport/result outcome and zero rows unless the accepted I01 envelope can
prove real parseable rows. All classify `UNKNOWN_BLOCKED`. Automatic deliver retry is forbidden.
Only a safe preflight recheck or deliver reconciliation may run.

## Dispatch gate, transactions and crash recovery

The only authorization function is conceptually:

```text
authorize_dispatch(tenant_id, seller_id, warehouse_id, supply_id,
                   current_fingerprint, persisted_projection)
  -> allow only exact POSITIVE_CONFIRMED match
```

It is called inside `fbs_shipment_service.deliver_supply()` immediately before any WB deliver call.
Every route, UI, worker or old client therefore inherits the same refusal.

Ordered execution:

1. Lock the tenant-owned supply row and reject cross-tenant/seller/warehouse membership without
   revealing another tenant's resource.
2. Recompute the current scope fingerprint and create/commit a validation run plus each preflight
   attempt identity before its I01 network call.
3. Persist each terminal outcome and all real verdict rows atomically. Evaluate and commit the
   projection only from committed evidence.
4. Re-lock the supply, recompute the fingerprint, and require an exact `POSITIVE_CONFIRMED`
   projection sourced from this dispatch execution. Any drift closes the gate and requires a new
   run.
5. Resolve or create the existing seller-scoped `FbsWbOperation` idempotency record. Create and
   commit the linked deliver-attempt identity before calling WB.
6. Hold the supply-level dispatch fencing lock through the external call so another local request
   cannot mutate the active dispatch intent or launch a second deliver. Marking/supply mutation paths
   reject an active deliver intent; they do not wait and then silently reuse stale evidence.
7. Persist the deliver outcome, actual real 409 rows if any, operation state and local supply state in
   one transaction before returning any operator success or failure.

Crash rules:

- After a read-only preflight response but before terminal persistence: the pre-created attempt is
  later closed `PROCESS_INTERRUPTED_UNKNOWN`; projection remains blocked and a new run may safely
  recheck.
- Before the deliver request is sent: an expired intent with no external call marker is closed
  unknown and may be replaced only after reconciliation.
- During/after deliver with no committed outcome: the linked `FbsWbOperation` remains
  `pending_confirmation`. A retry never calls deliver first; it uses the existing WB supply-state
  reconciliation. Confirmed `done` produces a recovered accepted outcome/local transition without a
  second mutation. Not confirmed remains blocked/pending and requires bounded reconciliation, not an
  optimistic retry.
- A response/outcome uniqueness conflict, projection CAS loss or fencing-token mismatch is an
  integrity failure and blocks. It is never resolved by taking the greener row.

The existing reconciliation journal is reused for side-effect idempotency; evidence tables do not
replace it. Conversely, the mutable operation journal never substitutes for exact attempt/outcome
and verdict evidence.

## Worker boundary

No worker is allowed to dispatch. A new task may only perform bounded recheck/reconciliation:

- enqueue only for committed `WAITING_BLOCKED` (`pending` or `deadlineExceeded`) or an existing
  deliver `pending_confirmation` operation;
- payload contains tenant, seller, warehouse, supply, source run/operation ID and expected
  fingerprint, never a token or full KIZ;
- acquire the same tenant/supply fencing lock and revalidate ownership/fingerprint on execution;
- consume I01 polling/rate-limit primitives and create a new run/attempt for every actual call;
- stop on fingerprint drift, non-waiting result, maximum attempts, lease loss, `4XX`, `5XX`, malformed
  response or encryption/persistence failure;
- publish no green UI state before committed read-back and never invoke `supply_deliver`.

The task must route to the task-scoped/tenant-safe Celery queue selected by deployment configuration.
S18 may extend `background_jobs.py` and Celery routing only if S17 grants the exact worker locks. A
periodic global scanner is out of scope; enqueue is explicit from the validation service.

## API and operator read-back

No new screen is created. The canonical read surface is the existing
`GET /operations/fbs-supplies/{supply_id}/workspace`, with an additive typed
`dispatch_validation` object (the existing nullable `delivery_preflight` may be retained as a
backward-compatible alias during migration):

- state, `can_dispatch`, safe reason codes/messages, checked/observed time;
- source run ID, attempt/result summary, completeness and current fingerprint-match boolean;
- per-order safe problem summaries with masked identifiers, never raw payload/full KIZ;
- `recheck_allowed`, but no client-computed permission.

`POST .../delivery-preflight` uses the same persisted service and returns that read model after
commit. `POST .../deliver` independently reruns/validates the in-path preflight and server gate; a
stale client confirmation version cannot authorize it. Blocked requests return a stable 409 error
envelope carrying only the safe state/reasons and perform zero WB deliver calls.

Both existing operator surfaces consume the same workspace field and disable/hide the deliver
command unless `can_dispatch=true`. Ready, negative, waiting and unknown remain visually distinct;
recheck is available only where the server says it is safe. Reload/restart displays the same durable
state. UI behavior is defense in depth: backend refusal is authoritative.

## Tenant, seller and warehouse isolation

- Every run, attempt, outcome projection and job begins from a tenant-filtered supply query.
- Seller and warehouse IDs are copied from that locked supply graph, never trusted from request
  bodies, UI state or worker payloads.
- Repositories expose no unscoped `get(id)` method for evidence. Detail/outcome access joins through
  a tenant-scoped run/attempt parent.
- WB order IDs are accepted only after membership in the locked local supply. An omitted or foreign
  ID blocks completeness; it is not looked up across tenants for a more specific error.
- Seller-scoped idempotency/rate limits cannot be shared across sellers. Warehouse is part of the
  fingerprint even when WB's endpoint itself is seller-scoped.
- Cross-tenant, cross-seller and cross-warehouse tests prove both denial and non-disclosure.

## Migration, backfill, compatibility and rollback

The migration is expand-only and attaches to the actual Alembic head discovered at S17; S13 does
not guess a revision ID while multiple current heads may be present. It creates the new tables,
foreign keys, unique constraints and scoped indexes without dropping or retyping existing columns.
`check_migrations.py` and an upgrade on a representative snapshot must prove lock duration and head
integrity.

There is deliberately no historical positive backfill. Existing mutable `meta_details_json`,
`metadata_delivery_allowed`, `check_status` and `FbsWbOperation` summaries cannot prove which exact
WB response authorized an old state. Existing undelivered supplies therefore start with no current
projection and read as `UNKNOWN_BLOCKED` until a fresh I01 preflight is persisted. Already delivered
supplies keep their historical local status, but no synthetic per-key verdict is created.

Compatibility sequence:

1. Apply additive schema first; old code ignores it.
2. Deploy the evidence writer/read model and server gate together. There is no release state in
   which the new UI can claim green while the old backend still authorizes optimistically.
3. Old clients remain callable, but backend 409 refusal protects them. Additive workspace fields do
   not remove old response fields.
4. After observation proves all active consumers use the new read model, legacy mutable fields may
   stop receiving compatibility writes in a separate future card. They are not removed here.

Downgrade drops are not an operational rollback because they destroy evidence and would restore
optimistic behavior. The honest rollback is: stop outbound FBS deliver, keep the additive schema and
evidence, and roll forward with a corrected gate. No automatic app rollback to code that can dispatch
without persisted confirmation is permitted. Destructive schema removal requires separate owner
authorization and retention review.

## Future S18 code boundaries and locks

S17 must allocate one atomic workspace and exclusive write locks for the complete vertical graph.
The exact migration filename/revision is chosen against the then-current Alembic heads, but its
logical lock is fixed now.

| Resource | Planned responsibility |
| --- | --- |
| `backend/alembic/versions/<new>_fbs_wb_verdict_evidence.py` | Additive runs/attempts/outcomes/verdicts/projection schema and indexes. |
| `backend/app/models/fbs_wb_validation.py` | New evidence and projection models; finalized evidence has no mutation API. |
| `backend/app/models/__init__.py` | Model registration only. |
| `backend/app/db/fbs_wb_validation_repository.py` | Tenant-scoped inserts, outcome uniqueness, projection CAS, scoped read-back and recovery queries. |
| `backend/app/services/fbs_wb_verdict_service.py` | Fingerprint, classification, completeness, encryption envelope, persistence orchestration and read model. |
| `backend/app/services/fbs_shipment_service.py` | In-path preflight, authoritative dispatch gate, supply lock and deliver outcome ordering. |
| `backend/app/services/fbs_supply_reconcile_service.py` | Link evidence attempt to existing deliver operation and recover uncertain side effects without duplicate deliver. |
| `backend/app/services/fbs_marking_service.py` | Remove legacy mutable verdicts from authorization; notify fingerprint invalidation while preserving compatibility output. |
| `backend/app/services/fbs_workspace_service.py` | Durable `dispatch_validation` read-back on reload/restart. |
| `backend/app/services/wildberries_fbs_client.py` | Read-only consumer boundary from BLG-I01; only envelope hooks proven necessary by I01 may be integrated here. BLG-I02 does not own endpoint semantics. |
| `backend/app/api/fbs_supplies.py` | Additive typed API output and stable blocked 409 envelope; no raw evidence route. |
| `backend/app/tasks/background_jobs.py` | Optional bounded recheck/reconcile entrypoint; never dispatch. |
| `backend/app/celery_app.py` | Explicit queue/routing only if required by the accepted worker design. |
| `frontend/src/screens/v2/fbsApi.ts` | Typed persisted state/read-back and server-authored permission. |
| `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` | Existing workspace command/state only; no redesign or new screen. |
| `frontend/src/screens/v2/FfFbsSupplyDrawer.tsx` | Existing drawer command/state parity. |
| `backend/tests/test_fbs_wb_verdict_persistence.py` | Direct evidence, HTTP semantics, append-only and recovery cases. |
| `backend/tests/test_fbs_shipment_delivery.py` | Gate, idempotency, crash/reconcile and zero-deliver-on-block integration cases. |
| `backend/tests/test_wildberries_marketplace_fbs_client.py` | I01 envelope/204/409/all-4XX compatibility cases without live WB. |
| `frontend/src/screens/v2/fbsApi.test.ts` | Additive contract and blocked response mapping. |
| existing FBS browser/e2e spec selected at S15 | Reload/read-back, distinct states and unavailable dispatch proof on both touched surfaces. |

Canonical logical locks:

```text
task:BLG-I02
db-schema:fbs-wb-validation-evidence
db-table:fbs_wb_validation_runs
db-table:fbs_wb_validation_attempts
db-table:fbs_wb_validation_outcomes
db-table:fbs_wb_validation_verdicts
db-table:fbs_wb_dispatch_projection
service:fbs-wb-verdict
service:fbs-shipment-deliver
service:fbs-supply-reconcile
service:fbs-marking-authorization
api:operations-fbs-supplies-dispatch-validation
worker:fbs-wb-validation-recheck
ui:fbs-supply-workspace-dispatch
ui:fbs-supply-drawer-dispatch
external-contract:BLG-I01-orders-meta
oracle:BLG-D03-marking-applicability
```

Another card requiring any write lock above serializes with BLG-I02. I01 and D03 are read/dependency
owners, not files that BLG-I02 may overwrite. Discovery of a required app-code file outside this
table returns the card to S13 before S18 expands scope.

## Ordered implementation sequence

These are waves inside one atomic card, not separately acceptable deliverables:

1. **Dependency bind and schema.** Verify the exact accepted I01 adapter and D03 oracle hashes;
   allocate locks; add models/migration/repository and migration tests. No old data becomes positive.
2. **Pure evidence/classifier.** Implement canonical fingerprint, raw decision matrix, completeness,
   protected payload envelope and append-only persistence with emulator fixtures.
3. **Preflight and projection.** Integrate I01 batches, persist before classification, add CAS
   projection and restart-safe read-back. Dispatch remains server-blocked until this wave is proven.
4. **Deliver gate and recovery.** Bind the gate to `deliver_supply`, link attempts to
   `FbsWbOperation`, persist 204/409/all-error outcomes and prove no duplicate side effect across
   crash/retry.
5. **Worker and operator parity.** Add bounded recheck only if S15 cases require it; bind API and both
   existing operator surfaces to the same persisted state without adding a new screen.
6. **Integrated proof.** Run migration, backend, frontend, emulator, tenant-breaker, worker and
   reload/read-back cases on one exact commit before independent review.

## Mandatory S14 falsification targets

S14 must reject this plan if it can produce a deliver call or green read-back under any of these:

- missing/unknown/unapproved `optional`, `pending`, `deadlineExceeded`, stale KIZ, changed order
  membership, omitted order/key, duplicate conflict, malformed response or partial batch run;
- bodyless/non-204 response, any `4XX`, `429`, `5XX`, timeout or connection failure;
- partial or empty `409 MetaValidationFail` replacing a complete preflight or making omissions green;
- crash after preflight response, crash around deliver response, operation retry or concurrent
  deliver producing a second external mutation;
- projection written before evidence commit, stale projection CAS, outcome uniqueness conflict or
  evidence encryption failure;
- cross-tenant/seller/warehouse evidence read, worker execution or idempotency collision;
- old frontend/direct API client bypassing the gate, or reload showing a client-memory green state;
- rollback/backfill synthesizing historical positive evidence.

Any successful false-green or duplicate-side-effect path returns to S13. S14 may not weaken Product
semantics to make the plan pass.

## S15, S16 and S18 conditions

### S15 CASE_FACTORY

S15 may proceed now and must bind direct plus destructive cases to a deterministic WB emulator or a
separately authorized sandbox. Production calls are forbidden. Cases cover every S11 decision,
unknowns, D03-unapproved optional, multi-batch scope, omissions, duplicates, changed fingerprint,
200/204/409/all-4XX/5XX/transport/malformed outcomes, append-only cardinality, restart read-back,
worker limits, concurrency, crash/reconcile and tenant/seller/warehouse isolation. Every blocked
case asserts zero WB deliver calls and zero synthetic verdict rows.

### S16 PRODUCT_APPROVED_FOR_DEV

S16 must not pass until controller-linked evidence proves both:

1. BLG-I01 has an independently accepted versioned endpoint/transport/batching/polling contract
   compatible with this plan and the S15 emulator envelope.
2. BLG-D03 has an approved oracle table for applicable `requiredMeta`/`optionalMeta` behavior,
   including the exact rule used to classify `optional`.

If either edge is open, S16 uses the controller's typed waiting/hold outcome naming the dependency,
owner, closure artifact and resume stage. Product may not approve a mock, local copy or always-block
substitute as dependency closure.

### S18 DEVELOPMENT

S18 additionally requires S14 pass, S15 accepted cases, S16 approval, S17 atomic workspace/locks,
and the BLG-I01 implementation boundary available at an accepted commit/receipt. Development must
implement the entire vertical chain in one isolated workspace. It may use the D03 oracle as a
versioned data/policy dependency, but may not rewrite it. No Dev dispatch occurs while either
dependency gate is unresolved.

## Explicit exclusions

- FBO, cancel/return, KIZ correction, stock/reserve movement and direct Chestny ZNAK integration.
- A new screen, a raw-evidence operator endpoint, manual database override or optimistic feature
  flag.
- Credential/key management, live WB/Ozon calls, production data, release, deploy or rollback
  execution.
- Historical evidence fabrication, destructive migration, retention purge or legacy-field removal.

## Handoff

Recommended S13 verdict: `ARCH_PLAN_READY`.

Next stage: `S14 ARCHITECT_FALSIFICATION`, independent role `solution-architect`. S14 and S15 may run
with the current dependency states because the plan is fail-closed. The mandatory BLG-I01 and
BLG-D03 gates remain attached to S16 and S18 and must not be bypassed.
