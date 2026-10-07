# WMS-681: independent frozen corrections review · 2026-10-07

This is the independent frozen-test correction review by actual **gpt-6.1-sol**, reasoning effort **high**, on 2026-10-07. It approves the exact correction chain and its legitimate semantic scope. It does not supply product acceptance, a new product review, CI, deployment or physical-print proof. No Astra identity or verdict is claimed.

AGENTS.md and both owner/failure case libraries were read fully before the verdict. origin/etalon was fetched and verified at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`; active worktrees have identical rule/library blobs: AGENTS `510ce8febd402f9a78a5f1fddd964d99283afaff`, owner-cases `19a12f266ef38e697e1b30cf2f3da3d589e8cce2`, failure-cases `48263ba41e8fdb67c744864f7ec52a26b768598b`. The root frozen-contract-audit README/inventory were used as inventory, not approval or an up-to-date chain. Git objects, full original-to-final diffs and each correction's parent delta were inspected. Existing run evidence below is attributed to its actual session; this reviewer did not rerun suites, install dependencies, invoke agents or exercise production/browser/printing.

The original contract, every listed correction and reviewed source are Git ancestors of this report's branch. Integrating this proof must preserve the report/source commit as an ancestor; copying its Markdown or cherry-picking only its content is not ancestry proof. Checker/policy/ledger binding is a later moderator/testwriter operation; none was changed by this reviewer.

**Verdict: PASS for the entire two-file chain**, original `75b7d074` → `a4a54b9` → `0e39bf4`. Both of the original frozen files changed, so this is an explicit full 2/2 chain approval, not a strict-subset exception or approval only of the last 48 inserted lines. There are no ancillary files in either correction.

AST comparison found all 35 original backend test functions retained and four additions. Only two old functions differ: the concurrent-other-group case assigns B its own order so the unique order-position constraint no longer prevents reaching recovery; the foreign-tenant test merely renames an unused local binding. Its original concurrency, one-create, exclusion-of-B and physical/business-state assertions remain. The fixture correction restores a valid independent physical group; it does not excuse duplicate recovery or relax tenant scoping.

Added guards cover a pending readback already owned by B, confirmed readback followed by QR-fetch failure, durable first sticker after the second fetch fails, and both historical marker prefixes. They require no blind create or reassignment of another group's trbx. The controlled boundary calls actual mock WB sticker handling, persists A1 and checks a subsequent ordinary workspace GET exposes ready A1 while A2 remains absent; HTTP 502/504 is still failure, not fake successful recovery.

The DOM partial case initially changed two inputs from already-ready/missing to both missing, so success must be acquired in the attempt before A2 fails. The existing C9 case still covers preserving an initially ready asset. `0e39bf4` adds the distinct real HTTP-error/no-success-body case and requires a fresh workspace GET, A1-only preview, visible error/missing count, no A2 image and no `/boxes` create. The zero-ready case still requires no print window and successful explicit retry after network restoration. Ozon uses its actual existing action text, while retaining no WB retry and normal label preview assertions. Consistent A/B supply IDs and added delayed-single-response coverage strengthen isolation; HTMLButtonElement selectors fix types without changing assertions. R4–R7 remain intact.

Active progress.json identifies original tester `01a112cc-24e7-7b92-839e-9c95cb3a0674`, replacement testwriter `01a112fa-2b80-7883-8d15-9c403173230e`, developer `01a112e3-9966-7d31-bb2e-23f6f03663ee`, and final independent review `01a11333-77cf-7ba3-8d9c-356f1f6aac80`. The testwriter's actual tester_repair_contract.jsonl thread and command results bind both correction commits; tester_repair-handoff.md and tester_repair-r6-handoff.md record their scopes and runs. The original tester's reverted role-boundary incident is disclosed in progress.json and is not attributed as these corrections' product work.

The first repair records meaningful product RED, not the original duplicate-order fixture error. The R6 handoff records backend 1 PASS and DOM 1 FAIL/28 PASS on `ba59fedd6f6b0c9557bf7dc46bce32c2625e81a4`, specifically the absent recovery workspace GET. Current review_r6_final.result.md, rather than stale review.result.md FAIL, independently records PASS on `de76be359ea4c02a0ee70aa204eae2e853c47b1f`, with backend 1 PASS and DOM 29 PASS. This correction review does not promote those results into browser acceptance, PostgreSQL multi-worker proof, physical printing or full CI. The active acceptance document remains incomplete.


## Immutable Git binding

Reviewed source snapshot: `a9b4a6194eb3d63536297874d0e60a5d666c9d15`. Original contract: `75b7d074f00ea6ad1b63b1ba229c4d9b2333f8f9`. Final correction: `0e39bf4ed8f444f5b00e1287aa27f1161596a101`. Branch: `codex/night1007-681`.


Original frozen file list, with original → final full blob IDs:


- `backend/tests/test_fbs_packing_box.py`: `7f3d8754f68c2da1fd96ecdfb21f92ce1a6297c3` → `1cca9c86a4e50842919d0ca4aec4c57607c0fe7a`.

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`: `c6647a611da4d6f92d9afe0c3cd8990a0c7b9fc4` → `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3`.


### a4a54b9cc72e7c1cdd242c2b0726e9761cf1f385 · PASS

Source/parent: `d3fad344bd35c4ca4b96fbe64ea2c36429fdd41d`. Kind: `exact_fixture_correction`. Repair independent order assignments, consistent A/B supply fixture and actual Ozon action; add confirmed, foreign-owned, durable partial and legacy-key guards.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_fbs_packing_box.py`: `7f3d8754f68c2da1fd96ecdfb21f92ce1a6297c3` → `bf92738de529c1ca4882240a0b617df5db82dedd`.

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`: `c6647a611da4d6f92d9afe0c3cd8990a0c7b9fc4` → `c809482c9eb151425e9031e33b06246cb1e6039a`.


Changed original frozen files: `backend/tests/test_fbs_packing_box.py`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`.

Other touched files: none.



### 0e39bf4ed8f444f5b00e1287aa27f1161596a101 · PASS

Source/parent: `ba59fedd6f6b0c9557bf7dc46bce32c2625e81a4`. Kind: `exact_fixture_correction`. Add real partial-QR HTTP error followed by workspace readback; retain ready-label/no-create and zero-ready business guards.


Exact touched files, parent blob → correction blob:


- `backend/tests/test_fbs_packing_box.py`: `bf92738de529c1ca4882240a0b617df5db82dedd` → `1cca9c86a4e50842919d0ca4aec4c57607c0fe7a`.

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`: `c809482c9eb151425e9031e33b06246cb1e6039a` → `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3`.


Changed original frozen files: `backend/tests/test_fbs_packing_box.py`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`.

Other touched files: none.


Only this new review report is owned and committed by this reviewer. No tests, product, requirements, checker, policy or ledger edits were made.
