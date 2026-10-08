# WMS-666: independent review of the renderer contract correction

Reviewer: gpt-6-astra, effort high. Date: 2026-10-08. Verdict: PASS for the two-file correction below. This is a bounded test-contract review, not a new product acceptance or release approval.

Original frozen contract: `28a7999fefd886de41f6ffda5b05b69cd49aa496`.
Reviewed correction: `ec44815fe063611723c2794781ff8b1a9288bf52`.
Accepted product: `ffb524e2950cfb250993ad4db3b0f394ca55f735`.

The original contract is an ancestor of the correction. The correction commit changes exactly these two frozen files, and no runtime file:

- `frontend/src/screens/v2/fbsPickingColor.wms673.dom.test.tsx`: original blob `381bb2c66163be3a25fc13a64c2644992285fb4f`; corrected blob `e9b1bd53ddd772154bb25f3660d4adf6a08d23d4`.
- `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts`: original blob `b6d9ed169356023611d7f2140faf9c8b0ed94f38`; corrected blob `e26144984bd195a710d915f51dc427ddb5b32c0a`.

I inspected the cumulative original-to-correction diff as well as the correction commit itself. No test case is deleted or skipped in that diff. Historical branch differences outside this original contract are not attributed to this correction.

The WMS-673 cumulative change replaces an `unknown[]` fixture with its explicit existing object shape and removes a corresponding type assertion. Its data and request behavior remain the same. The single changed expected cell uses `Нет текущего остатка`, the established empty-location text in `buildFbsPickingListPrintHtml` in `fbsUx.ts`. It continues to verify the fresh picking response, exact table contents, GET-only requests, authorization and unchanged workspace fixtures. This corrects the fixture typing and literal expectation without relaxing those checks.

The WMS-657 C5 fixture changes the nonnumeric WB-order sentinel to numeric order ID `5524537174`, and changes the exact expected PDF text to `№5524537174`. WB order IDs in the existing application contract are numeric. All page-size, orientation, full-column text, table bounds, non-overlap, row alignment and intentionally corrupted-PDF rejection assertions remain present. This correction does not permit clipped, missing or misplaced PDF text.

These two narrowly scoped corrections are suitable for the existing `corrections` ledger mechanism: declare the original contract and correction above, with exactly these two file paths and this independent PASS record. Do not include the separate partial-acknowledgement addition, unrelated scan tests or runtime changes in this ledger entry. Do not modify the checker or exempt these files from mandatory execution.

Validation for this metadata review consists of Git ancestry, exact file/blob scope, the full cumulative test diff and the corresponding renderer semantics. Earlier specialized renderer execution remains separately recorded in the accepted evidence; no new test execution is claimed by this document. The final S commit must retain these exact corrected bytes, preserve all mandatory cases and reports, pass the existing document/contract checks, and receive the full exact-S CI result. Product acceptance remains the separately published R; deployment is still gated on release checks.
