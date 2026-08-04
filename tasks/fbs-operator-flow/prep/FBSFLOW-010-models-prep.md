# FBSFLOW-010 prep — models & migration plan

> Source: [Prep FBSFLOW-010 models plan](c5b3be5f-57b4-4b5b-b7c3-e9db47de8299), 2026-08-03  
> Alembic base: `20260802_0068` → new `20260803_0069_fbs_operator_flow_models`

## 5 new tables

| Table | Purpose |
|-------|---------|
| `fbs_order_picks` | 1:1 active pick per order; unique active per order |
| `fbs_order_pick_events` | undo audit append-only |
| `fbs_packaging_fulfillments` | 1 pack unit → 1 FbsOrder; unique active per order |
| `fbs_print_assets` | binary assets; `storage_path` internal only |
| `fbs_wb_operations` | WB journal; unique `(seller_id, operation_kind, idempotency_key)` |

## Alter existing

**fbs_orders:** `pick_status`, `pack_status`, `sticker_status`, `required_meta_json`, `optional_meta_json`, `meta_details_json`, timestamps; indexes `(tenant, seller, status, deadline)`

**fbs_order_markings:** `meta_status`, `reason`, `meta_details_json` — backfill from `check_status` only where provable

**fbs_supplies:** `planned_destination_*`, `last_wb_sync_at`, `barcode_asset_id`

**fbs_trbxes:** `qr_asset_id`, `qr_applied_*`

**packaging_task.py:** relationships to `FbsPackagingFulfillment` only — no new columns on lines

## Backfill rules

- Status columns → `pending` / `not_requested`
- `sticker_status='ready'` only where `sticker_file IS NOT NULL`
- Do NOT invent picks, fulfillments, WB ops, or migrate paths to assets (080)

## New model files

- `fbs_order_pick.py`, `fbs_print_asset.py`, `fbs_wb_operation.py`, `fbs_packaging_fulfillment.py`

## Tests

- `test_fbs_operator_flow_models.py` — constraint violations
- `test_fbs_operator_flow_migration.py` — PG upgrade→downgrade→upgrade

## Out of scope 010

Services, API, WB client, deleting legacy `sticker_file` paths, requiredMeta intake (070)
