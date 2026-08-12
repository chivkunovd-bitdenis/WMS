# Independent system-wide review — teamlead

Status: **FINAL — STOP-SHIP** for the reviewed inbound completion path. Date: `2026-08-12 MSK`.

## Executive verdict

The strongest result is not a code hypothesis: staging independently reproduced a stock-conservation failure twice in two fresh synthetic tenants. One accepted unit, completed concurrently by two clients, produced two successful responses, two `+1` inventory movements and balance `2`, while the document still recorded fact `1`. The affected code is byte-identical between the orchestrator-represented deployment candidate `44fe72e` and etalon `a39530c`. This is `TL-F001`, P0, and blocks release of that path until concurrency/retry is single-effect and existing staging data is checked for duplicate receipt movements.

The rest of the system cannot receive a blanket “green” verdict. Ten evidence-backed findings remain: one P0, seven P1 and two P2. The most material P1s concern mobile release provenance, a clean mobile build that depends on absent generated source, sorting lost updates, stranded background jobs, competing migration owners/false-green deploy, email-only initial account claim, and email-substring shop-manager authorization. The named Inventory screen is only a placeholder (P2), and shared desktop layout overflow is P2.

## What was actually covered

The ledger inventories all tracked source at the pinned objects: backend `377`, frontend `259`, mobile `71` files. All 14 source groups are `REVIEWED`; generated wrapper binaries, logos/fixture binaries and template boilerplate are explicitly inventory-only rather than silently omitted. Review focus was transactional correctness, tenant/seller scope, authentication/authorization, migrations, jobs, retries/idempotency, recovery, tests and runtime alignment. “Reviewed” means the group was inventoried and its assigned risks were traced; it is not a line-by-line guarantee or a runtime pass.

UI execution was split deliberately. The orchestrator performed real staging clicks through the Browser skill on synthetic data. The teamlead then personally opened every supplied image at original detail and independently adjudicated it. Code inspection without an image was never counted as a route run. Evidence comprises 12 early FF routes, 12 stable FF routes at verified CSS `1920×1080`/DPR1, warehouse/cell and catalog workflows, seller first-login and four stable routes, seller document actions, MP draft creation/reload/reopen, and all five FBS order tabs plus WB-stock/reload.

Two bounded visual/state slices pass: a warehouse and two cells survive navigation/reload/reselection, and an MP shipment draft survives reload/reopen. Neither is a complete inventory or document lifecycle. The mandatory top-level results are therefore:

- Authentication: first-login and role landing were visibly reached, but reload plus `/auth/me` and a negative-role check were not supplied; `NOT_RUN` as a complete scenario.
- Inventory mutation: `FAIL`; the Inventory route only says “section under development”, and the catalog attempt was correctly stopped because seller was unselected.
- Document lifecycle: `NOT_RUN`; draft persistence passes, but no submit→processing→completion lifecycle was exercised.
- FBS: `NOT_RUN` for mutation/retry; tabs and reload pass as read-only navigation, but no order/supply or WB write was authorized/executed.

## Findings and impact

1. `TL-F001` P0 BUG — concurrent complete-receiving doubles stock. Reproduced `2/2`, separate tenants and clients, with server read-back and movement delta proof.
2. `TL-F002` P1 SECURITY — tracked mobile signing material plus tracked unlock configuration lets any repository reader produce a signature-equivalent pilot APK. Offline metadata/history only; the key was not used, exported or changed, and values are omitted.
3. `TL-F003` P1 RELIABILITY — a clean pinned mobile tree imports an ignored generated API client in 14 source files but tracks none of it; generation is outside Gradle and may bind to a live local backend.
4. `TL-F004` P1 RELIABILITY RISK — mobile sorting merges a fresh GET into a whole-list PUT; backend deletes and recreates all draft rows without version/lock. A two-writer runtime reproduction is still required, but the lost-update window is explicit in both clients and server contract.
5. `TL-F005` P1 RELIABILITY RISK — generic background jobs commit `pending` before broker publish and `running` before work, with no delivery compensation, late acknowledgement, lease or stale-job recovery. Fault injection remains pending.
6. `TL-F006` P1 RELIABILITY — deploy is not CI-gated, smoke proves only three HTTP 200s, and API/worker can both run Alembic concurrently. A later non-etalon hotfix corroborates the migration-owner issue.
7. `TL-F007` P2 PRODUCT GAP — Inventory has no operator action.
8. `TL-F008` P1 SECURITY — unauthenticated first-password setup accepts only email plus new password and returns an access token. Existing tests encode this behavior; hostile staging takeover was deliberately not attempted.
9. `TL-F009` P1 SECURITY — hard-coded personal-name substrings in an email grant seller-shop manager capability; the explicit DB flag/configured allowlist is bypassed. Tenant boundary remains, seller boundary does not.
10. `TL-F010` P2 BUG — stable FF/seller desktop routes repeatedly overflow horizontally and hide actions/data even at verified 1920 CSS pixels.

P1 items without safe second runtime reproduction remain P1 evidence-backed risks, not falsely promoted runtime facts. Their closure gates are in the individual cards.

## UI engineering verdict

All stable routes load without a visible fatal error, but the desktop layout has a shared horizontal-overflow problem even at a verified 1920 CSS pixels: action groups, explanatory copy and tables repeatedly extend beyond the right edge. Early dark/narrow frames are transition artifacts and were superseded by stable captures; they are not used to overstate the defect. Creation dialogs for warehouse, cell and product are also clipped at the right/bottom, although warehouse/cell writes succeeded.

Seller Documents, Products, Honest Sign and Settings render real states; first password setup lands in Documents. The discrepancy action explicitly says it will be implemented at a later stage. FBS tabs render coherent empty/read-only states, but some intermediate captures are transitional and no external write/retry behavior was exercised.

The claimed generic product-create non-2xx fallthrough was independently **refuted**: both `44fe72e` and `a39530c` contain `setError(raw); return`, and their dialog file has no diff. Runtime evidence shows only correct required-seller validation and no product after reload.

## Tests and false-green boundaries

Static quality commands recorded earlier passed Ruff and Mypy, but they do not cover business races. Local functional tests were prohibited; a prematurely started pytest run was stopped and excluded from evidence.

Default backend tests use SQLite. PostgreSQL migration/concurrency tests skip or cannot reproduce locking semantics without `WMS_TEST_DATABASE_URL`. Default Playwright ignores the full FBS flow, uses one SQLite worker and mocks WB cards, supplies and warehouses. CI itself is PR-only and explicitly does not block a main deployment. Production smoke checks only HTTP status, not SHA, schema head, worker readiness or business read-back. These facts explain how the P0 can coexist with green static/unit pipelines.

## Runtime alignment and blockers

Source declarations align at Python 3.11, Node 20 and Java 17. That is not deployment proof. The public frontend bundle exposes no build SHA; API health exposes no SHA; worker and schema expose no version. The orchestrator represented staging as `44fe72e`, and the teamlead verified that object and its relation to etalon, but could not independently bind frontend, API, worker and schema separately to it. Environment verdict remains `BASELINE_BLOCKED`; staging observations must not be attributed to etalon as a whole.

Production/live WB, real printer/scanner hardware and destructive/bulk actions were excluded. Browser execution was unavailable inside the teamlead runtime but was performed by the orchestrator; adjudication remained independent. No secret dashboard was opened, no key lifecycle action occurred, and no credential/signing value is present in the review artifacts.

## Release gates

Before treating this system as release-ready:

1. close `TL-F001` with a PostgreSQL concurrency test and two clean runtime repetitions proving one movement/one balance effect under double click and lost-response retry;
2. expose and verify exact frontend/API/worker SHA plus schema revision, and serialize migration ownership;
3. run the missing inventory, complete document and FBS retry/recovery scenarios with reload and server read-back;
4. execute PostgreSQL concurrency/migration suites and a clean mobile build from pinned inputs;
5. close the account-claim, shop-manager and mobile signing provenance boundaries before granting real tenant/operator access.

Until then, the honest status is: **tracked source reviewed, critical receiving path failed, several high-impact boundaries statically proven, mandatory runtime coverage incomplete, deployment baseline unproven.**
