# 00–04 — fbs-shipment-pvz (модератор MVP)

## In
1. Model `FbsTrbx`: id, supply_id FK, wb_trbx_id str, packaging_box_id nullable UUID **without FK** if packaging_box table unclear — OR FK to `warehouse_boxes` if that is the box entity. Prefer nullable UUID without FK + optional `length_mm/width_mm/height_mm/weight_g` on trbx for validation when no box.
2. Migration 0066; set `fbs_orders.trbx_id` FK → fbs_trbx ON DELETE SET NULL.
3. WB: POST `/api/v3/supplies/{sid}/trbx` body `{"amount": N}` (or count — check SDK; use amount), PATCH add orders to trbx, POST trbx/stickers.
4. API under `/operations/fbs-supplies/{id}/trbx...`
5. Validation on add orders: max side ≤600mm, weight ≤5000g, ≥2 orders unless override flag `allow_single` default false; supply volume sum ≤1m³.
6. Extend `deliver_supply`: if `delivery_type==pvz` require all orders have trbx_id; if warehouse_sc keep existing path. Reject wrong type as before.
7. Stickers cache like order stickers.

## Out
Deep packaging_task wiring; frontend; exact packaging_box FK if model is messy — use dimensions on request.

## Tests TC-NEW-FBS-SHIPPVZ-001..004
`tests/test_fbs_shipment_pvz.py`

## Ок на код
