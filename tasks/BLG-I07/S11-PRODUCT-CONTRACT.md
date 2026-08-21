# S11 PRODUCT_CONTRACT_APPROVAL - BLG-I07

## Product decision

Product approves a capacity and performance remediation whose result is visible
in the ordinary warehouse journey, not only in server metrics. Operators must be
able to open working lists, scan and confirm items, assemble a supply and request
printing without the WMS appearing frozen, losing an action or encouraging a
second click because the first result is uncertain.

The approved outcome has three inseparable parts:

1. establish a repeatable before-baseline for the primary operator journeys and
   rank the largest browser, API, database and background-worker contributors;
2. remediate the highest-impact causes without moving the delay to another
   screen, worker or warehouse step; and
3. prove the same journeys after the change against explicit latency, capacity,
   stability and data-integrity thresholds.

The historical 20 August observation is valid incident context, not a reusable
post-change baseline: 3.8 GB total memory, 145 MB free memory, 1.3 GB swap, one
API process, repeated container restarts, synchronous PDF/image work and heavy
browser polling were observed together. S13 and S15 must reproduce the relevant
load in an isolated production-like environment before attributing causality or
selecting a remedy.

## Operator journeys in scope

The performance map and before/after evidence must cover at least these complete
journeys with the same fixture, environment and concurrency profile:

- opening and paging the principal order, supply and packaging lists;
- opening a 500-order working set and retaining access to every order while the
  browser renders and refreshes manageable pages;
- scanning or confirming an item and seeing an honest accepted, rejected or
  still-processing state;
- assembling or updating a supply while background synchronization is active;
- requesting labels, PDF or image generation for representative small output,
  155 codes and 500 codes;
- notification refresh and other periodic browser activity while an operator is
  actively scanning, opening a list or printing;
- read-back and reload after every mutating journey.

S12 may split implementation into vertical cards, but no card may claim the
product result from an isolated endpoint benchmark. Each accepted slice must
leave one of these operator journeys observably faster or remove a measured
capacity/stability limit without weakening another journey.

## Product performance thresholds

For the agreed production-like fixture and the representative concurrency profile
defined at S13, "became fast" means all of the following:

- A scan, confirmation or ordinary command receives an honest visible
  acknowledgement within 1 second at p95 and 2 seconds at p99. Acknowledgement
  may be a completed result or a truthful processing state; it may not be a fake
  success.
- A principal list exposes its first usable page of up to 50 rows within 2
  seconds at p95. Paging, filtering or server-backed search exposes the next
  usable result within 1 second at p95. The operator can still reach and select
  the complete 500-order working set; pagination is not a 50- or 100-row cap.
- A print/PDF/image request is accepted or rejected visibly within 1 second at
  p95. Generation for 155 codes completes within 5 seconds at p95 and generation
  for 500 codes within 15 seconds at p95, unless S13 proves a stricter existing
  business deadline. Longer work must show durable progress and a recoverable
  final result rather than block the operator screen.
- While 155- and 500-code generation runs, unrelated interactive journeys stay
  inside their own thresholds. Heavy generation may not pause all API traffic or
  starve the worker queue.
- A 30-minute representative load run has no application restart, out-of-memory
  termination, unbounded queue growth or continuously increasing swap use. S13
  must set the numeric CPU, memory, event-loop lag, connection and queue-lag
  envelopes from the measured deployment shape and preserve at least 20 percent
  memory headroom at steady state.
- Background refresh must not increase the p95 latency of an active operator
  journey by more than 20 percent compared with the same load without refresh.
  Notification polling from one visible browser is no more frequent than once
  per 30 seconds. Re-fetching two complete 500-row lists every 26 seconds is not
  an acceptable steady state.

Each percentile is calculated from enough repeated samples to expose tails, not
from a single fastest run. S13 defines the exact sample count and concurrency
profile; S14 must challenge whether they represent ordinary and peak warehouse
work. If the production-like environment cannot sustain the thresholds, the
result is a named capacity gap and release blocker, not a silently relaxed
target.

## Warehouse, data and worker invariants

- Performance work must not drop, duplicate, reorder or falsely acknowledge a
  scan, packing action, supply update, print request or background event.
- Repeated clicks, request retries, worker retries and process restarts converge
  on the same business result and do not create duplicate durable effects.
- Faster lists and pagination do not hide older orders, reset a cross-page
  selection, weaken filters or silently replace current data with an incomplete
  client-side subset.
- Reducing polling does not make marketplace or warehouse state indefinitely
  stale. S13 must define freshness, invalidation and manual-refresh behavior for
  every changed refresh path.
- Background work remains isolated to the task's queue and tenant/seller/
  warehouse scope. Interactive traffic cannot starve durable jobs, and a large
  job cannot starve unrelated operator traffic.
- Any database change is backward compatible, preserves existing records and
  has an explicit backfill, integrity check, restore rehearsal and honest
  rollback boundary. Speed is not evidence that stored results remain correct.
- Authorization, tenant isolation, warehouse validation, marking rules and
  external-contract limits keep their existing force. No safety check may be
  bypassed, deferred without a visible state or removed to satisfy a latency
  target.

## Degraded and failure behavior

When capacity is temporarily insufficient, WMS must remain truthful and
recoverable. It may queue long work, apply bounded backpressure or show a
processing state, but it may not present an indefinite spinner, a blank screen,
an unexplained stale result or success before durable read-back.

Timeout, overload, worker outage and partial failure preserve the operator's
valid input and identify whether the action is pending, failed or safe to retry.
Recovery cannot require the operator to reconstruct a 500-order selection or
guess whether printing, scanning or supply mutation already completed.

## Acceptance boundaries for downstream stages

S12 must keep baseline, remediation and proof traceable as one product outcome.
It may create separate vertical cards for measured causes, but each card must
name the affected journey, before metric, target metric, non-regression journeys
and rollback boundary. Infrastructure capacity changes, application changes and
browser changes remain separately attributable.

S13 must define the resource graph, representative concurrency and data-volume
fixtures, measurement protocol, observability, capacity envelope, worker
isolation, database compatibility and stop/rollback conditions. It decides such
mechanisms as process count, thread/offload boundary, queue shape, caching,
pagination implementation and infrastructure sizing. S14 independently
falsifies that plan. This S11 verdict does not approve any one of those
mechanisms.

S15 must include direct and breaker cases for small/155/500-code printing,
500-order list access and selection, concurrent polling, overlapping worker jobs,
timeout, retry, worker restart, queue saturation, reload/read-back, migration,
backfill, restore and integrity reconciliation. Cases must compare before and
after measurements on the same immutable build and fixture.

S22 and S23 must bind browser timing, API latency, event-loop lag, CPU/memory,
database timing, queue lag, durable worker effects and read-back to one evidence
set. A faster isolated function, HTTP 200 or lower average latency alone is
insufficient. p95/p99, error rate, restart count and invariant results are
required.

If implementation changes visible controls, list behavior, loading/error states
or any other operator-facing UI contract, post-diff classification must add
`ui_change` and route through S09, S10, S24 and live Product Browser acceptance.
Reducing polling, introducing pagination or moving work to a background state
must not silently change operator behavior without that route. A purely internal
remediation still requires browser performance evidence for the journeys above,
but this S11 role does not perform or accept that future evidence.

Any production capacity purchase, container change, deployment or live
measurement remains a separately authorized release/operations action. Historical
production observations may be cited after sanitization, but this task does not
authorize new live WB/Ozon calls, production data mutation or secret access.

## Out of scope

This contract does not redesign warehouse workflows, cap large-order work,
remove refresh or validation, introduce unrelated analytics, choose code/schema/
infrastructure implementation, operate production, deploy, commit or push. It
does not accept future architecture, implementation, review, tests or browser
evidence.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: BLG-I07 succeeds only when repeatable before/after
evidence shows that the primary operator journeys meet the stated latency and
stability thresholds under representative 155/500-item load, while preserving
complete access, durable results, worker/data invariants and honest degraded
behavior.
