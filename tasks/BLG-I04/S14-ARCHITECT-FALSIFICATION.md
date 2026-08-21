# S14 ARCHITECT_FALSIFICATION - BLG-I04

## Binding

- Task: `BLG-I04`
- Card: `BLG-I04-C1`
- Stage: `S14 ARCHITECT_FALSIFICATION`
- Role: `pipeline-reviewer`
- Agent: `codex-pipeline-reviewer-blg-i04-s14`
- Controller baseline: `69c271678782d7dcfa39df97cd905cbee1678727`
- Inspected checkout: `a6a2a40ce02530a919d4ea979e4f3322591a6a49`
- Product contract SHA-256:
  `2d90b8f48d3a62ad1afd7d877b0769fb895dd7476d25a6f683480663644d7fc9`
- Task cut SHA-256:
  `b9d7956b694dfe27aa3a0f47f5e7ab8ebc731c46280bf3966ff6e6a2c19b9a8c`
- Reviewed S13 plan SHA-256:
  `58170e3b7056956c02e177a9b824358f825b2a9ba75021389412f4a9ae45a924`

## Verdict

`BLOCKED` with arbiter decision `REPLAN`.

The S13 plan survives the selection-count, multi-page arithmetic, inclusive
100-sheet threshold, stale-confirmation and truthful-wording attacks. It does
not yet define an executable durable transaction boundary for the idempotent
mutating print operation, and it accepts unbounded browser page materialization
without a resource-safe execution contract. Both gaps can cause an uncertain
or unusable print run, so `ARCH_REVIEW_PASSED` is not permitted. S15 and
development must not start until S13 is revised and independently reviewed
again.

## Independent model built before reading S13

The current FBS bulk path passes selected order IDs and `layout_json` from
`FfFbsSupplyWorkspace` through `MarkingPrintDialog` to
`POST /operations/fbs-supplies/{supply_id}/order-print-tape`. That endpoint has
no idempotency key. Its service may obtain QR assets, allocate or reuse marking
codes, mark them printed and send order metadata to WB before the route commits
the database transaction. The React `busy` flag therefore cannot be the
exactly-once boundary for double activation, timeout or process death.

The independent safe model required:

1. one canonical plan and one final multiplication edge, with selected order
   count never used as copies;
2. one inclusive backend-owned threshold and a confirmation bound to the exact
   current plan;
3. a committed operation intent before the first local or external side effect;
4. explicit durable phases that make every crash point either replayable from
   the same recorded material or fail closed without another mutation;
5. one exact page manifest or equivalent count postcondition shared by
   preflight, accepted response and renderer; and
6. a resource-safe policy for every accepted copies value, including very
   large but numerically valid totals.

S13 independently reaches items 1, 2 and the count-postcondition portion of
item 5. The following attacks remain unresolved.

## Blocking findings

### F1 - The idempotency journal has no durable phase/commit boundary

Severity: critical. Finding type: `PLAN | IDEMPOTENCY | EXTERNAL`.

S13 proposes reusing `fbs_wb_operations`, creating or reading an operation
before order mutation, locking it, and reconstructing a same-key result. It
does not specify which state is committed before each external or local
effect, which transaction/session owns that commit, or how the exact code and
asset IDs become durable before the effect can escape.

That omission leaves this concrete crash path:

```text
insert/flush pending operation in the request transaction
-> allocate/mark a code or send WB metadata
-> process dies before the route-level commit
-> database rollback removes the pending intent and local response mapping
-> same idempotency key appears new and may repeat the mutation
```

The existing unique key prevents a second row only after the first intent is
durably committed. A `flush`, row lock or request hash inside the same
uncommitted route transaction does not survive the crash. Conversely, merely
committing the operation first is insufficient unless the plan defines how a
pending operation reserves the exact order/code/asset material, how a lost WB
metadata response is reconciled, and how a same-key concurrent request returns
the identical result without holding PostgreSQL row locks across HTTP.

Minimum closure:

- define a concrete persisted phase machine and transaction boundaries, for
  example durable intent, durable material reservation, external-pending,
  external-confirmed/unknown and response-ready;
- identify the exact operation summary fields or existing rows that bind every
  selected order to the code/asset IDs needed to reconstruct the accepted
  response, without storing raw CIS or label bytes in the journal;
- define same-key concurrent insert/lock behavior, cancellation and process
  death before and after every commit and external call;
- prove that no database row/advisory lock spans WB HTTP and that an unknown
  external outcome never triggers a blind second metadata write or code
  allocation; and
- if existing rows cannot represent those phases safely, return to S02/S13,
  add the required `database_change` or worker trait, and plan its receipts
  instead of deferring the decision to S18.

The required breaker must kill the process after intent creation, after code
reservation, immediately after WB accepts metadata, after local confirmation
and before response delivery. Same-key sequential and concurrent retries must
produce one durable intent, the same recorded material and no repeated
external emulator effect.

### F2 - Accepted large totals can exhaust the browser before printing

Severity: high. Finding type: `PLAN | PRINT | VOLUME`.

S13 intentionally accepts every positive whole-number copies value whose total
fits a JavaScript safe integer and forbids a hard maximum. The renderer then
builds `printSections` with length `acceptedPlan.totalSheets` before invoking
the browser print dialog. Numeric exactness does not make that operation
resource-safe: a value can be a valid safe integer while requiring gigabytes
of DOM/string/array memory, freezing or terminating the operator tab before a
usable print job exists. The 100-sheet confirmation only records intent; it is
not a capacity control.

This conflicts with the Product promise that a confirmed legitimate large run
is allowed and with the S14 requirement to assess unusual print volume. S13
has no bounded generation, batching, streaming, browser/printer capability
preflight, or explicitly approved operational cap. Its S15 list tests integer
overflow but not a large, representable total that exceeds renderer capacity.

Minimum closure:

- choose a resource-safe generation strategy that preserves the exact visible
  total and never silently prints a partial batch, or return to S11 for an
  explicit Product decision on a supported operational limit/batching journey;
- define cancellation, failure and retry semantics between batches if batching
  is selected, including whether one idempotency identity covers the whole run;
- make the renderer avoid allocation proportional to an unbounded total before
  capacity is known; and
- add deterministic volume cases for a confirmed large normal run and a much
  larger but numerically valid run, proving bounded memory/work, truthful error
  state, zero hidden clamping and no unexpected `window.print` call.

## Checks that survived falsification

- `selectedOrderCount`, `sheetsPerOneCopy` and
  `copiesPerRequiredLabel` are separated, and the final formula multiplies the
  base page count exactly once.
- A ten-order one-page default run is ten sheets, while ten explicit copies is
  100 sheets; the latter requires confirmation.
- The server-owned threshold is correctly inclusive at 100 and cannot be
  bypassed by a direct commit request.
- The plan fingerprint binds selection, normalized layout, partial/reprint/QR
  flags, outer copies and total; stale modal and stale preflight responses are
  required to fail closed.
- Renderer page-count assertions prevent missing QR/code/label material from
  silently opening a print window with fewer pages than the accepted total.
- Close/reopen resets outer copies to one, and request/browser success wording
  remains distinct from physical printer evidence.
- The proposed S15/S22 matrix covers default, multi-page, 99/100/101,
  invalid input, no selection, cancel, stale confirmation, double activation,
  unknown outcome, tenant isolation and printer/device evidence. It must retain
  those lanes and add the F1/F2 breakers above.

## Scope and safety judgement

This stage reviewed architecture and current local code only. It performed no
implementation, test execution, migration, commit, push, merge, deployment,
printer operation, production request, secret access or live WB/Ozon call. It
did not modify unrelated worker artifacts.

## Required replan artifact and handoff

Return to `S13 ARCHITECT_PLAN`, owned by `solution-architect`. The revised
`tasks/BLG-I04/S13-ARCHITECT-PLAN.md` must close F1 and F2 with:

1. an executable durable idempotency phase/transaction model across local and
   WB effects;
2. exact same-key response reconstruction and process-death/concurrency cases;
3. a resource-safe very-large-run strategy or an approved Product contract
   revision; and
4. the updated S15/S22 coverage and resource graph, including any newly
   required trait or migration.

After controller resume and a new S13 receipt, S14 must be dispatched to a new
independent reviewer. Until then, S15 and all development stages remain
blocked.
