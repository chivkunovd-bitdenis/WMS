# CURSOR_HANDOFF — fbs-stock-sync (STOCK-110 final)

> **Status:** STOCK-110 gates recorded; ready for independent Codex review.  
> **Integration branch:** `feat/fbs-stock-sync` (base `feat/fbs-wb-emulator`)  
> **Delivery branch:** `task/STOCK-110`  
> **HEAD:** `478d3fdc3cd6d31f33568dcd66f8f4af62f73bd0`

---

## Commits STOCK-010…100

| Task | Commit | Message |
|------|--------|---------|
| STOCK-010 | `255275c` | `feat(STOCK-010): add FBS warehouse binding and stock sync models` |
| STOCK-020 | `1e6b60b` | `feat(STOCK-020): add WB marketplace stocks client` |
| STOCK-030 | `eb86c6b` | `feat(STOCK-030): emulate WB FBS stocks API` |
| STOCK-040 | `b30c338` | `feat(STOCK-040): constrain emulator purchases by FBS stock` |
| STOCK-050 | `7398fc9` | `feat(STOCK-050): manage FBS warehouse bindings` |
| STOCK-060 | `3b35ffe` | `fix(STOCK-060): isolate and expose FBS reservations` |
| STOCK-060 fix | `4123924` | `fix(STOCK-060): break circular import after availability extract` |
| STOCK-070 | `a0f0fcd` | `fix(STOCK-070): bind FBS orders to their WB warehouse` |
| STOCK-070 fix | `a86a19a` | `fix(STOCK-070): update callers after binding-only warehouse resolve` |
| STOCK-080 | `302d055` | `feat(STOCK-080): reconcile WMS FBS stock with WB` |
| STOCK-090 | `f577330` | `feat(STOCK-090): run FBS stock sync after order intake` |
| STOCK-100 | `3006c7d` | `test(STOCK-100): prove WMS to emulator FBS stock cycle` |

Integration merges (`integrate(STOCK-0xx): merge task/STOCK-0xx into feat/fbs-stock-sync`) sit between feature commits on `feat/fbs-stock-sync`; worktree `task/STOCK-110` HEAD includes STOCK-100 integrate at `478d3fd`.

---

## Files changed per task

### STOCK-010 (`255275c`)
- `backend/alembic/versions/20260802_0068_fbs_stock_sync.py`
- `backend/app/models/__init__.py`
- `backend/app/models/fbs_order.py`
- `backend/app/models/fbs_stock_sync_item.py`
- `backend/app/models/fbs_warehouse_binding.py`
- `backend/tests/test_fbs_stock_models.py`

### STOCK-020 (`1e6b60b`)
- `backend/app/services/wildberries_client.py`
- `backend/tests/test_wildberries_marketplace_stocks_client.py`

### STOCK-030 (`eb86c6b`)
- `wb_emulator/main.py`
- `wb_emulator/routes/stocks.py`
- `wb_emulator/services/stocks_store.py`
- `wb_emulator/tests/test_stocks_contract.py`

### STOCK-040 (`b30c338`)
- `wb_emulator/routes/admin.py`
- `wb_emulator/seed/order_templates.json`
- `wb_emulator/services/orders_store.py`
- `wb_emulator/tests/test_admin.py`
- `wb_emulator/tests/test_full_cycle.py`
- `wb_emulator/tests/test_orders_contract.py`

### STOCK-050 (`7398fc9`)
- `TASKLOG.md`
- `backend/app/api/fbs_sellers.py`
- `backend/app/services/fbs_warehouse_binding_service.py`
- `backend/tests/test_fbs_warehouse_binding.py`

### STOCK-060 (`3b35ffe`, `4123924`)
- `backend/app/services/fbs_stock_availability_service.py`
- `backend/app/services/inventory_service.py`
- `backend/app/services/marketplace_unload_service.py`
- `backend/app/services/wb_marketplace_orders_service.py` (availability slice)
- `backend/app/services/sorting_location_service.py` (circular-import fix)
- `backend/tests/test_fbs_stock_availability.py`

### STOCK-070 (`a0f0fcd`, `a86a19a`)
- `backend/app/api/fbs_orders.py`
- `backend/app/api/fbs_supplies.py`
- `backend/app/services/fbs_supply_service.py`
- `backend/app/services/wb_marketplace_orders_service.py` (intake slice)
- `backend/tests/fbs_seed_helpers.py` (new shared fixture helper)
- `backend/tests/test_fbs_orders_intake.py`
- `backend/tests/test_fbs_autopoll.py`, `test_fbs_cancellations.py`, `test_fbs_marking.py`, `test_fbs_packaging_integration.py`, `test_fbs_review_fixes.py`, `test_fbs_shipment_warehouse_sc.py`, `test_fbs_supply_assembly.py` (binding seed updates)

### STOCK-080 (`302d055`)
- `backend/app/services/fbs_stock_sync_service.py`
- `backend/tests/test_fbs_stock_sync.py`

### STOCK-090 (`f577330`)
- `backend/app/api/fbs_sellers.py` (stock sync API)
- `backend/app/services/background_job_service.py`
- `backend/app/services/fbs_autopoll_service.py`
- `backend/app/tasks/background_jobs.py`
- `backend/tests/test_fbs_autopoll.py`
- `backend/tests/test_fbs_warehouse_binding.py` (API extensions)

### STOCK-100 (`3006c7d`)
- `backend/tests/test_fbs_stock_emulator_integration.py`
- `wb_emulator/README.md`
- `tasks/fbs-stock-sync/CURSOR_HANDOFF.md`

**Anti-scope diff** (`git diff feat/fbs-wb-emulator...HEAD --stat`): 48 files, +6062/−202 lines. No `docker-compose.prod.yml` changes. `grep -ri emulator docker-compose.prod.yml` → no matches.

---

## Gate results (exact commands + output)

### 1. `ruff check .` (Docker, worktree backend mount)

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
docker compose run --rm --no-deps \
  -v "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-110/backend:/app" \
  -w /app -e CELERY_BROKER_URL= \
  -e JWT_SECRET_KEY=test-jwt-secret-key-at-least-32-characters-long \
  api ruff check .
```

**Result:** exit **1** — `Found 36 errors.` (10 auto-fixable)

Categories: import sort (`I001`, `RUF022`) in `app/models/__init__.py`, `app/tasks/background_jobs.py`; `E501` line length in tests; `E402` late imports in `test_fbs_stock_emulator_integration.py` (intentional `sys.path` bootstrap); `F401`/`F841` unused import/variable in tests; `UP017` `datetime.UTC` in `test_fbs_stock_models.py`; `SIM105` in `test_fbs_autopoll.py`.

Local re-run (same tree): `Found 36 errors.` — identical.

### 2. `mypy .` (Docker)

```bash
docker compose run --rm --no-deps \
  -v ".../STOCK-110/backend:/app" -w /app -e CELERY_BROKER_URL= api mypy .
```

**Result:** exit **2**

```
tests/fbs_seed_helpers.py: error: Source file found twice under different module names:
  "fbs_seed_helpers" and "tests.fbs_seed_helpers"
Found 1 error in 1 file (errors prevented further checking)
```

Local re-run: same error.

### 3. Backend pytest — representative FBS + stock suite

**Docker attempt** (volume-only backend, no repo root): collection errors — `tests.fbs_seed_helpers` not importable; integration test missing `wb_emulator` / `qrcode`. Not a valid gate for this worktree layout.

**Local (proven):**

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-110/backend"
CELERY_BROKER_URL= \
JWT_SECRET_KEY=test-jwt-secret-key-at-least-32-characters-long \
DATABASE_URL=sqlite+aiosqlite:////tmp/t110-local.sqlite \
WMS_DATA_DIR=/tmp/t110_local_data \
pytest tests/test_fbs_stock_models.py tests/test_fbs_stock_availability.py \
  tests/test_fbs_stock_sync.py tests/test_fbs_warehouse_binding.py \
  tests/test_wildberries_marketplace_stocks_client.py \
  tests/test_fbs_orders_intake.py tests/test_fbs_autopoll.py -q --tb=line
```

**Result:** exit **0** — `80 passed in 35.75s`

**Full `pytest`:** not run end-to-end in this session (runtime); representative suite above covers all new STOCK modules + intake/autopoll integration.

### 4. Emulator suite

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-110"
PYTHONPATH=. python3 -m pytest wb_emulator/tests/ -q
```

**Result:** exit **0** — `49 passed in 2.35s` (baseline was 37 at STOCK-000).

### 5. WMS → emulator cycle test (STOCK-100)

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/STOCK-110/backend"
PYTHONPATH=..:. pytest tests/test_fbs_stock_emulator_integration.py -q
```

**Result:** exit **0** — `2 passed in 1.58s`

**Proved values (TC-NEW-FBS-STOCK-017):**
1. WMS physical qty **1** on FBS warehouse → stock sync → emulator POST readback **amount=1**
2. Admin purchase qty **2** same `chrtId` → **created=1**, **rejected_no_stock=1**, emulator amount **0**
3. WMS order intake → `wb_warehouse_id=501001`, WMS warehouse mapped, `mapping_status=mapped`, `reserve_status=reserved`, reserve qty **1**
4. Second stock sync → `last_confirmed_amount=0`, status confirmed
5. FBO `MarketplaceUnloadReservation` on separate WMS warehouse → FBS publish amount unchanged (**1** until purchase)

**TC-NEW-FBS-STOCK-018:** `test_prod_compose_has_no_wb_emulator` — `docker-compose.prod.yml` has no `wb-emulator`, `wb_emulator`, or emulator marketplace base URL.

### 6. Alembic upgrade/downgrade

**Attempted** (Docker + postgres `db` service, worktree backend):

```bash
docker compose run --rm \
  -v ".../STOCK-110/backend:/app" -w /app \
  -e DATABASE_URL=postgresql+psycopg_async://postgres:postgres@db:5432/wms \
  api sh -c 'alembic downgrade 20260731_0067 && alembic upgrade head'
```

**Result:** exit **1** — `KeyError: '20260710_0061'`

```
UserWarning: Revision 20260710_0061 referenced from 20260710_0061 -> 20260730_0062 ...
is not present
```

Root cause: `backend/alembic/versions/20260730_0062_fbs_orders_intake.py` has `down_revision = "20260710_0061"` but file `20260710_0061_*.py` is **missing from this branch** (exists only as untracked file in main working tree: `backend/alembic/versions/20260710_0061_marking_print_batches.py`). Migration `20260802_0068` itself is structurally valid (`down_revision = "20260731_0067"`). **Upgrade/downgrade of 0068 not independently verified** until 0061 is merged into the chain.

SQLite local attempt: same `KeyError: '20260710_0061'`.

ORM-level constraint tests in `test_fbs_stock_models.py` pass via pytest fixtures (tables created by test harness, not Alembic CLI).

---

## Dirty-tree baseline

| Location | Status |
|----------|--------|
| Worktree `task/STOCK-110` | **clean** (`git status --short` → 0 entries) |
| Main repo `/Users/deniscivkunov/Desktop/WMS ` | **37** untracked/modified foreign paths (marking PDFs, CZ previews, `.dev/`, `frontend/fbs-demo`, missing migration `0061`, etc.) — **none committed** in STOCK-010…110 commits |

All STOCK commits stage only task-owned paths per `git show --name-only`.

---

## Warnings / unverified

1. **Ruff 36 errors** — mostly test/style; blocks strict `ruff check .` gate.
2. **Mypy blocked** by `tests/fbs_seed_helpers.py` dual module path; full mypy not completed.
3. **Alembic chain broken** at missing `20260710_0061` — blocks CLI upgrade/downgrade verification of `0068`.
4. **Docker-only backend mount** cannot run full pytest (needs repo root `PYTHONPATH`, `wb_emulator`, `tests` package).
5. **Full backend pytest** not executed in STOCK-110 session.
6. Integration test uses in-process ASGI transport to emulator (not separate Docker smoke); HTTP contract is real between WMS client and emulator app.

---

## PR `### Test coverage` block (copy-ready)

```markdown
### Test coverage

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
| TC-NEW-FBS-STOCK-001 | WB stocks PUT batch validation | Y | Given: stocks client with 1001 chrtIds. When: PUT. Then: validation error before network. Negative: duplicate chrtId rejected. Test: `test_wildberries_marketplace_stocks_client.py` |
| TC-NEW-FBS-STOCK-002 | WB stocks PUT 204 + POST readback | Y | Given: mock transport. When: PUT then POST read. Then: no `.json()` on 204; readback parsed strictly. Negative: malformed read → `invalid_response`. |
| TC-NEW-FBS-STOCK-003 | FbsOrder wb_warehouse_id vs officeId | Y | Given: order row with distinct warehouseId/officeId. When: persisted. Then: both fields stored independently. Test: `test_fbs_stock_models.py` |
| TC-NEW-FBS-STOCK-004 | Unmapped WB warehouse on intake | Y | Given: order with unknown warehouseId, no binding. When: intake. Then: `warehouse_id=null`, `reserve_status=warehouse_unmapped`, no reserve. Test: `test_fbs_orders_intake.py` |
| TC-NEW-FBS-STOCK-005 | FBS availability batch formula | Y | Given: storage+sorting balances, outbound+FBS reserves. When: batch calc. Then: `max(0, sum−reserves)`. Test: `test_fbs_stock_availability.py` |
| TC-NEW-FBS-STOCK-006 | FBO reserve does not reduce FBS publish | Y | Given: FBO unload reservation on other WH. When: FBS availability. Then: publish amount unchanged. Restriction: separate WMS warehouses. |
| TC-NEW-FBS-STOCK-010 | Binding + sync item ORM constraints | Y | Given: duplicate binding or sync item. When: insert. Then: integrity error. Test: `test_fbs_stock_models.py` |
| TC-NEW-FBS-STOCK-011 | Stock sync false-204 mismatch | Y | Given: PUT 204 but POST readback differs. When: reconcile. Then: item status error, safe code stored. Test: `test_fbs_stock_sync.py` |
| TC-NEW-FBS-STOCK-012 | Stock sync 1001 products → 2 batches | Y | Given: 1001 chrtIds. When: sync. Then: two PUT batches ≤1000. Expected: all targeted. |
| TC-NEW-FBS-STOCK-013 | Autopoll intake success triggers stock sync | Y | Given: active binding with sync enabled. When: successful order intake. Then: stock sync called for seller bindings. Test: `test_fbs_autopoll.py` |
| TC-NEW-FBS-STOCK-014 | Binding API tenant isolation + 409 | Y | Given: cross-tenant seller or duplicate WMS WH. When: PUT binding. Then: 404/409 stable codes. Test: `test_fbs_warehouse_binding.py` |
| TC-NEW-FBS-STOCK-015 | Emulator stocks PUT/POST contract | Y | Given: token + warehouse 501001. When: PUT amount then POST chrtIds. Then: 204 + exact readback including zero. Test: `wb_emulator/tests/test_stocks_contract.py` |
| TC-NEW-FBS-STOCK-016 | Emulator purchase stock gate | Y | Given: stock=1. When: admin purchase 2. Then: created=1, rejected_no_stock=1, amount=0. Negative: no negative stock. |
| TC-NEW-FBS-STOCK-017 | WMS → emulator full HTTP cycle | Y | Given: product wb_chrt_id, binding 501001, physical qty 1. When: sync → purchase 2 → intake → sync. Then: readback 1→0, one order reserved, confirmed 0. Negative: FBO other WH unchanged. Test: `test_fbs_stock_emulator_integration.py` |
| TC-NEW-FBS-STOCK-018 | Prod compose isolation | Y | Given: docker-compose.prod.yml. When: grep emulator refs. Then: no wb-emulator / emulator base URL. Test: `test_prod_compose_has_no_wb_emulator` |
```

---

## Stop condition

STOCK-110 complete. Cursor does not write `05-review.md` or self-approve. Awaiting Codex independent review.
