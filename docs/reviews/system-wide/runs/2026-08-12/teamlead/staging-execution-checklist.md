# Staging Browser execution checklist — teamlead-owned

Execution is delegated to the orchestrator because the teamlead Browser runtime has no available browser. The teamlead owns the scenario, stop conditions, expected result, and later adjudication. Credentials from `frontend/tests-e2e/live-fbs-stand.spec.ts` may be read only inside the orchestrator's Browser flow and must never be copied into evidence.

## Global stop conditions

1. Do not execute any mutation until the selected tenant, seller, product, locations, document, and FBS order are explicitly synthetic staging data created for this review.
2. Do not call token/settings endpoints, WB sync/import, stock publication, supply delivery, shipment, cancellation, or any control that could contact live WB.
3. If staging WB mode cannot be proven emulator/test, all FBS mutations are `BLOCKED`; only list/open/refresh/reload GET paths are allowed.
4. Never capture a filled login form, email, password, authorization header, cookie, token, personal data, or credential screen. Before every post-login screenshot, temporarily mask any visible login/email label in the rendered DOM.
5. Capture sanitized network evidence as `time, method, path, status, Railway request-id, response state fields`. Omit headers, request bodies containing credentials, tokens, and cookies.
6. Use `1280×720` for the complete sequence. Repeat the final reload screenshot at `1920×1080` for each scenario.
7. Do not attribute an observation to `a39530c`: deployed frontend/API/worker/schema versions remain unknown.

## TL-AUTH-01 — login, session read-back, and denial without authentication

1. Open the staging root at `1280×720`. Confirm blank login form and no private navigation. Save `TL-AUTH-01__ff-admin__1280x720__before.png`.
2. Fill the permitted staging credentials from the spec. Do not screenshot this state.
3. In parallel, observe `POST /api/auth/login` and the following `GET /api/auth/me`; click `Войти`.
4. Record only statuses and non-secret state: `/login=200`, `/me=200`, returned `role`, whether `tenant_id` exists, and whether `seller_id` is null/non-null. Do not record token or email.
5. Mask any visible email/login in the header. Confirm FF landing/dashboard and role-appropriate navigation. Save `TL-AUTH-01__ff-admin__1280x720__result.png`.
6. Reload normally. Observe a fresh `GET /api/auth/me=200`, confirm the same role and private shell, mask the email, save `TL-AUTH-01__ff-admin__1280x720__reload.png` and `TL-AUTH-01__ff-admin__1920x1080__reload.png`.
7. Open a fresh unauthenticated Browser context/tab without copying session state and request `/api/auth/me` from that context. Expect `401` with a non-secret error code and no tenant/seller fields. Save the blank/public UI as `TL-AUTH-01__anonymous__1280x720__failure.png`.
8. In the authenticated FF context navigate to `/seller/`. Expected: FF-admin session is not admitted to seller private screens; visible portal-mismatch/login state, with no seller documents. Mask any credential label and save `TL-AUTH-01__ff-admin__1280x720__portal-boundary.png`. Record the `/api/auth/me` status and visible outcome only.

Pass requires all of: durable reload, correct FF shell, unauthenticated `401`, and no seller-private content in the portal-boundary step.

## TL-INV-01 — one reversible stock transfer, read-back, retry, and cleanup

Precondition: one explicitly synthetic product `TL-20260812-*`, two synthetic locations in one synthetic warehouse, and at least `3` available units in the source. Record opaque test IDs in a non-secret state file; never use production-like catalog rows.

1. Through normal navigation open `Операции → Перемещения` (`/app/ops/transfers`).
2. Select source via `transfer-from-loc`, destination via `transfer-to-loc`, product via `transfer-product`, quantity `1` via `transfer-qty`.
3. Capture the form before mutation: `TL-INV-01__ff-admin__1280x720__before.png`.
4. Record server state before: source and destination quantities from a normal inventory summary/list GET and the current movement count for the synthetic product.
5. Observe `POST /api/operations/stock-transfers`; click `transfer-submit` once. Record status and returned transfer/movement identifiers only.
6. Confirm visible success/no error, then open `Операции → Движения`, refresh, and locate exactly two movement rows for this one transfer (out/in) or the baseline's documented equivalent. Save `TL-INV-01__ff-admin__1280x720__result.png`.
7. Reload. Re-read balances and movements. Expected delta: source `-1`, destination `+1`, total unchanged; save `TL-INV-01__ff-admin__1280x720__reload.png` and `TL-INV-01__ff-admin__1920x1080__reload.png`.
8. Retry test: return to transfers and deliberately submit the exact same semantic transfer once more, after the first response and reload. Save the filled form as `TL-INV-01__ff-admin__1280x720__retry-action.png`; record whether the server creates a second transfer or deduplicates it. Do not classify yet—report the exact effect.
9. Save the post-retry read-back as `TL-INV-01__ff-admin__1280x720__retry-result.png`. Expected safety property for a lost-response retry is one durable business result; if the endpoint treats the retry as a new transfer, record source `-2`/destination `+2` and the extra movements exactly.
10. Cleanup: transfer the observed total delta back from destination to source using one explicit reverse operation. Reload and prove both balances equal their before values. Save `TL-INV-01__ff-admin__1280x720__cleanup.png`.

Stop if the source has fewer than `3` units, any selected row is not clearly synthetic, or cleanup cannot be calculated from read-back.

## TL-DOC-01 — reversible outbound draft lifecycle

Precondition: use the same synthetic warehouse/product/location. This scenario must not submit, ship, or post stock.

1. Navigate normally to `Операции → Исходящие` (`/app/ops/outbound`). Record the list GET and save `TL-DOC-01__ff-admin__1280x720__before.png`.
2. Click `outbound-create-submit`; observe one `POST /api/operations/outbound-shipment-requests=201`. Record the new opaque request ID and visible `draft` state.
3. Select the synthetic product/location, quantity `1`; save `TL-DOC-01__ff-admin__1280x720__action.png`.
4. Click `outbound-line-submit`; observe one line-create `POST=201`. Confirm the visible line and `draft` state. Save `TL-DOC-01__ff-admin__1280x720__result.png`.
5. Reload and observe `GET /api/operations/outbound-shipment-requests/{id}=200`. Confirm the same request ID, one line, quantity `1`, and `draft`. Save `TL-DOC-01__ff-admin__1280x720__reload.png` and `TL-DOC-01__ff-admin__1920x1080__reload.png`.
6. Safe retry check: click the visible delete-line control once, observe `DELETE .../lines/{line_id}=200`, and confirm the line disappears. Reload and prove the draft has zero lines. Save `TL-DOC-01__ff-admin__1280x720__cleanup.png`.
7. Do not submit/post the draft. Record that the empty synthetic draft remains because the API exposes no delete-request lifecycle; this is cleanup limitation evidence, not automatically a defect.

## TL-FBS-01 — safe FBS list/workspace refresh and reload

1. First record whether staging exposes trustworthy non-secret evidence that WB calls are emulator/test. If not, state `FBS mutation BLOCKED` and perform only steps 2–6.
2. Navigate normally to `ФБС` (`/app/ff/fbs`). Observe `GET /api/operations/fbs-orders/worklist`; do not click sync/import.
3. Filter only by an explicitly synthetic review marker if present. Save list context as `TL-FBS-01__ff-operator__1280x720__before.png`.
4. Open one synthetic order with `Продолжить работу` or its row action. Observe the workspace GET and record only order/supply opaque IDs, WMS status, `supplierStatus`/`wbStatus` fields when present, and stage. Save `TL-FBS-01__ff-operator__1280x720__result.png`.
5. Reload the workspace. Expected: same server-owned stage/progress, no duplicated supply/order/box, no spinner dead-end. Save `TL-FBS-01__ff-operator__1280x720__reload.png` and `TL-FBS-01__ff-operator__1920x1080__reload.png`.
6. Trigger the normal read-only refresh twice, recording both worklist GET statuses and item identity. Save `TL-FBS-01__ff-operator__1280x720__retry-result.png`.
7. Only if emulator/test mode is independently proven and the selected order is synthetic may the orchestrator test a WMS mutation. Preferred reversible action: create one empty local packing box and delete that same empty box; capture before/action/result/reload/cleanup and prove no WB endpoint was called. Otherwise stop.
8. Never click `Сформировать поставку`, `Передать в WB`, delivery, cancellation, stock sync/publication, sticker/QR acquisition, or any action whose external boundary is uncertain.

## Evidence handoff to teamlead

Return:

- absolute screenshot paths;
- sanitized network/state log for each numbered step;
- viewport and MSK timestamp;
- synthetic tenant/seller/product/location/document/order identifiers or stable aliases;
- cleanup proof;
- explicit list of skipped/blocked steps and why.

The teamlead will inspect each image independently with `view_image`, compare it with the sanitized network/state evidence, and record `execution by orchestrator / adjudication by teamlead` in `ui-evidence/index.md` and the final report.
