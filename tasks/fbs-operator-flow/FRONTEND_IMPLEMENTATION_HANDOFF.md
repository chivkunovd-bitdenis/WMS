# Frontend implementation handoff — live

**Branch:** `feat/fbs-stock-sync`
**Frontend baseline:** `a391281`
**Owner split:** Composer edits backend only; Codex edits frontend and this handoff only.
**External actions:** no push, merge, deploy, or live WB calls.

## Integrated snapshot

- Backend stabilization: `ea247ce` (`fix(FBS): stabilize UI-facing error and print contracts`).
- Frontend implementation: `6842cbd` (`feat: implement FBS operator frontend flow`).
- Current branch order is correct: frontend commit is a direct child of the backend commit.

## Objective

Replace the legacy FBS operator path with the contract in `BACKEND_CONTRACT.md` and
`FRONTEND_TASKS.md`, while preserving the existing WMS navigation and MUI theme.
The UI must be designed in running React and visually checked in a browser; Composer
must not invent the visual design.

## Verified baseline

- Current frontend worklist uses legacy `GET /operations/fbs-orders`.
- Supply creation uses unsafe `create supply -> add order N times`.
- Supply UI is a narrow legacy drawer and delivery sends no preflight/version/idempotency body.
- Picking stores operator state in `localStorage`.
- Existing WMS theme is retained: Inter/system font, violet primary, light slate background,
  rounded MUI surfaces.
- Untracked frontend demo/print files predate this task and must not be edited or committed.

## Design decisions

1. FBS remains inside the existing authenticated WMS layout.
2. Worklist is an operator cockpit, not an accounting table: product identity, stock location,
   route eligibility, metadata and deadline are visible before selection; price is absent.
3. Creating a supply always passes server preflight and one atomic `from-orders` command.
4. Supply work opens in a near-fullscreen workspace with six stable operator stages.
5. One primary action per stage; blockers are visible next to the disabled action.
6. Operational progress is server-owned. No FBS pick/pack state is written to browser storage.
7. Print assets are URLs with a preview; no base64 fallback.
8. WB mutations reuse one idempotency key for a user operation and never show optimistic success.

## Implementation ownership

Planned task-owned files:

- `frontend/src/screens/v2/fbsApi.ts`
- `frontend/src/utils/readApiErrorMessage.ts`
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx` (new)
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (new)
- `frontend/src/components/fbs/FbsChips.tsx`
- targeted frontend tests if time permits
- this handoff

## Current status

- [x] Backend P0 fixes independently accepted on `a391281`.
- [x] Existing frontend and FBSFE-010..090 requirements mapped.
- [x] New API client/types; structured `FbsApiError` keeps code/context/retryable.
- [x] Worklist and atomic create dialog.
- [x] Fullscreen workspace and route-specific delivery.
- [x] TypeScript gate.
- [x] Visual composition checked at 1280x720 and 1920x1080.
- [x] Production build, lint and unit gates independently re-run after a clean dependency install.
- [x] Synced with Composer backend P1 commit and independently audited its targeted tests.

## Implemented frontend behavior

- Worklist uses `/operations/fbs-orders/worklist` with server status/search/seller filters.
- Visible product photo, WB/WMS warehouses, locations/availability, identifiers, buyer/cargo,
  PVZ eligibility, metadata state, status and server-clock deadline.
- Selection excludes rows with server blockers and exposes the blocker in the sticky action bar.
- Create dialog re-runs preflight for selection/route and sends one atomic `from-orders` request.
- Fullscreen workspace has six stable stages and polls active picking/delivery every 15 seconds
  only while the document is visible.
- Picking and undo use server operations; no operational localStorage state.
- Picking is aggregated by product and shows locations/available units, required/picked counts,
  linked WB orders, marking need and nearest deadline; undo remains per server order state.
- Existing `FfPackagingTaskPanel` is embedded through `packaging_task_id`.
- Metadata scan preserves the raw value without `.trim()` and the workspace renders required and
  actual metadata state for every WB order.
- Print batch shows ready/missing/failed and exact per-order errors. The preview dialog fetches
  protected PNG assets with auth, renders them before printing, emits 58mm x 40mm pages, never
  opens a blank print window at `ready=0`, and keeps print/applied as separate actions.
- Order sticker requests support selected/all/retry-missing paths.
- PVZ shows physical cargo places without order-to-box assignment and prints one/all cargo QR;
  warehouse/SC skips cargo places and prints the supply QR after delivery.
- Delivery always uses fresh preflight version and a stable idempotency key retained on failure.
- Tracking/status refreshes from canonical workspace, exposes stale sync state, and renders
  accepted/rejected rows plus rejection reason when the backend provides it.

## Contract note

The frozen frontend task text describes cargo preflight as `{boxes}`, but the live backend
`FbsCargoPlacesPreflightBody` requires `{count, boxes}`. The client currently follows the live
backend. Composer/backend must either preserve this shape or update both contract documents before
the final freeze; do not add a runtime fallback.

## Final local verification

```text
./node_modules/.bin/tsc -b --pretty false    PASS
targeted eslint                              PASS
npm run test:unit                            PASS: 13 files, 110 tests
npm run build                                PASS: TypeScript + Vite, 11993 modules
targeted backend SQLite suite                PASS: 49 passed, 4 skipped
FBS contract Playwright                      PASS: 2 tests
Playwright real-stack with PostgreSQL        NOT RUN
```

The backend pytest run emitted SQLAlchemy warnings about cyclic foreign keys while dropping
SQLite test tables. Treat those warnings and the four PostgreSQL-only skips as test-environment
limits, not as a green PostgreSQL proof.

Earlier visual QA used a static high-fidelity composition. It is not an end-to-end React proof.
At both 1280x720 and 1920x1080 the worklist and fullscreen workspace had no horizontal document
overflow; primary actions, blockers and progress remained visible.

Composer's backend P1 is integrated at `ea247ce`. This audit proves emulator/SQLite behavior only;
live WB (TC-24), PostgreSQL, Celery and deployment remain release gates.

## Resume point

The local frontend gates are green. The next proof is a real React/browser pass against backend,
PostgreSQL and the emulator together. Static composition QA does not need to be repeated unless
layout code changes.

## Required final gates

```bash
cd frontend
npm run build
npm run test:unit
```

Run touched-file lint and targeted browser checks at 1280x720 and 1920x1080. Full real-stack
Playwright remains a separate gate until PostgreSQL/backend/emulator are available together.
