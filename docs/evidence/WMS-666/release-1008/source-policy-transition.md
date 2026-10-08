# WMS-666 source-policy transition for release S

The accepted product candidate is `ffb524e2950cfb250993ad4db3b0f394ca55f735` (P). Independent product acceptance is recorded in [`final-product-acceptance-ffb524e.md`](../independent-review-1008/final-product-acceptance-ffb524e.md), copied byte-for-byte from reviewer commit `a9fe9577ba25f5d18f6e96be59574fcf6b6fbbaa` (SHA-256 `8af218e6cf782c238c06460f889376c45ccc94e9cbe84356fbd3cc60a38e08dc`). Acceptance is scoped to software behavior and does not claim live Wildberries acceptance, physical paper, full CI, or deployment.

S updates the existing `guards/PROCESS_CONTRACTS.json` using the trusted process source `39d1afdc8f37cdfda3c7768804ccccc3c9ad4e6e`, whose base is `a5df04f1560de0eaaf855199065936cb22a222b1`. The candidate registry retains all 282 original protected paths, all 29 original suites and their report/format/exact settings, and all 1,715 original cases. It restores the three missing protected files from the trusted source and adds the separately reviewed partial-ack and WMS-666 scan-recovery cases without deleting or renaming earlier cases. The original 37 WMS-477 case identifiers remain present.

The added permanent UI checks are kept in their existing test files. Commit `32ef4945aeb2bb3dcdc51f7879c181e63735b207` adds the ordinary-row validation and queued-Escape checks. The accepted partial-ack checks remain in `MarkingPrintDialog.availability.dom.test.tsx`. Their bytes and required Vitest case names are included in the updated candidate registry. The C2 mixed-task case is retained as well. No test expectation or negative guard is weakened here.

The exact restored protected files are:

- `scripts/deploy/retain-web-assets.py` — SHA-256 `bfb6d0bc7d465bf8c3e9b194a8415f6d257f7097db7426e0ab5362924c78b64c`.
- `scripts/ci/tests/test_retain_web_assets.py` — SHA-256 `776f150a5c489291b7bb38120c2cab036a3f1892667db9b6043c8d581be9a6df`.
- `frontend/tests/fixtures/wms666AcceptedRecoveryHistory.json` — SHA-256 `615e82d1b6dd98ca4117ae6c0fd3f3f503bc3eceaab2fea0562b61bd1b3de969`.

The existing WMS-517 correction-history ledger was also restored byte-for-byte from the trusted source (`docs/reviews/contract-corrections/WMS-517.json`, Git blob `5bbfb0c7dcf6cf8bdd035c97120d85ca472382ca`). The current WMS-517 requirement table now points to literal parameterized test templates instead of expanded runtime titles or a setup hook. This is reference maintenance; it does not change the tests.

The source-policy upgrade is not self-authorizing. The trusted-main bootstrap currently pins the earlier source. A separate, reviewable main-anchor change must identify the exact S commit under the existing `process_bootstrap.json` mechanism. That anchor change is not merged by this work. The task-document checker, full picking suite, mandatory exact-S CI, and deployed-SHA readback remain release gates; this document does not mark any of them green.
