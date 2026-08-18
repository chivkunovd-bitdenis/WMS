# Frontend e2e final gate, ORDER 041

Date: 2026-08-15 MSK.

Branch: `integration/wms-wave0-20260814`.

Commit: `4f7148f3e2139ce931dc27b2956ec9a2c0c92d48`.

Stage: final integration frontend regression gate after Wave 1, Wave 2, rescued KIZ binding, and e2e stabilization.

Status: `FRONTEND_GATE_GREEN`.

This is an automated frontend regression gate. It is not a replacement for the earlier live external-browser product acceptances.

## Final numbers

Backend baseline from ORDER 041:

- `763 passed`
- `0 failed`

Frontend command:

```bash
cd frontend
E2E_API_PORT=18009 \
E2E_WEB_PORT=5183 \
E2E_API_ORIGIN=http://127.0.0.1:18009 \
E2E_DB_FILE=/tmp/wms_e2e_full_fresh_$$.sqlite \
npm run build

E2E_API_PORT=18009 \
E2E_WEB_PORT=5183 \
E2E_API_ORIGIN=http://127.0.0.1:18009 \
E2E_DB_FILE=/tmp/wms_e2e_full_fresh_$$.sqlite \
npm run test:e2e
```

Frontend result:

- `npm run build`: passed
- `npm run test:e2e`: `140 passed`, `0 failed`, `7 skipped`
- Playwright total: `147` tests
- Duration: `11.8m`

Earlier control run before the final auth-dual fix:

- `139 passed`, `1 failed`, `7 skipped`
- The only failed test was `auth-dual-portal-sessions.spec.ts`.
- Targeted rerun after the fix: `auth-dual-portal-sessions.spec.ts`: `2 passed`.

Repository state after the green run:

- `HEAD`: `4f7148f3e2139ce931dc27b2956ec9a2c0c92d48`
- `origin/integration/wms-wave0-20260814`: `4f7148f3e2139ce931dc27b2956ec9a2c0c92d48`
- `etalon`: `2fb61a39f4659df4bf4411924bbf3d5bc4dc38b6`
- `origin/etalon`: `2fb61a39f4659df4bf4411924bbf3d5bc4dc38b6`
- Dirty state: none

## 27 to 0

Observed progression from ORDER 041:

- 20:45: `27` failed
- 21:15: `12` failed
- 21:45: `0` failed

The raw first-run failure artifact is not preserved in `frontend/test-results`; Playwright only kept failure context during active failed runs. Therefore the breakdown below is by recovered root causes from the ORDER text, local command output, and the six stabilization commits, not a preserved per-line failure manifest.

Recovered classification:

- True product regressions fixed in source code: `2` root causes.
- Stale e2e contract / setup / selector issues fixed in tests or helpers: `10` root causes.
- Individual failure count represented by those root causes: `27 -> 0`; the exact original per-test mapping is not recoverable from current artifacts.

True source-code regressions:

- `frontend/src/screens/ff/FfDashboard.tsx`: dashboard did not expose the organization name required by `TC-S01-001`. Fixed by restoring visible `org-name` and marking it with `data-task-id="TC-S01-001"`.
- `frontend/src/apps/seller/SellerApp.tsx`: FF-token-only browser contexts opening `/seller/products` got the wrong surface contract. Fixed to show human access denied for the cross-portal route, with `data-task-id="R02-F14"`.

Stale e2e contract / setup root causes:

- Legacy inbound tests created drafts without planned boxes although `REC-08` made planned cargo places/boxes mandatory.
- Legacy inbound setup used outdated receiving lifecycle assumptions instead of current `begin-receiving`.
- Inbound queue tests expected older composition fields and a separate boxes test id.
- Receiving operation type tests still expected `Поставка` where the current FF screen uses `Приёмка`.
- MP/FBO tests expected old not-yet-distributed box progress.
- MP/FBO full-flow date input used a helper that no longer matched the visible MUI date spinbuttons.
- Dashboard test clicked shell navigation while an MP document dialog was still intentionally open.
- Shift-lead permission test used the old technical permission checkbox instead of the compact product group.
- Auth dual-portal test expected seller login for an FF-token-only `/seller/products` route although R02/F14 evidence requires human denial.
- Some checks were strengthened from "element visible" to exact state text or explicit discrepancy confirmation.

## Changed checks and task IDs

- `summary-distributed: 0 -> 2` and `summary-remaining: 2 -> 0`: `MPFBO-05`. Boxes are inside packaging, and the current flow distributes the two units into the box before the packaging summary is asserted.
- `ff-mp-tab-packaging-panel` exact text `Готово 2 / Осталось 0` instead of just `ff-packaging-task-status` visible: `MPFBO-05`. The test now verifies completed packaging progress, not only element presence.
- Visible `ff-inbound-discrepancy-dialog` before completion confirmation: `REC-07`, `REC-13`. Discrepancies are explicit and must be confirmed instead of silent completion.
- Legacy inbound `planned_box_count` patch before submit: `REC-08`. The test setup now satisfies the mandatory planned boxes rule.
- `beginInboundReceiving` / `beginInboundReceivingWithBoxes` in setup: `REC-03`, `SEL-03`, `REC-09`. The flow is "seller transferred to warehouse -> FF took into work -> boxes/receiving", not a legacy primary-accept shortcut.
- Inbound queue composition from `1 поз.` / separate boxes field to `0 из 1 коробов` and `3 ед.`: `REC-10`, `REC-08`. Queue rows expose operational box/unit composition directly.
- FF receiving operation type from `Поставка` to `Приёмка`: `REC-01`. The FF warehouse screen uses receiving terminology.
- `/seller/products` with only FF token from seller login to human access denied: `R02`, `F14` live evidence. FF sessions must not see seller data or seller navigation on a seller deep route.
- Shift-lead permission selector from technical `shift_lead` checkbox to compact `Отгрузки` access: `F14` product evidence. The product-facing group grants the shipment/packaging/reprint/shift-lead capability bundle.
- MP planned date input via visible `Day` / `Month` / `Year` spinbuttons while still waiting for `PATCH /operations/marketplace-unload-requests/`: `TC-NEW-MP-FULL-001` / MP full-flow evidence. Business assertion was not weakened.
- Dashboard navigation after MP dialog: close `ff-supplies-doc-dialog` before `nav-dashboard`: `CAL-01`. Calendar is checked from normal shell state, not through a modal backdrop.
- `org-name` on dashboard: `TC-S01-001`. The visible element existed as a long-standing test requirement; final follow-up only added explicit `data-task-id`.
- API origin fallback to `E2E_API_PORT`: e2e infrastructure correction only, no visible product requirement.

## Commits in this frontend gate

- `fd13a83` - `test(e2e): align inbound receiving regression flows`
- `4b0f68a` - `test(e2e): sync inbound receiving flows`
- `2a75939` - `fix(e2e): stabilize auth staff permissions specs`
- `5dea64c` - `test(e2e): stabilize MP dashboard flows`
- `e178c36` - `test(e2e): finalize remaining frontend checks`
- `4f7148f` - `test(e2e): align seller route guard contract`

## Final blockers

Code/test blockers: none.

Deployment blockers: user decision required.

Do not merge `integration/wms-wave0-20260814` into `etalon`, and do not start stage or production deployment, without explicit user instruction.
