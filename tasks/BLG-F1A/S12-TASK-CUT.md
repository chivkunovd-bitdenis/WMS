# S12 TASK_CUT - BLG-F1A

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-F1A-C1`
**Title:** Fail closed when an acceptance claim lacks the real artifact for its declared evidence level and surface.

This is one atomic pipeline-control card. It must not be divided into separate
checks for test reports, API captures, database read-backs, browser evidence or
release identity: an unguarded required surface would still let a task report a
higher-level result from a lower-level substitute. The observable outcome is
complete only when every supported controller, validator and CI acceptance path
either validates the complete required real-artifact set for the declared claim
or refuses the dependent pass verdict with an actionable missing/invalid-proof
result.

## Observable contract

For a Pipeline v2 task that declares an acceptance claim, the pipeline records
the claim's evidence level and affected surface, then checks the applicable
real artifacts before the dependent acceptance verdict can pass.

1. `E0 ASSERTION_OR_INSPECTION` remains contextual information only and cannot
   close an acceptance verdict.
2. `E1 COMPONENT_EXECUTION` proves only a deterministic executed component
   boundary with its captured fixture/result; it cannot stand in for a
   consumer, journey, acceptance or production claim.
3. `E2 CONSUMER_BOUNDARY` requires the real consumer representation or
   durable read-back for the declared API, data, worker, print, mobile or
   equivalent boundary.
4. `E3 INTEGRATED_SCENARIO` requires the declared isolated end-to-end journey,
   including applicable durable effect, read-back and reload/retry.
5. `E4 INDEPENDENT_ACCEPTANCE` requires the assigned independent acceptance
   role on the declared candidate surface; an operator-visible flow requires
   the live visible-browser verdict.
6. `E5 PRODUCTION_TRACE` remains available only after separately authorized
   release/deploy work and an observed exact production artifact. No local or
   integration artifact may be labelled production proof.

Each required record must resolve to a readable allowed artifact (or an
allowed immutable external-artifact reference) and bind task/case or journey,
producer, command or run ID, fixture, environment, exact baseline SHA,
applicable digests, timestamps, result, content hash and redaction status.
Missing, empty, wrong-type, path-escaping, unreadable, foreign-task, stale,
hash-mismatched, invalidated, unsanitized or contradictory evidence leaves the
claim `NOT_PROVEN`. It must not be converted to a warning, `N/A`, a generated
success receipt, or a pass based on a lower evidence level.

The card covers pipeline-control claims only. It does not change a warehouse
operator action, marketplace contract, production data, external-system call,
deployment authorization or existing historical evidence retroactively.

## S13/S14 design boundary

S13, owned by `solution-architect`, must produce the resource graph and one
machine-enforceable plan for every public controller/validator/CI entrypoint
that can create or pass an acceptance claim. Its minimum closure artifact must:

- map each declared claim/surface to its minimum evidence level and required
  artifact types, including the union when several surfaces are affected;
- identify the authoritative evidence manifest/record, allowed storage roots
  and immutable-reference policy, canonicalization and sanitization boundary;
- define how task/case/run identity, baseline SHA, content hashes, freshness
  and invalidation are bound and checked without trusting a prose report or a
  hand-written receipt;
- state how a failed proof is represented and propagated so every dependent
  pass verdict fails closed across controller, validator and CI; and
- integrate evidence failures with BLG-F01's canonical blocker/dependency
  registry when that dependency supplies its source of truth, without
  duplicating or bypassing it.

S13 does not get to weaken the S11 proof levels, choose a production action or
trust a lower-layer artifact as a higher-layer substitute. S14 independently
falsifies the plan for bypassed entrypoints, substitute artifacts, identity and
freshness confusion, forged summaries/receipts, contradictory layers,
concurrent-task isolation and an unavailable BLG-F01 dependency.

## Acceptance cases reserved for S15

| ID | Fixture or oracle | Required result |
| --- | --- | --- |
| `BLG-F1A-AC01` | A component-only execution artifact presented for an API, integrated-scenario, independent-acceptance or production claim | The claim is `NOT_PROVEN`; the lower layer is recorded only at its actual boundary. |
| `BLG-F1A-AC02` | Valid serialized API response, durable database read-back, worker acknowledgement/read-back, print/mobile consumer result, and isolated integrated journey fixtures | Each surface accepts only its applicable declared artifact set and binds it to the exact task/run/baseline. |
| `BLG-F1A-AC03` | Required artifact path absent, empty, unreadable, directory, source file, hand-written receipt or prose success summary | The dependent pass verdict is rejected with the invalid-proof reason; no implicit `N/A` or warning pass occurs. |
| `BLG-F1A-AC04` | Artifact path that escapes the allowed evidence location, plus a valid in-root control artifact | The escaping path is rejected before use; the valid control remains usable. |
| `BLG-F1A-AC05` | Artifact from another task, case, run, fixture, environment or baseline SHA | It cannot prove the current claim, even when its content otherwise looks successful. |
| `BLG-F1A-AC06` | Changed content after recording, a declared hash mismatch, and a stale artifact after an invalidating input | Each is rejected; the claim stays `NOT_PROVEN` until fresh matching evidence is produced. |
| `BLG-F1A-AC07` | Unsanitized artifact containing a prohibited sensitive field and a sanitized equivalent | The unsanitized artifact is not admitted as proof; the sanitized equivalent can proceed only when all other bindings validate. |
| `BLG-F1A-AC08` | Conflicting artifacts for the same claim, including a successful lower layer and failed consumer/journey layer | The conflict fails closed and routes to the stage owning the disputed contract, implementation, fixture or environment. |
| `BLG-F1A-AC09` | A representative feature expected to leave a durable trace but with zero observed traces | The feature is `NOT_PROVEN`; an isolated end-to-end run with durable read-back is required, without calling this production proof. |
| `BLG-F1A-AC10` | A relevant `TODO`, `unknown until` or `not verified` marker tied to an affected capability | The acceptance packet records an explicit evidence obligation; omission cannot pass acceptance. |
| `BLG-F1A-AC11` | Paired sanitized values on both sides of a format mapping, followed by a mismatched pair | Only an exactly supported mapping is accepted; similar names or assumed normalization do not prove equivalence. |
| `BLG-F1A-AC12` | Independent acceptance and release fixtures, including a local candidate and a separately authorized production-trace fixture | Local evidence may satisfy only its declared non-production level; `E5` requires exact deployed identity and observed runtime trace. |
| `BLG-F1A-AC13` | Valid manifest and real artifacts across all applicable surfaces for one multi-surface task | The public controller/validator/CI path accepts the verdict only after the full union of requirements validates. |

S15 must turn every row into deterministic, isolated cases with an explicit
fixture/reset, public entrypoint, expected receipt/verdict and evidence output.
It must include both pass and fail-closed paths; it may not use live WB/Ozon,
production data, secrets or a self-authored receipt as its test oracle.

## Implementation and later-gate boundary

S18 may implement only the S13/S14-approved enforcement and the S15/S16-
approved cases needed for `BLG-F1A-C1`. It must not broaden into deployment,
production tracing, credential handling, a new operator interface, external
marketplace traffic, or a second blocker registry.

S20 review must reject any path that accepts a verdict before validating the
complete union of required evidence, trusts an internal return/prose/receipt as
the underlying artifact, permits path escape or foreign/stale/hash-mismatched
evidence, or treats a higher evidence level as inferred from a lower one.
S25 must independently execute the approved public pipeline meta-test surface;
it cannot use the S11 Product author, S12 BA author, or an internal function
call as the accepting authority.

## Handoff and exclusions

- **Next stage:** `S13 ARCHITECT_PLAN`, role `solution-architect`, required by
  the `critical` `pipeline_change` risk profile.
- **S16 packet condition:** Product receives this card, S11, S13/S14 and S15
  artifacts. A material change to the evidence contract or this card
  invalidates the later Product-before-Dev decision.
- **Not produced by S12:** implementation, controller/CI changes, tests,
  commit, push, merge, deploy, production trace or final acceptance.

## Verdict

`TASK_CUT_READY`: `BLG-F1A-C1` keeps the whole observable fail-closed proof
outcome atomic, reserves complete positive and negative acceptance coverage,
and hands the enforcement design to independent architecture stages.
