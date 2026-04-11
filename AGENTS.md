# AGENTS

This repo is optimized for an “autopilot” development loop.

## Product decisions (source of truth)

Before picking an issue, read **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)** (RU): tenants, billing liter‑day, WB import‑only, portal scope, printer 58×40.

Epic map for splitting work: **[docs/BACKLOG_EPICS_RU.md](docs/BACKLOG_EPICS_RU.md)**.

## Autopilot loop (single feature at a time)

1. Pick the next GitHub Issue with label `ready` (skip `blocked`).
2. Re-state the acceptance criteria (Given/When/Then) and identify impacted modules.
3. Implement **vertical slice**:
   - API routes only in `backend/app/api` (в т.ч. интеграции: `wildberries_integration.py` → `/integrations/wildberries/...`, в т.ч. `status` и `sellers/{id}/tokens` для админа)
   - business logic only in `backend/app/services`
   - data models only in `backend/app/models`
   - DB access only via `backend/app/db`
   - Celery tasks only in `backend/app/tasks` (enqueue from API; broker via `CELERY_BROKER_URL`; unset `CELERY_BROKER_URL` uses FastAPI `BackgroundTasks` for local/tests; типы джоб: `movements_digest`, `wildberries_cards_sync` + `seller_id` в теле)
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

The scenario must match the real user path (e.g. register → screen that uses the new API), not an isolated HTTP check. With the default Playwright web server (one API + sqlite file), CI runs **`workers: 1`** to avoid DB lock flakes. In React async submit handlers, capture `const form = e.currentTarget` **before** any `await`, then call `form.reset()` — otherwise Strict Mode can leave `currentTarget` null after awaits.

When asserting on network: subscribe with `page.waitForResponse` **in parallel** with the UI action (`Promise.all([waitForPostOk(...), locator.click()])`). If you `click()` first and only then await the response, the request may already have finished and the test will time out. After a successful submit that resets the form, the next step must refill **all** required fields (e.g. product dimensions), not only the fields that differ from defaults.

