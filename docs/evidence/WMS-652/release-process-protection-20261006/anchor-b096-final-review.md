# WMS-652: final bounded Astra A review of queue fix and explicit bootstrap

Fixed input: `b096cd12916e63e8ee7507f508f00dd8526c15fa` in `.worktrees/wms652-trusted-anchor`; the source checkout was clean at that SHA. This review covers the delta after `6b778ebb2aa4b8dbb4580201841f5ba0bfc4430f`, not a repeated full release audit. **Verdict: PASS for this prepared code and configuration mechanism.** No new blocking implementation defect was found. This verdict does not select or approve a concrete bootstrap source commit, install the workflow, or authorize a product release.

The owner has already authorized the main installation, as relayed by the lead. This report does not request that permission again. The lead still needs the concrete reviewed pin and complete integration evidence before treating protection as active. This auditor changed no product, implementation, tests, main, ruleset or production files.

## Queue finding closed

The prepared YAML now has one constant publisher group, `queue: max` and `cancel-in-progress: false`. The additive contract was fixed in `b6cac70edddf9b383cae5c03eefc6b19cbe7a7f7` before the YAML correction `2f3646f7d`. Its three-event case retains the pending failure for A when unrelated B arrives; its negative control documents the previous replacement under default single mode. A separate case models the 100-pending ceiling and rejects overflow instead of displacing an earlier waiting failure.

This closes the specific residual P1 reported in `anchor-6b778-server-165-review.md`. The supported semantics were checked against [official GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency) during that review. These are deterministic scheduler-model contracts, not a live Actions scheduler experiment. Overflow above 100 and unavailable check publication remain stated operational boundaries. The change does not claim an unbounded queue or atomicity across CI, metadata reads and outgoing POST.

## Explicit bootstrap preserves the trust boundary

The nine-method bootstrap contract was fixed in `f4e6d2526b075a430491e57540c345dc214e3973` before implementation `b096cd129`. The only subsequent test-file change is import ordering; the prior 30 tests are byte-for-byte unchanged. I read the new tests, checker delta, `bootstrap-preparation.md` and `queue-fix.md`.

The CLI loads only the checker-adjacent `process_bootstrap.json` in its trusted checkout. There is no CLI, event or environment option selecting an alternate configuration. Its exact two-field shape requires different full lowercase `base_sha` and `source_sha`. Duplicate fields, malformed data, oversized file and symlink are refused. No actual config file is present at the reviewed SHA, so absence of BASE policy still cannot silently authorize bootstrap.

With an approved pin, the checker first obtains the full actual BASE Git tree. It selects SOURCE only when that complete tree lacks the policy and the actual PR base exactly equals the configured base. A present policy takes precedence over the seed, including when the stale pin names another base. A BASE API failure, truncated tree, malformed existing policy or inaccessible existing contents never invokes a source fallback.

For the approved absence case, SOURCE must have a complete Git tree and regular policy blob. Its policy becomes the baseline contract: protected file names/digests and required case sets are preserved, while SOURCE/HEAD/MERGE protected Git blob IDs and modes must match. Self-updating a candidate digest, removing a case or changing a protected source file does not approve itself. SOURCE is an explicit trust root chosen outside the candidate; correctness/completeness of the selected SOURCE is therefore part of the subsequent concrete pin review, not something a two-SHA loader can decide.

The real PR base is preserved for run matching, returned `base_sha` and artifact execution metadata. SOURCE is separately disclosed as `bootstrap_source_sha`; substituting SOURCE for artifact base is rejected. Latest attempt, required jobs, complete strict artifact identity and final rereads remain mandatory. The metadata-only helper still cannot authorize publication. Once BASE itself contains policy, normal BASE protection resumes without a continuing source exception.

## Independent evidence and remaining integration work

Executed the six exact anchor unit modules at the fixed SHA: **39 PASS**, saved in `anchor-b096-tests.txt`. This includes the original strict artifact/publication failures and the new queue/bootstrap cases. No Chrome, broad CI, live GitHub writes or production commands were run.

Additionally, `anchor-b096-extra-probe.py` extracts fixed Git bytes into an isolated temporary directory and tests four omitted edge paths with synthetic callbacks. All four refuse: symlink config, config over 64 KiB, SOURCE policy symlink mode, and truncated SOURCE tree. The source and output are preserved beside this report. Temporary extraction is only the test environment; all resulting audit evidence is stored in the permanent named Git branch.

The earlier event-head and two-publisher P1 fixes remain accepted; the three-event queue P1 is now closed. The separate server gate `1656809d…` retains its prior bounded PASS. Actual installation and concrete pin must use the final reviewed source containing the complete process contracts, including the pending C59 work if required by the release. Missing or mismatching pin/BASE remains a refusal. Required GitHub contexts, strict current base, final exact CI and deployed version are separate facts to verify during activation; this prepared-code PASS does not assert that they are already active.
