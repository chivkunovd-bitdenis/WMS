# WMS-658: independent frozen corrections review · 2026-10-07

This is the independent frozen-test correction review by actual **gpt-6.1-sol**, reasoning effort **high**, on 2026-10-07. It approves the exact correction chain and its legitimate semantic scope. It does not supply product acceptance, a new product review, CI, deployment or physical-print proof. No Astra identity or verdict is claimed.

AGENTS.md and both owner/failure case libraries were read fully before the verdict. origin/etalon was fetched and verified at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`; active worktrees have identical rule/library blobs: AGENTS `510ce8febd402f9a78a5f1fddd964d99283afaff`, owner-cases `19a12f266ef38e697e1b30cf2f3da3d589e8cce2`, failure-cases `48263ba41e8fdb67c744864f7ec52a26b768598b`. The root frozen-contract-audit README/inventory were used as inventory, not approval or an up-to-date chain. Git objects, full original-to-final diffs and each correction's parent delta were inspected. Existing run evidence below is attributed to its actual session; this reviewer did not rerun suites, install dependencies, invoke agents or exercise production/browser/printing.

The original contract, every listed correction and reviewed source are Git ancestors of this report's branch. Integrating this proof must preserve the report/source commit as an ancestor; copying its Markdown or cherry-picking only its content is not ancestry proof. Checker/policy/ledger binding is a later moderator/testwriter operation; none was changed by this reviewer.

**Verdict: PASS for the full original → final frozen correction chain**, including both changed frozen files in `4769712`, not only the last marking-file delta. All four original frozen files are enumerated below. The normalized-identity regression and frontend dialog files are byte-identical to the original. Python AST comparison (ignoring source locations) found all 16 original marking-import test functions unchanged, with four additions, and all five original WB-honest-sign test functions unchanged, with one addition. No original test was removed.

`4769712` strengthens C22: a full CIS/DataMatrix match must not hide substitution of the supplier label or raster image. Both PDFs are actually decoded and compared before auditing; assertions require the correct first divergence/evidence gap. Its additional C19/C20 guard requires raw WB nmID to belong to the product and rejects apply before writing. The exact diff of its sole ancillary file, own requirements WMS-658.md, changes only C19/C20/C22 Test references; expectations and verdicts remain unchanged. This is additive bug coverage within existing R9–R11, not a new business rule or removal of the original guards.

`16a58ac` added a legitimate positive crop case, but its initial fixture did not draw a frame: the parser retained a 600×800 page, and the original frozen test passed before the fix. It must not be recorded as historical RED. The late `ff86e912` correction, after product `6e9575ecfd83d1c933d8cf017c1aa071fb49ebeb`, adds the frame and asserts the actual saved page is 220×220. It preserves the payload, unchanged-label and no-evidence-gap expectations. The original tester's separate diagnostic run loads the audit module from `16a58ac` in memory and records 1 meaningful FAIL on `label_artifact_pdf`; current crop records 1 PASS. This late repair is honestly approved as a fixture correction, not retroactively described as tests-before-code.

`a9443e3` adds a meaningful negative case: two pages decode the same complete CIS while carrying different visible articles; permitted import dedup produces one code but the audit must retain source-layout uncertainty. All preliminary page/payload/article/parser assertions passed, followed by RED on the missing `source_to_artifact_layout` gap before product `441ce28536837b70a3e6fc8b6d4b1e6121f264b2`. Import dedup is not forbidden, and uncertainty is not fabricated as a definite first divergence.

Separate-role provenance is supported by original tester session `01a112cb-44be-7ce1-8cfb-f23674c8d994`, distinct from developer `01a112d3-882f-7a62-b9e1-65ce1e12fa63` in active progress.json/events. Root lane `658/{review-regression-tests,crop-regression-tests,crop-fixture-correction,ambiguous-source-test-contract}-events.jsonl` each records the original tester thread, corresponding test-only role prompt and exact published correction result. Git author alone was not used to infer a role or model; the recorded historical tester/developer model differs from this reviewer's model.

Existing product review `e8e3208345b93ff8fcdec159bf2779fbe8d00f89` independently records technical PASS after F4, five focused PASS and same-sheet ambiguity controls. Current PostgreSQL receipt at `953c45ae338b811bf583175c333ac4a4a2f14724`, product snapshot `a9cc021f90c9412875c79cef75836fab228a8df7`, records 9 PASS/0 skip for the unchanged identity concurrency contract. These are existing evidence, not this reviewer's runs. Historical R11 incident artifacts, live R10 and browser/physical-print acceptance retain their documented limits. This correction PASS closes none of them.


## Immutable Git binding

Reviewed source snapshot: `2a7d3100d0405762761c6884bb1e0e142dfcdfc1`. Original contract: `6a5ff0e39ea05d0503908a7ca1cb9139018db24d`. Final correction: `a9443e3f3ceee39f3dae04d72bc3cf61fc75a1dd`. Branch: `codex/night1007-658`.


Original frozen file list, with original → final full blob IDs:


- `backend/tests/test_wms658_marking_import_contract.py`: `9661a123265f1ea75d084fbf1b6da13d34481856` → `6e76bf1d4bcf38ff59341e6d3459346313421e6c`.

- `backend/tests/test_wms658_normalized_identity_regression.py`: `43517c0adc7df0f257befb1c229f1555c366f044` → `43517c0adc7df0f257befb1c229f1555c366f044`.

- `backend/tests/test_wms658_wb_honest_sign_contract.py`: `9bf03cba6847065ee8b59030aece6f1695b4d22d` → `946ec81ef52d7fb888379b327dcd74be8ce52a99`.

- `frontend/src/screens/shared/MarkingImportDialog.wms658.test.ts`: `d5f4525b6f2775f8a239650c859786d29832abbc` → `d5f4525b6f2775f8a239650c859786d29832abbc`.


### 4769712e70ca825dbc8d1f98ea632343e5b25b57 · PASS

Source/parent: `6e0926102c6d7e71aee001b1ccda7bc8fc9bdf1b`. Kind: `exact_fixture_correction`. Additive source-label/raster-image substitution and raw nmID mismatch coverage; own requirements Test links only.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_wms658_marking_import_contract.py`: `9661a123265f1ea75d084fbf1b6da13d34481856` → `0a267634279a868660cbc014c6312bbf4cfc7798`.

- `backend/tests/test_wms658_wb_honest_sign_contract.py`: `9bf03cba6847065ee8b59030aece6f1695b4d22d` → `946ec81ef52d7fb888379b327dcd74be8ce52a99`.

- `docs/requirements/WMS-658.md`: `88a79ede1de989790d4cf814d208f3615420740f` → `a1625ab8ba3c943cb7d8b7ed89c1db67f777eb58`.


Changed original frozen files: `backend/tests/test_wms658_marking_import_contract.py`, `backend/tests/test_wms658_wb_honest_sign_contract.py`.

Other touched files: `docs/requirements/WMS-658.md`.



### 16a58ac82df16fada0571d249b0827e8900527ad · PASS

Source/parent: `24fcbdabc5560012e5ac849c8ae229e4ba740d28`. Kind: `exact_fixture_correction`. Additive valid supplier-page crop case; original fixture did NOT reproduce crop and is not approved as historical RED.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_wms658_marking_import_contract.py`: `0a267634279a868660cbc014c6312bbf4cfc7798` → `ff481b1e693884c103e46624a05807f3120bc040`.


Changed original frozen files: `backend/tests/test_wms658_marking_import_contract.py`.

Other touched files: none.



### ff86e9126c0ac87b02cd0588c17a5884e964a246 · PASS

Source/parent: `f6f382e684fab4d9da291d439a61b452a01666b2`. Kind: `exact_fixture_correction`. Late crop-fixture repair: draw actual frame and assert actual 220x220 crop, retaining audit assertions.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_wms658_marking_import_contract.py`: `ff481b1e693884c103e46624a05807f3120bc040` → `cee12538b9d752f040edcc2c7a892726d307d68d`.


Changed original frozen files: `backend/tests/test_wms658_marking_import_contract.py`.

Other touched files: none.



### a9443e3f3ceee39f3dae04d72bc3cf61fc75a1dd · PASS

Source/parent: `3df33bab79ab27d5612271e351f06f2a5edf17e6`. Kind: `exact_fixture_correction`. Additive same-CIS/different-layout ambiguity within one source PDF; pre-product meaningful RED.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_wms658_marking_import_contract.py`: `cee12538b9d752f040edcc2c7a892726d307d68d` → `6e76bf1d4bcf38ff59341e6d3459346313421e6c`.


Changed original frozen files: `backend/tests/test_wms658_marking_import_contract.py`.

Other touched files: none.


Only this new review report is owned and committed by this reviewer. No tests, product, requirements, checker, policy or ledger edits were made.
