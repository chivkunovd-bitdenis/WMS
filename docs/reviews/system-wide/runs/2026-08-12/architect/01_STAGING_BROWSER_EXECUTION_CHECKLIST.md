# Staging Browser execution checklist for architect adjudication

## Responsibility split

- Execution and screenshot capture: orchestrator, using the mandatory Browser skill on deployed staging commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`.
- Architecture adjudication: architect, after independently opening every supplied screenshot with `view_image` and matching it to sanitized API/DB-state evidence.
- UI evidence is not evidence for `etalon` `a39530c…`; it is staging-only evidence for `44fe72e…`.
- If a listed control is absent or the browser cannot perform the step, stop that scenario and record `NOT_RUN` or `BLOCKED`; do not substitute source inspection.

## Safety setup

Create one isolated synthetic staging tenant through the public registration UI. Use a unique prefix such as `ARCH-20260812-<timestamp>` for organization, user emails, warehouse/location codes, seller, product and document. Do not reuse existing tenant IDs or WB-linked seller data.

Within that tenant create, through staging API setup if the UI setup is too large:

- one WMS warehouse `ARCH-WH-<timestamp>`;
- two locations `ARCH-A-<timestamp>` and `ARCH-B-<timestamp>`;
- one seller `ARCH-SELLER-<timestamp>` with no WB credentials;
- one product `ARCH-SKU-<timestamp>` linked to that seller, with a synthetic barcode;
- no WB token, warehouse binding, order sync or external object.

Record only opaque test IDs and counts in `evidence/state/*.json`; never record authorization headers, cookies, passwords or token values. Screenshot viewports: first pass 1280×720; final/reload at 1920×1080 where feasible.

## REV-ARCH-AUTHZ-001 — role mutation and backend enforcement

Purpose: prove that a server-owned permission mutation changes both navigation and API access.

1. From normal FF login and sidebar navigation, open `Настройки`.
2. Screenshot before staff creation:
   - `REV-ARCH-AUTHZ-001__ff-admin__1280x720__before.png`.
3. In the `Пользователи` section enter a unique synthetic staff email and press `Добавить сотрудника`.
4. Screenshot success row/message:
   - `REV-ARCH-AUTHZ-001__ff-admin__1280x720__action.png`.
5. Enable only `Приёмка`; explicitly keep `Упаковка` disabled. Wait for the saved notice.
6. Sanitized state read-back as admin:
   - `GET /auth/staff-accounts` contains exactly one row for the synthetic email;
   - record `{staff_id, role, must_set_password, permissions}` only in `REV-ARCH-AUTHZ-001__staff-readback.json`.
7. Log out using the visible `Выйти` button. Log in as the new staff via the normal login path (first login uses the documented empty-password flow, then sets a synthetic password).
8. Prove visible boundary:
   - `Приёмка` visible;
   - `FBS`, `Селлеры`, `Каталог`, admin user controls absent;
   - screenshot `REV-ARCH-AUTHZ-001__limited-staff__1280x720__result.png`.
9. Navigate directly to `/app/ff/fbs`. Expect the visible no-access placeholder, not the FBS workspace.
   - screenshot `REV-ARCH-AUTHZ-001__limited-staff__1280x720__failure.png`.
10. Using the same authenticated browser session, make a read-only request to `/api/operations/fbs-orders/worklist`; record status only. Expected `403`.
11. Reload `/app/ff/fbs`; access must remain denied.
   - screenshot `REV-ARCH-AUTHZ-001__limited-staff__1920x1080__reload.png`.
12. Restore by logging in as the synthetic admin and disabling `Приёмка` for the staff. Do not delete accounts because no supported UI/API delete exists; list this synthetic row as retained staging test data.

## REV-ARCH-DOC-001 — inbound document to durable inventory

Purpose: trace one document mutation through status, line, movement and balance.

Precondition: synthetic tenant, warehouse, locations, product; admin logged in.

1. Navigate from sidebar to the inbound route `/app/ops/inbound` (or the currently visible route leading there).
2. Screenshot initial document list and form:
   - `REV-ARCH-DOC-001__ff-admin__1280x720__before.png`.
3. Set a planned date and press `Новая заявка на приёмку` exactly once.
4. Add the synthetic product with quantity `5` and location `ARCH-A-*`; submit the line.
5. Screenshot draft with line and opaque document identity visible only if already present in normal UI:
   - `REV-ARCH-DOC-001__ff-admin__1280x720__action.png`.
6. Press submit, then the visible primary accept action. Set actual quantity `5`, complete recount, retain/select `ARCH-A-*`, then `Провести весь остаток`.
7. Wait for visible `posted`, `+5 inbound_intake`, and balance `5`.
   - screenshot `REV-ARCH-DOC-001__ff-admin__1280x720__result.png`.
8. Sanitized state evidence:
   - `GET /operations/inbound-intake-requests/{id}`: document `status`, line expected/actual/posted quantities, location ID;
   - `GET /operations/inventory-movements?inbound_intake_request_id={id}` or documented equivalent: movement IDs, type, delta, product/location IDs;
   - `GET /operations/inventory-balances?...`: quantity/reserved/available for the product/location;
   - store as `REV-ARCH-DOC-001__readback.json`.
9. Reload the page and reselect the document. The same posted status, `+5` movement and balance must persist.
   - screenshot `REV-ARCH-DOC-001__ff-admin__1920x1080__reload.png`.
10. Negative: while a fresh second synthetic draft has no line, attempt `Отправить`; capture the exact visible validation/rejection and confirm no inventory movement appeared.
   - screenshot `REV-ARCH-DOC-001__ff-admin__1280x720__failure.png`;
   - state `REV-ARCH-DOC-001__negative-readback.json`.

## REV-ARCH-INV-001 — transfer conservation and double-submit boundary

Purpose: prove `sum(quantity)` conservation and movement pairing for a stock mutation.

Precondition: result of REV-ARCH-DOC-001, balance `A=5`, `B=0`, reserved `0`.

1. Navigate through the visible application to `/app/ops/transfers`.
2. Select `ARCH-A-*` → `ARCH-B-*`, synthetic product, quantity `2`.
3. Screenshot complete form before mutation:
   - `REV-ARCH-INV-001__ff-admin__1280x720__before.png`.
4. Press `Переместить` once and wait for visible success/read-back.
5. Expected state: A=3, B=2, total=5; exactly one `stock_transfer_out -2` and one `stock_transfer_in +2`, same tenant/product and corresponding locations.
   - screenshot `REV-ARCH-INV-001__ff-admin__1280x720__result.png`;
   - state `REV-ARCH-INV-001__readback.json`.
6. Reload and verify the persisted values from the visible inventory/movement screen.
   - screenshot `REV-ARCH-INV-001__ff-admin__1920x1080__reload.png`.
7. Negative: attempt quantity `4` from A (current A=3). Expect a visible rejection and unchanged balances/movement count.
   - screenshot `REV-ARCH-INV-001__ff-admin__1280x720__failure.png`;
   - state `REV-ARCH-INV-001__negative-readback.json`.
8. Retry/double-submit is permitted only on this isolated product and only if Browser can deterministically issue two user clicks without inventing a lower-level client. Set quantity `1`, rapidly submit twice, then count movement pairs. Record the exact number of POSTs and resulting balance; do not infer from button behavior. If two transfers occur, reverse the extra quantity through the visible UI and retain before/after recovery evidence. If the browser cannot deterministically perform this, mark `NOT_RUN_TOOL_LIMITATION`.

## REV-ARCH-ISOLATION-001 — cross-tenant object boundary

Purpose: prove horizontal access denial independently of hidden navigation.

1. Create a second isolated synthetic tenant B via the public registration screen in a separate browser context.
2. Use tenant B's authenticated session to request tenant A's inbound document ID and tenant A's product/balance object through the same staging origin.
3. Expected: `403` or non-enumerating `404`; response must not include tenant A product, seller, warehouse or document fields.
4. Record only endpoint template, status, response key names and boolean `foreign_data_present` in `REV-ARCH-ISOLATION-001__readback.json`.
5. Navigate in tenant B UI to its own inbound/inventory screens, demonstrating no tenant A rows.
   - `REV-ARCH-ISOLATION-001__tenant-b__1280x720__before.png`;
   - `REV-ARCH-ISOLATION-001__tenant-b__1280x720__result.png`;
   - `REV-ARCH-ISOLATION-001__tenant-b__1920x1080__reload.png`.

## REV-ARCH-FBS-001 — explicit runtime blocker, no WB mutation

Staging `44fe72e…` is configured as the historical WB-connected test stand, while this review forbids live WB and provides no deployed emulator or synthetic FBS-order injection endpoint. Therefore do not click:

- `Обновить из WB`;
- `Сформировать поставку` on any existing order;
- delivery, QR, cargo-place, cancellation or status-sync controls;
- any seller token/binding control.

Safe read-only browser evidence only:

1. In the isolated tenant with no WB credential, navigate normally to `FBS`.
2. Capture the empty/error/credentialless screen without pressing WB controls:
   - `REV-ARCH-FBS-001__ff-admin__1280x720__before.png`;
   - `REV-ARCH-FBS-001__ff-admin__1920x1080__reload.png`.
3. Record read-only worklist status/count and presence flags only in `REV-ARCH-FBS-001__readback.json`.
4. Runtime mutation status remains `BLOCKED_NO_SYNTHETIC_FBS_AND_LIVE_WB_FORBIDDEN`. Static baseline evidence may describe paths and risks but cannot promote a defect.

## Lost-response and restart boundary

- Do not restart the shared staging API, database or Railway deployment.
- A browser-side response abort may be used only for creation of a synthetic inbound draft if Browser can send the real request and drop only the response without retrying or touching other traffic. After reload, read back by unique synthetic prefix and count created rows. Repeat with a new unique prefix for a second attempt if a P0/P1 is suspected.
- Otherwise mark lost-response and restart scenarios `NOT_RUN_SHARED_STAGING_NO_ISOLATED_FAILURE_INJECTION`.
- Worker restart is `BASELINE_BLOCKED_NO_WORKER_SERVICE`.

## Delivery back to architect

Send absolute paths to every screenshot and state file plus an execution note containing:

- deployed SHA `44fe72e…`;
- timestamp MSK;
- viewport;
- synthetic tenant/seller/product/document IDs;
- exact action and observed visible result;
- cleanup/recovery performed;
- any step not run and why.

The architect will inspect the files directly and will not accept an orchestrator summary as substitute evidence.
