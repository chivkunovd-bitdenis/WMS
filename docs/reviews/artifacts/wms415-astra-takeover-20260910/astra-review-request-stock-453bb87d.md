# Astra 6 high independent read-only review — stock lane

## Ask
Independently review branch `feat/wms338-stock-min-formula` at HEAD `453bb87d` versus base SHA `bc7f760c11b032fbb94376f042bb6d0f2dd7c13b`. Do NOT rewrite. Do NOT rebase. Do NOT run destructive operations. Reply in Russian.

Deliver a written verdict with:
1. Semantic correctness of each committed change vs the owner's contract (below).
2. Concrete evidence lines you actually read (path:line — from the diff, not from memory).
3. Any material findings that must be fixed before release.
4. Edge cases the tests miss.

## Scope in this diff — 7 commits

The branch closes:
- **WMS-338 / WMS-341 / WMS-329** — remove non-operator mutations of `FbsBindingStockPool.quantity`. Contract: the field is an OPERATOR-SET CAP. Only the operator changes it. Publication is `min(cap, free_stock)`. No journals, no counters, no reservation ledger.
- **WMS-060** — frontend `/ff/fbs-stock` no longer silently resets `units_mode` when saving a rule with `units_by_warehouse`.
- **WMS-384** — unified predicate helper `product_has_rule_predicate()` in `fbs_stock_rule_service.py`; other services import it.

## Files (per author report)

- `backend/app/services/inventory_service.py` — five removals of `pool.quantity` writes: reservation (~L200-226), cancel (~L253-260), inventory shortage (~L305-311), `apply_fbs_supply_write_off` (~L1697-1707), and a units-mode reserve check adjustment. Please quote the exact current lines.
- `backend/app/services/fbs_stock_rule_service.py` — added `product_has_rule_predicate()`.
- `backend/app/services/fbs_stock_sync_service.py`, `backend/app/services/fbs_warehouse_binding_service.py` — call the shared predicate.
- `frontend/src/screens/ff/products-fbs/FfProductsFbsPage.tsx` — sends `units_mode` + `units_by_warehouse` on save.
- `backend/tests/test_inventory_stock_cap_wms338.py` — 6 new regressions.
- `backend/tests/test_fbs_stock_rule_service.py`, `backend/tests/test_fbs_pr140_shipment_write_off.py` — legacy assertions updated.
- `docs/reviews/wms338-stock-fix-2026-09-10.md` — review record.

## Known open point — do NOT re-derive; treat as given

The author's note also claims **WMS-352 / WMS-386 done** by asserting no `FbsBindingStockPool` mutations in Ozon services. Owner (root) verified independently that the actual filter in `backend/app/services/ozon_fbs_sync_service.py` between lines 513-545 (`_stock_is_published_for_row`) still requires the product publication flag, and `sync_ozon_orders` at line 836 calls it. So **WMS-352/386 are NOT fixed on this branch**. Do NOT try to fix them here — a separate slice will address them. Please still comment briefly on whether the diff introduces any regression in Ozon paths.

## Specific questions
1. Are all five documented `pool.quantity` write removals actually removed at the claimed line ranges? Any remaining callers of `pool.quantity =/+=/-=` outside the operator save path?
2. Does the `min(cap, free_stock)` publication path stay intact end-to-end in `inventory_service.py`? Any place that would now under-publish because a formerly-decremented cap no longer decrements?
3. `product_has_rule_predicate()` — is it a strict semantic replacement of prior inline predicates? Any call site diverging?
4. Frontend `FfProductsFbsPage.tsx` — does it send both `units_mode` and `units_by_warehouse` on every save, including the WMS-060 previously-broken code path?
5. Test coverage: do the six new tests actually assert cap-unchanged on the reservation / cancel / shortage / transfer / apply_fbs_supply_write_off paths, or do they only cover pool creation? Please quote the assertion patterns.
6. Migration risk: does dropping the mutations require a data backfill or downgrade path? Any alembic considered but skipped?

## Boundaries
- Do NOT touch mobile/, chat components, product_merge_service.py, fbs_cancellation*, chat_*, FBS columns.
- Do NOT run against production data.
- Do NOT propose replacing the operator-set cap with a counter or a journal — that violates the owner's second ⛔ rule.
- Output: 20-100 lines of Russian text; prefer specific path:line citations over prose.
