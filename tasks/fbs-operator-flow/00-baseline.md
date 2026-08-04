# FBSFLOW-000 — baseline audit and contract gap map

**Date:** 2026-08-03  
**Auditor:** builder (FBSFLOW-000 gate)  
**Integration branch:** `feat/fbs-stock-sync` @ `ef92a22`  
**Task branch:** `task/FBSFLOW-000`  
**Worktree:** `/Users/deniscivkunov/Desktop/WMS /.cursor/wt/FBSFLOW-000`

---

## 1. Git snapshot

| Item | Value |
|------|-------|
| Task branch | `task/FBSFLOW-000` |
| HEAD (task worktree) | `ef92a225a0ccd008a54015698ec7d87461188a04` (`ef92a22`) |
| Integration branch | `feat/fbs-stock-sync` @ same HEAD |
| Main repo branch | `feat/fbs-stock-sync` @ `ef92a22` |
| Worktree git status | **clean** (0 modified/untracked in worktree) |
| Main repo dirty tree | **49 entries** — user untracked/modified; **not cleaned** (per gate rules). Notable: `tasks/fbs-operator-flow/` (untracked on main), duplicate SESSION_HANDOFF/TASKLOG, untracked `backend/alembic/versions/20260710_0061_marking_print_batches 2.py`, frontend FBS demo files, `output/pdf/**`, etc. |

### Worktrees (`git worktree list`)

```
/Users/deniscivkunov/Desktop/WMS                           ef92a22 [feat/fbs-stock-sync]
/Users/deniscivkunov/Desktop/WMS /.cursor/wt/FBSFLOW-000   ef92a22 [task/FBSFLOW-000]
… (+ 24 other task worktrees)
```

### Alembic

```bash
cd backend && .venv/bin/alembic heads
```

| Check | Result |
|-------|--------|
| `alembic heads` (exit **0**) | `20260802_0068 (head)` — file `backend/alembic/versions/20260802_0068_fbs_stock_sync.py` |
| Alembic warning | `Revision 20260710_0061 is present more than once` — duplicate revision id in chain (see main dirty tree untracked `20260710_0061_marking_print_batches 2.py`) |
| `alembic current` | **Not run** — requires live PostgreSQL; local attempt failed (`password authentication failed for user "postgres"`) |
| Known chain gap (from `tasks/fbs-stock-sync/HANDOFF.md`) | Untracked duplicate `20260710_0061` in main dirty tree; tracked chain jumps to `0068` |

### Python environment

- Worktree has **no** `.venv`; tests run via main repo `backend/.venv` (Python 3.14.3, pytest 9.0.3).
- Tests use sqlite via `tests/conftest.py` (`WMS_TEST_DATABASE_URL` override supported).

---

## 2. Baseline test runs (no code changes)

All commands from worktree `backend/` unless noted. Env for API tests:

```bash
export WMS_TEST_DATABASE_URL="sqlite+aiosqlite:////tmp/fbsflow000_baseline.sqlite"
export WMS_DATA_DIR="/tmp/fbsflow000_baseline_data"   # conftest overrides to tests/wms_pytest_data
export JWT_SECRET_KEY="test-jwt-secret-key-at-least-32-characters-long"
```

### 2.0 Static analysis gates (pre-existing; do not fix in FBSFLOW-000)

Source: [Run FBS pytest baseline](4d6779e8-2774-401d-a9c2-86e5ee6e2376). Use main repo `backend/.venv` from worktree.

| Gate | Command | Exit | Result |
|------|---------|-----:|--------|
| **ruff** | `ruff check .` | **0** | All checks passed |
| **mypy** | `mypy .` | **1** | **93 errors in 54 files** (317 checked) — legacy debt, not introduced by FBS operator flow |

> FBSFLOW-010+ must not regress ruff; mypy on **changed files** is gate for each task. Full-repo mypy green is out of scope for FBSFLOW queue unless explicitly scheduled.

### 2.1 FBS pytest gate (canonical command)

```bash
cd backend && .venv/bin/pytest tests/ -k fbs -q --tb=line 2>&1 | tail -30
```

**Required env** (isolated sqlite — avoids parallel-run / shared-DB flakes):

```bash
export WMS_TEST_DATABASE_URL="sqlite+aiosqlite:////tmp/fbsflow000_baseline.sqlite"
export JWT_SECRET_KEY="test-jwt-secret-key-at-least-32-characters-long"
```

| Metric | Count |
|--------|------:|
| Selected (`-k fbs`) | 131 |
| Passed | 130 |
| Skipped | 1 |
| Failed | 0 |
| Duration | ~121 s |
| **Exit code** | **0** |

**Tail output (last lines):**

```
130 passed, 1 skipped, 401 deselected, 6 warnings in 121.06s (0:02:01)
EXIT_CODE=0
```

**Skipped (1):**

| Test | Reason |
|------|--------|
| `tests/test_fbs_supply_assembly.py::test_fbs_supply_add_order_concurrent` | `row-level FOR UPDATE locking requires PostgreSQL` |

> **Without isolated DB:** default shared `tests/wms_pytest.sqlite` under parallel pytest can produce sqlite setup/teardown errors (14 errors + 23 failures observed). **Not product regressions** — use `WMS_TEST_DATABASE_URL` per run.

**FBS test modules (16 files, 131 tests):**

`test_fbs_autopoll`, `test_fbs_cancellations`, `test_fbs_marking`, `test_fbs_orders_intake`, `test_fbs_packaging_integration`, `test_fbs_review_fixes`, `test_fbs_seller_warehouse`, `test_fbs_shipment_deliver_gate_unit`, `test_fbs_shipment_pvz`, `test_fbs_shipment_warehouse_sc`, `test_fbs_stock_availability`, `test_fbs_stock_emulator_integration`, `test_fbs_stock_models`, `test_fbs_stock_sync`, `test_fbs_supply_assembly`, `test_fbs_warehouse_binding`

### 2.2 Packaging tests (FBS-relevant)

```bash
pytest tests/test_fbs_packaging_integration.py tests/test_packaging_tasks.py -q --tb=line
```

| Passed | Failed | Exit |
|-------:|-------:|-----:|
| 20 | 0 | **0** |

### 2.3 WB emulator

```bash
cd "/Users/deniscivkunov/Desktop/WMS /.cursor/wt/FBSFLOW-000"
PYTHONPATH=. pytest wb_emulator/tests/ -q --tb=line
```

| Passed | Failed | Exit |
|-------:|-------:|-----:|
| 49 | 0 | **0** |

### 2.4 Red baseline summary

| Category | Red count | Notes |
|----------|----------:|-------|
| FBS pytest (`-k fbs`, isolated DB) | **0** | 130 passed, 1 skipped, exit 0 |
| FBS pytest (shared sqlite / parallel) | **37** | 23 failed + 14 errors — sqlite race; not product |
| FBS pytest skipped | **1** | needs PostgreSQL FOR UPDATE |
| Packaging (FBS integration) | **0** | 20/20 green |
| Emulator | **0** | 49/49 green |
| Alembic CLI on live DB | **not verified** | postgres auth failed |
| Full backend pytest | **not run** | out of scope; HANDOFF cites ~80 FBS representative passed historically |

---

## 2.5 WB FBS client gaps (from `prep/FBSFLOW-020-wb-client-prep.md`)

Most FBS WB calls exist as **untyped dict helpers** in `wildberries_client.py`. Reference pattern: stocks client (STOCK-020) + `test_wildberries_marketplace_stocks_client.py`. Builder MUST re-verify OpenAPI on FBSFLOW-020 implementation day.

### Missing client methods (target FBSFLOW-020)

| Method | Gap |
|--------|-----|
| Batch `PATCH …/supplies/{id}/orders` (≤100) | Today: single-order `add_order_to_marketplace_supply` only |
| GET supply details + order IDs | Reconcile after partial WB ops |
| POST batch orders meta; DELETE meta | No metadata batch API |
| GET trbx list; DELETE trbx | Partial — create/stickers exist |
| Chunk splitters for orders/stickers/status | No ≤100 enforcement |
| Typed `WildberriesBusinessError` + `MetaValidationFail` on 409 | 409 body discarded in several callers |
| Shared `_ensure_success(allow_empty=True)` for 204 | `create_marketplace_supply` always `.json()` — breaks on 204 |

### Exists but untyped / risky

| Function | Risk |
|----------|------|
| `create_marketplace_supply` | `.json()` on 204 |
| `fetch_marketplace_order_stickers` | no ≤100 cap |
| `deliver_marketplace_supply` | 409 body discarded |
| `add_orders_to_marketplace_trbx` | **deprecate** for operator flow (manual order→trbx) |

### Planned test file

`backend/tests/test_wildberries_marketplace_fbs_client.py` — MockTransport exact URL/body, 204, chunk 101→2, 409 MetaValidationFail, timeout, 429 no-retry-on-409.

### Emulator note

Emulator uses single-order PATCH; client targets batch contract per `BACKEND_CONTRACT.md`; emulator alignment → **FBSFLOW-120**.

---

## 3. Existing FBS API inventory (28 routes)

Prefix base: `/operations/…`. Error shape today: plain string `detail` (e.g. `"supply_not_found"`), **not** structured envelope from contract §1.

### 3.1 `fbs_orders.py` — `/operations/fbs-orders`

| Method | Path | Response shape (actual) | Contract target | Gap |
|--------|------|-------------------------|-----------------|-----|
| POST | `/sync` | `{id, status}` job | (admin sync — out of operator flow) | — |
| GET | `` | flat `FbsOrderOut[]` offset/limit | **GET `/worklist`** enriched cursor page | **Missing** — no product/inventory/metadata/sticker/pick/pack/blockers |
| PATCH | `/{order_id}/cancel` | flat order | — | OK for admin |
| POST | `/sync-statuses` | `{statuses_updated}` | — | OK for admin |

### 3.2 `fbs_marking.py` — `/operations/fbs-orders/{order_id}/markings`

| Method | Path | Actual | Contract | Gap |
|--------|------|--------|----------|-----|
| GET | `/markings` | `[{kind, value, check_status, marking_code_id}]` | **GET `/metadata`** with required/optional/states/delivery_allowed | **Different model** — no WB requiredMeta/optionalMeta |
| PUT | `/markings/{kind}` | manual value PUT | **POST `/metadata/scan`** with idempotency + auto WB send | **Missing scan path** |
| POST | `/markings/sync` | refresh check_status | metadata sync from WB metaDetails | Partial |

### 3.3 `fbs_supplies.py` — `/operations/fbs-supplies`

| Method | Path | Actual | Contract | Gap |
|--------|------|--------|----------|-----|
| POST | `` | create empty supply `{seller_id, warehouse_id, name, delivery_type…}` | **POST `/from-orders`** atomic batch | **Obsolete split flow** |
| GET | `/{supply_id}` | flat supply + optional orders with `sticker_file` paths | **GET `/workspace`** stage/progress/blockers | **Missing workspace** |
| POST | `/{supply_id}/orders` | **one** `order_id` per call | batch ≤100 in single create | **Obsolete single-add** |
| GET | `/{supply_id}/picking-list` | aggregated SKU qty list | server pick via scan endpoints | **Local aggregate only** — no pick records |
| POST | `/{supply_id}/stickers` | `[{order_id, sticker_code, sticker_file}]` paths | **POST `/print-assets`** + binary content URL | **Paths exposed** |
| POST | `/{supply_id}/trbx` | create by count | **POST `/cargo-places`** + preflight | Partial rename only |
| POST | `/{supply_id}/trbx/stickers` | trbx list with `sticker_file` paths | print-assets for cargo QR | **Paths exposed** |
| POST | `/{supply_id}/trbx/{trbx_id}/orders` | **manual order→trbx bind** | **deprecated / forbidden** | **Obsolete — must remove** |
| PUT | `/{supply_id}/status` | client-driven status string | server stage from workspace | **Local status flags** |
| POST | `/{supply_id}/trbx/bind-box` | WHB box → trbx | optional internal only | Over-emphasized in flow |
| POST | `/{supply_id}/deliver` | no body | idempotency + preflight version | **Missing guards** |
| GET | `/{supply_id}/barcode` | raw PNG bytes | supply QR via print-assets | Partial (binary OK, no asset model) |

**Not implemented at all:**

- `POST /operations/fbs-supplies/preflight`
- `POST /operations/fbs-supplies/from-orders`
- `GET /operations/fbs-supplies/{id}/workspace`
- `POST /operations/fbs-supplies/{id}/start-work`
- `POST …/pick/scan-location`, `…/pick/scan-product`, `…/pick/{order_id}/undo`
- `POST /operations/fbs-supplies/{id}/print-assets`
- `GET /operations/fbs-print-assets/{asset_id}/content`
- `POST /operations/fbs-print-assets/{asset_id}/applied`
- `POST …/cargo-places/preflight`, `GET …/cargo-places`
- `POST …/delivery-preflight`

### 3.4 `fbs_sellers.py` — `/operations/fbs-sellers` (stock-sync era; keep)

Warehouses, offices, warehouse-bindings CRUD, stocks sync — **in scope for FBS stock** but not operator-flow contract. No gaps vs `BACKEND_CONTRACT.md` (contract does not redefine these).

---

## 4. Obsolete patterns (explicit)

| # | Pattern | Where today | Contract expectation | Target task |
|---|---------|-------------|---------------------|-------------|
| 1 | **Add one order** instead of batch | `POST …/supplies/{id}/orders` → `add_order_to_supply()` → WB `PATCH …/orders/{orderId}` per call (`wildberries_client.add_order_to_marketplace_supply`) | `POST /from-orders` + WB batch `PATCH /api/marketplace/v3/supplies/{id}/orders` ≤100 | FBSFLOW-020, 040 |
| 2 | **`sticker_file` / `barcode_file` as paths** | `FbsOrder.sticker_file`, `FbsTrbx.sticker_file`, `FbsSupply.barcode_file`; API returns relative paths like `fbs-stickers/…` | Authorized binary `/fbs-print-assets/{id}/content`; never expose internal paths | FBSFLOW-080 |
| 3 | **Local pick flags / aggregate picking list** | `GET …/picking-list` groups by SKU; no per-order pick state; no server scans | Server pick records 1:1 order; workspace `pick.status` | FBSFLOW-050 |
| 4 | **Manual bind order → trbx** | `POST …/trbx/{trbx_id}/orders` + `order.trbx_id` FK + `add_orders_to_marketplace_trbx` | Count-only cargo places; no order mapping | FBSFLOW-090 |
| 5 | **Missing requiredMeta/optionalMeta** | No fields on `FbsOrder`; intake does not parse/store; marking uses `Product.requires_honest_sign` gate | WB authoritative metadata on order; states + delivery_allowed | FBSFLOW-070 |
| 6 | **Missing per-order packaging link** | `try_promote_fbs_supply_if_ready()` marks **all** supply orders `packed` when aggregate `PackagingTask` lines complete | Each `qty_done` tied to one `FbsOrder`; `fulfilled_order` in response | FBSFLOW-060 |

Additional partial gaps:

- **Error envelope:** string codes only, no `{code, message, context, retryable}` (contract §1).
- **Deliver:** no `idempotency_key`, no `confirmed_preflight_version`, no `pending_confirmation` on timeout.
- **WB client:** no batch supply add, no metadata API (`requiredMeta`/`optionalMeta`/`metaDetails`), per-order supply PATCH only.

---

## 5. Schema baseline (pre-FBSFLOW-010)

**Present:** `FbsOrder`, `FbsOrderMarking`, `FbsOrderReservation`, `FbsSupply`, `FbsTrbx`, `FbsWarehouseBinding`, `FbsStockSyncItem`, `PackagingTask`/`PackagingTaskLine`.

**Absent (required by contract):**

- Per-order pick record (source/sorting location, user, idempotency, undo audit)
- Print asset entity (kind, content_type, blob key, checksum, applied audit)
- WB operation journal (idempotency, pending_confirmation, reconcile)
- PackagingTaskLine ↔ FbsOrder fulfillment link (1:1 physical unit)
- Order-level `required_meta` / `optional_meta` / meta state snapshot

---

## 6. Top 5 contract gaps (priority for downstream)

1. **No worklist / workspace read models** — frontend cannot show enriched orders or supply stage/progress/blockers (`FBSFLOW-030`).
2. **No preflight + atomic `from-orders`** — supply creation is split create + N× single add; no compatibility validator (`FBSFLOW-040`).
3. **No server-side picking** — only aggregate picking-list; progress not durable per order (`FBSFLOW-050`).
4. **Stickers/QR as file paths** — `sticker_file` exposed; no print-asset abstraction or applied confirmation (`FBSFLOW-080`).
5. **Manual order→trbx binding still required in API** — contradicts PVZ contract; must deprecate (`FBSFLOW-090`).

---

## 7. Reference artifacts

| Doc | Role |
|-----|------|
| `BACKEND_CONTRACT.md` | Target API wire contract |
| `CURSOR_TASKS.md` | Queue FBSFLOW-010…140 |
| `tasks/fbs-stock-sync/HANDOFF.md` | Stock-sync integration state @ `202978b` (HEAD now `ef92a22`) |
| `prep/FBSFLOW-000-api-inventory-prep.md` | Route inventory prep |
| `prep/FBSFLOW-010-models-prep.md` | Migration 0069 plan |
| `prep/FBSFLOW-020-wb-client-prep.md` | WB client gap analysis (merged §2.5) |

---

## 8. Gate verdict

| Gate | Status |
|------|--------|
| Baseline recorded (branch, HEAD, worktrees, alembic file head) | **PASS** |
| Targeted FBS tests executed | **PASS** (`-k fbs`: 130 passed, 1 skipped, exit 0) |
| Contract gap map | **PASS** |
| Obsolete patterns documented | **PASS** |
| Code changes | **NONE** (docs only) |

**Next task:** `FBSFLOW-010` — models + migration for pick records, print assets, WB operation journal, per-order packaging link.
