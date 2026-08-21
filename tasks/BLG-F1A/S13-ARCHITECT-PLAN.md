# S13 ARCHITECT_PLAN - BLG-F1A

## Verdict

`ARCH_PLAN_READY`

BLG-F1A remains one atomic critical control-plane card. The implementation must
introduce one evidence decision used by every public path that can record or
rely on an acceptance claim. A pass receipt is emitted only after the complete
union of evidence obligations for the claim has been resolved to real,
readable, hash-matching artifacts from the exact task, run and baseline.

The design does not infer a higher evidence level from a lower one. It does not
treat a stage receipt, prose summary, internal return value, source file,
successful status code or mutable external URL as the underlying proof.

## Bound inputs and observed baseline

- Product contract:
  `tasks/BLG-F1A/S11-PRODUCT-CONTRACT.md`, SHA-256
  `ccffae1e18b69d17c71a14c7d02561f62eeeba293c5dc660872c5c445e8bc4c0`.
- Atomic task cut:
  `tasks/BLG-F1A/S12-TASK-CUT.md`, SHA-256
  `0d4ce399b81b94578b8e84e009640762eda99f246374d1e2502eefd16531139c`.
- Controller task baseline: `69c271678782d7dcfa39df97cd905cbee1678727`.
- S13 observation checkout: `a6a2a40ce02530a919d4ea979e4f3322591a6a49` on
  `codex/wms-pipeline-unified-v2-20260820`.
- Declared acceptance surface for this pure control-plane card:
  `pipeline_meta_tests`.

The current implementation has five material gaps that the future Dev card
must close:

1. `pipeline/evidence.schema.json` is permissive, has
   `additionalProperties: true`, and is not loaded by the controller's schema
   validator.
2. `pipeline/controller.py` creates stage receipts with empty `output_hashes`;
   `advance` accepts a pass verdict without an evidence manifest or artifact.
3. `validate` rechecks receipt structure and local hashes, but does not resolve
   or rehash the real files underlying a result.
4. `case-result` and `record-release-proof` accept result strings without a
   required runner/release artifact, while `next`, `packet` and `report` cannot
   distinguish `PROVEN` from `NOT_PROVEN`.
5. CI runs a regex secret scan over evidence, but has no shared evidence-policy
   validator and no claim-to-artifact coverage check.

These facts describe the observed baseline only. They do not authorize a
release, production check, live marketplace call or trust in current receipt
signatures beyond the managed local-controller boundary.

## Architectural invariants

1. **One policy decision.** Controller mutation paths and CI call the same pure
   evidence resolver. No entrypoint keeps its own evidence matrix.
2. **Obligations, not level numbers.** Evidence levels are labels over observed
   boundaries. The resolver computes a set of obligations from the claim,
   affected surfaces, traits and verdict. A numerically higher level does not
   waive a missing applicable lower-boundary artifact.
3. **Artifact before receipt.** The controller validates opened artifact bytes,
   records their hashes and the policy/input binding, and only then creates the
   pass receipt. A receipt is an index of a completed decision, not proof by
   itself.
4. **Fail closed.** Missing, empty, unreadable, wrong-type, escaping, symlinked,
   foreign, stale, changed, unsanitized or contradictory evidence yields
   `NOT_PROVEN` or `CONTRADICTED`. It never becomes a warning, pass or implicit
   `N/A`.
5. **Exact identity.** Every accepted artifact binds the task, claim, stage,
   run, case/journey, fixture, environment, producer role binding, baseline
   SHA, applicable artifact digests, input binding hash and evidence-policy
   hash.
6. **Independent acceptance.** E4 artifacts bind the controller-issued
   accepting role and candidate identity. The producer of the candidate cannot
   approve it. For operator flows the only E4 surface is a live visible-browser
   walkthrough; for BLG-F1A it is independent execution of public pipeline
   entrypoints and meta-tests.
7. **Production language is reserved.** E5 requires separately authorized
   exact-artifact deployment and observed runtime trace. S13, local tests,
   integration tests and S25 cannot generate E5.
8. **No retroactive invention.** Historical receipts remain historical. They
   are not backfilled with evidence levels or synthesized manifests. Any new
   dependent acceptance claim must satisfy the policy version bound to that
   attempt.

## Machine contracts

### Evidence policy

Add `pipeline/evidence-policy.yml` in the JSON subset of YAML and
`pipeline/evidence-policy.schema.json`. The policy is versioned and hashed
independently of `pipeline/pipeline.yml` so evidence changes cannot be hidden
inside a prose edit and do not silently rewrite the pipeline hash of every
in-flight task.

The policy contains:

- stable level IDs `E0` through `E5`, their allowed claim scope and whether
  they can support a pass verdict;
- stable surface IDs and their required obligation sets;
- artifact types, allowed media types and required metadata per type;
- claim-bearing verdicts and their minimum level/surface rules;
- trait-to-surface additions and union semantics;
- allowed repository roots and deny-by-default immutable-reference adapters;
- invalidation inputs, role incompatibilities and contradiction rules;
- stable failure reason codes and owning/resume-stage mappings.

`scripts/ci/check_pipeline_contract.py` validates policy completeness against
the stages, pass verdicts, traits and acceptance surfaces already declared by
`pipeline/pipeline.yml`. Any declared acceptance surface without a policy row
is a CI error. This card does not need to change the total stage order or weaken
the existing pipeline contract.

### Evidence levels and minimum surfaces

| Claim surface | Minimum observed boundary | Mandatory artifact obligations |
| --- | --- | --- |
| `component` | E1 | deterministic runner report, named fixture/result and real consumer boundary when one is affected |
| `api` | E2 | route-level serialized response after authorization, schema validation and error mapping |
| `database` | E2 | transaction/mutation result, invariant totals and durable read-back through the intended consumer |
| `worker` | E3 | enqueue, queue ownership, acknowledgement/effect, durable write, consumer read-back and applicable retry/duplicate/outage trace |
| `ui_operator` | E4 | applicable API/data/worker chain, exact candidate identity, independent live visible-browser journey, read-back and reload |
| `print` | E2 or E4 when human/device acceptance is declared | generated artifact plus approved printer/device or emulator evidence required by the contract |
| `mobile` | E2 or E4 when device acceptance is declared | versioned consumer response plus approved device/emulator evidence |
| `external_system` | E2/E3 | versioned contract and local emulator or separately authorized sandbox result; live WB/Ozon is never an implicit test source |
| `release_candidate` | E4 | full Git SHA, tree/candidate identity, immutable artifact digests and independent acceptance on that candidate |
| `production_runtime` | E5 | separate authorization, exact promoted identity and observed production trace with declared denominator/threshold |
| `pipeline_control` | E4 | real meta-test files produced by supported controller/validator/CI entrypoints, including pass and fail-closed results |

A multi-surface task receives the set union of all applicable obligations. The
resolver reports each obligation separately; it never selects the cheapest row
or accepts a universal screenshot/test report.

### Evidence manifest and artifact records

Strengthen `pipeline/evidence.schema.json` into the strict schema for
`docs/evidence/<task-id>/manifest.json`. The manifest is the authoritative task
index and contains immutable-by-hash run records rather than prose summaries.
Unknown contract fields are rejected after schema-version migration.

Each claim record contains at least:

- `claim_id`, `stage_id`, `verdict`, `level`, `surfaces`, `result`;
- `task_id`, `run_id`, `case_ids` or `journey_ids`;
- `policy_version`, `policy_hash`, `pipeline_hash`, `source_hash`;
- `input_binding_hash`, `baseline_sha`, candidate/artifact digests;
- computed `required_obligation_ids` and resolved artifact IDs;
- producer and acceptance role bindings, started/finished timestamps;
- `PROVEN | NOT_PROVEN | CONTRADICTED`, reason codes and minimum closure.

Each local artifact record contains its relative path, artifact type, media
type, byte size and SHA-256 plus the same task/run/baseline identity. The
artifact itself lives under
`docs/evidence/<task-id>/artifacts/<run-id>/`. Source files, stage receipts and
the manifest cannot be listed as their own underlying proof.

An external artifact reference is disabled by default. A policy adapter may
allow only a content-addressed URI with an immutable digest, size, provider,
retention and verifier result. Branch URLs, `latest`, mutable CI links and an
unresolved remote reference are `NOT_PROVEN`. BLG-F1A's own S25 acceptance uses
repository artifacts and needs no remote account or secret.

### Sanitization boundary

An artifact is admitted only with `REDACTION_VERIFIED` bound to its exact
content hash. Structured artifacts use allowlisted fields and reject request
headers, cookies, authorization data, environment dumps and unclassified raw
bodies. Screenshots or other binary artifacts require the declared binary/OCR
sanitization adapter; absence of that adapter is not a reason to accept the
file. The existing secret scanner remains a second CI defense, not the source
of the redaction verdict.

## Shared resolver and validation algorithm

Add a pure module `pipeline/evidence.py`, used by the controller and CI. It
returns a typed `EvidenceDecision` and performs the following order:

1. Load and validate the evidence policy and strict manifest; bind their
   SHA-256 values before evaluating claims.
2. Derive affected surfaces from controller state, task traits, the declared
   claim and verdict; compute the complete obligation union from policy.
3. Reject an omitted applicable surface. `N/A` requires a hash-linked,
   independently produced `NOT_APPLICABLE_VERIFIED` record; free text is not
   sufficient.
4. Resolve each local path lexically and physically under the exact task/run
   root. Reject absolute paths, `..`, path escape, directories, sockets,
   devices and any symlink in the path chain.
5. Open the file fail-closed, require a non-zero regular file, read the bytes
   once, and compute size/hash from that opened descriptor. Validate type and
   media type from policy rather than filename alone.
6. Match task, run, case/journey, fixture, environment, role binding, policy,
   source, pipeline, baseline and candidate identity to controller truth.
7. Match freshness by `input_binding_hash`, not timestamp alone. An artifact
   produced before an invalidating input cannot be reused even if copied or
   renamed later.
8. Validate exact redaction attestation and artifact-type metadata. A status
   string without the bound verifier result is invalid.
9. Evaluate all artifacts for the claim. Any required failed or contradictory
   artifact makes the claim `NOT_PROVEN` or `CONTRADICTED`; a convenient
   success at another layer cannot overwrite it.
10. Return a deterministic decision with sorted obligation IDs, artifact
    hashes, reason codes, owner/resume stage and minimum closure. The receipt
    stores this decision hash and manifest hash; `validate` and CI recompute it.

The controller serializes evidence validation and receipt/state publication
under its controller lock. Hashing opened bytes removes path-switch ambiguity
during validation. Later mutation is still detected because every subsequent
validation reopens and rehashes the artifact.

## Public entrypoint parity

| Entrypoint | Required behavior |
| --- | --- |
| `advance` | Accept `--evidence-manifest` for claim-bearing verdicts, run the shared resolver before receipt creation, reject non-PROVEN decisions, and record manifest/decision hashes in non-empty `output_hashes`. |
| `case-result` | A green result that contributes to S22 requires a real runner artifact and exact case/run binding; a bare `green` string is not proof. |
| `record-release-proof` | Commit, pushed ref and check strings are projections only. Release/candidate claims require the manifest's immutable identity artifacts and cannot be promoted by this command alone. |
| `validate` | Recompute every recorded evidence decision from current bytes and policy; fail on missing, changed, stale, foreign, unsanitized or contradictory inputs. It does not silently repair state. |
| `close` | Reuse full state/evidence validation and reject `IMPLEMENTATION_DONE`, `READY_FOR_RELEASE` or `DONE` when the applicable claim union is not PROVEN. |
| `next` / `packet` | Project the current claim level, missing obligations, reason codes, minimum closure and dependency status. They cannot create proof. |
| `report` | Use only recomputed/proven claim projections and name exact level/surface. Never render `works`, `accepted`, `deployed` or `production-proven` from a lower layer. |
| `dispatch`, night runner and wave driver | Consume controller packets only. They do not implement a second evaluator or auto-author evidence. |
| CI | Run `scripts/ci/check_pipeline_evidence.py`, which imports the shared resolver, validates tracked task snapshots/receipts/manifests and fails on the same fixture for the same reason as controller `validate`. |

`pipeline/receipt.schema.json` gains a required evidence-decision reference for
claim-bearing pass verdicts. `pipeline/task-state.schema.json` gains the bound
evidence policy version/hash and typed claim decisions. Backward-compatible
schema fields may remain optional only for receipts created before the policy's
recorded effective point; they cannot be interpreted as E1-E5 proof.

## Failure, invalidation and recovery

Stable reason codes include at least:

- `EVIDENCE_LEVEL_SUBSTITUTION`;
- `EVIDENCE_MISSING`, `EVIDENCE_EMPTY`, `EVIDENCE_UNREADABLE`;
- `EVIDENCE_WRONG_TYPE`, `EVIDENCE_PATH_ESCAPE`, `EVIDENCE_SYMLINK`;
- `EVIDENCE_FOREIGN_IDENTITY`, `EVIDENCE_STALE_INPUT`;
- `EVIDENCE_HASH_MISMATCH`, `EVIDENCE_UNSANITIZED`;
- `EVIDENCE_CONTRADICTED`, `EVIDENCE_SURFACE_OMITTED`;
- `EVIDENCE_POLICY_MISMATCH`, `EVIDENCE_BASELINE_MISMATCH`.

A failed new advance writes an append-only decision event but no pass receipt.
Producer-fixable absence or mismatch stays typed rework at the owning stage.
True access, environment, security, baseline or oracle conditions may enter
typed `WAITING` only through the canonical blocker decision. The packet always
names the exact missing obligation and minimum closure artifact.

If a previously accepted artifact changes or its input binding is invalidated,
the controller removes the owning claim-stage receipt and all dependent
receipts, restores `last_valid_receipt` to the last unaffected receipt, and
returns to the earliest owning stage. Earlier unrelated receipts and artifacts
remain auditable. CI reports the same invalidation requirement but does not
mutate controller state.

Recovery replays only hash-linked evidence decisions from the journal. It
revalidates current bytes before recreating a projection; it never reconstructs
proof from receipt text.

## BLG-F01 dependency boundary

`BLG-F01` is currently at S13 and has no accepted S13/S14 architecture contract.
It owns the canonical blocker/dependency registry and lifecycle. BLG-F1A must
not edit `docs/product/blocks.json`, invent `BLK-*` identities, create a second
registry or embed registry storage rules in the evidence resolver.

BLG-F1A defines only the payload it needs to hand to the future canonical
decision adapter:

```text
EvidenceFailure {
  task_id, claim_id, stage_id, policy_hash, input_binding_hash,
  reason_codes[], obligation_ids[], artifact_hashes[],
  owner_role, resume_stage, minimum_closure_artifact
}
```

The adapter must return a canonical blocker/dependency decision and stable
reference. Until BLG-F01 S13/S14 provides an accepted schema, authority and
atomic lifecycle API, S18 may implement and test the pure evidence resolver but
must not merge a competing persistence or unblock path. The exact BLG-F01 plan
hash and review receipt become a required input to BLG-F1A S16/S17 for the
integration portion. If the contracts conflict, return BLG-F1A to S13; do not
guess or bypass the dependency.

This dependency is a controlled implementation gate, not an S13 blocker: the
evidence policy, resolver, failure payload and all non-registry boundaries can
be independently falsified now.

## Resource graph and future S18 write set

The Atomic Dev card takes one exclusive control-plane lock over the complete
write set. The card is not split into separate schema/controller/CI deliveries.

| Resource | Planned responsibility |
| --- | --- |
| `pipeline/evidence-policy.yml` | Versioned levels, surfaces, obligations, artifact types, verdict rules and failure routes. |
| `pipeline/evidence-policy.schema.json` | Strict policy schema. |
| `pipeline/evidence.schema.json` | Strict task manifest, claim and artifact-record schema. |
| `pipeline/evidence.py` | Shared pure resolver, safe file opening, identity/hash/freshness/contradiction checks. |
| `pipeline/receipt.schema.json` | Evidence decision and non-empty output-hash contract for claim-bearing receipts. |
| `pipeline/task-state.schema.json` | Evidence-policy binding and typed claim decision projection. |
| `pipeline/controller.py` | Entrypoint enforcement, atomic receipt ordering, invalidation and packet/report projection. |
| `scripts/ci/check_pipeline_contract.py` | Policy/schema completeness and stage/surface parity. |
| `scripts/ci/check_pipeline_evidence.py` | CI adapter over the shared resolver and tracked snapshots. |
| `scripts/ci/check_pipeline_evidence_secrets.py` | Secondary content scan aligned with the strict artifact inventory. |
| `scripts/ci/check_pipeline_metatests.py` | Public-entrypoint pass/fail, tamper, stale, contradiction and concurrency metatests. |
| `.github/workflows/ci.yml` | Mandatory evidence-policy/evidence validation gate. |

Read dependencies, not owned writes:

- `pipeline/pipeline.yml` for stage, trait and acceptance-surface declarations;
- `docs/process/PIPELINE-RU.md` sections 20, 34-36 and 42;
- `docs/product/blocks.json` and the future accepted BLG-F01 adapter contract;
- `scripts/pipeline/run.py`, `dispatch.py`, `night_runner.py` and
  `wave_driver.py`, which remain thin public consumers unless S14 proves a
  bypass requiring a scoped replan;
- existing task receipts and manifests as negative migration fixtures only.

Canonical locks are at least:

- `control-plane:evidence-policy`;
- `control-plane:evidence-resolution`;
- every file in the write-set table;
- `contract:blg-f01-blocker-adapter` once its accepted hash exists;
- `ci:pipeline-meta-tests`.

Concurrent task evidence never shares a writable run directory. Discovery of a
required write outside this set returns to S13 before scope expansion.

## Implementation and gate order

1. **S14 architecture falsification.** Attack entrypoint bypasses, obligation
   union, policy drift, path/symlink handling, role confusion, mutable external
   refs, TOCTOU, contradiction handling, invalidation and the unavailable
   BLG-F01 contract.
2. **S15 cases.** Turn AC01-AC13 into deterministic public-entrypoint cases and
   add parity, race and recovery breaker lanes. Cases use temporary isolated
   evidence roots and no live external system.
3. **S16 Product before Dev.** Approve the exact S11/S12/S13/S14/S15 hashes.
   The packet must include the accepted BLG-F01 architecture/review hash or an
   explicit typed dependency hold for the integration portion.
4. **S17 workspace.** Acquire the complete resource lock and pin the policy,
   controller, CI and BLG-F01 adapter baselines.
5. **S18 implementation.** Deliver the strict policy/schema, shared resolver,
   controller integration and CI adapter atomically. No production or
   marketplace action is part of development.
6. **S19-S22 independent binding, review and execution.** Bind every AC case to
   public CLI/CI entrypoints; review authority and path handling; run all
   positive and fail-closed cases on isolated filesystems.
7. **S23 immutable integration candidate.** Record full integration SHA, tree
   hash and artifact digests. Rebuild/rebase invalidates S25 evidence.
8. **S25 independent internal acceptance.** A separate acceptance identity runs
   the supported controller CLI and CI evidence checker against the exact
   candidate and preserves raw structured outputs under the manifest.
9. **S26 release authorization.** Without separate production authority the
   honest result is `READY_FOR_RELEASE`. BLG-F1A does not authorize S27/S28.

## Required S15/S22 architecture cases

S15 must preserve AC01-AC13 from S12 exactly and add these architecture-level
checks:

- identical fixtures passed through `advance`, `validate`, `close`,
  `case-result`, `record-release-proof` and CI produce the same decision code;
- path escape through `..`, absolute path and symlinked parent/file is rejected;
- file replacement during/after validation cannot change the bytes bound to a
  pass receipt and is caught on revalidation;
- two tasks with identical-looking artifacts cannot consume one another's
  file, manifest, run or role binding;
- policy or input-hash change invalidates only the dependent claim chain;
- contradictory lower/higher layers fail regardless of ordering;
- historical unbound receipts are not relabelled as proven;
- mutable or unavailable external references fail closed;
- controller restart restores the evidence decision from journal and rehashes
  current bytes before projecting it;
- a missing BLG-F01 adapter cannot create a second blocker registry or
  self-authorized unblock path.

The valid multi-surface fixture must prove the complete union and preserve a
manifest, artifact bytes, controller output, revalidation output and CI output.
Tests of `pipeline/evidence.py` alone are component evidence and cannot satisfy
S25.

## S25 acceptance package

The exact S23 candidate must contain a sanitized manifest with:

- public `run.py advance` success for a complete valid evidence set;
- public fail-closed outputs for representative substitution, missing file,
  path escape, foreign task, stale input, hash mismatch, unsanitized content
  and contradiction cases;
- `run.py validate` revalidation of the same candidate artifacts;
- `check_pipeline_evidence.py` CI-equivalent result over the same fixtures;
- proof that the pass receipt contains non-empty manifest, policy, input and
  artifact decision hashes;
- proof that no pass receipt was emitted for failed claims;
- exact candidate SHA/digests and independent acceptance identity.

Calling the resolver directly, presenting this architecture plan, or showing a
hand-written receipt cannot satisfy S25.

## Stop conditions and minimum closure

Return to S13 or hold the dependent stage if any of the following remains
unresolved:

- an acceptance surface or claim-bearing verdict has no policy row;
- controller and CI cannot share one resolver and reason-code set;
- a pass receipt can be emitted before artifact bytes are opened and hashed;
- mutable, escaping, foreign, stale, unsanitized or contradictory evidence can
  satisfy a claim;
- invalidation can preserve a downstream pass on changed inputs;
- role identity is trusted only from artifact metadata;
- BLG-F01 integration requires a duplicate registry or its accepted adapter
  contract is absent at the integration gate.

Minimum closure for implementation is: accepted S14 falsification; complete
AC01-AC13 plus entrypoint/concurrency/recovery cases; one strict versioned
policy and manifest schema; one shared resolver; controller/CI parity; a
hash-linked BLG-F01 adapter contract; and S16 approval over the exact package.

No secret, production access, live WB/Ozon call, deploy, commit, push, merge or
self-acceptance is required for S14. There is no S13 blocker.
