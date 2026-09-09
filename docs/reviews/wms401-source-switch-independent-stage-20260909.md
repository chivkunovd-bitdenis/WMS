# WMS-401 — independent review and staging checkpoint before reboot

Independent read-only review: **PASS** for published source `aa7de3de8a965d1088ec44db1bb5f41a766d9dc5`, based on production `a75ed98a03e0500e41a69e5b617a27587bed9792`. The remote branch `codex/wms401-source-switch` was verified at that SHA. Only `backend/app/services/fbs_picking_service.py` and its existing targeted test file changed; API schemas, container resolver, location resolver, migrations, frontend and mobile code are unchanged.

## Verified behavior and review limits

The mobile ViewModel retains its selected container in subsequent scan requests. Previously `pick_scan` only resolved a container barcode when both saved container fields were empty. A new box barcode therefore fell through to product lookup and returned `wrong_product`. The change reuses the existing container resolver before processing the saved source, returning the newly scanned container and its actual location before any product pick. A resolver miss continues the original product path with the saved source intact.

The incomplete-pair XOR guard is now before container resolution, after the unchanged location-scan return. Tenant/warehouse scope and ambiguity handling remain in the existing resolver. The source validation and location-consistency guards still apply to product scans. No packing operation, navigation blocker, inventory movement or reservation logic was added.

Keeping the source on a product lookup miss in the mobile list matters: the workspace publishes the product barcode, while the backend also recognizes a different order barcode. Clearing the source merely because the APK did not match an order would lose the intended physical source for that accepted alias.

The added regression exercises box A, then box B in a different location while the request still contains A, then an order barcode alias without a product hint, followed by the same idempotency key. It checks the returned B/location, stored pick source B, one active pick, unchanged inventory snapshots and order reservation statuses. HTTP malformed-pair rejection is also checked. The reviewer inspected this test and did not rerun it or use the AVD.

Author-reported checks: 16 targeted tests passed; after moving the XOR guard, the final regression passed (`1 passed, 8 deselected, 5 warnings in 14.47s`). Ruff on both changed files passed. Mypy on both files with `--follow-imports=silent` passed. Normal import-following mypy reported three pre-existing errors in unchanged imported test helpers; this is not represented as a clean full mypy run.

Container detection adds four scoped SELECTs to product scans that already have a selected container. The models declare unique tenant/barcode indexes for the searched container types. There are no external API requests, order loops or new locks in this detection. Actual scan latency has not yet been measured. Runtime coverage of pallet/cargo-place switching is not claimed from the box regression.

## Deployment checkpoint

The current Railway mapping was verified read-only: project `c28e681d-4535-4c96-ac97-c7b600a7f8e4` (loyal-wonder), environment `58a08b66-1290-45a2-8737-e3d7408389e5` (named production in this **staging** project), service WMS `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`, root `/backend`, public domain `wms-production-780c.up.railway.app`.

A Git archive of the exact source SHA containing the `backend/` prefix was uploaded with explicit project/environment/service IDs, `--path-as-root --no-gitignore --detach`. The upload completed with exit code 0. The archive contains 737 tracked files, 10,045,440 archive bytes; SHA256 `4b38de4ab97a31c84a5dfa6f7266adf712e1e872c09e85a345092f6a64ead8e9`. Backend Git tree: `151e39c418596ed0720c663a3a33e035188fc284`. The archive was checked for path traversal, symlinks, dependencies and secret-directory entries. No settings, variables or other services were changed.

**Deployment ID: `a4ec12eb-3607-40e9-813f-36f9e2195d66`. Created 2026-09-09 11:00:41.444 UTC. Last verified status: BUILDING.** The upload has finished and server-side deployment can continue independently of the local machine. The user requested an immediate reboot checkpoint, so no further verification is claimed here.

The previous active backend deployment was `4b82ac4b-270c-471d-a71a-3d99e755ce85`. The frontend mapping remained `b4134355-1542-4189-9567-6db5fbf61e79`. Production was not deployed by this task. No QA order, supply, pick or inbound was created or changed by the reviewer.

## Resume after reboot

1. Inspect the exact deployment above with Railway deployment list/logs; do not upload again merely because local execution stopped.
2. If SUCCESS, compare all runtime Python files under `/app/app` and `/app/alembic` to the exact Git source manifest, especially `app/services/fbs_picking_service.py`; verify public `/health`.
3. Only after that send mobile_publish_ci READY to repeat A → B → product in its existing QA supply and APK. The reviewer must not take over its AVD.
4. Root handles production only after CI, requested Opus Max review and the actual APK repeat. This checkpoint is not final staging acceptance.

The disposable archive and transport remain in this worktree under `tmp/wms401-stage/`; they are not the authoritative copy. The committed source manifest, mapping and last deployment status are in [artifacts/wms401-stage-checkpoint-20260909](artifacts/wms401-stage-checkpoint-20260909/). The source itself is recoverable from the pushed implementation commit. Canonical backlog updates remain with root.
