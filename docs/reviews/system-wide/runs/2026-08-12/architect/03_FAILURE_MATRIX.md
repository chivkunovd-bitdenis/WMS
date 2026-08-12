# Failure and recovery matrix

The matrix distinguishes an implemented control from a runtime result. `Static` means the path was inspected but not failure-injected on staging.

| Failure | Inbound / inventory | Marketplace unload / packaging | FBS / WB / print | Job / deployment | Verdict |
|---|---|---|---|---|---|
| Duplicate click / concurrent request | Completion has no row lock, conditional transition or operation key. Two parallel calls both committed in each of two runs | Most local create/plan/pack routes have no request idempotency key; availability checks and row locks vary by step | Supply, cargo place, delivery and packing-box paths require keys; `FbsWbOperation` is unique by seller/kind/key. FBS packing fulfillment has unique task/key and active-order constraints | N/A | **Confirmed P0** for inbound; other local contours are static exposure, not reproduced |
| Lost HTTP response after local commit | Draft creation and completion return after service commit; retry is not correlated to prior logical request | Pack progress commits before response; committed mobile client expects wrong response and supplies no key | External paths persist operation state and WB object identity; uncertain calls become `pending_confirmation` and reconcile before repeating | Manual API background start persists job then schedules inline | Inbound lost-response injection `NOT_RUN`; mobile risk `P1 static`; FBS design is materially stronger |
| Partial batch success | Multi-line document transitions generally run in one DB session, but some workflows add notifications or derived tasks in later commits | Planning, packaging-task sync and box work contain several service-level commits, so a later failure can leave a recoverable earlier state | WB add-order/cargo batches reconcile the remote supply membership; runtime partial batch was not exercised | N/A | Static recovery paths present; `NOT_RUN_LIVE_WB` for external batch |
| API process restarts | Committed DB state remains; in-flight request rolls back if commit not reached | Same, except post-commit in-process publish can be lost | Event-loop stock publication can vanish after commit; exception is swallowed with periodic reconcile intended as safety net | No worker/Beat exists, so the safety net is absent | `P1` deployment gap; restart injection `NOT_RUN_SHARED_STAGING` |
| Worker process restarts | No separate worker participates | No separate worker participates | Broker tasks cannot be proven because no worker is deployed | There is no worker or scheduler identity to restart/check | `BASELINE_BLOCKED_NO_WORKER_SERVICE` |
| Database/session concurrency | Balance increment is atomic, but business transition is not; duplicate movements result | MP collect/remove uses row locks in reservation paths; other status transitions vary | Supply/pack integration uses row locks and uniqueness barriers in key places | N/A | One concrete concurrency failure confirmed; no blanket safety claim for other transitions |
| Reservation race | Location transfer/availability sees outbound reservation only | MP subtracts outbound+MP+FBS | FBS subtracts outbound+FBS but explicitly omits MP | N/A | Static divergence confirmed; overbooking runtime not reproduced |
| External timeout / unknown WB result | N/A | WB warehouse cache/sync not exercised | Durable operation journal supports `pending_confirmation`, stored WB IDs and reconciliation for core supply/cargo/delivery operations | Periodic reconciliation not deployed | Control exists in code; runtime timeout not exercised because live WB mutation forbidden |
| External non-2xx | N/A | UI error reader preserves structured API detail; captured product attempt never reached HTTP | Service maps WB errors; core operation state can fail/pending-confirmation | Background publish catches and logs errors | Static only. Product screenshot is client validation, not evidence of non-2xx masking |
| Print generation/storage failure | Cell label browser print not exercised | Packaging marking gate prevents completion when required codes are not printed | Print asset services store metadata/artifacts, but no artifact generation/download/reprint was executed | N/A | `NOT_RUN` |
| Migration/API mismatch | Deployed API and inferred schema are both from `44fe72e`; direct schema head not readable | Same | Staging lacks migration 0076 and two FBS commits in etalon | Worker identity absent | Staging is internally plausible at inferred 0075, but full API/schema/worker compatibility gate is `BLOCKED` |
| Old mobile with new API | Mobile can read many shared resources from bundled contract | Pack response changed from task to wrapper after mobile client generation | No FBS endpoints exist in committed mobile OpenAPI | N/A | `P1` static contract mismatch; device runtime not run |
| Cross-tenant object reference | Most service getters filter tenant; JWT tenant is compared to DB user tenant | Seller products and requests are rechecked against tenant/seller | External operation keys include seller; service queries carry tenant/seller | N/A | Static controls observed; two-tenant runtime probe `NOT_RUN` |
| Staff permission changed while token remains | Permission dependency reloads permission row on each request; JWT does not embed the permission bits | Same | FBS operator alias maps to packaging permission | N/A | Static expected immediate enforcement; browser/API scenario `NOT_RUN` |

## Idempotency and external-ID inventory

Strong, durable identities exist for FBS external operations (`FbsWbOperation`), FBS physical packing fulfillment, packing-box creation, document numbers and WB order/supply IDs. Those controls are scoped to the FBS paths that use them.

They do not cover ordinary local mutations such as inbound draft creation, inbound completion, warehouse/cell/product creation, generic stock transfer, non-FBS pack progress, or marketplace-unload draft creation. A response loss on these endpoints leaves the client no operation resource or stable request key with which to distinguish “not applied” from “committed but response lost.” `ARCH-P0-001` proves this is not merely theoretical for inbound completion.

## Compatibility matrix

| Component pair | Evidence | Result |
|---|---|---|
| Staging frontend ↔ staging API | Both Railway deployments report exact commit `44fe72e…`; representative routes and API health/load succeeded | Same-SHA pair proved |
| Staging API ↔ staging schema | API image is `44fe72e…`; Docker runs Alembic; startup succeeded; schema head inferred 0075 | Plausible, not direct `alembic_version` proof |
| Staging API ↔ worker/beat | No worker/beat service | Incompatible deployment topology for scheduled tasks |
| Etalon API ↔ migration | Etalon adds migration 0076 together with FBS behavior changes | Static pair present in Git; not deployed/runtime verified |
| Mobile `09aa479…` ↔ staging/etalon API | Committed OpenAPI response types differ on pack-progress | Static incompatibility confirmed |
