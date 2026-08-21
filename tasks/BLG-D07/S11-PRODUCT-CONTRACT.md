# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D07

## Product decision

Product approves repeat reconciliation of Wildberries FBS order statuses as a background safety
process. The business result is not merely that a worker runs: after the first import, an eligible
order continues to be checked until WMS has a justified terminal result, and the operator can tell
whether the displayed WB state is current, delayed, stale, or has never been confirmed.

This closes the source problem in full: a cancelled, changed, or already processed WB order must not
remain indefinitely presented as an up-to-date actionable order in WMS. A failed attempt never makes
old data look fresh, and a successful response for one order never certifies another order or the
whole seller cycle.

S11 approves the product behavior and evidence obligations below. It does not choose queue, schema,
transaction, batch-size, cursor, or retry implementation; those decisions belong to S13 and must
preserve this contract.

## Expected operator and warehouse effect

1. A healthy seller lane regularly rechecks every eligible FBS order, including orders whose last
   known WB state is `sorted`, `ready_for_pickup`, `postponed_delivery`, `accepted_by_carrier`, or
   `sent_to_carrier`. `sorted` is not treated as proof that later sale, refusal, defect, or
   cancellation can no longer happen.
2. Under healthy WB connectivity and within the shared seller rate budget, each eligible order has a
   target successful freshness of no more than 15 minutes. This is the operator-facing service
   target, not permission to exceed a WB limit or starve interactive FBS operations.
3. When WB returns a different valid status for an order, WMS records the observed raw transition
   with its source and time, recalculates only the explicitly mapped local status, and makes the new
   business meaning visible on the existing order-status surface.
4. Cancellation, completion, refusal, defect, and carrier cancellation must no longer leave an
   order looking like an ordinary current work item. The operator sees both the latest mapped state
   and when WB last confirmed it.
5. Reconciliation does not silently create, cancel, reopen, pack, ship, reserve, unreserve, move
   stock, modify a box, or repeat a marketplace command. Any such warehouse side effect requires a
   separately approved mapping and case. BLG-D07 authorizes status read, truthful persistence,
   explicit status projection, freshness, and observability only.

## Eligible and terminal WB states

The approved Product classification is:

- regular reconciliation: `waiting`, `sorted`, `ready_for_pickup`, `postponed_delivery`,
  `accepted_by_carrier`, and `sent_to_carrier`;
- terminal external outcomes: `sold`, `canceled`, `canceled_by_client`, `declined_by_client`,
  `defect`, and `canceled_by_carrier`;
- supplier-side terminal cancellation: `supplierStatus=cancel` or
  `supplierStatus=cancel_carrier`.

An order may leave the regular reconciliation set only after a valid matching WB row established a
terminal outcome and the durable write completed. S13 must define a bounded confirmation/retention
policy for terminal outcomes so that crash replay cannot skip the terminal observation. This task
does not authorize reopening a finished warehouse operation or reversing stock/reserve history from
one late status. If a late valid WB result conflicts with an already completed local operation, WMS
records and exposes a reconciliation conflict for responsible review; it does not hide the conflict
or invent an automatic compensating mutation.

An unknown `supplierStatus` or `wbStatus` is never guessed into a known business state. WMS preserves
the raw value, marks the reconciliation result as requiring attention, emits a safe operational
signal, and performs no irreversible side effect. The prior local business status may remain visible
only as the last known mapping, clearly separated from the unknown current WB value.

## Frequency and shared WB rate safety

- The 15-minute freshness target is subordinate to WB's current per-seller limits and to the shared
  budget used by other FBS orders, supplies, passes, and auto-return calls. Status reconciliation
  must coordinate with that shared budget rather than maintain an isolated counter.
- The current research oracle is 300 requests per minute per seller account, at least 200 ms between
  requests, burst 20, with each `4XX` charged as 10 requests. S13 must use a conservative safety
  margin and reserve capacity for operator-triggered FBS work; it may not plan to consume the
  documented ceiling continuously.
- Batch size, scheduling tick, safety margin, priority weights, and terminal retention interval are
  architecture decisions. Whatever values S13 selects must prove that the oldest eligible orders
  eventually run and that a permanent cycle cap cannot starve the tail.
- A `429` pauses only the affected seller lane until the later of a valid `Retry-After` value and the
  local rate-budget delay. In the absence of a valid header, the bounded local policy applies.
- One seller's throttling, access problem, malformed response, or outage must not stop independent
  tenants or sellers. IDs from different tenant/seller lanes are never mixed in one WB request or
  applied across their boundary.
- Batch-to-single fallback is not a general retry strategy. It is allowed only when S13 proves a
  bounded diagnostic value, shared-budget accounting, and a circuit breaker; it is forbidden for
  rate, access, payment, and malformed-request failures.

If the shared rate budget cannot meet the 15-minute target safely, WMS preserves safety, reports the
affected orders as delayed/stale, and raises an operational capacity signal. It must not exceed the
external contract to keep the UI green.

## Attempt, success, and stale visibility

The operator-facing status surface must provide, for each affected order, the latest mapped WB state
and these distinct facts:

- `last_attempt_at`: when WMS most recently began a WB status request that included this order;
- `last_success_at`: when WMS most recently received, validated, and durably applied exactly one
  matching response row for this order;
- the current freshness state and, after a failed attempt, a safe human-readable failure category;
- `next_retry_at` when an automatic retry is scheduled and the time is known.

Times are stored with timezone in UTC and rendered in the operator's local timezone. A batch-level
HTTP `200` is not enough to update `last_success_at`: the response must contain one valid unambiguous
row with the requested ID. Missing, duplicate, foreign, malformed, or wrong-seller rows update the
attempt fact and safe error state, but never the success time. A worker cycle success marker is a
separate operational fact and cannot replace per-order success.

Approved freshness states are:

- `NOT_SYNCED`: no successful reconciliation exists; show "WB ещё не подтвердил статус" and the
  latest attempt/failure when present;
- `FRESH`: `last_success_at` is no older than 15 minutes and no newer unresolved contradictory
  response exists;
- `DELAYED`: the last success is older than 15 minutes but no older than 60 minutes; show the last
  success time and the reason/retry time when known;
- `STALE`: the last success is older than 60 minutes, or no success was obtained within 15 minutes
  after the order first became eligible; show "Статус WB устарел" and never present the mapped value
  as current;
- `CONFLICT`: WB supplied a valid status that conflicts with an already completed local warehouse
  operation; show both the last known local meaning and the new WB observation for responsible
  review, without automatic compensation.

An attempt failure does not erase a previous `last_success_at`; it changes freshness/error state and
shows that the last success is historical. Recovery requires a new valid matching row. Repeating the
same valid response is idempotent: it may advance the new success timestamp but cannot repeat a
business side effect or duplicate transition history.

If visible UI changes are needed to satisfy this section, S12 must classify the affected vertical
card as `ui_change` and route it through S09/S10 before Dev, plus S24/S25 afterward. S11 does not
permit hiding the timestamps only in logs or an administrator-only metric when the operator is being
shown the order as actionable.

## Retry and outage behavior

- Transport failure, DNS failure, timeout, and `5XX`: bounded exponential retry with jitter. The
  failed attempt is visible; `last_success_at` is unchanged; exhausted retry budget leaves the order
  delayed/stale for a later scheduled cycle.
- `429`: no immediate retry storm and no per-ID fallback. The seller lane waits under the shared
  rate limiter while other seller lanes continue.
- `400`: the same payload is not retried blindly. The affected batch is marked as a request/contract
  failure for investigation.
- `401`/`403`: the affected seller lane stops automatic retries until access health is restored. No
  credential, token, cabinet, or secret operation is part of BLG-D07.
- `402`: the affected seller lane stops with a distinct payment-required operational state.
- unexpected `404`, other `4XX`, invalid JSON/schema, duplicate response ID, foreign ID, and missing
  requested ID: no success claim, no hidden last-row-wins rule, no irreversible mutation, and a
  bounded observable failure under S13 policy.
- Worker crash or restart: unfinished attempts/cycles may be replayed, but already applied rows are
  idempotent and an incomplete seller cycle is never reported as successful.

The operator receives business-safe wording, not raw response bodies, tokens, headers, stack traces,
or internal exception names. Operational evidence may retain sanitized category, seller pseudonym,
attempt ID, timestamps, and counts.

## No hidden status changes

Every accepted WB transition records at minimum order identity, tenant/seller scope, previous and new
raw `supplierStatus`/`wbStatus`, previous and new mapped local status, observed time, apply result,
and reconciliation attempt identity. The operator-visible current state and the audit/read-back state
must agree after reload.

The following are forbidden:

- updating a local business status from a response row whose ID or seller scope is not an exact
  match;
- treating an absent row, failed request, or cycle completion as evidence that the old status is
  still current;
- mapping an unknown WB enum to a convenient known status;
- overwriting a newer observation with an older concurrent response;
- changing status without a durable transition trace and a refreshed visible timestamp;
- running stock, reserve, packaging, box, marking, shipment, or cancellation side effects merely
  because the polling worker observed a value.

## Required downstream evidence

### S12 - atomic task cut

S12 must cut vertical cards that preserve one observable outcome rather than separate "worker" and
"UI timestamp" tasks with no end-to-end owner. At minimum the cut must explicitly own: eligible and
terminal selection; shared rate/retry behavior; per-order attempt/success/freshness persistence;
raw-to-local mapping and conflict/audit behavior; operator visibility; and observability. Any visible
surface change must add the `ui_change` route instead of bypassing Design/Product Browser stages.

### S13 - architecture plan

S13 must provide the resource graph and exact plan for tenant/seller isolation, shared seller rate
budget, safety reserve, batching, fairness/cursor, terminal confirmation/retention, bounded retries,
circuit breaker, concurrent-response ordering, durable attempt/success/error fields, idempotent apply,
restart/replay, and sanitized observability. It must show why the 15-minute target is achievable at
expected volume or how capacity breach becomes visible without violating WB limits.

### S15 - case factory

S15 must materialize all 19 `D07-EMU-*` cases handed off by S03 and add direct/breaker cases for the
Product states `NOT_SYNCED`, `FRESH`, `DELAYED`, `STALE`, and `CONFLICT`; 15/60-minute boundaries;
terminal selection; late conflicting status; out-of-order concurrent responses; multi-tenant/seller
isolation; operator reload/read-back; no hidden side effects; and capacity-induced staleness. Each
case needs an oracle, fixture/reset, expected trace, and planned automation binding.

No S15, S18, S19, S22, or S23 test may call live WB. External behavior is exercised through the
local emulator; a separately authorized sandbox proof may supplement but never replace deterministic
emulator coverage, and is not authorized by this contract.

### S18 - development

S18 must implement only the S16-approved card and scoped resources. Its commit evidence must include
the worker behavior, persisted timestamps/freshness, exact mapping/conflict trace, operator-visible
read-back required by the approved cut, and proof that no unrelated marketplace or warehouse
mutation was introduced. Application code is not changed at S11.

### S19 - runnable automation bindings

S19 must bind every applicable S15 case to deterministic `pytest`, worker harness, contract runner,
and local WB emulator references with isolated tenant/seller fixtures, reset, timeout, expected
trace, and evidence schema. Bindings must prove that outbound hosts are limited to the emulator and
that replay, rate accounting, retry timing, starvation, timestamps, mapping, read-back, and forbidden
side effects are machine-checkable. Manual evidence cannot replace these deterministic cases.

## Non-goals

BLG-D07 does not approve:

- live WB production or sandbox calls, secret/cabinet work, token validation, rotation, or replacement;
- webhook introduction or replacement of polling with a new integration;
- order-content, price, address, deadline, label, supply, marking-code, stock, reserve, box, return,
  or shipment reconciliation;
- automatic rollback or compensation of already completed warehouse operations;
- historical production backfill or manual production-data correction;
- a new operator action, manual refresh command, bulk action, screen redesign, or notification center;
- release, deploy, production monitoring, or a claim that future emulator/sandbox evidence already
  exists.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: repeat WB status reconciliation may proceed to S12. It is approved only
as a rate-safe, retry-bounded, tenant/seller-isolated process that distinguishes attempt from success,
marks stale truth explicitly, preserves unknown/conflicting observations, exposes freshness to the
operator, and performs no hidden warehouse or marketplace side effect.
