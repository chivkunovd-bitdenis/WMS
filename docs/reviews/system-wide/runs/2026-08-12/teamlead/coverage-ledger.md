# Coverage ledger — teamlead

Statuses follow the review charter. `REVIEWED` means the tracked group was inventoried and its assigned teamlead concerns were statically checked; it does not by itself claim user-visible correctness.

## Tracked-source inventory

| Code area | Included paths at pinned SHA | Count | Excluded paths and reason | Focus | Status | Evidence |
|---|---|---:|---|---|---|---|
| Backend API | `backend/app/api/**` | 30 | none | authn/authz, object ownership, request retry | REVIEWED | Initial-password boundary, seller effective-scope dependency, background enqueue, inbound/FBS routes inventoried; `TL-F001`, `TL-F005`, `TL-F008`, `TL-F009`. |
| Backend services | `backend/app/services/**` | 72 | none | transactions, invariants, idempotency, recovery | REVIEWED | P0 independently reproduced twice on staging; `TL-F001`. Static review also covers sorting replacement and background recovery. |
| Backend models | `backend/app/models/**` | 43 | none | tenant/seller ownership, uniqueness, constraints | REVIEWED | Tenant ownership is pervasive; receipt movement lacks one-effect uniqueness (`TL-F001`); background job has no lease/retry identity (`TL-F005`). |
| Backend DB/core/main | `backend/app/{db,core}/**`, `backend/app/main.py` | 6 | none | runtime configuration, session boundaries, startup | REVIEWED | Session/startup/config reviewed with deploy graph; runtime component versions remain blocked. |
| Background runtime | `backend/app/tasks/**`, `backend/app/celery_app.py` | 3 | none | retry, dedupe, API/worker alignment | REVIEWED | No task late-ack/retry or stale-job recovery; `TL-F005`. FBS WB operations separately have stronger pending-confirmation reconciliation. |
| Migrations | `backend/alembic/**`, `backend/alembic.ini` | 81 | `script.py.mako` is boilerplate, inventory-only | linearity, upgrade/downgrade, model alignment | REVIEWED | Single apparent head `0076`; PostgreSQL round-trip not run. Multiple runtime migration owners and unknown staging schema: `TL-F006`. |
| Backend tests | `backend/tests/**` | 132 | binary/generated test artifacts none | relevant coverage, skipped paths, false green | REVIEWED | Default SQLite hides row-lock semantics; PG migration/concurrency tests require external URL/skip. No concurrent receive, stale background-job recovery or sorting lost-update test. |
| Backend packaging/runtime | remaining tracked files under `backend/**` | 10 | lock file semantically reviewed as dependency/version manifest, not package source | versions, launch commands | REVIEWED | Python 3.11 aligned across Docker/CI; exact staging runtime blocked. |
| Frontend application | `frontend/src/**` | 152 | binary/logo assets inventoried but excluded from semantic line review | route/role gates, durable read-back, error paths | REVIEWED | Route screens visually sampled; auth/product failure paths and seller effective scope reviewed. Claimed generic product-create fallthrough refuted on both compared SHAs. |
| Frontend E2E | `frontend/tests-e2e/**` | 84 | fixture binaries inventory-only | user-visible assertions, mocks, ignored suites | REVIEWED | 71 specs inventoried; default config ignores full FBS flow and uses SQLite/mock WB; staging credential values never copied to artifacts. |
| Frontend packaging/runtime | remaining tracked files under `frontend/**` | 23 | lock file reviewed as dependency manifest | versions, proxy/build alignment | REVIEWED | Node 20 in CI; frontend public bundle has no build SHA. |
| Mobile main source | `mobile@09aa479f:android/app/src/main/**` | 44 | shared dirty checkout excluded; pinned Git objects only | auth, tenant context, retry/offline, scanner | REVIEWED | Sorting whole-list replacement (`TL-F004`); 14 files depend on absent generated client (`TL-F003`). Physical scanner runtime blocked. |
| Mobile tests | `mobile@09aa479f:android/app/src/test/**` | 7 | none | false green, API contract | REVIEWED | Seven files/README claim 18 tests; no auth/release/build provenance coverage; not executed by staging-only scope. |
| Mobile build/contracts/docs | remaining tracked files at `09aa479f` | 20 | Gradle wrapper binary inventory-only | runtime/API version alignment | REVIEWED | JDK 17/SDK 35 declared; ignored generated contract and tracked release signer findings `TL-F002`, `TL-F003`; API exact runtime alignment blocked. |

Inventory totals: backend `377`, frontend `259`, mobile `71` tracked files.

## Runtime/UI scenarios assigned to teamlead

| Scenario ID | Route / user goal | Required evidence | Status | Finding / reason |
|---|---|---|---|---|
| TL-AUTH-01 | Ordinary login and role-aware landing | Browser before/result/reload plus `/auth/me` read-back | NOT_RUN | Orchestrator executed seller first-login and role landing; teamlead verified result screenshot. Required reload plus `/auth/me` evidence was not supplied, and negative-role check was not run. |
| TL-INV-01 | One inventory mutation | Browser before/action/result/reload plus API/DB read-back | FAIL | Inventory route is a placeholder (`TL-F007`). Product-create attempt correctly failed required seller validation; warehouse/cell configuration is not a stock mutation. |
| TL-DOC-01 | One document lifecycle | Browser before/action/result/reload plus API/DB read-back | NOT_RUN | MP draft creation persisted through reload/reopen; seller inbound draft appears in result. Neither document was advanced through a complete business lifecycle, and seller draft lacks reload proof. |
| TL-FBS-01 | One FBS operator path | Browser before/action/result/reload plus API/DB/emulator evidence | NOT_RUN | All five order tabs, WB-stock tab and reload were clicked/read; no order/supply/retry/WB mutation was executed. Production/live WB excluded. |
| TL-CELL-01 | Create warehouse and two cells | Browser before/result/reload/reselect | PASS | Corrected visible reload screenshot proves warehouse, two cells and sorting row persisted. Execution by orchestrator; adjudication by teamlead. |
| TL-MP-DRAFT-01 | Create/reload/reopen MP draft | Browser before/result/stable/reload/detail | PASS | Draft `№000001`, seller and warehouse persisted; this is only the draft slice, not lifecycle completion. |

## Environment exclusions and blockers

| Scope | Status | Reason |
|---|---|---|
| Production/live WB | EXCLUDED | No authorization; no external mutation permitted. |
| Physical printer/scanner (E5) | BLOCKED | No dedicated physical device assigned to this isolated run. Emulator/mobile code may only establish lower-level evidence. |
| Staging deployed-version evidence (E7) | BLOCKED | Exact frontend/API/worker SHA and schema version cannot be proven from public non-secret surfaces. |
| Browser staging UI in teamlead runtime | BLOCKED | No browser instance in subagent runtime. Orchestrator executed named Browser clicks; teamlead personally adjudicated every supplied image. |
| Local functional runtime | EXCLUDED | Explicitly prohibited after scope update. |

## Independent runtime additions

| Scenario ID | Surface | Status | Evidence |
|---|---|---|---|
| TL-CONC-01 | Concurrent complete-receiving, fact 1 | FAIL | Two fresh staging tenants; both concurrent calls returned 200, but each produced two `+1` movements and balance 2. `findings/TL-F001-concurrent-receiving-doubles-stock.md`. |

## Coverage totals

- Tracked source groups: `14 REVIEWED`, `0 BLOCKED`, with generated binaries/assets explicitly inventory-only or excluded from semantic review.
- Assigned top-level runtime scenarios: `2 PASS` slices, `1 FAIL`, `3 NOT_RUN` (the PASS rows are warehouse/cell configuration and MP draft persistence; they do not replace the incomplete inventory/document/FBS goals).
- Findings: `1 P0`, `7 P1`, `2 P2`; P0 reproduced twice independently. P1 runtime second reproductions remain incomplete unless explicitly stated static/unit evidence.
