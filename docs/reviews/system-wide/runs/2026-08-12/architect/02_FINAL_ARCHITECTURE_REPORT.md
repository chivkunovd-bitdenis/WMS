# Final architect report — WMS system-wide review

## Executive result

The architecture has a generally clear local state owner—PostgreSQL—and good tenant filtering plus unusually strong uncertainty handling in the core FBS→WB operations. It is not release-safe as reviewed because one ordinary warehouse operation is not exactly-once: two concurrent completions of the same inbound receipt double inventory while the document still says one unit. This was reproduced twice on staging and is the top stop-ship defect.

Two system boundaries are also incomplete: periodic jobs have no deployed worker/scheduler, and the committed Android client consumes an older packaging response than both staging and etalon servers return. Reservation ownership is split across three calculations, and seller-shop manager policy partly depends on hard-coded email text.

Runtime conclusions apply to staging commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`, **not** to requested etalon `a39530c5137deb31e189c2136b613d01093af87b`. Static comparison shows the P0, worker topology code and mobile server contract are unchanged in etalon, but etalon was not deployed on this stand.

## Scope and method

The review mapped UI → API → service → transaction → PostgreSQL → background job → WB/print/mobile → read-back for:

- identity, roles, staff permissions, tenant and seller scope;
- warehouses, cells, product catalog and inventory read models;
- inbound reception/sorting, generic outbound and marketplace unload/FBO-style shipment;
- packaging and unpacked/packed quantities;
- FBS orders, reservations, picking, packing boxes, supplies, delivery, stock publication and reconciliation;
- Honest Sign, print artifacts, notifications, worker/scheduler and Android TSD boundaries.

Local functional execution was forbidden. Static inspection used etalon Git objects. Runtime/API/data evidence used staging only. The orchestrator executed Browser-skill navigation; the architect personally inspected the cited screenshots and independently adjudicated them. No production or live WB mutation was performed.

Detailed traceability is in `02_BOUNDARY_TRACEABILITY_MAP.md`, failure behavior in `03_FAILURE_MATRIX.md`, and every accepted screenshot/verdict in `05_UI_EVIDENCE_INDEX.md`.

## Deployment identity and compatibility gate

At 2026-08-12 12:57 MSK, Railway metadata proved:

- frontend `web`: deployment `9960b498-ebe5-4115-b7d8-37fc2e2a769f`, commit `44fe72e…`;
- API `WMS`: deployment `e0a55a42-8159-4cc6-a976-1331cf98dd07`, commit `44fe72e…`;
- PostgreSQL service present;
- no worker or Beat service.

The API health endpoint and public frontend returned 200. Schema head is only inferred as migration 0075 from the deployed tree, Docker migration command and successful startup log; `alembic_version` was not directly read. The deployment inventory was checked again at `2026-08-12T10:20:24Z` and remained API/web/Postgres only.

Staging is two runtime commits behind etalon:

1. `c03fd76e347ae7d30288e8171b4869b53a3684c2` adds migration 0076 and changes FBS warehouse-binding defaults.
2. `a39530c5137deb31e189c2136b613d01093af87b` changes WB order intake to use the real `canPvz` field.

Therefore frontend↔API same-SHA compatibility is proved for staging, API↔schema is inferred but not directly proved, API↔worker/Beat fails because the processes do not exist, and no runtime claim certifies etalon.

## Confirmed findings

### P0 — inbound completion double-applies inventory

In each of two independent synthetic documents with expected/actual quantity 1, two parallel completion calls both returned 200. Read-back showed document `status=sorting`, expected 1, actual 1, but balance 2 and two movements with total delta +2. Server timestamps for each request pair differ by only microseconds and are recorded in `evidence/state/STAGING_INBOUND_CONCURRENCY.md`.

The service reads a permissible state without a lock or conditional state transition, applies inventory, then commits. Balance arithmetic is atomic, but the business operation is not. The relevant paths have zero diff from staging `44fe72e…` to etalon `a39530c…`. Full card: `findings/ARCH-P0-001_INBOUND_DOUBLE_COMPLETION.md`.

### P1 — periodic work has no deployed process

Celery Beat defines five periodic jobs, including FBS order/status polling and stock reconciliation, but Railway deploys neither worker nor Beat. Two safe manual digest jobs completed inline, proving only the API fallback. The service inventory absence was observed at two timestamps. Event-driven stock publication swallows external failure on the premise that periodic reconciliation will recover it, yet that scheduler is absent. Full card: `findings/ARCH-P1-002_PERIODIC_JOBS_NOT_DEPLOYED.md`.

### P1 — mobile packaging response contract is stale

Committed mobile `09aa479…` expects pack-progress to return `PackagingTaskOut`; staging and etalon return `PackProgressOut { packaging_task, fulfilled_order }`. The server commits before serializing the wrapper, while the client expects to read `.lines` directly and sends no idempotency key. This is independently confirmed by the bundled mobile OpenAPI and committed ViewModel call site against the server OpenAPI/implementation. Device runtime was not run, so the deserialization/retry consequence remains a static compatibility finding rather than a runtime reproduction. Full card: `findings/ARCH-P1-003_MOBILE_PACK_CONTRACT_DRIFT.md`.

### P2 — reservation read models do not share owner semantics

FBS availability excludes MP reservations; MP availability subtracts FBS; location inventory sees outbound only; default catalog summary omits FBS because it requests no warehouse. The semantic divergence is static and certain. Actual cross-contour overbooking was not runtime reproduced because synthetic FBS injection was unavailable and live WB was forbidden. Full card: `findings/ARCH-P2-004_RESERVATION_READMODELS_DIVERGE.md`.

### P2 — access policy is partly inferred from email text

Seller-shop manager capability can arise from hard-coded email markers in addition to an explicit DB flag/configured list. A same-tenant enabled delegation is still required, so no direct cross-seller bypass was proved. This is policy ownership debt, not a runtime isolation finding. Full card: `findings/ARCH-P2-005_ACCESS_POLICY_BY_EMAIL_MARKER.md`.

## Positive controls worth retaining

- JWT tenant is compared with the current DB user's tenant; most domain getters query by tenant and seller-owned mutations check product/seller consistency.
- FBS supply/cargo/delivery operations have durable `FbsWbOperation` identity, unique seller/kind/idempotency key, stored WB object ID, `pending_confirmation`, and reconcile-before-repeat behavior.
- FBS packing has per-unit fulfillment identity and uniqueness constraints, plus reversal-ledger support.
- Marketplace unload and FBS are distinct models/state machines. Their coupling is intentionally limited to shared inventory, packaging/marking and availability.
- External stock publication is scheduled after DB commit, so a slow WB call cannot roll back a physical warehouse operation. The missing recovery scheduler, not that separation, is the defect.
- Browser product-create code retains structured non-2xx errors and closes only after success. The captured failed attempt was native required-field validation, not error masking.

## Visual and state adjudication

Stable 1920×1080/DPR1 screens were inspected for all twelve FF routes and four seller routes. Warehouse creation, two cell creations, MP shipment draft creation, seller/account creation and seller first-login were actually exercised. Corrected reload evidence proves the warehouse and both cells persisted. MP draft `№000001` persisted after reload and reopened with the same seller, warehouse, draft status and zero plan.

The seller portal created an empty inbound draft and showed it in the list, but no reload, submit, movement or balance read-back was supplied. The Inventory route is explicitly `Раздел в разработке`. Catalog product creation never issued HTTP because the required seller was empty. The discrepancy-act CTA is explicitly a future placeholder. FBS tabs and WB-stock bindings were traversed read-only; no WB button was invoked.

The architect rejected transitional screenshots as layout proof, including early clicked frames and black-margin frames. Execution attribution remains “orchestrator”; visual/state adjudication remains “architect.”

## Coverage ledger and blockers

| Required area | Result |
|---|---|
| Static UI→API→service→transaction→DB inventory | `COMPLETE` for all listed domain contours |
| Staging frontend/API identity | `PROVED_44fe72e_NOT_ETALON` |
| Worker identity | `BLOCKED_NO_DEPLOYED_WORKER` |
| Schema identity | `INFERRED_0075_NOT_DIRECT_READBACK` |
| Warehouse/cell browser mutation + reload | `PROVED` |
| Document browser mutation + reload | MP draft `PROVED`; full receive/post inventory lifecycle `NOT_RUN_BROWSER`, API concurrency mutation separately proved |
| Inventory browser mutation | `BLOCKED_PRODUCT_SURFACE_PLACEHOLDER` |
| FBS browser mutation | `BLOCKED_LIVE_WB_FORBIDDEN_AND_NO_SYNTHETIC_INJECTION` |
| Authorization permission mutation/direct route/API denial | `BLOCKED_REQUIRED_EXECUTION_BATCH_NOT_SUPPLIED` |
| Tenant/seller cross-object runtime test | `NOT_RUN`; static filters reviewed |
| Lost-response injection | `NOT_RUN_SHARED_STAGING_NO_ISOLATED_FAILURE_INJECTION` |
| Partial WB batch/timeout | `BLOCKED_LIVE_WB_FORBIDDEN` |
| API/worker restart | `NOT_RUN_SHARED_STAGING`; worker restart impossible because no worker exists |
| Packaging/packed invariant runtime | `NOT_RUN`; static path reviewed |
| Print artifact generation/read-back | `NOT_RUN` |
| Mobile emulator/device | `NOT_RUN_LOCAL_FUNCTIONAL_RUN_FORBIDDEN_DIRTY_MOBILE_TREE` |

Because three of the four mandated critical browser mutations are blocked/not supplied (inventory, FBS, authorization), this is a complete static architecture review plus bounded staging evidence, not a claim of complete end-to-end runtime certification.

## Minimal remediation order

1. Make inbound completion a single conditional/locked state transition and add a database uniqueness barrier for the logical receipt movement. Add the exact parallel regression that currently fails.
2. Deploy worker and Beat from the same SHA/configuration as the API; expose last-success/liveness and include API/worker/beat/schema identities in deployment acceptance.
3. Regenerate the Android client, consume `packaging_task` from the wrapper, send one stable idempotency key per logical pack action, and add a server-contract/lost-response test.
4. Centralize the existing availability calculation so outbound, MP and FBS active reservations are consistently included. Preserve explicit “exclude current document/order” parameters.
5. Remove email-marker authority in favor of the existing explicit DB capability and stored same-tenant delegations.

This order repairs concrete correctness and deployment gaps without proposing a new architecture.

## Git and publication status

- Working area: only `docs/reviews/system-wide/runs/2026-08-12/architect/**`.
- Branch: `review/system-wide-architect-20260812`.
- Application code: unchanged.
- Review artifacts: committed as one scoped commit at handoff; the verified SHA is reported with the handoff because a commit cannot truthfully contain its own final SHA.
- Push: not performed, by contract.
- Deployment: not changed.
