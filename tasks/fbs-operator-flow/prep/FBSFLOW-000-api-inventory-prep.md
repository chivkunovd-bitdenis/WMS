# FBSFLOW-000 prep — API inventory & contract gaps

> Source: [Map FBS API endpoints](f5385515-4021-4b5b-afb2-20c37091d6c5), 2026-08-03

## Existing routes (28)

- **fbs_orders.py:** sync, list, cancel, sync-statuses
- **fbs_marking.py:** markings GET/PUT/sync
- **fbs_supplies.py:** create, get, add-order, picking-list, stickers, trbx, trbx/stickers, trbx/orders, status, bind-box, deliver, barcode
- **fbs_sellers.py:** warehouses, offices, bindings CRUD, stocks sync

Alembic head: `20260802_0068_fbs_stock_sync`

## Models today

- FbsOrder, FbsOrderMarking, FbsOrderReservation, FbsSupply, FbsTrbx, FbsWarehouseBinding, FbsStockSyncItem
- PackagingTask/Lines — **no** fbs_order_id, pick records, print assets

## Contract gaps (~19 missing/changed)

| Missing | Partial |
|---------|---------|
| GET worklist | POST deliver (no idempotency/preflight version) |
| POST preflight | POST trbx (order binding still present) |
| POST from-orders | packaging-tasks (no fulfilled_order) |
| GET workspace | |
| POST start-work | |
| pick scan-location/product/undo | |
| metadata GET/scan | |
| print-assets batch + content + applied | |
| cargo-places preflight/list | |
| delivery-preflight | |
| structured error envelope | |

**Deprecate:** `POST …/trbx/{trbx_id}/orders` still live.

## Schema implied by contract (→ 010)

Pick records 1:1 order, print assets + applied audit, PackagingTaskLine↔FbsOrder link.
