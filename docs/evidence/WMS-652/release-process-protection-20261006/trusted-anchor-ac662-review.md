# WMS-652: independent Astra A review of trusted anchor

Reviewed immutable commit `ac6628aacda5631e0be886364ed01d2a324847c4`. This is a bounded continuation of the infrastructure review, not a new product audit. No product, test, workflow, repository setting, check-run or production changes were made. Verdict: **changes required before activating this anchor as the release protection**.

The standalone verifier makes a substantial improvement: it reads trusted BASE policy and Git trees through GitHub, checks protected bytes/modes in BASE, HEAD and the current merge, requires the latest exact PR CI run and mandatory successful jobs, then downloads the API-selected artifact for the exact merge/run/attempt. The metadata helper deliberately returns `evidence_complete=false`; the publishing CLI only calls the strict artifact verifier. Archive path, size, duplicate and symlink restrictions are present. Candidate Python is not imported or executed by the anchor.

I read the implementation, prepared workflow, README and all three frozen/additive test modules. Independent run of `test_trusted_process_check`, `test_trusted_process_artifact` and `test_trusted_process_cli`: **22 PASS**. The following two additional synthetic probes run the actual publishing CLI with injected API/download/publish callbacks. They perform no GitHub writes. Their source and output are saved beside this report in `trusted-anchor-ac662-probe.py` and `.txt`.

## P1: an initial metadata outage leaves an old success untouched

At `scripts/ci/trusted_process_check.py:330–344`, `head` starts as `None` and is assigned only after a fresh `api_get` plus scope validation. If that first read raises `ValueError`, the CLI returns failure but cannot enter the `publish(... failure ...)` branch because `head` is still false. The trusted workflow event already carries the affected head, but it is not used as a failure-only fallback.

The probe starts with an earlier success for H and makes the initial API read unavailable. Actual CLI exit is **2**, but publication history remains exactly `[earlier success H]`. Thus a failed anchor invocation is not equivalent to withdrawing the existing `process-integrity` success on the PR head. This is a concrete local reproduction of publication behavior, not a claim that a live PR was merged through it.

Minimal correction: derive and validate the same-repository affected head from the trusted event, and use it only for a conservative failure publication when fresh identity cannot be read. A stale event must never fail a different fresh head or authorize success. Add tests for PRT and workflow_run payloads, missing/invalid identity, and initial read failure after an earlier success. If GitHub writes are also unavailable, no client code can guarantee revocation; the required pipeline result and strict current-base protection remain necessary.

## P1: independent event queues can publish success after a newer failure

The prepared `process-integrity.yml:18–20` uses the PR number for PRT concurrency but workflow **run ID** for workflow_run concurrency. Two CI runs for one PR therefore use different queues; a PRT invocation and a workflow_run invocation also use different queues. `cancel-in-progress: false` does not serialize these queues. In the CLI, final verification and the `publish` POST (`trusted_process_check.py:333–337`) are separate operations.

The second probe pauses the older invocation after its strict verification, at the start of its outgoing success publication. It changes the synthetic latest CI run to a newer failed run and executes a second actual CLI invocation. The new invocation exits **2** and publishes failure H. The old outgoing POST then completes, and the old invocation exits **0**, leaving publication order **failure H, success H**. Both artifact and metadata verification really ran in the old CLI; this is not a metadata-helper-only shortcut.

Minimal correction: serialize all publishers that can affect one PR across both event kinds. A single global queue is a simple acceptable starting point for this small checker; a validated per-PR dispatch is possible but more complex. Keep `cancel-in-progress: false`. Add an explicit overlap/publication-order contract. Re-reading immediately before POST reduces a window but does not prevent a slow outgoing POST from completing after another publication. Serialization closes this demonstrated out-of-order publisher case; it does not make verification, external CI changes and GitHub publication a single atomic transaction. Mandatory current pipeline proof and strict current base are still required for the complete release gate.

## Boundaries and verified positives

- A read-only check of the historical actual PR CI `37505511512` confirms GitHub run `head_sha` is PR head `d61805978…`, while the executed artifact is bound to merge SHA. The implementation's distinction between API head and tested merge is appropriate; rejecting all PR artifacts because API head differs from merge would be wrong.
- Strict proof rechecks PR identity and latest run after downloading the artifact. Ordinary head/base/merge changes and a newer run discovered during download are rejected by the implementation/tests. The race above starts after those checks.
- Raw testcase reports are not reparsed by this standalone anchor. It relies on the verified immutable proof-producing pipeline. That is the documented design boundary, not evidence that testcase execution was independently reproduced by this audit.
- Default branch is `main`. The anchor is prepared documentation, not an installed workflow. Existing active ruleset `24431521` is real and requires PR plus five existing job contexts; absence of legacy branch protection is not absence of branch protection. The proposed anchor/process-proof requirement and strict current-base enforcement are not active protection merely because the files exist.
- BASE must already contain the reviewed policy; the strict verifier does not silently bootstrap missing policy. Initial policy/main-anchor activation requires an explicit reviewed bootstrap. No `main`/ruleset changes were made by this audit.
- These 22 unit tests plus two additional publication probes are narrow synthetic evidence. They are not a full CI, a live GitHub check-publication experiment, browser acceptance, deployment, or proof about hostile administrators.

The original developer should add the missing failure/overlap contracts before fixing these two paths, then return the exact delta for review. No implementation was edited here.
