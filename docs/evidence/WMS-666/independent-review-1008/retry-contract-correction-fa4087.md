# WMS-666: independent retry-test correction review

Reviewer: gpt-6-astra, effort high. Date: 2026-10-08. Verdict: PASS for the exact two-file correction `fa4087f73770d553dc9f178ec086b11deb93c50d` against original frozen contract `28a7999fefd886de41f6ffda5b05b69cd49aa496`.

The reviewed files are `frontend/src/components/MarkingPrintDialog.availability.dom.test.tsx` and `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms514.test.ts`. The correction commit changes exactly these two files. I also inspected their cumulative diff from the original frozen contract: it equals this narrow correction, with no hidden additional case or expectation changes.

Exact-S CI run `37726973064`, frontend job `113147272545`, failed before correction. The availability suite's preceding 12-order QR test clears its print spy, dispatches once and leaves that call recorded. Shared setup resets `print` but did not clear `printTapeSections`. The next acknowledgement test adds its own dispatch, so the cumulative spy count is two. The correction clears that history in `beforeEach`. It preserves every exact-one-dispatch assertion before and after acknowledgement recovery, exact acknowledgement sequence, and completion/close assertions; it cannot excuse a duplicate dispatch within the case.

The WMS-514 source check searched for an obsolete `run(operation, success, onError, onSuccess)` spelling inside the automatic-preparation slice. The actual operator retry in that slice uses `retryOperation`, a fresh workspace read and only its still-missing stickers, guarded by `write.isCurrent()`. The correction asserts that concrete fenced retry call and adds assertions for the fresh workspace fetch and missing-sticker filter. Existing request and explicit-retry-action assertions remain. No runtime change, missing call tolerance or automatic-retry permission is introduced.

The writer reports a focused run with 2 passed and 20 skipped after the correction; this review does not represent that as a complete-file or full-CI pass. The original full job remains failed (4 failed, 1,734 passed, 3 skipped), with independent C19/history, scope-contract and print-boundary issues still under investigation. Those issues are not accepted by this report.

Use the existing correction ledger with the exact original/correction commits and exactly these two file paths. They are disjoint from the separately reviewed ec44815 renderer files. Preserve mandatory execution and update protected digests through the legitimate reviewed source transition; no checker exception or main merge is authorized here.
