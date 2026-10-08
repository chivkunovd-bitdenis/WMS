# WMS-666 source-policy transition for release S

The accepted product candidate is `ffb524e2950cfb250993ad4db3b0f394ca55f735` (P). Independent product acceptance is recorded in [`final-product-acceptance-ffb524e.md`](../independent-review-1008/final-product-acceptance-ffb524e.md), copied byte-for-byte from reviewer commit `a9fe9577ba25f5d18f6e96be59574fcf6b6fbbaa` (SHA-256 `8af218e6cf782c238c06460f889376c45ccc94e9cbe84356fbd3cc60a38e08dc`). Acceptance is scoped to software behavior and does not claim live Wildberries acceptance, physical paper, full CI, or deployment.

S updates the existing `guards/PROCESS_CONTRACTS.json` using the trusted process source `39d1afdc8f37cdfda3c7768804ccccc3c9ad4e6e`, whose base is `a5df04f1560de0eaaf855199065936cb22a222b1`. The candidate registry retains all 282 original protected paths, all 29 original suites and their report/format/exact settings, and all 1,715 original cases. It restores the three missing protected files from the trusted source and adds one standalone partial-ack test file plus five separately reviewed UI cases and three backend verdict cases (the final refused-KIZ regression and the C5 missing-kind/other-value controls), for 286 protected paths and 1,723 cases. No original case is removed or renamed; the three WMS-477 identifiers are restored exactly.

The permanent UI checks remain discoverable by the existing unfiltered frontend Vitest suite. Commit `32ef4945aeb2bb3dcdc51f7879c181e63735b207` adds the ordinary-row validation and queued-Escape checks. The partial-result acknowledgement case is isolated in `MarkingPrintDialog.partialAck.wms666.dom.test.tsx`; the pre-existing availability suite is restored byte-for-byte to its `28a7999f` contract version. The C2 mixed-task case is retained as well. No test expectation or negative guard is weakened here.

The exact restored protected files are:

- `scripts/deploy/retain-web-assets.py` — SHA-256 `bfb6d0bc7d465bf8c3e9b194a8415f6d257f7097db7426e0ab5362924c78b64c`.
- `scripts/ci/tests/test_retain_web_assets.py` — SHA-256 `776f150a5c489291b7bb38120c2cab036a3f1892667db9b6043c8d581be9a6df`.
- `frontend/tests/fixtures/wms666AcceptedRecoveryHistory.json` — SHA-256 `615e82d1b6dd98ca4117ae6c0fd3f3f503bc3eceaab2fea0562b61bd1b3de969`.

The existing WMS-517 correction-history ledger was also restored byte-for-byte from the trusted source (`docs/reviews/contract-corrections/WMS-517.json`, Git blob `5bbfb0c7dcf6cf8bdd035c97120d85ca472382ca`). The current WMS-517 requirement table now points to literal parameterized test templates instead of expanded runtime titles or a setup hook. This is reference maintenance; it does not change the tests.

The source-binding fixture now adds the independently accepted product SHA `ffb524e2950cfb250993ad4db3b0f394ca55f735` and R record `a9fe9577ba25f5d18f6e96be59574fcf6b6fbbaa` while retaining prior accepted history and explicit rejection of self-selecting references. The candidate workflow uses that exact product SHA as `product_scope.py --trusted-ref`; it also retains the trusted `maxWorkers=2` frontend run and invokes `test_retain_web_assets.py`, which supplies the 14 protected CI-shard cases. `scripts/deploy/prod-update.sh` is byte-equivalent to the trusted 39d version and keeps the old web assets referenced by already-open operator tabs during deployment.

The renderer test correction in `ec44815fe063611723c2794781ff8b1a9288bf52` has an exact correction record in `docs/reviews/contract-corrections/WMS-666.json`, linked to Astra’s bounded report. The correction changes only the approved WMS-657 numeric WB fixture and WMS-673 established empty-location wording; layout, fresh-read, and output guards remain intact.

The source-policy upgrade is not self-authorizing. The trusted-main bootstrap currently pins the earlier source. A separate, reviewable main-anchor change must identify the exact S commit under the existing `process_bootstrap.json` mechanism. That anchor change is not merged by this work. The task-document checker, full picking suite, mandatory exact-S CI, and deployed-SHA readback remain release gates; this document does not mark any of them green.

## Local checks on the committed candidate

The following checks ran after commit `2a9643159a935cf6d175b47355f2356be6623ef5`, with the trusted source, registry, and source-binding fixture already committed:

- `python3 -m unittest scripts.ci.tests.test_ci_release_additions` — **7 tests, OK**.
- `python3 scripts/ci/check_task_documents.py origin/etalon` — **Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают.**
- `python3 scripts/ci/product_scope.py --root . --trusted-ref ffb524e2950cfb250993ad4db3b0f394ca55f735` — **`{"unapproved_product_paths": []}`**.

These local checks validate the source-binding/workflow contract, required task-document fields, and product-tree equality with accepted P. They do not replace exact-S full CI, full picking, or deployment readback.
