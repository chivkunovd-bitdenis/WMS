# AGENTS

This repo is optimized for an “autopilot” development loop.

## Product decisions (source of truth)

Before picking an issue, read **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)** (RU): tenants, billing liter‑day, WB import‑only, portal scope, printer 58×40.

Epic map for splitting work: **[docs/BACKLOG_EPICS_RU.md](docs/BACKLOG_EPICS_RU.md)**.

## Autopilot loop (single feature at a time)

1. Pick the next GitHub Issue with label `ready` (skip `blocked`).
2. Re-state the acceptance criteria (Given/When/Then) and identify impacted modules.
3. Implement **vertical slice**:
   - API routes only in `backend/app/api`
   - business logic only in `backend/app/services`
   - data models only in `backend/app/models`
   - DB access only via `backend/app/db`
4. Add tests:
   - backend: pytest for core logic/validation
   - frontend: Playwright e2e that verifies **user-visible outcome** (not just HTTP 200)
5. Run gates locally:
   - backend: `ruff check . && mypy . && pytest` (in `backend/`)
   - frontend: `npm run build && npm run test:e2e` (in `frontend/`)
6. Open PR with the template and wait for CI green.
7. Only after green CI: mark issue done and move to next `ready`.

## E2E rule (must be user-centric)

Every feature that changes UI flow must ship with at least one Playwright scenario that:
- performs actions through the UI
- asserts visible UI state and primary outcomes
- uses stable selectors (`data-testid`)

