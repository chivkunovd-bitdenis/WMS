# Commands and sanitized results — teamlead

## Baseline and inventory

- `git rev-parse --show-toplevel` → isolated review worktree under canonical `/Users/deniscivkunov/Projects/WMS`.
- `git branch --show-current` → `review/system-wide-teamlead-20260812`.
- `git rev-parse HEAD` → `c964e0e8a47e690d7938e486073bd40d74bf0cc7`.
- `git diff --name-status a39530c..HEAD` → only four review-protocol Markdown files.
- `git diff --quiet a39530c -- backend frontend ...` → exit `0`, runtime code unchanged.
- `git ls-files backend | wc -l` → `377`.
- `git ls-files frontend | wc -l` → `259`.
- `git -C mobile ls-tree -r --name-only 09aa479f | wc -l` → `71`.
- API inventory: 30 route modules and 224 decorated HTTP operations.
- Frontend inventory: 71 Playwright `*.spec.ts` files; FF/admin and seller route trees recorded in `coverage-ledger.md`.

No command in this run reads `.env`, a token store, browser cookies/local storage, production data, or a credentials dashboard.

## Staging baseline gate

- Public root `200`; asset `/assets/ff-Cq0IpEp3.js`; `Last-Modified: 2026-08-09 14:10:41 GMT`.
- `/api/health` → `200`, body `{"status":"ok"}`; it does not identify API SHA or schema.
- `/api/version` and `/api/meta` → `404`; SPA fallbacks at `/version` and `/meta` are not version evidence.
- `git ls-remote origin refs/heads/staging` → `74b84939a7e6e4082ac4761d6332197e14f108fd`, but a remote ref is not proof of a Railway deployment.
- Public frontend bundle contains no `a39530c`, review SHA, or other 40-hex build marker.
- No non-secret public worker or schema version surface was found.
- Result: `BASELINE_BLOCKED`; frontend/API/worker/schema alignment is unknown.

## Browser execution and adjudication

- The Browser skill was read in full before browser actions.
- Browser runtime selection for the staging URL returned `No browser is available`.
- Required bootstrap troubleshooting was read; one discovery call returned an empty browser list.
- The orchestrator therefore executed named staging interactions through its Browser runtime. Teamlead used `view_image` on every supplied PNG and bound verdicts to SHA-256 in `ui-evidence/index.md`.
- Stable desktop viewport evidence is CSS `1920×1080`, DPR `1`. Early dark/narrow frames are treated as transitional, not stable layout evidence.
- Durable visual passes: warehouse + two cells after reload/reselect; MP shipment draft after reload/reopen.
- Incomplete mandatory paths: stock inventory mutation, full document lifecycle, and an FBS mutation/retry remain `NOT_RUN`; seller auth lacks reload plus `/auth/me` proof.

## Local gate boundary

- `ruff check .` → passed.
- `mypy .` → passed, `237` source files checked.
- A local `pytest -q` was launched before the staging-only scope update, interrupted almost immediately, then terminated. It has no result and no evidentiary value; generated synthetic files were moved to Trash.

## Independent P0 staging verification

- Two attempts used two newly registered synthetic staging tenants (`TL-P0-A`, `TL-P0-B`), not the architect tenant or IDs. No WB endpoint was called.
- Each attempt created one product and one inbound line with plan/fact `1`, then issued two concurrent `complete-receiving` requests from separate HTTP clients.
- Attempt A: response statuses `200, 200`; final document fact `1`; balance `2`; movement deltas `[+1,+1]`.
- Attempt B: response statuses `200, 200`; final document fact `1`; balance `2`; movement deltas `[+1,+1]`.
- Result: `2/2 reproduced`; sanitized evidence is `evidence/TL-P0-double-complete-receiving.md`.
- `git merge-base --is-ancestor 44fe72e a39530c` → yes. Critical inbound API/service/inventory files are identical between the commits. The whole runtime delta from `44fe72e` to etalon changes a WB orders service and adds migration `0076`, but not this inbound path.

## Static reliability, authorization and release checks

- Product-create control-flow compare: `git diff 44fe72e..a39530c -- frontend/src/screens/ff/FfManualProductCreateDialog.tsx` → empty. Both objects contain a generic `setError(raw); return`; the proposed generic non-2xx fallthrough is refuted.
- Background jobs: a pending row is committed before Celery `.delay`; tasks commit `running` before work. No late acknowledgements, retry policy, lease/heartbeat or stale-job recovery was found (`TL-F005`).
- Sorting: mobile performs fresh GET + whole-list PUT; backend deletes and replaces all distribution rows without version control (`TL-F004`).
- Deploy: CI is PR-only and explicitly non-blocking; main deploy smoke checks only three HTTP 200 responses. API and worker both invoke Alembic. Later reachable hotfix `8097bc0` separates the migration owner but is not in etalon (`TL-F006`).
- Tests: backend default DB is SQLite; PostgreSQL migration/concurrency cases skip or alter semantics without `WMS_TEST_DATABASE_URL`. Default Playwright ignores `ff-fbs-full-flow.spec.ts`, runs one SQLite worker and mocks WB cards/supplies/warehouses.
- Initial-password endpoint takes email/password without authentication or one-time proof and returns a bearer token; existing tests codify that flow (`TL-F008`).
- Seller-shop manager predicate grants on hard-coded email substrings in addition to explicit stored/configured permissions; tests codify five examples (`TL-F009`).

## Mobile pinned-tree checks

- `git ls-tree` at `09aa479f` → 44 main files, 7 unit-test files, 20 other tracked build/contract/doc files.
- Fourteen main files import an ignored generated API package; zero generated sources are tracked. Generation is a separate, non-Gradle script that can select a running local backend (`TL-F003`).
- Offline keystore metadata: tracked 2680-byte PKCS12 container with one private-key entry. Release build references it and tracked unlock literals; it entered history in `3ab29af...` (`TL-F002`). No value is reproduced here, and the signing key was never used/exported/changed.
- Runtime declarations align at Python 3.11, Node 20 and Java 17 at source/CI level. Exact mobile client ↔ deployed API/schema/worker alignment remains blocked by missing staging component version evidence.
