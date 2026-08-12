# Mobile/API compatibility evidence

## Compared identities

- Mobile repository recorded commit: `09aa479fd8e311a8155c92074ab2f4a6ec843da4`.
- Staging API: deployed commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`.
- Etalon API: `a39530c5137deb31e189c2136b613d01093af87b`.
- The mobile working tree contained unrelated local modifications, so all mobile facts below were read from the committed Git objects, not the worktree.

## Contract mismatch

The mobile commit's bundled `openapi.json` declares:

- `POST /operations/packaging-tasks/{task_id}/lines/{line_id}/pack` returns `PackagingTaskOut`;
- request `PackProgressIn` contains only required `quantity`.

The deployed staging OpenAPI declares:

- the same endpoint returns `PackProgressOut` with required `packaging_task` and optional `fulfilled_order`;
- request additionally supports optional `order_id` and `idempotency_key`.

The mobile ViewModel at `android/app/src/main/java/ru/wms/tsd/features/outbound/OutboundAssemblyViewModel.kt:202-245` routes this call through a function typed as `Response<PackagingTaskOut>` and immediately reads `result.value.lines`. The server commits at `backend/app/services/packaging_task_service.py:634` for FBS and `:661` for non-FBS before serializing the wrapper response in `backend/app/api/packaging_tasks.py:324-327`.

No relevant API diff exists between deployed `44fe72e…` and etalon `a39530c…`; the mismatch applies statically to both server SHAs.

## Boundary

The mobile app/emulator was not run: local functional runs were forbidden, and the mobile working tree was dirty. Therefore response-deserialization failure is a high-confidence static compatibility finding, not a runtime reproduction. The risk is material because the server mutation can commit before the incompatible client discovers the response shape, and the committed client does not send the optional idempotency key.
