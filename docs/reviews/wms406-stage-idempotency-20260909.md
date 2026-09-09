# WMS-406 — final legacy idempotency fix on staging

Backend `7b02fb98be1d1d8fc557760f359beb64ac2a4312` was uploaded to the existing staging WMS service using a Git archive containing only the tracked `backend/` prefix: 737 files, 9,454,872 bytes. No service settings or secrets changed. Deployment `4b82ac4b-270c-471d-a71a-3d99e755ce85` reached SUCCESS. The temporary transport directory was removed after upload finished and lsof showed no users.

At 09:12:25 UTC on 09.09.2026, all 428 runtime Python files under app/alembic matched this Git commit exactly: zero missing, differing or extra files. Frontend remains the already browser-verified `829684a0106dd8a0d6cfb050abadfebed74908dc`, deployment `abc8c3ff-4a1a-4bc7-8b71-b4d3f05d97fc`; the final backend commit has no frontend diff.

Read-only staging verification passed: backend health 200, web 200, authenticated QA tenant/role matched, seller billing details GET with limit=1 returned 200, and the existing own invoice `325b20ca-30d8-4e15-a2e1-a3d34b49d906` remained cancelled. Its original lines remained 12,500 / 100 / 28,123 kopecks, total 40,723. Only GET requests were sent. No new invoice, service, ledger, tariff or warehouse objects were created, and Chrome was not launched again. The previous actual invoice UI evidence remains in wms406-stage-reviewfix-20260909.md.

This bounded check validates delivery and existing invoice reads; it does not claim to reproduce a SQLite concurrency race on the staging PostgreSQL server. The repaired existing parallel legacy HTTP test and cross-format guards have the separate local targeted result of four passing tests. Full CI and production rollout are separate release gates.

Evidence: [runtime hash comparison](artifacts/wms406-stage-idempotency-20260909/runtime.json), [read-only checks](artifacts/wms406-stage-idempotency-20260909/readonly.json), [repeatable GET-only script](scripts/wms406-stage-readonly-check.cjs). Session values and authorization headers are not recorded.
