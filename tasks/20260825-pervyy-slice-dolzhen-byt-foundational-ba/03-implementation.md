# Call 76 — Slice 1 implementation record

## Implemented

- Added the additive, reversible `marketplace_accounts` schema and generic model with a hidden
  `primary` slot, tenant/seller scope, encrypted secret field and disconnect audit fields.
- Added self-scoped Ozon `GET`/`PUT`/manual validation/`DELETE` routes. They expose only the
  public status contract, use the current seller `settings` permission and never accept a seller
  or account selector from the client.
- Added a minimal injectable validation adapter. One action performs at most one read-only
  `POST /v1/seller/info` with `{}`, ignores the response body, disables redirects and schedules no
  jobs. The existing isolated E2E harness uses its local provider fake, so the tests do not call
  Ozon.
- Added one Ozon `Paper` between the unchanged WB and Honest Sign cards on S-32. It has inline
  disconnected, checking, connected, invalid/unavailable-error and inline disconnect-confirm
  states; it adds no route, modal, selector or sync control.

## Verification

- `backend`: focused marketplace-account, Ozon API/migration and WB-regression pytest selection
  passed locally with test fakes.
- `backend`: scoped `ruff check` and `mypy` passed for the new/changed production modules.
- `frontend`: `npm run build` passed.
- `frontend`: the focused Playwright file could not start in this sandbox because its backend
  webServer was denied bind to `127.0.0.1:18000` (`operation not permitted`). No browser tests or
  real Ozon traffic ran. This must be re-run in a sandbox that permits the local test server.

## Scope and deviations

Only NARYAD-authorized production/test files and this report were changed. The frozen backend
tests received two harness-only corrections: unauthenticated route calls now use the compatible
generic HTTPX request method, and the migration guard forbids crypto operations rather than the
required `secret_encrypted` column name. The seller-settings test now waits for the correct PUT and
exercises connect, inline cancel, inline confirm and idempotent DELETE as required by Call 76.

## Persistence blocker

The sandbox denied creation of
`/Users/deniscivkunov/Projects/WMS/.git/worktrees/ozon-module-sol-20260824/index.lock` with
`Operation not permitted`, so this agent could not stage or create the required isolated commit.
The lead must stage only the listed Slice 1 files and commit them from an environment permitted to
write the worktree Git index; no SHA exists yet.
