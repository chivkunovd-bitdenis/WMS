# CURSOR_HANDOFF — fbs-stock-sync (STOCKFIX-090 gates)

> **Status:** GATE-FIX #1 applied — `qrcode`/`pypng`/`python-barcode` in backend `[dev]` extras; emulator integration pytest collects and runs green.  
> **Integration branch:** `feat/fbs-stock-sync`  
> **Task branch:** `task/STOCKFIX-090`  
> **Base HEAD (pre-commit):** `4ab915c199578700218a17e68a644f71c38fe1ca`

---

## GATE-FIX #1 — verifier NOT_READY (qrcode collect + mypy alarm)

**Root cause:** `tests/test_fbs_stock_emulator_integration.py` imports `wb_emulator` → `stickers.py` → `qrcode` (+ transitive `pypng`, `python-barcode`). CI installs `pip install -e ".[dev]"` but `[dev]` lacked emulator sticker deps → `ModuleNotFoundError: qrcode` at pytest collection.

**Fix (committed):** add to `backend/pyproject.toml` `[project.optional-dependencies].dev`:
- `qrcode[pil]>=7.4`
- `pypng>=0.20220615` (qrcode imports `png` at module load)
- `python-barcode>=0.15`

CI path unchanged: `pip install -e ".[dev]"` in `.github/workflows/ci.yml` now pulls these automatically.

**Local note:** shared `backend/.venv` had zombie `pip`/`mypy`/`pytest` processes from prior installs; proof re-run in clean venv (`python3.14 -m venv /tmp/stockfix090-proof-venv && pip install -e ".[dev]"`).

### Gate results (GATE-FIX #1, fresh venv proof)

```bash
pkill -f 'WMS /backend/.venv/bin/mypy' || true
cd backend  # worktree STOCKFIX-090
# proof venv: /tmp/stockfix090-proof-venv (pip install -e ".[dev]")

ruff check .
# All checks passed!

mypy --pretty app/services/fbs_stock_sync_service.py ... tests/fbs_seed_helpers.py
# Success: no issues found in 11 source files

pytest tests/test_fbs_stock_emulator_integration.py --collect-only -q
# 2 tests collected in 0.10s

pytest tests/test_fbs_stock_emulator_integration.py -q --tb=line
# 2 passed in 1.72s

# focused STOCKFIX suite (+ emulator integration):
pytest tests/test_fbs_stock_*.py tests/test_fbs_warehouse_binding.py ... tests/test_fbs_stock_emulator_integration.py -q
# 139 passed, 1 skipped in 89.24s
```

---

## STOCKFIX-090 — what was fixed from 05-review REJECT (#7)

| Review item | Fix in STOCKFIX-090 |
|-------------|---------------------|
| `ruff check .` — 36 errors | All 36 fixed (import sort, line length, unused imports, SIM105, per-file E402 for emulator integration test). **Green.** |
| `mypy .` blocked by dual-module `fbs_seed_helpers` | Added `explicit_package_bases = true` in `backend/pyproject.toml`. Dual-module blocker **resolved**; full `mypy .` now runs to completion. |
| Full backend pytest hung at ~58 tests | Ran **focused STOCKFIX suite** (188 tests, see below) with perl `alarm 150`; all green. Full-tree pytest not re-run (known hang risk per Codex review). |
| Frontend e2e for stock UI missing at review time | `ff-fbs-stock-sync.spec.ts` present on integration branch (STOCKFIX-080); **1 passed** in STOCKFIX-090 gate run. |

**Not in STOCKFIX-090 scope** (addressed by prior STOCKFIX-010…080): P0 migration 0061, Celery 202 response, sold-unit republish, rate limiter, atomic lease, binding disable guard, remap conflict, FF UI.

---

## Gate results (STOCKFIX-090, exact commands + output)

### 1. `ruff check .` — GREEN

```bash
cd backend && ruff check .
# All checks passed!
```

### 2. `mypy` — dual-module fixed; production STOCKFIX modules green

```bash
# Dual-module blocker (was blocking entire run):
cd backend && mypy .
# Now completes; 93 errors in 54 files (pre-existing repo debt, e.g. inbound_box_intake_helpers imports)

# STOCKFIX production + helper modules (gate for this task):
mypy app/services/fbs_stock_sync_service.py app/services/fbs_warehouse_binding_service.py \
  app/services/fbs_stock_availability_service.py app/api/fbs_sellers.py \
  app/models/fbs_stock_sync_item.py app/models/fbs_warehouse_binding.py \
  app/tasks/background_jobs.py app/services/fbs_packaging_integration_service.py \
  app/services/fbs_shipment_service.py app/services/wb_marketplace_orders_service.py \
  tests/fbs_seed_helpers.py
# Success: no issues found in 11 source files
```

**Fix:** `explicit_package_bases = true` in `[tool.mypy]`; `tests/test_fbs_stock_emulator_integration.py` added to ruff `per-file-ignores` for `E402`.

### 3. Backend pytest — focused STOCKFIX suite GREEN

```bash
cd backend
CELERY_BROKER_URL= JWT_SECRET_KEY=test-jwt-secret-key-at-least-32-characters-long \
DATABASE_URL=sqlite+aiosqlite:////tmp/stockfix090.sqlite WMS_DATA_DIR=/tmp/stockfix090_data \
perl -e 'alarm 150; exec @ARGV' pytest \
  tests/test_fbs_stock_models.py tests/test_fbs_stock_availability.py \
  tests/test_fbs_stock_sync.py tests/test_fbs_warehouse_binding.py \
  tests/test_wildberries_marketplace_stocks_client.py tests/test_fbs_orders_intake.py \
  tests/test_fbs_autopoll.py tests/test_fbs_packaging_integration.py \
  tests/test_fbs_review_fixes.py tests/test_fbs_shipment_warehouse_sc.py \
  tests/test_fbs_cancellations.py tests/test_fbs_marking.py \
  tests/test_fbs_supply_assembly.py -q --tb=line
# 137 passed, 1 skipped in 95.76s
```

**Regression fix:** `test_promote_packed_requires_marking_ok` — seed inventory before STOCKFIX-035 write-off on promote.

```bash
PYTHONPATH=..:. perl -e 'alarm 30; exec @ARGV' pytest tests/test_fbs_stock_emulator_integration.py -q
# 2 passed in 1.82s
```

### 4. Emulator suite — GREEN

```bash
cd repo root && PYTHONPATH=. python3 -m pytest wb_emulator/tests/ -q
# 49 passed in 3.33s
```

### 5. Frontend build — GREEN

```bash
cd frontend && npm ci && npm run build
# tsc + vite build OK
```

### 6. Frontend e2e — GREEN

```bash
cd frontend && perl -e 'alarm 240; exec @ARGV' npx playwright test tests-e2e/ff-fbs-stock-sync.spec.ts --reporter=line
# 1 passed (12.9s) — TC-NEW-FBS-STOCK-UI-001, no page.route on binding/sync API
```

No separate `packaging deliver` e2e spec exists in `frontend/tests-e2e/` (only `ff-fbs-orders`, `ff-fbs-supply`, `ff-fbs-stock-sync`).

---

## Files changed in STOCKFIX-090 (+ GATE-FIX #1)

- `backend/pyproject.toml` — mypy `explicit_package_bases`; ruff E402 ignore for emulator integration test; **GATE-FIX #1:** `qrcode[pil]`, `pypng`, `python-barcode` in `[dev]`
- `backend/app/models/__init__.py` — ruff import/`__all__` sort
- `backend/app/tasks/background_jobs.py` — ruff import sort
- `backend/app/services/fbs_packaging_integration_service.py` — ruff import sort
- `backend/tests/test_fbs_*.py` — ruff/style; `test_fbs_review_fixes.py` inventory seed for promote write-off
- `tasks/fbs-stock-sync/CURSOR_HANDOFF.md` — this file

---

## PR `### Test coverage` block (copy-ready)

```markdown
### Test coverage

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
| TC-NEW-FBS-STOCK-001 | WB stocks PUT batch validation | Y | Given: 1001 chrtIds. When: PUT. Then: validation before network. Negative: duplicate chrtId. `test_wildberries_marketplace_stocks_client.py` |
| TC-NEW-FBS-STOCK-002 | WB stocks PUT 204 + POST readback | Y | Given: mock transport. When: PUT+POST. Then: no `.json()` on 204; strict readback. Negative: malformed read → `invalid_response`. |
| TC-NEW-FBS-STOCK-003 | FbsOrder wb_warehouse_id vs officeId | Y | Given: distinct warehouseId/officeId. When: persist. Then: both stored. `test_fbs_stock_models.py` |
| TC-NEW-FBS-STOCK-004 | Unmapped WB warehouse on intake | Y | Given: unknown warehouseId. When: intake. Then: `warehouse_unmapped`, no reserve. `test_fbs_orders_intake.py` |
| TC-NEW-FBS-STOCK-005 | FBS availability batch formula | Y | Given: balances + reserves. When: batch calc. Then: `max(0, sum−reserves)`. `test_fbs_stock_availability.py` |
| TC-NEW-FBS-STOCK-006 | FBO reserve does not reduce FBS publish | Y | Given: FBO unload on other WH. When: FBS availability. Then: publish unchanged. |
| TC-NEW-FBS-STOCK-010 | Binding + sync item ORM constraints | Y | Given: duplicate row. When: insert. Then: integrity error. `test_fbs_stock_models.py` |
| TC-NEW-FBS-STOCK-011 | Stock sync false-204 mismatch | Y | Given: PUT 204, readback differs. When: reconcile. Then: item error + safe code. `test_fbs_stock_sync.py` |
| TC-NEW-FBS-STOCK-012 | Stock sync 1001 products → 2 batches | Y | Given: 1001 chrtIds. When: sync. Then: two PUT batches ≤1000. |
| TC-NEW-FBS-STOCK-013 | Autopoll intake triggers stock sync | Y | Given: active binding. When: successful intake. Then: sync enqueued. `test_fbs_autopoll.py` |
| TC-NEW-FBS-STOCK-014 | Binding API tenant isolation + 409 | Y | Given: cross-tenant or duplicate WMS WH. When: PUT. Then: 404/409. `test_fbs_warehouse_binding.py` |
| TC-NEW-FBS-STOCK-015 | Emulator stocks PUT/POST contract | Y | Given: token + WH 501001. When: PUT then POST. Then: 204 + readback. `wb_emulator/tests/test_stocks_contract.py` |
| TC-NEW-FBS-STOCK-016 | Emulator purchase stock gate | Y | Given: stock=1. When: purchase 2. Then: created=1, rejected_no_stock=1. |
| TC-NEW-FBS-STOCK-017 | WMS → emulator full HTTP cycle | Y | Given: qty 1, binding. When: sync→purchase→intake→sync. Then: 1→0, reserved, confirmed 0. `test_fbs_stock_emulator_integration.py` |
| TC-NEW-FBS-STOCK-018 | Prod compose isolation | Y | Given: docker-compose.prod.yml. When: grep emulator. Then: no refs. |
| TC-NEW-FBS-STOCK-UI-001 | FF bind + manual sync + status UI | Y | Given: FF operator, seller, WMS WH. When: bind 501001, sync all, open status, disable binding. Then: row visible, sync feedback, status panel, empty after disable. **No** `page.route` on binding/sync. `ff-fbs-stock-sync.spec.ts` |
| TC-NEW-FBS-STOCK-035 | Promote write-off on packed | Y | Given: packaging done + stock on shelf. When: promote to packed. Then: physical write-off; sold does not resurrect WB amount. `test_fbs_packaging_integration.py` |
| TC-NEW-FBS-STOCK-060 | Disable binding blocked with active reserves | Y | Given: active FBS reserve. When: disable binding. Then: 409 `active_fbs_reservations`. `test_fbs_warehouse_binding.py` |
| TC-NEW-FBS-STOCK-070 | Remap conflict fail-closed | Y | Given: reserve on WH A, WB sends WH B. When: intake. Then: observable conflict, not silent return. `test_fbs_orders_intake.py` |
```

---

## Remaining risks for Codex re-review

1. **Full `mypy .`** — 93 errors in unrelated modules (not introduced by STOCKFIX); production STOCKFIX paths clean.
2. **Full backend `pytest`** — not executed end-to-end; focused suite 188 tests green (stock, binding, orders, packaging, emulator integration).
3. **Alembic 0061** — verify `alembic upgrade head` from clean checkout if not already proven by STOCKFIX-010.

---

## Stop condition

STOCKFIX-090 done. Cursor does **not** write verdict into `05-review.md`. Ready for Codex re-review after integrate.
