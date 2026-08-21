# S13 ARCHITECT_PLAN - BLG-D14

## Verdict

`ARCH_PLAN_READY`

`BLG-D14-C1` remains one vertical concurrency card. The plan closes
`BLK-ARCH-002` at architecture level by defining one lock order, bounded
database retry and timeout behavior, durable idempotency/read-back, poller
overlap semantics, and a reproducible PostgreSQL load case with 155 orders.
No implementation, migration, external call, test run, commit, push, deploy,
or production action is part of this artifact.

## Current failure chain

The present code has a concrete lock-order inversion:

1. `create_supply_from_orders` validates and locks all selected `fbs_orders`
   with `FOR UPDATE`, then tries to acquire the per-seller PostgreSQL advisory
   lock (`backend/app/services/fbs_supply_service.py:324-344`).
2. The status poller acquires that advisory lock first, then
   `sync_order_statuses` locks up to 500 `fbs_orders` with `FOR UPDATE`
   (`backend/app/services/fbs_autopoll_service.py:365-383` and
   `backend/app/services/wb_marketplace_orders_service.py:891-922`).
3. If the two paths overlap, creation can hold order rows while waiting for the
   seller lock, while the poller holds the seller lock while waiting for the
   same order rows. PostgreSQL must abort one participant or the operator waits
   until a timeout.

Both paths also currently keep row locks while awaiting WB HTTP. The WB client
uses a 60-second request timeout, and 155 orders are split into two batches of
at most 100. Therefore a large operation can hold database rows across several
network waits even when no deadlock is formed.

## Architectural decisions

### A1. One canonical lock order

Every BLG-D14 path that coordinates supply creation or automatic status writes
for one seller must acquire resources in this order and may never invert it:

```text
1. seller advisory lock: wb_seller_lock(seller_id)
2. fbs_wb_operations rows: operation_kind, idempotency_key
3. fbs_supplies rows: ascending supply UUID
4. fbs_orders rows: ascending order UUID
5. order-owned dependent rows, one order at a time:
   reversal ledger -> reservation/inventory -> packaging linkage
```

Absent resources are skipped; skipping does not change the order of later
resources. A preview query may run before the seller lock only without
`FOR UPDATE` and may not authorize a write. Every write re-reads and validates
the locked rows.

For a new operation, the seller advisory lock serializes creation of the
otherwise absent idempotency row. The existing unique constraint on
`(seller_id, operation_kind, idempotency_key)` remains the final duplicate
barrier. If a uniqueness race is still observed, the transaction rolls back
and reads the winner; it does not create a second external supply.

The seller advisory lock is session-scoped and must always be released in a
`finally` path. A failed or rolled-back database transaction does not authorize
releasing it before the operation has reached a durable state.

### A2. Never hold row locks across WB HTTP

The per-seller advisory lock may cover the coordinated WB operation, but
`fbs_wb_operations`, `fbs_supplies`, `fbs_orders`, reservation, inventory, and
packaging rows must not remain locked while waiting for WB. Creation is split
into three explicit phases:

**T1 - durable intent (short database transaction).** Under the seller lock,
lock or create the operation row, then lock selected orders in ascending UUID.
Revalidate tenant, seller, warehouse, authorization and eligibility. Create the
local pending supply and durable `pending` operation, including request hash,
the exact sorted order IDs and local supply ID, then commit before the first WB
write. A retry with the same key reads this durable intent; a different request
hash is a business conflict.

**E1 - external effect (no database row locks).** Still under the seller lock,
create/read the WB supply, add the orders in deterministic 100-order batches,
and read back WB membership. A transport timeout is an uncertain result, not a
rollback claim. It is persisted as `pending_confirmation` in a separate short
transaction before returning a retryable response. The whole create flow is
never replayed blindly after any WB call may have succeeded.

**T2 - local finalization (short database transaction).** Lock operation,
supply and all selected orders in canonical order, then revalidate current
business state and the WB read-back. Only a confirmed exact membership binds
the orders and marks the operation `confirmed`; the commit is atomic. A real
eligibility change is returned as a business conflict with affected order IDs,
not retried as a deadlock. An uncertain external result remains
`pending_confirmation` and is resolved by read-back with the same idempotency
key.

If T2 sees that another legitimate path changed an order while E1 ran, it must
not overwrite that state. It records the operation as requiring reconciliation
and returns the truthful business-conflict or pending-confirmation outcome.
S18 may not introduce an unresearched destructive WB compensation call.

No schema migration is required by this plan: the existing operation journal,
pending/confirmed/pending-confirmation states, request summary, local entity
link and unique idempotency constraint can represent these phases. If S18 finds
that durable phase recovery cannot be represented without a new column or
constraint, implementation stops and returns to S13; it must not invent a
migration inside Dev.

### A3. Poller overlap contract

The status poller keeps non-blocking seller-lock acquisition. If creation owns
the seller lock, that seller is skipped with a structured `busy` observation
and is eligible for the next configured poll cycle; the worker must not spin or
open an unbounded retry loop.

When the poller obtains the seller lock first, it must not lock order rows while
performing WB status HTTP. It reads candidate IDs without row locks, fetches WB
statuses, then enters a short apply transaction: infer and lock affected supply
rows in ascending UUID, lock candidate orders in ascending UUID, re-read their
current state, apply only still-valid status transitions, and commit. Creation
can wait for the seller lock without holding any order row, so the prior cycle
is impossible.

The poller must preserve legitimate external statuses. A skipped busy cycle is
observable and delayed, not discarded; the next cycle or an explicit test
trigger applies it. A status snapshot fetched before a local change cannot
overwrite `supply_id` or another newer business transition without revalidation.
Worker replay/restart repeats the read/apply decision and converges on the same
order state.

### A4. Bounded retry and timeout policy

Database recovery applies only to PostgreSQL concurrency SQLSTATE values:

- `40P01` deadlock detected;
- `40001` serialization failure;
- `55P03` lock not available, including the local lock-timeout path.

Each short transaction gets at most three attempts total: the initial attempt
plus two retries. Before each attempt set transaction-local
`lock_timeout = 2s` and `statement_timeout = 10s`. After a full rollback, wait
with bounded jitter: 100-250 ms before attempt 2 and 250-750 ms before attempt
3. Reacquire and re-read every row in canonical order; never reuse ORM state
from an aborted transaction. The maximum database lock-recovery envelope is
under 7 seconds plus normal statement execution.

The creator may wait at most the existing 15 seconds for the seller advisory
lock. The poller waits zero seconds and skips a busy seller. Exhaustion returns
the existing API error shape as `operation_in_progress`, HTTP 503,
`retryable=true`, with a message that the temporary conflict did not complete
the action. The existing create dialog retains its selection, entered values
and idempotency key while showing the error, so pressing Create again represents
the same intent rather than risking a duplicate.

Do not retry authorization, validation, eligibility, tenant/seller/warehouse,
unique-request-hash mismatch, or other business errors. Do not retry a WB write
merely because its response was lost. Existing WB calls retain their 60-second
per-request timeout; timeout recovery is read-back/reconciliation under the
same durable operation. For 155 orders, the known external sequence is bounded
to create, two add batches, and read-back; S15 must inject timeouts at each
boundary rather than sleeping for real network time.

### A5. Idempotency, read-back and response truth

The business identity is `(seller_id, supply_from_orders, idempotency_key)` and
its request hash includes the stable sorted order set, name and delivery type.
All automatic transaction retries, repeated clicks, explicit operator retries,
lost responses and service restarts use that same identity.

Before executing an external effect, read the durable operation:

- `confirmed` returns the existing local workspace after database read-back;
- `pending_confirmation` reads WB membership first and either finalizes once or
  remains honestly retryable;
- `pending` with a durable WB object resumes from the recorded phase and never
  creates another WB supply;
- `failed` returns its classified non-retryable result unless the failure is an
  explicitly recoverable concurrency outcome;
- a different request hash returns `idempotency_key_reused`.

Success is emitted only after T2 commits and a fresh workspace query confirms
one local supply, exact order membership and confirmed operation state. An
ordinary subsequent reload must return the same supply and membership. A
timeout or disconnected response never implies rollback; the next same-key
request performs read-back first.

## Resource graph and implementation boundary

```text
FbsSupplyCreateDialog retained intent/idempotency key
  -> POST /operations/fbs-supplies/from-orders
  -> create_supply_from_orders
       -> seller advisory lock
       -> T1 operation journal + pending supply + ordered order locks
       -> WB create + two 100-order add batches + WB membership read-back
       -> T2 ordered operation/supply/order locks + exact membership bind
  -> workspace read-back and reload

Celery beat status poller
  -> per-seller advisory lock (non-blocking)
  -> WB status fetch without row locks
  -> ordered supply/order apply transaction
  -> durable status read-back on next query/cycle
```

| Resource | S18 ownership implied by this plan | Lock / rule |
| --- | --- | --- |
| `backend/app/services/fbs_supply_service.py` | Phase T1/E1/T2 orchestration and retry classification | Seller lock before every row lock; no row lock across HTTP |
| `backend/app/services/fbs_supply_reconcile_service.py` | Durable resume/read-back transitions | Operation row before supply/order rows |
| `backend/app/services/fbs_autopoll_service.py` | Busy-seller observation and short apply boundary | Non-blocking seller lock; commit/rollback per seller |
| `backend/app/services/wb_marketplace_orders_service.py` | Fetch/apply split and ordered row locking | Supply UUID then order UUID; no HTTP under `FOR UPDATE` |
| `backend/app/services/fbs_wb_seller_lock_service.py` | Existing primitive; only timeout/observability support if required | No lock-key or scope change |
| `backend/app/api/fbs_supplies.py` | Preserve error shape and commit only durable phase state | No false rollback/success response |
| `backend/tests/test_fbs_supply_from_orders.py` | PostgreSQL concurrency, idempotency and read-back cases | Required 155-order fixture |
| `backend/tests/test_fbs_autopoll.py` or focused integration harness | Poller overlap, skip/replay/restart cases | Isolated queue and no live marketplace |
| `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx` | Read-only unless post-diff proves current retry UX insufficient | Existing state already retains key and selection |
| Alembic/models | No planned write | Any schema need returns to S13 |

S17 must allocate the exact files selected from this graph and serialize overlap
with another task touching the same supply/poller services. S18 must not expand
into polling cadence changes, general cancellation redesign, bulk-selection UX,
new WB endpoints, live marketplace access, or unrelated inventory work.

## Required 155-order load and overlap case

S15 must materialize `BLG-D14-AC02` as a PostgreSQL-only deterministic harness,
not SQLite and not a live WB call:

1. Create one tenant, seller and warehouse with exactly 155 eligible local FBS
   orders. Shuffle request order IDs with a fixed seed so the service must prove
   its ascending lock order. The emulator returns two add batches (100 + 55).
2. Start creator C with one stable idempotency key. At a barrier after the
   seller lock and before T1 order locks, start poller P for the same seller and
   all 155 WB order IDs. Release both in controlled order.
3. Repeat with P owning the seller lock first and paused immediately before its
   short apply transaction, then start C. Also run subset overlap (77 orders),
   no selected-order overlap, and inverse input ordering as controls.
4. Inject `40P01`, `40001`, and `55P03` once and then persistently at each short
   transaction boundary. Record attempt number, SQLSTATE, backoff bucket,
   seller-lock wait/skip, transaction duration and final classification.
5. Inject a lost response after WB create, after batch 100, after batch 55, and
   after T2 commit. Retry with the same key and restart the worker between
   attempts. Read-back must resume the recorded phase without another supply.
6. Change one order to genuinely ineligible before T2. Assert that it is a
   business conflict, not a concurrency retry, and that no stale poller write
   restores eligibility or silently binds a partial local supply.
7. Drain the isolated worker queue, then query through the normal workspace API
   and reload path.

Pass requires all of the following:

- zero PostgreSQL deadlock reports and zero sessions left `idle in transaction`;
- no transaction exceeds its declared lock/statement timeout;
- exactly one operation row and at most one local/WB supply for the intent;
- on success, exactly 155 distinct orders belong to that supply and read-back
  plus reload return the same set;
- on exhausted concurrency, no partial local membership exists and the same
  intent remains safely retryable;
- every legitimate poller status is either applied once or recorded as a busy
  skip and applied on the next controlled cycle;
- attempt count never exceeds three, poller does not spin, and no test traffic
  reaches live WB/Ozon or production data.

The harness must capture sanitized timestamps/barriers, lock owner/waiter
identities, SQLSTATE, transaction attempt/duration, idempotency key pseudonym,
operation transitions, batch sizes, supply count, membership digest, poller
skip/apply counters, queue drain and final read-back digest. A green HTTP status
without those database and worker observations cannot pass.

## S14 falsification handoff

The independent architect must try to disprove this plan with at least:

- any remaining path that locks an order before the seller advisory lock;
- poller HTTP still occurring while `FOR UPDATE` rows are held;
- operation/supply/order inversion during same-key resume;
- dependent cancellation, reservation, inventory or packaging locks that
  introduce a hidden inverse edge;
- advisory-lock timeout combined with transaction retry exceeding the bounded
  envelope;
- SQLAlchemy session state reused after a failed transaction;
- process death after T1, after each WB batch, and immediately after T2 commit;
- stale poller status overwriting newer membership or losing a cancellation;
- two distinct WB supplies for one idempotency key;
- 155-order input locking in caller order rather than ascending UUID;
- SQLite mocks falsely passing behavior that requires PostgreSQL locks;
- current dialog or API error handling replacing the idempotency key or losing
  the selected order set after retry exhaustion.

Any unresolved inverse edge, non-durable external phase, unbounded wait, false
rollback assumption, duplicate-supply path, or missing 155-order proof returns
`ARCH_REVIEW_REWORK` to S13. S14 does not implement the correction.

## Blocker closure

`BLK-ARCH-002` minimum closure is satisfied by this artifact:

- lock ordering: A1 plus the resource graph;
- retry/timeout policy: A4;
- load case for at least 155 orders: the required load/overlap case above.

The architecture blocker can therefore be resolved by the controller against
this file. Development remains prohibited until independent S14 falsification,
S15 cases and S16 Product-before-Dev approval pass.

## Final verdict

`ARCH_PLAN_READY`: the known inverse lock cycle is removed by one seller-first
order, database row locks are confined to short durable transactions, retries
are bounded and SQLSTATE-specific, uncertain external effects resume by
idempotent read-back, and the 155-order overlap case has explicit barriers,
oracles, evidence and stop conditions for S14/S15.
