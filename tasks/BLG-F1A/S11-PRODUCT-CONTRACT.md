# S11 PRODUCT_CONTRACT_APPROVAL - BLG-F1A

## Product decision

Product approves a fail-closed evidence contract for Pipeline v2. A task may
claim only the result proved at the actually observed boundary. A developer
report, code inspection, internal function result, green lower-layer test,
local build or screenshot may support an investigation, but none may be
promoted into proof of a higher layer.

The operational outcome is that every acceptance claim is backed by a real,
readable artifact from the layer named in that claim. Missing, stale,
unreadable, hash-mismatched or lower-layer evidence leaves the claim
`NOT_PROVEN` and blocks the dependent pass verdict. The pipeline must not turn
absence of evidence into success, a warning or an implicit `N/A`.

This change protects operators and release owners from starting work on a
process that was verified only in code or inside one service. It introduces no
new warehouse action, confirmation, screen, status or marketplace operation.

## Approved evidence levels

The following levels describe increasing observed scope. A higher level must
include or link the applicable lower-boundary results; it cannot be inferred
from them.

1. `E0 ASSERTION_OR_INSPECTION` - prose, code reading, static analysis,
   internal return value or unexecuted plan. Useful context only; never an
   acceptance result.
2. `E1 COMPONENT_EXECUTION` - an executed deterministic component or service
   test with a named fixture and captured result. It proves only that component
   boundary.
3. `E2 CONSUMER_BOUNDARY` - the real consuming boundary has produced and
   returned the expected representation: for example serialized HTTP response,
   committed database state read through the intended consumer, acknowledged
   worker effect, generated print artifact or mobile-consumer response.
4. `E3 INTEGRATED_SCENARIO` - the complete declared journey ran on an isolated,
   pinned baseline through all applicable boundaries, including durable effect,
   read-back and reload/retry where the behavior mutates state.
5. `E4 INDEPENDENT_ACCEPTANCE` - the declared acceptance role independently
   exercised the exact candidate artifact on the required surface. For an
   operator-visible flow this is a live visible-browser walkthrough; for this
   pure pipeline change it is independent execution of the pipeline meta-test
   surface through supported public entrypoints.
6. `E5 PRODUCTION_TRACE` - the explicitly authorized exact artifact was
   observed in production with its declared runtime signal and threshold. Only
   this level can support a claim that a result is deployed and working in
   production.

The words `works`, `passed`, `accepted`, `deployed` and `production-proven` must
name the corresponding level and surface. In particular, `E1` does not imply
an HTTP response, `E2` does not imply an operator journey, `E3` does not imply
Product acceptance, and a local `E4` candidate does not imply `E5`.

## Minimum proof by affected surface

- A component-only internal change requires its executed component artifact
  and the highest real consumer boundary affected by that component. A returned
  service dictionary alone cannot close a consumer-facing claim.
- An API contract change requires the actual route-level serialized response
  after authorization, response-schema validation and error mapping. Direct
  service output or an HTTP status without the response body is insufficient.
- A database or data-policy change requires mutation/transaction evidence,
  invariant totals and durable read-back through the intended consumer.
  A write log or row count alone cannot prove the consuming workflow.
- A background-worker change requires enqueue, queue ownership, worker
  acknowledgement/effect, durable state and consumer read-back, including the
  applicable retry, duplicate and outage behavior.
- An operator-visible UI mutation requires the applicable API/data/worker
  chain plus independent live-browser acceptance on the exact candidate, with
  read-back and reload. A screenshot, DOM assertion or Playwright result alone
  cannot provide the Product verdict.
- Print, scanner and mobile changes require the generated artifact or consumer
  response and the approved device or emulator/sandbox surface where the
  contract depends on it. A preview or backend payload alone is insufficient.
- An external-system claim requires a versioned contract and emulator or
  separately authorized sandbox evidence. No test may silently use live
  WB/Ozon as its proof source.
- A release or deploy claim requires one full Git SHA linked to immutable
  artifact digests, runtime identity and, when frontend is affected, the exact
  browser-loaded asset. Build output, branch name, health response or local URL
  alone is insufficient.
- A pipeline-control change requires real files from meta-tests that invoke the
  supported controller/validator/CI entrypoints and cover both pass and
  fail-closed paths. Calling an internal Python function or presenting a
  hand-written receipt is not evidence that the pipeline enforces the rule.

When a task affects several surfaces, its minimum level is the union of all
applicable rows, not the cheapest single row. Each impact/resource-graph edge
must have evidence or a separately approved, hash-linked reason why that edge
is not applicable.

## Real artifact contract

Every required proof must resolve to a real file or immutable external-artifact
reference allowed by the evidence policy. Its machine-readable record must
identify the task, case or journey, producer role, command or run id, fixture,
environment, exact baseline SHA and applicable artifact digests, start/finish
time, result, content hash and redaction status. A prose summary may explain the
artifact but cannot replace it.

The controller must fail closed when a required artifact path is absent, is not
a regular readable artifact of the declared type, resolves outside the allowed
evidence location, has a different content hash, belongs to another task/run,
predates an invalidated input, lacks the required baseline identity or fails
sanitization. A self-authored placeholder, copied receipt, empty file, source
file, mock return value or success text without the underlying result is not a
valid substitute.

Evidence remains proportional to the claim. Screenshots prove visible state;
structured HTTP artifacts prove serialized API output; sanitized database
artifacts prove queried durable state; runner reports prove executed cases;
browser acceptance proves the observed operator journey; exact SHA and digest
records prove artifact identity. No one artifact type is treated as universal
proof.

## Unproven and contradictory signals

- If an existing feature is expected to leave a durable operational trace but
  the representative history contains zero such traces, the feature is marked
  `NOT_PROVEN`, not `working`. Acceptance requires an isolated end-to-end run
  that produces the expected trace and read-back. This does not authorize
  production-data access or allow a synthetic run to be called production
  proof.
- Warnings such as `unknown until`, `not verified`, `deliberately not
  implemented` and relevant `TODO` comments become explicit evidence
  obligations for the affected capability. They cannot be silently omitted
  from the acceptance packet.
- Format mappings are proved with paired, sanitized representative values at
  both sides of the boundary, such as scan-to-database, file-to-record or
  marketplace-response-to-model. Similar names or assumed normalization are
  not proof of equivalence.
- Contradictory artifacts fail closed and route to the stage that owns the
  disputed contract, implementation, fixture or environment. The strongest
  convenient artifact must not overwrite a conflict.

## Dependency and downstream boundaries

`BLG-F01` owns the shared registry of business blockers and dependency
conditions. BLG-F1A must integrate its evidence failures with that canonical
registry once the dependency is available, while retaining its own rule that
missing required proof blocks the dependent verdict. The dependency does not
allow either task to duplicate, bypass or silently invent the other's source
of truth.

S12 may cut vertical cards by evidence surface, but every card must preserve an
observable claim and its complete minimum proof. S13 and S14 must determine and
falsify the machine enforcement design, artifact-type validation, hash and
freshness linkage, invalidation behavior, role separation and safe handling of
concurrent tasks. This S11 artifact does not choose those mechanisms.

S15 must cover at least lower-layer substitution, missing/empty/wrong-type
files, path escape, stale or foreign-task artifacts, hash mismatch,
invalidated baseline, forged summaries/receipts, contradictory layers, zero
operational traces, warning-comment obligations, sanitized paired-value format
mismatch and the valid path for each affected surface. S25 must independently
prove the pipeline meta-test acceptance surface through public entrypoints; it
must not accept this Product author as the artifact approver.

## Out of scope and authorization

This contract does not implement schemas, validators, storage, CI, controller
logic, test runners or UI. It does not change an operator workflow, inspect or
mutate production data, call live WB/Ozon, deploy, access secrets, commit, push,
accept implementation or provide final independent acceptance.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: Pipeline v2 may claim only the layer and surface
proved by real, hash-linked, sanitized artifacts from the exact task, run and
baseline. Missing or lower-layer evidence fails closed, while warehouse
operator behavior remains unchanged.
