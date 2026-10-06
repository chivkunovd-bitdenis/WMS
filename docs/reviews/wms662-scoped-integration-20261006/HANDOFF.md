# WMS-662: scoped integration for independent delta review

The scoped integration is saved on `codex/wms662-scoped-integration-20261006`
in a new permanent worktree of the same name under `WMS/.worktrees/`.
This prepares a reviewable candidate for the future combined release. It does
not declare new analyst acceptance, independent review, complete CI, or deployment.

## Exact identities and preserved history

- Fresh fetched integration base: `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`.
- Accepted source: `d640d6da1e5ddb16a5628b480ac893b541e3644b`, still published as PR #386 HEAD.
- Historical comparison base: `0f1460b023700a99f17b504d6af3934a02bc68cc`.
- First commit, frozen tests: `2006171f0feae5513f887b471125ecae1a96c2ae`, subject exactly `WMS-662: контракт тестов`.
- Second commit, scoped code and original proofs: `a53f0002040baea4ceec90144e675b2055a1f11d`.
- A following documentation-only commit records this handoff and local integration results. Review the published branch HEAD; its product code is identical to the second commit.

All 11 accepted test files are byte-identical to the source. The original
test-writer contract `77dc127344ff164417cc13c8d2b218af3ac09266` and its transfer
`43f4bdbae7fff1fcbaf7a47d7293a7faaf5428a1` are preserved as provenance, along with
the subsequent per-file contract/correction history. No new pre-fix RED run is
claimed. See `test-provenance.json` and `original-testwriter-provenance.json`.
The current contract precedes the code commit and remains protected by the
unmodified document checker.

The full accepted WMS-662 requirements, C1–C19 verdicts, 62 historical review/proof
files, and the exact WMS-662 backlog entry are retained. Requirements and proof
blobs were copied without edits, including historic FAILs and their limitations.
Shared historical `analysis.md` remains intact because it contains WMS-662 sources
and boundaries; its discussion of other tasks does not add their introductions
to this candidate.

Only the unrelated unfinished introduction documents `docs/requirements/WMS-663.md`
and `docs/requirements/WMS-675.md`, plus their two introduced backlog entries,
were omitted from the mixed source delta. They remain in the source branch.
References to those separate tasks inside legitimate WMS-662 requirements and
proofs were not removed. No verdict, test expectation, guard, CI workflow, or
document-checking rule was weakened to make the gate pass.

## Exact product delta and fresh etalon preservation

`product-vs-etalon.patch` contains the exact product delta: nine backend service
files and the existing FBS supply workspace. There are no API, model, migration,
dependency, shared stock-publishing, or global component changes in this delta.
The original C19 scripts/workflow are preserved literally. That workflow still
targets the original source branch and pins the accepted UI product; it is
historical proof infrastructure, not a fresh integration-SHA browser result.

Eight backend service files match the accepted source blobs exactly. Two product
files combine the accepted delta with fresh etalon changes:

- `backend/app/services/fbs_shipment_service.py`: retain the etalon WB error presentation while applying the original exact-snapshot Ozon handoff and missing-write-off recovery delta.
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`: retain the etalon delivery errors, assembly behavior, and WB QR protection while applying the original order status chip in the composition row.

Both shared files applied cleanly through a three-way patch. Their added and
removed line sequences relative to fresh etalon equal the accepted source delta
relative to the historical base. No manual conflict resolution or product
adaptation was needed. `preserved-etalon-vs-source.patch` shows precisely the
etalon changes retained on top of the accepted product.

`scope-preservation.json` accounts for all 91 source-delta paths: 86 exact source
blobs, two shared product files with identical changed-line payload, the scoped
backlog insertion, and two omitted unrelated introductions. It also verifies
74 etalon-only changed files remain byte-identical. The complete etalon backlog
outside the inserted accepted WMS-662 entry is preserved.

WMS-681 QR protection is retained from the integration base, including unchanged
packing-box service/API/tests and the QR protections inside the shared workspace.
The owner-supplied expected production SHA `6838f11` is context for the future
combined release; production was not contacted or independently checked here.
This candidate is not a release based on that production SHA. A future combined
candidate must reconcile its actual production/base ancestry separately.

The stock boundary remains the accepted one: ordinary status refresh does not
introduce a new write-off/billing policy. The existing scoped WMS-created supply
with exact evidence of cabinet handoff may complete only its missing quantity,
once. Original scope, cancellation, split, billing, and unknown-outcome behavior
are preserved; no new product requirement was introduced.

## Local integration verification

The targeted backend run passed **20/20** cases on the integrated product:
both approve-scope races; confirmed checkpoint recovery; all C14 scope-isolation
variants; ordinary delivery without forced picking/packing; QR failure and QR-only
retry; and the fresh etalon WMS-653 safe-error scenarios. It used isolated SQLite,
fake marketplace transport, and two workers. See `backend-integration.txt`.
This is a focused integration check, not a fresh full C1–C18 or PostgreSQL run.

Ruff and Mypy passed for all nine changed backend service files. The unmodified
document gate and backlog gate passed against the fresh etalon SHA after the
integration code commit. Logs are stored alongside this report.

The targeted frontend DOM run passed **6/6** tests across two files: frozen C19
and the five WMS-653 error-presentation cases from fresh etalon. Actual output is
recorded in `frontend-integration.txt`, including MUI warnings about the existing
`packing` tab value; no warning was suppressed or product behavior changed.
These tests execute the integrated supply workspace and preserve the frozen C19
expectations. They do not replace the accepted remote API/PostgreSQL/visual proof
or claim a new manual browser acceptance. No Mac browser, full local suite,
production access, merge, deployment, or secret-management action was performed.

Reproduction from this worktree uses the existing Python environment and shared
frontend dependencies; no package files were changed:

```sh
python3 scripts/ci/check_task_documents.py 4b298efc95be7b4b6b7fe5665be9f3671f1fe747
./scripts/ci/check-backlog-ref.sh 4b298efc95be7b4b6b7fe5665be9f3671f1fe747
cd backend
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 2 \
  tests/test_wms662_approve_scope_race.py \
  tests/test_wms662_observed_handoff.py::test_c6_confirmed_checkpoint_local_recovery \
  tests/test_wms662_observed_handoff.py::test_c14_scope_isolation \
  tests/test_fbs_shipment_warehouse_sc.py::test_fbs_shipment_deliver_allows_optional_pick_pack \
  tests/test_fbs_shipment_warehouse_sc.py::test_warehouse_sc_deliver_qr_failure_keeps_confirmed_delivery_and_retries_qr_only \
  tests/test_fbs_shipment_warehouse_sc.py::test_retry_supply_qr_never_calls_wb_deliver \
  tests/test_fbs_shipment_warehouse_sc.py::test_wms653_pending_kiz_response_is_safe_but_operation_keeps_raw_context \
  tests/test_wms653_delivery_error_contract.py
cd ../frontend
./node_modules/.bin/vitest run \
  src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx \
  src/screens/v2/FfFbsSupplyWorkspace.wms653.dom.test.tsx \
  --configLoader runner --maxWorkers=1 --minWorkers=1 --no-file-parallelism
```

## Existing CI result and next independent stages

Live GitHub metadata still identifies CI `37444812092` with source HEAD
`d640d6da1e5ddb16a5628b480ac893b541e3644b`: backlog **failure**, backend
**cancelled**, frontend-build and guards **success**. The original unblock report
records the GitHub internal-error annotation and the unrelated unfinished
document failures; it is copied as `original-ci-unblock-result.txt`. The cancelled
backend is not classified as failed tests or as a completed backend PASS.

Remote C19 run `37443974022` remains **success**. Its proof-run HEAD is
`1b4352781ce472ff702052d19f49c62b05aea026`, while its preserved product manifest
pins UI product `7fb13f788a2d98efaa575493856b5b504363f3af`. Original backend review
`c9f9dd7df432f487fd1e440f145e4c8740030807`, UI review
`a998dafa7fa9785b0a4056ca127e413aa2b1cd80`, and proof preservation
`1cf03cc7ec283ebe5bb034947172902474e617aa` remain historical accepted evidence.
They are not relabeled as reviews of the new integration SHA.

The next independent reviewer is **Astra, explicit effort high** for the exact
published branch SHA. Read fresh `AGENTS.md`, accepted requirements, both owner/
failure case libraries, source reviews, the two exact patches, and the scope
manifest. Focus on fresh-etalon coexistence, unchanged tests and proofs, retained
QR/error behavior, and the ordinary-refresh versus proved WMS handoff boundary.
No re-review of unchanged historical behavior is requested without new grounds.

After independent delta review, the analyst must assess the integration against
the preserved requirements, then full CI must run on the exact resulting SHA.
The preserved accepted-source verdicts are provenance, not a fabricated new
integration acceptance. No new PR or full CI was triggered in this preparation;
the source PR #386 and all source/other worktrees are preserved. Publish this
branch without merging it into main or etalon; retain the single combined-release
requirement.
