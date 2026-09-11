# WMS-415/338/351/325/062: correction of PR217 CI failures

CI34477781077: 28 failed /2463 passed. Failed-job log saved locally, not committed because raw logs are not an operator artifact. Backlog WMS416 handled separately by root. No deployment/publicAPK action performed here.

## Actual code defect

WMS351 units validation counted disabled marketplace saved caps in the active publication total. The percent path already filtered enabled marketplaces. `fbs_stock_rule_service.py` now validates the sum of enabled marketplace caps while retaining disabled settings. A newly enabled marketplace is revalidated even if its numeric value did not change. New/increased disabled caps are individually bounded by physical free stock on the applicable warehouse; unchanged caps remain preserved after depletion. This fixes the existing WMS351 test without removing its assertion that enabling both overlapping allocations must fail.

## Fixture and platform corrections

- Intake/shared-WB-Ozon allocation tests now seed actual warehouse stock before configuring an operator cap; legacy fbs_stock_limit metadata alone is not physical stock. The cross-provider test explicitly enables both providers.
- Legacy emulator case now seeds its intended historical pool row directly, rather than invoking the operator endpoint which now correctly configures units mode and validates real stock. The test still requires no publication when the rule is absent.
- Legacy limit reset verifies obsolete Product.fbs_stock_limit is cleared while the existing operator cap7 is preserved.
- Scan fixture uses a distinct warehouse code; registration now legitimately creates main. Storage measurement fixture explicitly selects its stock-bearing warehouse for calculation/listing, preserving its scope and monetary assertions.
- WMS325 PG-trigger/outer-rollback tests receive explicit PostgreSQL-only markers. SQLite legacy SAVEPOINT can commit an audit insert outside its nominal outer transaction; it is not evidence of PostgreSQL rollback failure. Assertions are retained and execute when WMS_TEST_DATABASE_URL selects PostgreSQL. Previously accepted evidence: wms325-bounded-document-mutations-20260910.md (21 PG PASS), wms325-inbound-mp-independent-final-20260910.md and its corrected fixture followup, wms325-settings-billing-independent-20260910.md (author17+29 PASS). Those are earlier author runs, not new executions. One datetime assertion normalizes UTC after SQLite drops tzinfo, retaining exact timestamp equality.
- Backend CI installs Node20 + frontend npm dependencies because the two WMS417 backend HTTP contract tests execute actual TypeScript mapping helpers. Previously the backend job had no typescript package. No product assertion or dependency test is skipped.

## Bounded verification

One targeted run of original failures plus small affected WMS351/417 files:38 passed,13 skipped,2 failures in12.33s. The remaining two failures identified precise fixture mistakes (disabled publication in cross-provider test, multiple default/explicit warehouse rows in storage fixture). After those changes ONLY these2 cases were rerun:2 passed in1.35s. Total40 scenarios passed;13 skips are explicit PostgreSQL-specific cases, not claimed as PASS. No full pytest/build/review loop. Target node IDs are preserved in artifacts/wms415-evening-20260910/ci-fix-targets.json.

Ruff changed Python files PASS; mypy changed application service PASS. An explicit mypy invocation over tests exposed existing errors normally excluded by backend configuration; tests were not broadened or rewritten to address them. The one new mixed query-parameter dictionary received an explicit str/int annotation.

Root owns the single combined push and subsequent CI. The functional service delta must be included in the evening candidate verification; a prior stage deployment does not contain this correction.
