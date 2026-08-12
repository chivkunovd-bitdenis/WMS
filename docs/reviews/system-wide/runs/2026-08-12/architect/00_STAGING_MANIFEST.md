# Architect review — staging manifest

## Review identity

- Review ID: `system-wide-architect-20260812`
- Reviewer role: architect
- Review worktree: `/Users/deniscivkunov/Projects/WMS/.worktrees/system-review-architect-20260812`
- Review branch / HEAD: `review/system-wide-architect-20260812` / `c964e0e8a47e690d7938e486073bd40d74bf0cc7`
- Runtime-code baseline requested by the review: `a39530c5137deb31e189c2136b613d01093af87b`
- The two commits above the runtime baseline contain only the four system-review regulations.
- Mobile repository recorded SHA: `09aa479fd8e311a8155c92074ab2f4a6ec843da4` on `main`.
- Mobile working tree is dirty and therefore was not treated as proof of the recorded SHA; runtime/mobile verification is `NOT_RUN`.
- Evidence capture start: 2026-08-12 12:54 MSK.

## Allowed environment

- Local functional runs: forbidden by the user's updated instruction.
- Runtime, API and data checks: staging only.
- Production and live WB: forbidden.
- Secret/key dashboards and credential lifecycle operations: forbidden.
- Existing staging login credentials may be used only for staging sign-in and are never copied into artifacts, screenshots, messages or shell output.

## Staging deployment identity gate

Railway read-only deployment metadata and public HTTP responses were checked on 2026-08-12.

| Component | Runtime identity | Proof | Gate result |
|---|---|---|---|
| Frontend `web` | commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`; image digest `sha256:d0975289ca8df6ca1c2a117547cb89d4bc8bc9d3c1e4aac67db77f529ef25535`; deployment `9960b498-ebe5-4115-b7d8-37fc2e2a769f`, status `SUCCESS` | Railway deployment metadata; public `/` returned 200, `Last-Modified: Sun, 09 Aug 2026 14:10:41 GMT`; HTML SHA-256 `ca927851fda279ea73adc76a87872f1280de4e3c79c085e39e2f75a235c60545` | `PROVED_NOT_ETALON` |
| API service `WMS` | commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`; image digest `sha256:3d5bd164d886126eb9f0ffb2723e91d8e4b5f878e9fd11c88da75aff66dc5781`; deployment `e0a55a42-8159-4cc6-a976-1331cf98dd07`, status `SUCCESS` | Railway deployment metadata; public `/api/health` returned `{"status":"ok"}`; OpenAPI SHA-256 `f8a8cd41174f8f4ebd03b24f7fe5aa1320a6d8e5d9778a5b6c25ff3883f1cece` | `PROVED_NOT_ETALON` |
| Worker | No separate worker service exists in the Railway project manifest; only `WMS`, `web`, and `Postgres` are present. `backend/Dockerfile.railway` starts Alembic and Uvicorn only. | Railway project metadata plus `backend/Dockerfile.railway:18` | `BASELINE_BLOCKED` — no independent worker SHA or liveness proof |
| PostgreSQL schema | Deployment commit contains Alembic head `20260809_0075`. Deployment log shows PostgreSQL Alembic startup completed before Uvicorn and health became 200. Direct `alembic_version` read-back was not available without accessing database credentials. | Commit tree, Docker entrypoint, Railway deployment log | `INFERRED_0075_NOT_DIRECTLY_PROVED` |

## Etalon mismatch

Staging is not built from the requested runtime baseline. `44fe72e…` is an ancestor of `a39530c…`; two later runtime commits are absent on staging:

1. `c03fd76` — changes the FBS warehouse-binding default and adds migration `20260809_0076`.
2. `a39530c` — changes WB order intake interpretation of the real `canPvz` field.

The runtime delta is limited to:

- `backend/alembic/versions/20260809_0076_enable_stock_sync_on_bindings.py`;
- `backend/app/services/wb_marketplace_orders_service.py`;
- `backend/tests/test_fbs_orders_intake.py`;
- `wb_emulator/seed/bootstrap.py`.

Therefore:

- staging observations may describe only deployed commit `44fe72e…`;
- they must not be reported as runtime proof of `etalon` / `a39530c…`;
- any finding dependent on the four changed paths needs separate static baseline analysis and stays unverified at runtime;
- migration/API/worker compatibility as a single deployed unit is `BASELINE_BLOCKED` because the worker identity is absent and the schema version is inferred rather than read back.

## Browser and visual-evidence gate

The architect's subagent runtime did not expose the in-app Browser, so no alternative browser backend was substituted. The orchestrator executed the staging navigation with the mandatory Browser skill. The architect then personally opened every screenshot cited in `05_UI_EVIDENCE_INDEX.md` using `view_image` and adjudicated it independently.

The stable viewport was measured by the orchestrator in the active browser as `innerWidth=1920`, `innerHeight=1080`, `devicePixelRatio=1`; the PNG width is 1920. Early `clicked` and visibly transitional black-margin captures are retained as interaction evidence but excluded from layout conclusions. UI execution and architecture adjudication are deliberately attributed separately.

Coverage outcome:

- durable browser mutation/read-back proved for warehouse creation and one MP-shipment draft;
- warehouse and two cell creations are visible after action; the corrected reload/reselect capture shows the same warehouse, both physical cells and the sorting location, proving durable UI read-back;
- the product attempt was stopped by the required seller field before any HTTP mutation;
- the seller portal created an empty inbound draft and read it back in the document list, but no reload/state JSON was supplied;
- the deployed Inventory page is explicitly a placeholder, so an inventory mutation was not reachable from that page;
- an FBS mutation is `BLOCKED_LIVE_WB_NO_SYNTHETIC_INJECTION`; no WB action was invoked;
- a full authorization mutation/direct-route/API-denial scenario was not supplied and is `NOT_RUN`.
