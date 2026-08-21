# S12 TASK_CUT - BLG-I07

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-I07-C1`
**Title:** Restore predictable performance of the primary warehouse journeys
under representative 155/500-item load, with before/after evidence and without
weakening durable warehouse results.

This remains one vertical remediation card. Splitting it into a browser,
endpoint, database, worker or infrastructure card before the measured resource
graph exists would create local improvements without proving the operator's
actual journey improved. The observable result exists only when the same
fixture, concurrency profile and journey show a repeatable baseline, a
measured limiting cause, a remedy, and a post-change read-back that preserves
the business outcome.

## Card contract

**Observable operational result.** With the production-like fixture and
concurrency profile later fixed by S13, an operator can open and page the
principal order, supply and packaging lists; reach and select all orders in a
500-order working set; scan or confirm an item; assemble or update a supply
while synchronization runs; request representative small, 155-code and
500-code label/PDF/image work; and reload/read back every mutation. These
journeys meet the S11 latency, capacity, stability and truthful-state
thresholds as one evidence set. A faster isolated HTTP endpoint, lower average
latency, or successful asynchronous submission is not the result of this card.

**Scope.** The card covers a reproducible before-baseline, attribution of the
largest browser/API/database/worker contributors, the bounded remediation of
those measured contributors, and matched after-evidence for the affected and
non-regression journeys. It includes the explicit capacity envelope, durable
acknowledgement/progress/error states where a long operation needs them,
read-back, retry/idempotency and worker/data integrity proof required to show
that the measured improvement did not move delay or failure elsewhere.

It does not redesign warehouse workflows, cap the 500-order working set,
remove validation or refresh, choose a process/queue/cache/schema/browser
mechanism, change marketplace contracts, perform production operations, make
live WB/Ozon calls, access secrets, deploy, commit, push or authorize release.
Any visible change to list behaviour, refresh, pagination, controls or
loading/error states requires the separately classified UI route before it can
be implemented.

## Delivery and review boundaries

1. S13 maps the actual resource graph and fixes the isolated production-like
   fixture, data volumes, sample count, concurrency, baseline protocol,
   observability, capacity envelope, stop conditions and rollback boundary. It
   selects the smallest safe remediation mechanisms only after attribution.
2. S14 independently challenges whether the fixture represents ordinary and
   peak warehouse work, whether the proposed remedy merely transfers latency or
   starvation, and whether the capacity/integrity proof can be trusted.
3. S15 makes the product thresholds and destructive cases executable before
   code. S16 separately decides whether this one card may enter development.
4. S18-S23 deliver the bounded plan and bind browser timing, API latency,
   database timing, event-loop lag, CPU/memory, queue lag, restart/error data
   and durable read-back to the same candidate and fixture. No stage may claim
   success from a metric collected on a different build, fixture or concurrency
   profile.
5. S26 can at most authorize an immutable, independently reviewed candidate;
   production sizing, deployment and live measurement remain separate owner
   decisions.

## Acceptance shape for S15

S15 must create deterministic direct and breaker cases without a live
marketplace or production system. At minimum, the cases must prove:

- a repeated before/after run for every S11 operator journey uses the same
  immutable build-under-test, fixture, concurrency profile and percentile
  method, with p95/p99 thresholds evaluated from enough samples to expose tails;
- a principal list provides its first usable page of up to 50 rows within the
  approved target, supports paging/filtering/search within the approved target,
  and retains complete access and cross-page selection across 500 orders;
- scan, confirmation and supply mutation expose a completed result or truthful
  processing state within the target, and retry, reload and read-back converge
  on one durable result without duplicate business effects;
- representative small, 155-code and 500-code generation has timely visible
  acceptance/rejection, bounded completion or durable progress, and no false
  success after timeout, worker failure, retry or restart;
- while 155-code and 500-code work runs, unrelated interactive journeys remain
  within their own thresholds and a saturated or failed worker cannot silently
  lose, duplicate or indefinitely hide an outcome;
- notification refresh and other periodic browser work increase active-journey
  p95 by no more than 20 percent, do not poll a visible browser more often than
  once per 30 seconds, and do not replace a complete working set with a partial
  client-side subset;
- a 30-minute representative load run stays within the S13 capacity envelope,
  preserves at least 20 percent steady-state memory headroom, and shows no
  restart, out-of-memory termination, unbounded queue growth or continuously
  increasing swap use; and
- every database change, if S13 proves one necessary, is backward compatible
  and covered by migration order, backfill, integrity reconciliation, restore
  rehearsal and an honest rollback boundary.

S20 must reject a candidate that hides latency behind a fake success or
indefinite spinner, improves an isolated benchmark while a complete journey
regresses, moves starvation to another queue or tenant scope, drops a durable
effect, or relaxes warehouse, authorization, tenant or marketplace invariants
to meet a timing target.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, is
required because this high-risk card has `database_change` and
`background_worker` traits. The architect receives this cut and the S11
product contract; no downstream role may treat the historical 20 August
observation as causal proof or as the post-change baseline.

This stage creates neither an architecture decision nor an implementation,
test execution, review, acceptance, Git action, deployment or release verdict.
A change that separates a local optimization from matched operator-journey
evidence, narrows complete 500-order access, or alters the approved performance
thresholds requires S12 rework before development approval.

## Verdict

`TASK_CUT_READY`: `BLG-I07-C1` keeps measurement, attributed remediation and
matched end-to-end proof together as one observable warehouse-performance
outcome, while reserving technical choices and independent challenge for S13
and S14.
