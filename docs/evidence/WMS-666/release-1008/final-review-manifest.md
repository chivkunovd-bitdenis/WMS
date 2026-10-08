# WMS-666 release evidence manifest

Status as of this manifest: candidate `ffb524e2950cfb250993ad4db3b0f394ca55f735` is pushed on `codex/wms666-packing-release-1008`. Product acceptance is not final and production release is not authorized by this manifest. M26 is accepted at the focused UI/native layer by source equivalence; main screen and renderer checks passed. One exact-candidate full picking run has a single `group-lost-set` failure; an isolated rerun of that case passed, while the full picking suite still must pass on final source-policy S.

## Exact-candidate backend and static checks

| Evidence | Candidate/test identity | Result and limit |
|---|---|---|
| `exact-ffb524e/backend-targeted.txt` | Product `ffb524e2950cfb250993ad4db3b0f394ca55f735`; `fbs_marking_service.py` blob `0faa412f4a9ffac84e4d7e42cd8e9dc8ac059ca4`; frozen test commit `9627f455a` | 9 focused tests passed on isolated `sqlite+aiosqlite:///:memory:`. Not PostgreSQL concurrency. |
| `exact-ffb524e/static-checks.txt` | Same product SHA; changed service/test files identified in the log | Focused Ruff and targeted mypy passed. |
| `exact-ffb524e/baseline-red.txt` | Product base `7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc`, frozen tests `9627f455a` | Reconstructed result summary only; original pytest stdout was not saved. Do not cite as raw output. |
| `exact-p-local-checks-manifest.md` and its referenced logs | Earlier candidate `b6d23148f1571d08d13d83c6179c385e2f6a1efc` | 13 focused contracts, 119/121 in-memory FBS-KIZ tests with two dialect-limited concurrency failures, separate PostgreSQL concurrency tests, stale-pool DOM, Ruff, mypy, TypeScript and build. Historical at b6; not a full ffb backend suite. |

## Exact-candidate browser and CI checks

| Evidence | Candidate/test identity | Result and limit |
|---|---|---|
| `whole-process/m25-ui-refusal-unlink-ffb524e-r3/` | Product `ffb524e`; whole-process runner SHA-256 `4411c8270426df35d7a200f09c5cc46faef49e01b5ea1df0e5e5a3f4be512e00` | Scoped PASS: manual replacement, real loopback WB PUT refusal, UI resync, exact-row unlink, receiver and DB readback. This is a synthetic local WB endpoint, not a live marketplace. Astra independently reviewed the run. |
| `current-p-matrix-m01-m43.md` | Matrix distinguishes `b6` execution from `ffb` execution and source-equivalence claims | Current status per M01–M43, evidence layer, and remaining gaps. It records M26 source-equivalent UI acceptance and CI as open rather than carrying old PASS labels forward. |
| GitHub Actions run `37722109811` | Candidate `ffb524e2950cfb250993ad4db3b0f394ca55f735` | Main-screen workflow success (24/24 as reported); [run](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37722109811). |
| GitHub Actions run `37722109782` | Candidate `ffb524e2950cfb250993ad4db3b0f394ca55f735` | Base shard passed; extended shard finished 39/40 with failure `group-lost-set`: `fbs-picking/extended.mjs:179` expected `unload-pick-error` visible, but it was absent. Artifact `11526153288`. A later isolated rerun of that exact case passed after exercising lost HTTP-200→visible error→same-key recovery; the complete extended shard still needs a green final-S run. [Run](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37722109782). |
| GitHub Actions run `37722415370` | Explicit `application_ref=ffb524e2950cfb250993ad4db3b0f394ca55f735` | Linux renderer workflow passed. [Run](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37722415370). |

The local task-document guard was also run as `python3 scripts/ci/check_task_documents.py origin/etalon` and saved in `task-document-guard-origin-etalon.txt`. It exits 1 with 9 WMS-517 multi-reference cells using semicolons unsupported by this checker, plus 16 WMS-666 protected-guard verification mismatches. The task/contract checker no longer reports a missing `Тест` column after the appendix was corrected. WMS-517 links need separator normalization in the source-policy stage; WMS-666 guard digests need the reviewed P/R→S source-policy update. Frozen tests were not rewritten to silence the checker. This local check is not a pass.

The earlier exact-b6 CI report is `ci-verification-b6d23148.md` in the renderer evidence worktree, from commit `e98bd28bbf50aba8824fab853f986b7c7f39a835`. It records main-screen 24/24 (`37708207415`), picking (`37708207401`) and renderer (`37709255731`). These are historical candidate runs; ffb jobs above are tracked separately.

## Supporting exact-b6 UI/native evidence

The b6 results below remain labeled with their actual run SHA in the current matrix. The runtime delta from b6 to ffb includes `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` ordinary-row scan/Escape routing and `backend/app/services/fbs_marking_service.py` WB verdict handling. Do not infer whole-tree identity from those old runs. The M26 UI/native predicates have a separate Astra-accepted exact source comparison from 7f to ffb; other rows remain historical evidence for their named path and boundary.

- Browser matrix: `browser-matrix/m24-selected-neighbor-r4/`, `m41-r7-final/`, `supply-id-controls-r5/`, `supply-id-clear-r3/`, `supply-id-r1/`, `supply-ids-r1/`, and `ozon-scope-r1/`.
- Named-supply actions: `whole-process/group-packall-r3/`, `group-boxes-r19/`, `menu-transfer-r1/`, `menu-skip-r3/`, and `rejected-filter-r4/`.
- Native Handler checkpoints: `c975fcdf57b30cc54473780e269d48b822b84a8d` and `646ad87639ee082f198fe191bb180a6f5a04c175`; QR continuity and grouped manual→native scan evidence are in that checkpoint's `run-b6d23148` paths. The native grouped scan segment passed, while a later ancillary box request returned fixture `403 missing_marketplace_token`; the separate M33 software box run passed with the local synthetic adapter.
- M26 focused evidence: native checkpoint `0ca1ccb6207c0d6d072471723686bac396556ac3`, permanent DOM guards `32ef4945aeb2bb3dcdc51f7879c181e63735b207`, frozen browser RED `dabe1818c6e31ed3085c6257dddeb7018fb0eaf5`. Astra accepted frontend/native source equivalence from 7f to ffb because the ffb backend verdict guard is outside those predicates; full CI must execute the permanent guards.

## Explicit boundaries

This release set does not claim a live WB operation, production deployment, physical printer queue, or printed paper. The local WB receiver is a loopback emulator; browser manual printing uses Chromium HTML/PDF capture; native Handler receipts are software receipts. Full generic CI for final source-policy metadata S, final independent product acceptance R, and deployment are separate gates and are not claimed complete here. The observed picking failure must be resolved or independently classified before release.
