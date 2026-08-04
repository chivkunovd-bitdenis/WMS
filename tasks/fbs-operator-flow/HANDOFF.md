# HANDOFF — FBS operator flow (backend → frontend / Codex)

**Branch:** `feat/fbs-stock-sync` (worktree `task/FBSFLOW-140`)  
**Updated:** 2026-08-04
**Integration reference for frontend:** start from the current `HEAD` of `feat/fbs-stock-sync`; do not use a sibling task commit as a base.
**Reconciled backend merge:** `5b6aee0` (`76a4314` + remote PR head `e9d712c`)
**Audience:** frontend implementer (Codex), QA without live Wildberries cabinet

## Scope

Backend vertical slice for FBS operator flow is integrated on `feat/fbs-stock-sync`:

- Worklist, atomic supply create, workspace stages (pick / pack / marking / print / shipment / tracking)
- PVZ cargo places + warehouse/sc delivery with preflight + idempotent deliver
- WB emulator with **3 sellers**, **14+ seeded orders**, real PNG stickers/QR
- OpenAPI export + RU error catalog + product scenario TC-S17-001..024

This handoff does **not** claim live WB API compatibility — only emulator + pytest proof.

## Release-candidate proof (2026-08-04)

- `ruff check .` — PASS.
- `mypy .` — PASS, 229 production/script source files; pytest tests are excluded
  from mypy and are validated by runtime gates below.
- PostgreSQL marking suite — **10 passed**.
- PostgreSQL packaging/integrity suite — **11 passed**.
- PostgreSQL cancellation/review suite — **14 passed**, plus the corrected
  WB-metadata promotion regression — **1 passed**.
- Focused PostgreSQL union gate (marking reuse, valid box, foreign-tenant box,
  status-sync reversal) — **4 passed**.
- Alembic: fresh database upgrade to sole head `20260804_0072`, and
  `0072 -> 0069 -> 0072` round-trip — PASS.
- Intentional duplicate preflight: migration stopped at `0071`, reported one
  marking-code group and one packaging-box group, left all four links intact,
  and created neither unique index — PASS.

Not claimed here: live WB TC-24. It still requires an explicitly selected test
cabinet and credentials. GitHub CI is re-run only after this local merge is
pushed to PR #104; the old green result belongs to the old remote head.

## Production migration gate: 20260804_0072

Before applying `20260804_0072_fbs_marking_code_unique`, run the two read-only
preflight queries below against the exact production database and attach their
result to the deployment record. Both counts must be `0`. The migration refuses
to run when either count is non-zero; it never silently clears a code or box
link, because that would erase audit evidence.

```sql
SELECT COUNT(*) AS duplicate_marking_code_groups
FROM (
  SELECT marking_code_id FROM fbs_order_markings
  WHERE marking_code_id IS NOT NULL
  GROUP BY marking_code_id HAVING COUNT(*) > 1
) AS duplicate_groups;

SELECT COUNT(*) AS duplicate_packaging_box_groups
FROM (
  SELECT packaging_box_id FROM fbs_trbxes
  WHERE packaging_box_id IS NOT NULL
  GROUP BY packaging_box_id HAVING COUNT(*) > 1
) AS duplicate_groups;
```

If a count is non-zero: take a timestamped backup/export of the affected rows
and their linked orders first, decide the surviving relationship in an approved
repair ticket, preserve the rejected links in the audit record, then rerun the
preflight. Do not use an ad-hoc `UPDATE ... SET ... = NULL` during deployment.

## Local gate commands

From repository root (trailing space in path is intentional on this machine):

```bash
cd backend
export WMS_TEST_DATABASE_URL="sqlite+aiosqlite:////tmp/wms-fbs-handoff.sqlite"
export JWT_SECRET_KEY="test-jwt-secret-key-at-least-32-characters-long"

# Handoff smoke + shipment regressions (non-browser TC-17..21)
pytest tests/test_fbs_operator_flow_handoff.py \
  tests/test_fbs_shipment_pvz.py \
  tests/test_fbs_shipment_warehouse_sc.py -q --tb=line

# Emulator operator seed (TC-23 partial)
cd .. && PYTHONPATH=. pytest wb_emulator/tests/test_emulator_operator_seed.py -q

# OpenAPI contract
cd backend && pytest tests/test_fbs_openapi_contract.py -q
```

**Observed gate (2026-08-03):** `test_fbs_operator_flow_handoff.py` + 13 shipment tests → **23 passed** (~3 min); includes WMS↔emulator full flows (warehouse/sc + PVZ) and 409/timeout negatives.

### Full-flow integration tests (emulator transport)

| Test | TC | What it proves |
|------|-----|----------------|
| `test_full_flow_warehouse_sc_emulator` | TC-06, TC-21 | sync → from-orders → deliver → supply barcode PNG |
| `test_full_flow_pvz_emulator` | TC-17, TC-20, TC-21 | sync → from-orders (pvz) → cargo-places → deliver |
| `test_emulator_409_from_orders_no_false_success` | TC-06 neg | `POST /__admin/faults` supply_conflict → no local supply |
| `test_emulator_deliver_timeout_pending_confirmation` | TC-20 neg | deliver timeout → pending_confirmation, status unchanged |

`tasks/fbs-operator-flow/fixtures/handoff/*.json` are frozen, read-only sample evidence from a prior green run. Pytest never rewrites them; refresh requires an explicit reviewed update.

## Compose stack (optional full stack)

```bash
cp wb_emulator/.env.example wb_emulator/.env
docker compose -f docker-compose.yml -f docker-compose.emulator.yml up -d --build
docker compose ps
```

WMS API uses `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000` from overlay.

## Seed: three sellers

### Emulator (HTTP)

```bash
export WB_EMULATOR_ADMIN_TOKEN=admin-secret
export WB_EMULATOR_TOKEN_MAP='{"token-a":"seller_a","token-b":"seller_b","token-c":"seller_c"}'
curl -X POST -H "X-Admin-Token: $WB_EMULATOR_ADMIN_TOKEN" http://127.0.0.1:8099/__admin/seed
```

Templates: `wb_emulator/seed/order_templates.json` (14 scenario orders).  
Tokens: `wb_emulator/seed/tokens.json`.

### WMS (pytest helper)

`backend/tests/fbs_operator_emulator_seed.py` → `seed_operator_emulator_wms(async_client)`:

- Registers FF tenant + one physical warehouse + storage location
- Creates 3 sellers with emulator tokens + FBS warehouse bindings
- Products/inventory/marking pools aligned to emulator `chrtId` / barcodes

Used by `test_fbs_operator_flow_handoff.py::test_tc01_three_sellers_wms_seed_isolated`.

## API flow reference (frontend)

Canonical shapes: `tasks/fbs-operator-flow/BACKEND_CONTRACT.md`  
Live OpenAPI: `tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` (42 `/operations/fbs-*` paths)  
Errors: `tasks/fbs-operator-flow/ERROR_CATALOG_RU.md` (`retryable` column)

### Happy path sketch

1. `GET /operations/fbs-orders/worklist?seller_id=…` — enriched rows, deadlines
2. `POST /operations/fbs-supplies/preflight` — blockers before create
3. `POST /operations/fbs-supplies/from-orders` — atomic WB supply + confirmed lines
4. `GET /operations/fbs-supplies/{id}/workspace` — stage machine + blockers
5. Pick scans → packaging integration → marking → print assets
6. PVZ: `POST …/cargo-places` → QR assets; WH/SC: skip trbx
7. `POST …/delivery-preflight` → `POST …/deliver` with `idempotency_key` + `confirmed_preflight_version`
8. Tracking: `POST …/sync-tracking` when `stage=tracking`

### Fixtures for UI dev

| Asset | Path |
|-------|------|
| OpenAPI | `tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` |
| Error catalog RU | `tasks/fbs-operator-flow/ERROR_CATALOG_RU.md` |
| Test cases (product) | `docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md` §S17 |
| Emulator order templates | `wb_emulator/seed/order_templates.json` |
| Handoff API samples | `tasks/fbs-operator-flow/fixtures/handoff/` (frozen read-only evidence) |

## Test coverage map (non-browser)

| TC | Backend proof |
|----|----------------|
| TC-01 | `test_fbs_operator_flow_handoff.py::test_tc01_three_sellers_wms_seed_isolated` |
| TC-06 | `test_fbs_supply_from_orders.py` + `test_fbs_operator_flow_handoff.py::test_full_flow_*` |
| TC-17..18 | `test_fbs_shipment_pvz.py` + `test_full_flow_pvz_emulator` |
| TC-19..21 | `test_fbs_shipment_delivery.py` + handoff full-flow tests |
| TC-22 | `test_fbs_tracking.py` |
| TC-23 | `test_fbs_operator_flow_handoff.py::test_tc23_*` + `wb_emulator/tests/test_emulator_operator_seed.py` |

Browser paths (TC-23 full): **out of scope** for this handoff — see `TEST_CASES.md` §frontend browser paths.

## Limitations

- **No live WB smoke (TC-24)** — emulator ≠ production contract drift; run TC-24 only with explicit secrets.
- **PostgreSQL + Celery** not required for pytest gate (sqlite + inline tasks).
- **Emulator gaps filled for batch API:** `PATCH/GET /api/marketplace/v3/supplies/{id}/orders|order-ids`, `GET /api/v3/supplies/{id}/trbx` — required for real from-orders/cargo-places (not mock).
- **Fault injection** in emulator: env `WB_EMULATOR_FAULT_409` / `WB_EMULATOR_FAULT_TIMEOUT` or `POST /__admin/faults` (reset between pytest cases via `reset_fault_store()`).
- **Deprecated compatibility (OpenAPI `deprecated: true`):** `POST …/stickers`, `POST …/trbx/stickers`, `GET …/barcode`, create+add-order, `POST …/trbx/{id}/orders` (410). New UI must use print-assets + cargo-places only.
- **Sticker contract:** PNG via `print-assets` + authorized `content` URLs — never treat `sticker_file`/`barcode_file` as base64 or public paths.
- **Error envelope:** new operator paths return `{code,message,context,retryable}` under `detail` (see `ERROR_CATALOG_RU.md`).
- **PVZ missing dims:** `measurements_confirmed=true` persists audit in WB operation `request_summary_json.measurements_confirmation_audit` (actor, timestamp, source) — not in success JSON.

## Suggested frontend entry

Start from `tasks/fbs-frontend-supply-detail/TASK.md` (deprecated banners point here).  
Use workspace polling + stage tabs matching `BACKEND_CONTRACT.md` stage names.
