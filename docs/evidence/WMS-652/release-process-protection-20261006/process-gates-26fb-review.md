# WMS-652: independent Astra A delta review of process gates

Reviewed fixed commit `26fb8462b9e319cbc38b9ce2f7d8a6815416b4a2`, compared with the previously reviewed `cee68a42dd43aee1a7f6cf86277e6fb697133171`. The shared checkout had advanced, so execution used `git archive` of the exact commit, not its moving working tree. Verdict: **the earlier P1 platform-selection and P2 artifact-attempt findings are closed in this delta**. This does not close the separate trusted-anchor findings or authorize a release.

Independent reproducible evidence is `process-gates-26fb-probe.py` and `.txt` beside this report. The probe extracts fixed Git bytes, runs only the two process-gate unit modules, performs collection only for the native print test selectors, and checks all four producer/download artifact-name pairs. It does not access a printer or start a browser.

## Fixed platform selection preserves the original cases

The Linux CI command now excludes the single Windows-only `.cmd` case. Its policy is exact and requires **30** named cases. The Windows command excludes the two Unix-only real-child-process cases; its exact policy requires **29** named cases. Independent pytest collection using each actual selector equals its policy set exactly. Their union is all **31 unique original cases**. Test source and expectations were not weakened to turn platform skips into pass.

The Windows-only case is still required on Windows. Both Unix-only cases are still required on Linux. This closes the deterministic earlier problem where Windows produced 29 pass + 2 skip but the proof required 31 pass. Collection occurred on macOS and is not represented as Windows or Linux execution; actual platform execution remains for CI. Once this corrected policy is promoted to trusted BASE, removal of any of these required cases must again be rejected. Replacing the pre-bootstrap erroneous policy is not permission to weaken a future trusted policy.

## Every intermediate artifact is attempt-specific

All four producer names and their corresponding process-proof downloads now include full `${{ github.sha }}`, `${{ github.run_id }}`, and `${{ github.run_attempt }}`: backend-executed-contracts, frontend-executed-contracts, printer-windows-contracts, and release-print. The probe checks equality of each pair and exact format. There is no fallback to an earlier attempt's name. The already exact final proof artifact remains exact.

This closes both the predictable v4 upload name conflict on a full rerun and the collector-only path to wrapping old producer reports as a new attempt. A partial rerun without new producer artifacts now refuses to produce proof; obtaining a fresh complete attempt is intentional. This is code/contract evidence, not a claim that an actual GitHub rerun was performed in this review.

## Base format and receipt parsing

`verify_process_ci.py:82–86` now rejects absent, malformed, all-zero and self-equal `base_sha`. The new `test_invalid_or_self_base_does_not_pass_as_trusted_baseline` checks these cases through the real verifier and asserts no action is authorized. It closes the earlier malformed-base advisory. It does **not** independently prove that a syntactically valid other SHA is the actual event's BASE; that remains the trusted-anchor provenance responsibility.

The added browser-report parser requires exact tested SHA, overall PASS, named case PASS, no duplicate, and the policy's exact set. Its new contract checks old SHA, skipped/missing/replaced/duplicate case and failed suite. Together with the existing evidence/immutable-source tests, the two independently run modules pass **20/20**. The root's reported broader 83 tests were not redundantly rerun or relabeled as this auditor's execution. Real browser button/QR behavior was outside this bounded delta review.

The fixed registry contains 173 files and 586 suite entries, including the preserved native union. Counts are descriptive only; the acceptance evidence is the exact named-set comparison and the negative assertions, not those counts.

## Follow-up on R50 fixture loop lifetime

The general six-case PostgreSQL command in this fixed SHA still uses psycopg without explicit loop-scope flags. Prior independent R50 proof used asyncpg and both `asyncio_default_fixture_loop_scope=session` and `asyncio_default_test_loop_scope=session`. `backend/app/db/session.py:15–17` creates a module-global pooled AsyncEngine/SessionLocal; `backend/tests/conftest.py` resets rows but does not dispose this pool between function-scoped loops. R50 creates its Events/tasks inside the running test, so those objects themselves do not impose a different scope.

Adding **both** session loop flags to the general six-case batch is a sensible runner-only alignment with the proven pooled-engine lifetime. No test expectation or database driver change is needed. This is a robustness recommendation, **not a reproduced psycopg failure**: the historical CI already executed the older five cases, and driver differences alone do not establish a regression. The final exact six-case CI result should prove this runner invocation. No broad test rerun was requested or performed here.

Trusted main activation, mandatory anchor/process-proof ruleset requirements, strict current base and other deployment paths remain separate explicit release blockers/unfinished work. The companion anchor review reports two additional concrete publication defects. No product, settings, tests or registry bytes were edited by this auditor.
