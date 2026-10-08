# WMS-652 C71: independent binding and execution-policy review

**PASS for the reviewed static implementation and execution contracts. Release and analytical acceptance remain OPEN.** This independent review covers exact candidate `1fba79cf132e13d99dd563ef2dd3b67d57677b42` against baseline `41d027849e9b6221e06c73570066f9668a6e5801`. It includes the corrective test-first commit `e4c13bcc8a9b01ed0069636bcac6afc127a7b25f`, documentation commit `29845b57ef1539c2dfe9a7f6e4afd6dfa772d71f`, and policy correction `1fba79cf132e13d99dd563ef2dd3b67d57677b42`. The reviewer session is separate from the implementer and test writer. No implementation or binding fixture was edited by this reviewer.

AGENTS.md and the complete owner-cases.md and failure-cases.md libraries were read during the first review; all three are unchanged at this candidate. No skills were invoked, in accordance with the owner's instruction.

## Findings and correction

The first review of `90dfa0a160f566b029d873ac3fb5ab4a387bfeae` found a blocking mismatch: the 18 new C13 policy IDs omitted their describe prefix, while the actual Vitest JSON reporter supplies it in `fullName`. The synthetic receipt reproduced the shortened IDs and therefore failed to detect the mismatch.

The corrected candidate resolves that defect. Independently extracting the sole describe title and all 18 it names from `frontend/src/screens/v2/wms666ChangeScope.test.ts` yields exactly the 18 manifest IDs and the 18 WMS-666 C13 document references. Each full name begins with `WMS-666 C13: narrow UI-only change boundary `. The installed Vitest JSON reporter source constructs fullName from ancestorTitles plus the test name separated by spaces. The corrected contract rejects both a wholly shortened receipt and a receipt with one missing describe prefix, as well as missing, skipped, renamed and misattributed cases. No unresolved implementation defect was found within this review scope.

## Preservation and trust boundaries

All 282 baseline protected paths and all 1719 baseline case IDs remain present. All 29 suite definitions retain their non-case fields exactly, including report, format and exact semantics. The final manifest has 283 protected paths, 29 suites and 1742 cases; frontend-fbs has 355 cases. The additions are the 18 C13 cases and five C71 cases. Every one of the 283 saved SHA-256 digests matches the file bytes in the reviewed Git commit.

The workflow's sole product-scope trusted reference and the binding fixture's final/frozen values agree on `739a63343fc38d2a3441d9b613b4652c7f0380e0`. The previous eight accepted references are retained in order, with 739 appended. No HEAD, current CI SHA, or candidate-selected source is introduced. Product scope at this reference reports no unapproved product paths. C56/C66 controls continue to reject candidate self-approval, wrong BASE/SOURCE, corrupted trusted bytes, lost cases or paths, and changed suite semantics. The product reference is not a final bootstrap SOURCE; that separate exact commit and its trusted-main activation remain later release work.

The fixture deliberately still references the old acceptance record `c2cbd700fbf7f03fb00465b27ee8214428f9386e`. It cannot authorize this transition. Two C71 tests correctly remain red on that record. This review does not replace independent analytical acceptance, and the fixture must not be declared accepted or used for release until the genuine new acceptance is saved and its exact commit is bound and rechecked.

## Executed verification

On the exact reviewed candidate:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider scripts/ci/tests/test_ci_release_additions.py scripts/ci/tests/test_process_contracts.py scripts/ci/tests/test_reviewed_process_upgrade.py scripts/ci/tests/test_product_scope.py`: **76 passed, 44 subtests passed, 2 failed** in 28.79 seconds. Both failures are the expected old acceptance-record refusal, in `test_c71_final_binding_requires_a_new_saved_independent_acceptance_record` and `test_c71_final_binding_uses_exact_739_and_a_new_saved_acceptance_record`.
- Independent Python comparison of both immutable Git manifests, all retained paths/cases/suite fields, every source digest, and source-derived C13 full names against manifest and documentation: **PASS**.
- `python3 scripts/ci/product_scope.py --root . --trusted-ref 739a63343fc38d2a3441d9b613b4652c7f0380e0`: **PASS**, `unapproved_product_paths` empty.
- `python3 scripts/ci/check_task_documents.py origin/etalon`: **PASS**.
- `git diff --check 41d027849e9b6221e06c73570066f9668a6e5801 1fba79cf132e13d99dd563ef2dd3b67d57677b42`: **PASS**.

## Limits

This is static and contract verification, not a successful live Vitest execution receipt. The earlier attempt to run the main checkout's Vitest binary from this worktree failed during config loading because the worktree lacks the vitest package; no installation or cleanup was performed. The reporter naming rule was checked directly in the installed reporter source, and the corrected receipt behavior was executed through the Python validator tests. Full frontend runtime, exact-SHA full CI, process proof, final bootstrap SOURCE selection, analytical acceptance, deployment and operator behavior are not established by this report. No production operation was performed.
