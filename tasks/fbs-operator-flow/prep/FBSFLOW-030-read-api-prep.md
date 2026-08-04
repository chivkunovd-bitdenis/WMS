# FBSFLOW-030 prep — worklist & workspace read API

> Source: [Prep FBSFLOW-030 read-api](3d9c9a37-0456-4090-b755-43be4b77809f), 2026-08-03

## Missing endpoints

- `GET /operations/fbs-orders/worklist` — cursor pagination, enriched `FbsWorklistOrder`, `server_now`, **no price**
- `GET /operations/fbs-supplies/{id}/workspace` — stage, progress, blockers, cargo_places, delivery_preflight stub

Current `GET /fbs-orders` and `GET /fbs-supplies/{id}` stay for compat only.

## N+1 traps (fix before implement)

1. `list_location_balances_for_products_in_warehouse` — reserve query **per row**
2. Per-order `fbs_available_qty_for_product` — use `fbs_available_qty_by_product` batch
3. Markings without `selectinload`
4. WB warehouse names — batch per seller, not per order
5. Card images — batch `nm_id IN (…)` once

## New services

- `fbs_worklist_service.py` — fetch page + batch loaders + pure mappers + `build_worklist_items`
- `fbs_workspace_service.py` — supply graph + stage/progress/blockers + reuse worklist builder

## Query budget targets

- Worklist 500 orders: **≤15–20** SQL (flat vs N)
- Workspace 100 orders: **≤25** SQL

## Tests

`backend/tests/test_fbs_worklist_query_count.py` — copy pattern from `test_fbs_availability_batch_query_count_bounded`

## Dependencies

| Lane | Need |
|------|------|
| 010 | pick/pack/sticker/metadata real states; until then fallbacks from columns |
| 040 | full selection_blockers validator |
| 080 | asset URLs not paths |
| 100 | delivery_preflight in workspace |
