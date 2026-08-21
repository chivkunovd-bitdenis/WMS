# S12 TASK_CUT - BLG-D07

## Verdict

`TASK_CUT_READY`

## Source business meaning

After an FBS order is first imported, WMS may leave it in an old Wildberries
state. A cancelled, changed, completed, refused, defective, or carrier-cancelled
order can then keep guiding a warehouse operator as though its state were still
current. The requested business result is a regular, rate-safe repeat
reconciliation that makes the last confirmed WB truth and its age explicit,
without using a read of WB status to mutate stock, reserve, packaging, boxes,
marking, shipment, or another marketplace operation.

## Atomic vertical card

**Card ID:** `BLG-D07-C1`

**Title:** Keep every eligible FBS order honestly reconciled with WB and expose
whether its displayed status is confirmed, delayed, stale, never confirmed, or
in conflict.

This is deliberately one vertical card. A worker which merely polls, a database
field which merely stores a timestamp, or a status label which cannot be traced
to a successful per-order WB response does not produce the requested warehouse
outcome. The card is complete only when the same operator-visible order can be
selected safely, reconciled under the seller's shared WB budget, persisted with
the distinct attempt and success facts, mapped/audited without hidden side
effects, and read back after reload with truthful freshness.

For each eligible order, the observable result is one of these approved states:

1. A valid, exact-match WB row is durably applied, with raw and mapped status,
   `last_attempt_at`, `last_success_at`, freshness, and reconciliation trace
   agreeing on read-back and reload.
2. A valid terminal WB outcome is durably observed and retained/confirmed under
   the S13 policy before the order leaves regular reconciliation; a late result
   that conflicts with a completed warehouse operation becomes visible as a
   `CONFLICT`, never an automatic compensating warehouse mutation.
3. A temporary WB, network, or capacity failure leaves the last success intact,
   records the attempt and safe reason, schedules only the bounded permitted
   retry, and shows `DELAYED` or `STALE` rather than implying that old data is
   current.
4. No successful result yet is visibly `NOT_SYNCED`; an unknown, missing,
   duplicate, foreign, malformed, wrong-seller, or out-of-order observation
   cannot be converted into a convenient known local status or a false success.

## Card boundary and owned resources

The card owns the complete reconciliation path, but S12 does not select its
implementation primitives or edit application code. S13 must turn the following
resource boundary into an exact resource graph, file list, additive migration
plan, locks, and wave order:

- **Selection and durable order state:** tenant/seller-scoped FBS orders;
  eligibility for `waiting`, `sorted`, `ready_for_pickup`,
  `postponed_delivery`, `accepted_by_carrier`, and `sent_to_carrier`; terminal
  observation/retention for `sold`, `canceled`, `canceled_by_client`,
  `declined_by_client`, `defect`, `canceled_by_carrier`, `supplierStatus=cancel`,
  and `supplierStatus=cancel_carrier`; per-order attempt, success, error,
  retry, freshness, observation ordering, and audit data.
- **Worker and queue:** the periodic trigger, isolated task queue, durable work
  selection/cursor, retry/replay state, and worker-cycle operational markers.
  A cycle marker is never a substitute for per-order success.
- **External-contract boundary:** the existing status-read client and local WB
  emulator contract only. Requests contain IDs from exactly one tenant/seller
  lane; the shared seller FBS rate budget also protects interactive orders,
  supplies, passes, and auto-return work.
- **Business projection and audit:** raw `supplierStatus`/`wbStatus`, the
  explicitly approved local mapping, conflict preservation, reconciliation
  attempt identity, observed time, prior/new values, apply result, and
  sanitized operational signal.
- **Read surface:** the existing order-status API/read-back and the operator
  status surface must expose the mapped state, `last_attempt_at`,
  `last_success_at`, freshness state, safe failure category, and known
  `next_retry_at`; timestamps are stored as UTC and rendered in the operator's
  local timezone. This is an operational necessity, not an administrator-only
  log field.

The card excludes webhook work, manual refresh/bulk actions, notifications,
screen redesign, historical production backfill, token/cabinet work, live WB
or sandbox calls, deploy/release, and every stock/reserve/packing/box/marking/
shipment/cancellation side effect. A status read may only persist the approved
reconciliation facts and status projection.

If S13 determines that satisfying the mandatory operator read surface changes
the existing API or UI, the card must be reclassified through the controller as
`ui_change` and receive S09/S10 before S16 and S24/S25 after implementation.
This task cut does not permit hiding mandatory freshness behind logs, nor does
it bypass the UX/Product Browser route. If the existing approved surface already
contains the required data without a UI change, S13 must demonstrate that fact.

## Required worker behavior inside the card

1. **Fair eligible selection.** Orders are selected by tenant/seller lane and
   oldest successful reconciliation so the tail cannot starve. Terminal removal
   happens only after a matching terminal response is durably applied and the
   S13 confirmation/retention policy is satisfied. `sorted` remains eligible.
2. **Shared rate safety.** The architecture must use one seller-level budget,
   a conservative reserve for interactive FBS work, WB's 300 requests/minute,
   200 ms minimum interval, burst 20, and current `4XX x10` accounting. It may
   not spend the ceiling continuously merely to meet the 15-minute target.
3. **Attempt differs from success.** Every outbound inclusion records
   `last_attempt_at`. Only one validated, requested, exact tenant/seller match
   durably applied for that same order may advance `last_success_at`. A HTTP
   `200`, a partial batch, or completed worker cycle does not certify another
   order.
4. **Freshness is honest.** `FRESH` is success no older than 15 minutes without
   an unresolved contradiction; `DELAYED` is older than 15 and no older than 60
   minutes; `STALE` is older than 60 minutes or no success within 15 minutes of
   eligibility; `NOT_SYNCED` has no success; `CONFLICT` preserves a valid WB
   observation that contradicts a completed local warehouse operation.
5. **Bounded recovery.** Transport/DNS/timeout/`5XX` use S13's bounded
   exponential backoff with jitter. `429` pauses only that seller lane under
   the shared limiter, with no immediate per-ID fallback. `400` is not blindly
   replayed; `401`/`403` stop that seller lane pending access health; `402`
   stops it with a distinct payment-required state. Other unexpected `4XX`,
   invalid schemas, and ambiguous response rows are bounded observable
   failures, not successes.
6. **Safe restart and ordering.** Replay after crash/restart is idempotent;
   unfinished cycles are never reported successful. Older concurrent responses
   cannot overwrite a newer accepted observation. An unknown enum remains raw
   and requires attention; it does not trigger an irreversible side effect.
7. **Capacity is observable.** If safe seller capacity cannot meet the
   15-minute target, the worker preserves WB limits, records the cause, makes
   affected orders delayed/stale, and emits a sanitized capacity signal. One
   seller's outage, throttle, malformed response, access, or payment problem
   cannot stop an independent seller lane.

## S13 architecture-plan requirements

`S13 ARCHITECT_PLAN` is next because this is a database/worker card. It must
produce an implementable resource graph that names exact routes, services,
models/tables, additive migrations, scheduler/task/queue resources, API/read
models, emulator seams, observability sinks, locks, and owners. It must decide
and justify, rather than inherit implicitly:

- tenant/seller isolation, queue isolation, shared seller budget and safety
  reserve; batch size, tick, fairness/cursor and a volume proof for the
  15-minute target or a visible capacity-breach outcome;
- the durable schema and compatibility/backfill posture for attempt, success,
  retry, safe error, freshness, raw observation, mapping, conflict, audit and
  terminal confirmation/retention facts;
- retry count, backoff/jitter, timeout, circuit breaker, `429` header/local
  delay precedence, fallback cap, error classes, seller-lane stop/resume, and
  restart/replay semantics;
- idempotent per-row apply, exact-match validation, out-of-order concurrent
  response prevention, transition/audit ordering, and the explicit proof that
  no warehouse or marketplace command side effect is reachable; and
- whether the approved operator read surface needs a UI/API change. If so, it
  must raise the required `ui_change` route before S16 rather than silently
  extending an unapproved screen.

S13 may not choose a live WB proof, credentials, deployment, or a general
marketplace/warehouse rewrite. S14 is not enabled for the current controller
traits/risk, but S13 must leave its assumptions falsifiable through the S15
breaker cases below.

## S15 case-factory requirements

S15 must materialize all 19 research cases: `D07-EMU-200-FULL`,
`D07-EMU-200-PARTIAL`, `D07-EMU-200-DUPLICATE`, `D07-EMU-200-FOREIGN-ID`,
`D07-EMU-UNKNOWN-STATUS`, `D07-EMU-LATE-STATUS`, `D07-EMU-CARRIER`,
`D07-EMU-400`, `D07-EMU-401-403`, `D07-EMU-402`,
`D07-EMU-404-UNEXPECTED`, `D07-EMU-409-X10`,
`D07-EMU-4XX-X10-CURRENT`, `D07-EMU-429`, `D07-EMU-TIMEOUT-5XX`,
`D07-EMU-MALFORMED`, `D07-EMU-FALLBACK-CAP`,
`D07-EMU-RESTART-REPLAY`, and `D07-EMU-STARVATION`.

It must additionally cover the 15/60-minute boundaries and all five
operator-visible freshness states; eligible/terminal selection including late
conflict; per-order versus cycle success; consecutive retry exhaustion; seller
fairness and capacity-induced staleness; tenant/seller isolation; reload and
audit read-back; out-of-order concurrent responses; and the forbidden-side-
effect invariant. Each direct and breaker case needs a deterministic local
fixture/reset, oracle, expected durable trace, executor type, and planned S19
binding. Zero applicable rows may remain uncovered.

## Exact testing boundary

No S15, S18, S19, S20, S22, or S23 action for this card may call live WB,
WB sandbox, Ozon, or use production data, credentials, cabinets, or secrets.
All external responses, rate headers, timeouts, malformed data, and restart
conditions are exercised by the local WB emulator and isolated worker fixtures.
S19 must assert that the outbound host is the emulator only. A future separately
authorized sandbox proof can supplement but never replace this deterministic
coverage; it is not authorized by BLG-D07.

## S18, S19 and S20 execution gates

**S18 DEVELOPMENT** may implement only this S16-approved card and S13-approved
resources. Its scoped commit must prove the worker path, durable attempt/success
facts, freshness/read-back, mapping/conflict/audit trace, tenant/seller and
queue isolation, rate/retry/outage/replay behavior, and absence of unrelated
marketplace or warehouse mutation. No UI or API expansion is allowed without
the route stated above.

**S19 TEST_AUTOMATION_BINDING** must bind every applicable S15 case to isolated
deterministic `pytest`, local-worker harness, contract runner, and local WB
emulator references. Each binding includes fixture/reset, timeout, expected
trace, evidence schema, and host guard. It must make rate accounting, retry
timing, lane isolation, fairness/starvation, replay, timestamps, freshness,
mapping, conflict, reload/read-back, and forbidden side effects
machine-checkable; manual evidence cannot replace them.

**S20 CODE_REVIEW** must reject a diff that polls without truthful per-order
freshness, stores success for a batch rather than an exact row, treats `sorted`
as terminal, bypasses a shared seller limiter, retries non-retryable errors or
falls back per-ID after `429`, starves the tail, mixes seller/tenant lanes,
accepts ambiguous/unknown/out-of-order rows, loses audit/read-back, exposes
unsafe raw failures, writes non-additive data changes, or triggers an
unauthorized warehouse/marketplace side effect.

## Handoff

- **Next stage:** `S13 ARCHITECT_PLAN`, role `solution-architect`.
- **Card handed forward:** `BLG-D07-C1` only; no split worker, storage, API, or
  operator-visibility subcards.
- **S16 packet condition:** Product receives this task cut, S11 contract, S13
  plan, S15 cases and any required S09/S10 UX evidence. A material change to
  any of them invalidates the before-Dev decision.
- **Current blocker:** none. Architecture choices are intentionally open at S13;
  they are not an owner-input blocker and must not be guessed in S12.

## Verdict

`TASK_CUT_READY`: `BLG-D07-C1` is one atomic, business-observable reconciliation
card. It keeps the worker, rate/retry/outage policy, per-order timestamps and
freshness, status/audit truth, operator read-back, and deterministic no-live-WB
proof under one accountable boundary for the subsequent architecture, case,
development, automation, and review stages.
