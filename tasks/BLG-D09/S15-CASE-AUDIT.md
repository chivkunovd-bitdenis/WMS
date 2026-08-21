# S15 Independent Case Audit - BLG-D09

## Verdict

`CASE_AUDIT_FAILED`

This is an independent `case-auditor` review of the exact S15 package for the
single high-risk release card `BLG-D09-C1`. It does not decide S16 Product
approval, change the controller state, implement cases, deploy, access secrets,
or contact production or marketplaces.

- Auditor role: `case-auditor`
- Audit model/tier: `gpt-5.6-terra` / `moderate`
- Baseline SHA: `69c271678782d7dcfa39df97cd905cbee1678727`
- `S11-PRODUCT-CONTRACT.md`: `sha256:59ab6e6e6606f4d9f1e051175ebbefb019bb0f602ffcbdc1f4ecd04f8defe336`
- `S12-TASK-CUT.md`: `sha256:ba040d5aead8bb8e21e9c1ccd2b3fa1611814d8b69866faca2a9bfeb611439eb`
- `S13-ARCHITECT-PLAN.md`: `sha256:541840a7d81c39ecdd77d064bc8fcde03e018e63ac0a176adc84326b2202db74`
- `S14-ARCHITECT-FALSIFICATION.md`: `sha256:ac21372575908f8787506eca96fb3326b29678ed293e2d0d629c1c748371e70e`
- `S15-CASE-FACTORY.md`: `sha256:8651f9a06b99fa8c363eadab0276795bf14eb4282c039e4be1b2eeb92efe7d70`
- `S15-CASES.json`: `sha256:c9b56bd8fb24be4512df71e4d47dd6ccf5c9e2ecfcf0a51a14e0fe72d324b403`

## Coverage that is present

The package does cover the central exact-SHA chain. `AC01` is the direct
build-once journey; `AC02`--`AC04` break mutable/dirty selection, source drift,
target rebuild and manifest/artifact/revision tampering. `AC05`--`AC07` require
complete runtime identity and reject health-only proof. `AC08`--`AC10` cover a
stale or unlisted browser bundle, byte mismatch, effective cache headers and
hard reload, while preserving the open future S23 blocker
`BLK-RELEASE-001`. `AC11`--`AC12` constrain rollback to the named immutable
previous package and explicitly prohibit a claim of data rollback.

All 12 listed cases name the deterministic fixture version
`blg-d09-exact-sha-release-v1`, a fresh isolated reset, an executor type, an
oracle, and an `executable_ref` marked `PLANNED_FOR_S19`. The fixture contract
forbids production hosts, credentials, live deploy, WB/Ozon and external
egress. These are valid plans for S19; they are not execution, release or S23
closure evidence.

## Missing required destructive coverage

The S13 handoff requires S15 to add destructive cases for **every** listed
failure boundary, and S14 repeats that requirement for every falsification
attack. Two applicable rows have no direct or breaker case in either the JSON
matrix or the factory matrix:

| Missing row | Why existing cases do not cover it | Required S15 case boundary |
| --- | --- | --- |
| Migration preflight incompatibility or missing restore evidence | `AC06` only models a migration identity/head/exit mismatch after a mixed runtime is started. It does not prove that incompatible migration preflight or absent restore evidence stops before migration and before any application/runtime change. | A local-only destructive case must inject each preflight failure, assert no migration and no application promotion, and record the stop state without claiming data rollback. It needs the same deterministic fixture/reset and a planned S19 binding. |
| Best-effort marketplace side effect inside release success | The factory declares external-marketplace cases inapplicable, but S13/S14 explicitly identify the existing WB sync-in-deploy path as an attack that S15 must test. No case proves that release success neither invokes nor masks a marketplace sync. | A local-only destructive case must use an egress-denied fake sync boundary and prove that the exact-SHA release path excludes it from success; no live WB/Ozon call, credential or deploy is permitted. It needs a planned S19 binding. |

The second missing row is especially material because `S15-CASE-FACTORY.md`
states that external-marketplace cases are not applicable, which conflicts with
the explicit S13/S14 attack and handoff constraint. The release card need not
perform an external operation to test this; the required proof is that the
local release-success path cannot perform or ignore one.

## Blocker and next boundary

**S15 rework is required** before a truthful `CASE_AUDIT_PASSED` verdict can be
issued. The case writer must add the two rows above without changing their
S11--S14 oracle, then an independent auditor must review the changed exact
package again.

`BLK-RELEASE-001` remains open, unchanged, and is still a future S23 stopper.
Nothing in this audit resolves it, accepts S16, or authorizes deployment,
rollback execution, production access, secret access, or marketplace activity.

## Controller checks

`python3 scripts/pipeline/run.py next --task-id BLG-D09` reported S16 owned by
`pipeline-product`; this audit does not accept that stage. `python3
scripts/pipeline/run.py validate --task-id BLG-D09` returned
`{"validated_tasks":["BLG-D09"]}`. No controller command that mutates state was
run.
