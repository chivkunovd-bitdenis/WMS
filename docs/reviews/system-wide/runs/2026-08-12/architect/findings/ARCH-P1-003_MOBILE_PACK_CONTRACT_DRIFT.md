# ARCH-P1-003 — committed mobile client expects the wrong packaging response

## Result

**Severity: P1. Status: CONFIRMED_STATIC_CONTRACT_MISMATCH; RUNTIME_NOT_RUN.** Mobile commit `09aa479…` expects the pack-progress endpoint to return `PackagingTaskOut`. Both staging `44fe72e…` and etalon `a39530c…` return a wrapper `PackProgressOut`.

The client call and mutation helper are fixed to `Response<PackagingTaskOut>` at `OutboundAssemblyViewModel.kt:202-245`. The server commits the packing mutation before constructing its wrapper response (`backend/app/services/packaging_task_service.py:634-664`, `backend/app/api/packaging_tasks.py:324-327`). Therefore the device can receive a response it cannot decode after inventory/packing state has already changed.

## Retry consequence

The committed mobile request model contains only `quantity`; it does not send `idempotency_key`. On an apparent client failure, an operator retry can target another unit or increment non-FBS packing again, depending on remaining quantity. FBS has a server-side fulfillment uniqueness barrier, but without the same key a retry is not the same logical request.

## Boundary and countermeasure

This mismatch is proved from both committed OpenAPI contracts and committed call-site types. It was not executed on a device because local functional runs were forbidden and the mobile worktree was dirty.

The minimal repair is to regenerate the committed mobile client from the deployed/etalon OpenAPI, consume `response.packaging_task`, send a stable idempotency key for a logical pack action, and add a contract test against the server OpenAPI plus a lost-response retry test.
