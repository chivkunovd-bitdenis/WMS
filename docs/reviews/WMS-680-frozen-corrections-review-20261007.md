# WMS-680: independent frozen corrections review · 2026-10-07

This is the independent frozen-test correction review by actual **gpt-6.1-sol**, reasoning effort **high**, on 2026-10-07. It approves the exact correction chain and its legitimate semantic scope. It does not supply product acceptance, a new product review, CI, deployment or physical-print proof. No Astra identity or verdict is claimed.

AGENTS.md and both owner/failure case libraries were read fully before the verdict. origin/etalon was fetched and verified at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`; active worktrees have identical rule/library blobs: AGENTS `510ce8febd402f9a78a5f1fddd964d99283afaff`, owner-cases `19a12f266ef38e697e1b30cf2f3da3d589e8cce2`, failure-cases `48263ba41e8fdb67c744864f7ec52a26b768598b`. The root frozen-contract-audit README/inventory were used as inventory, not approval or an up-to-date chain. Git objects, full original-to-final diffs and each correction's parent delta were inspected. Existing run evidence below is attributed to its actual session; this reviewer did not rerun suites, install dependencies, invoke agents or exercise production/browser/printing.

The original contract, every listed correction and reviewed source are Git ancestors of this report's branch. Integrating this proof must preserve the report/source commit as an ancestor; copying its Markdown or cherry-picking only its content is not ancestry proof. Checker/policy/ledger binding is a later moderator/testwriter operation; none was changed by this reviewer.

**Verdict: PASS for the exact OWNER supersession and the three subsequent fixture corrections**, through `739bcadf1`, not only inventory candidate `7ad0aa`. This approval concerns legitimate test changes; the existing product review remains FAIL for D3 and is not overridden.

`3be84bb` is an actual OWNER semantic supersession, not a fixture repair: recorded owner clarification requires separate compact Article/Color/Size columns in all agreed print forms. It changes requirements and baseline evidence, not tests/product. It explicitly replaces only previous inline placement, retaining R1–R7 guards for variant sources, tenant/seller, identifiers, quantities, photos/barcodes/instructions/locations, empty Fact, page format and no new warehouse actions. The source owner statement is preserved in the requirements; this reviewer adds no invented quote or new approval.

`5739ed2` is the replacement test contract after those requirements and before product `73f5ce52045411a9b759040600f4cade1af70490`; Git ancestry/order verified. Its own requirements diff adds only Test links C680-15…18. The backend frozen file stays byte-identical. The frontend frozen file retains original scenarios and non-placement assertions, replaces obsolete inline prefixes and adds per-row separate-field controls for six builders, four variants, fallback/whitespace/string 0, preserved metadata and callers. The three pre-existing print-test files are substantive, directly superseded layout-contract files, not disguised ancillary Test links: inbound adds the three headers in order, FBO changes inline size/color to distinct cells while preserving article/barcode/no-composition, and FBS adapts 10→12 columns plus Article/Color without removing any other column. Removal of a fixed 78px size width is part of the owner-requested compact layout; text wrapping/no-nowrap stays guarded. All six FBS scenarios remain, including 34-row PDF/page correspondence, missing-size dash, original identifiers and mutation negative controls. Added Geometry is an additive real-PDF contract. This exact six-file change requires owner_ui_supersession binding; it is not a narrow fixture/subset ledger entry.

`7ad0aa` replaces erroneous rejection of any size/color/article substring in lawful Product text with exact cells, exact Product including retained SKU/WB metadata, unique headers and cell counts. A lawful name explicitly includes 0 and article/color words. A negative historical-inline example still fails. Attribute/row/scenario coverage is strengthened, not loosened to substring presence alone.

`11806bd` repairs the transient name-only PDF row anchor introduced in the replacement contract: the remaining identifier is still below the name in Product and must participate in that block's geometry, as before supersession. It restores name+identifier without moving Article/Color back inline. Function-level SHA-256 comparison found assertSamePdfRow, assertPdfTableWithinColumns and pdfTextMatches unchanged across original, replacement and correction; alignment/overflow thresholds therefore did not loosen. Deterministic controls show name-only false positive, valid complete block, genuinely shifted neighbor FAIL and 11-column FAIL.

`739bcad` only converts slash-bearing labels into safe temporary file basenames. Six display scenario labels, builders, normal 4-row and long 28-row inputs, assertions and PDF-coordinate/page-count checks remain unchanged. Before it, slash-bearing scenarios stopped at ENOENT before Chrome; this is not product geometry RED. Current handoff supplies actual 6/6 PDF cases (12 forms), plus FBS C4–C6 3/3 PASS; C1–C3 had their separate 3 PASS. No broad rerun was done here.

The original tester thread `01a112ca-fb4c-70f0-aa05-96df41271327` is in active progress.json/events, distinct from developer `01a112db-cd97-7d41-bc1b-a0eb4d3154f6`. The root 679-680 separate-columns-test-contract/columns-test-fixture-correction and 680-testwriter fbs-alignment-correction/pdf-fixture-path-correction event files all resume that same actual tester thread, with exact role prompts and correction outputs. Original-contract role-boundary correction is recorded in progress.json; no remaining product draft is being approved. No model identity is inferred from Git authors.

Known limitation: C680-18 guards headers/order and page word bounds, not every numeric column's compactness or the second picking table. Product review `3c6af57f4` records D3: Qty in that second table still occupies one third of the page. Neither filename nor anchor correction causes or hides that omission. PASS here approves preservation/legitimacy of the frozen correction chain; it does not claim full R9 coverage, accept D3, accept the UI, or authorize release. Full product review/acceptance must continue separately.


## Immutable Git binding

Reviewed source snapshot: `52b5d7101e6ee06fab76a8201e8c4ab93670dbae`. Original contract: `24009478c3a58b558ad8a661d83dc5920108cb00`. Final correction: `739bcadf1be4fe92e24af3d30b42f892f858e598`. Branch: `codex/night1007-679-680`.


Original frozen file list, with original → final full blob IDs:


- `backend/tests/test_wms680_print_payload_contract.py`: `f7510d80221621aa192dacfe0fd0f7837a18385e` → `f7510d80221621aa192dacfe0fd0f7837a18385e`.

- `frontend/src/utils/wms680PrintContract.test.ts`: `c8847911821967052947bd9f90691892188193e1` → `799f895bb38acca23867042e7b31c6cba96e7884`.


### 3be84bb091712caa2e32226f989e3008e47618a5 · PASS

Source/parent: `7015448e255f606ef74b69e04e81f53777a099d5`. Kind: `owner_ui_supersession`. OWNER semantic supersession: separate compact Article/Color/Size in all agreed print forms; requirements/evidence only.


Exact touched files, parent blob → correction blob:


- `docs/evidence/WMS-680/acceptance-20261007/baseline-source.json`: `ABSENT (added)` → `2d399ace6c00df72c28843d7e0802687a089e632`.

- `docs/evidence/WMS-680/acceptance-20261007/fbo-ozon-long-before-columns.html`: `ABSENT (added)` → `b507fdd97763f9227137321f32c0b4d5696e984b`.

- `docs/evidence/WMS-680/acceptance-20261007/fbo-wb-normal-before-columns.html`: `ABSENT (added)` → `c9a1711a963b8ec88b38ea26fad7f337705888a9`.

- `docs/requirements/WMS-680.md`: `aad7a41a3ea194fdcf2eb596643a30a0096ac488` → `b765c124dc7641ea83a6347fe4b1cc50e648ec4d`.


Changed original frozen files: none.

Other touched files: `docs/evidence/WMS-680/acceptance-20261007/baseline-source.json`, `docs/evidence/WMS-680/acceptance-20261007/fbo-ozon-long-before-columns.html`, `docs/evidence/WMS-680/acceptance-20261007/fbo-wb-normal-before-columns.html`, `docs/requirements/WMS-680.md`.



### 5739ed2ea900b8d6ddc8a9326bf1dc07e687fd8e · PASS

Source/parent: `8baaa27bf91851327ba30d6e93b29fbfb5c423fd`. Kind: `owner_ui_supersession`. New pre-product test contract implementing OWNER supersession; preserve other fields/scenarios and add actual PDF coverage.


Exact touched files, parent blob → correction blob:


- `docs/requirements/WMS-680.md`: `b765c124dc7641ea83a6347fe4b1cc50e648ec4d` → `20fcef00da292c0a1a0cec6a100bfb8a0e4e464e`.

- `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts`: `f01723a9ccee9cc4466797875c9d16a79f50a608` → `ab978dfabfb1f41076e0a16666e94fa081f3ec21`.

- `frontend/src/utils/printInboundReceivingSheet.test.ts`: `e71e18dddc41804c8cbf370362e58bd11154ea04` → `c4cc01c1726331f4ee5f912606017638ba6aea76`.

- `frontend/src/utils/printShipmentPackagingSheet.test.ts`: `9a11e5b4b88fe257622865dd0e0fb15c9083cf2e` → `f59bd4972d9c4a716263b24ab417c74c80377888`.

- `frontend/src/utils/wms680PrintContract.test.ts`: `c8847911821967052947bd9f90691892188193e1` → `f3b12dd1617453a445a5624e19c19692c70a4693`.

- `frontend/src/utils/wms680PrintGeometry.test.ts`: `ABSENT (added)` → `11ec2e43dcf3b696288bcaa55d6cd83a454858d8`.


Changed original frozen files: `frontend/src/utils/wms680PrintContract.test.ts`.

Other touched files: `docs/requirements/WMS-680.md`, `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts`, `frontend/src/utils/printInboundReceivingSheet.test.ts`, `frontend/src/utils/printShipmentPackagingSheet.test.ts`, `frontend/src/utils/wms680PrintGeometry.test.ts`.



### 7ad0aa781d175ef7f4e1d16074a12b47eed655f2 · PASS

Source/parent: `1d335e8aead87fc27895a9577253cb8abdf9ca5a`. Kind: `exact_fixture_correction`. Fixture/assertion correction: exact cells rather than lawful-name substring rejection for size 0; retain negative inline control.


Exact touched files, parent blob → correction blob:


- `frontend/src/utils/wms680PrintContract.test.ts`: `f3b12dd1617453a445a5624e19c19692c70a4693` → `799f895bb38acca23867042e7b31c6cba96e7884`.


Changed original frozen files: `frontend/src/utils/wms680PrintContract.test.ts`.

Other touched files: none.



### 11806bd237c48a030a4e0ff49bb12dd90dfe6778 · PASS

Source/parent: `e8638be207559fee31a069734026cda1d4fcccb4`. Kind: `exact_fixture_correction`. Restore complete Product name+remaining identifier row anchor; unchanged thresholds and negative misalignment/11-column controls.


Exact touched files, parent blob → correction blob:


- `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts`: `ab978dfabfb1f41076e0a16666e94fa081f3ec21` → `299ff644942016a7cee5ee665cbc321ebddbddbc`.


Changed original frozen files: none.

Other touched files: `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts`.



### 739bcadf1be4fe92e24af3d30b42f892f858e598 · PASS

Source/parent: `363e3b58110c61283f44cbb0cfdba5ee227de9aa`. Kind: `exact_fixture_correction`. Safe temporary filenames for slash-bearing scenario labels; six fixtures, 4/28 rows and all PDF assertions unchanged.


Exact touched files, parent blob → correction blob:


- `frontend/src/utils/wms680PrintGeometry.test.ts`: `11ec2e43dcf3b696288bcaa55d6cd83a454858d8` → `34f4ef6ca82d72cf65583d6ba6bdcefb689128a6`.


Changed original frozen files: none.

Other touched files: `frontend/src/utils/wms680PrintGeometry.test.ts`.


Only this new review report is owned and committed by this reviewer. No tests, product, requirements, checker, policy or ledger edits were made.

## Supplemental R9 contract · 2026-10-07 · PASS

Independent reviewer: actual **gpt-6.1-sol high**. This append approves only the additive test delta below; the preceding review remains unchanged.

- Content source: `739bcadf1be4fe92e24af3d30b42f892f858e598`.
- Actual parent/prior report: `d300851544c9587d6563462c23a60c3b67d1af12`.
- Correction/reviewed snapshot: `f2de20008df3b21c1decead0e1051dbda4a4a08a`.
- Only touched file: `frontend/src/utils/wms680PrintGeometry.test.ts`.
- Source and parent blob: `34f4ef6ca82d72cf65583d6ba6bdcefb689128a6`.
- Correction blob: `0c7cc8f9f06fad5df0f7f3bd924dde607179a068`.

The existing six parameterized PDF cases, their form list and assertions are byte-identical. Original rendering, safe filename, header and PDF-geometry helpers are unchanged. capturedWaybill gains an optional allocation argument with exactly its previous default; existing inputs therefore retain their meaning.

Three supplemental cases exercise the lower “Подбор по ячейкам” table for marketplace_unload, operational_outbound and inbound_intake through actual Chrome DOM measurements and rendered PDF. They preserve exact DOM headers, two allocation rows, locations, SKU, order and quantities, and check PDF header order and allocation values. Numeric Qty must be narrower than both text columns; no arbitrary millimetre target or new business constraint is introduced. This adds coverage of existing OWNER R9, rather than altering the earlier semantic supersession or weakening frozen expectations.

Original tester thread `01a112ca-fb4c-70f0-aa05-96df41271327`, in root 680-testwriter/picking-numeric-width-contract-events.jsonl, records **3 meaningful RED, 6 filtered** before the final product fix: Qty 246.34375px versus location 246.328125px. All three failures reached the compactness assertion after PDF creation. The existing independent product review `3c6af57f4eceb8613e7204b06c0868af80a238c5` documents approximately 61.9mm on defective product `e8638be207559fee31a069734026cda1d4fcccb4`. These are attributed evidence, not this reviewer's runs.

No product review or rerun was performed. Developer-owned product edits remain excluded. This PASS approves the additive RED contract and does not close D3 or assert the subsequent product fix passes.
