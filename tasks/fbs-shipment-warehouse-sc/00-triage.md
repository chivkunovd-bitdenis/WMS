# 00–04 — fbs-shipment-warehouse-sc (модератор)

## MVP
1. Extend `fbs_supplies` API (prefer same router):
   - `POST /operations/fbs-supplies/{supply_id}/deliver`
   - `GET /operations/fbs-supplies/{supply_id}/barcode?type=png`
2. WB client: `deliver_marketplace_supply`, `fetch_marketplace_supply_barcode`
3. Service `fbs_shipment_service.py` (or methods in fbs_supply_service — prefer separate file):
   - Preconditions: `delivery_type==warehouse_sc`; ≥1 order; no cancelled; each order status in {in_supply, assembling, packed}; if `product.requires_honest_sign` → must have sgtin marking (any check_status except missing)
   - Lock supply `with_for_update`; WB deliver; set supply.status=in_delivery, orders→in_delivery; set delivered_at
   - Barcode: fetch PNG, cache under wms_data_dir/fbs-supply-barcodes/{supply_id}.png, store path in barcode_file
4. Checklist endpoint — **defer** (optional in TASK)
5. Mock `e2e_mock_wb_marketplace_supplies` extend for deliver/barcode OR new flag

## Tests TC-NEW-FBS-SHIPWH-001..004
`tests/test_fbs_shipment_warehouse_sc.py`

## Ок на код
