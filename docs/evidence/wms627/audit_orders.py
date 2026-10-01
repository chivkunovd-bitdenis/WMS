"""Read-only all-tenant shipment/writeoff audit; no credentials in output."""
import asyncio, json
from sqlalchemy import text
from app.db.session import SessionLocal

QUERIES = {'missing_details': "SELECT t.name tenant,s.source,s.wb_supply_id,s.id supply_id,s.created_at supply_created,s.delivered_at,o.id order_id,o.product_id,o.wb_order_id,o.external_order_id,o.status,o.wb_status,o.created_at order_created,p.sku_code,p.created_at product_created,l.id ledger_id,l.quantity,l.created_at ledger_created,l.source_mode,l.storage_location_id ledger_location,\n(SELECT sum(b.quantity) FROM inventory_balances b WHERE b.product_id=o.product_id) stock,\n(SELECT min(m.created_at) FROM inventory_movements m WHERE m.product_id=o.product_id AND m.quantity_delta>0 AND m.movement_type IN ('inbound_intake','product_tz_import','inventory_count')) first_stock,\n(SELECT max(m.created_at) FROM inventory_movements m WHERE m.product_id=o.product_id AND m.movement_type='inventory_count') last_count,\n(SELECT count(*) FROM fbs_order_picks pk WHERE pk.fbs_order_id=o.id) picks,\n(SELECT count(*) FROM fbs_wb_operations op WHERE op.local_entity_id=s.id AND op.operation_kind='supply_deliver') delivery_operations\nFROM fbs_orders o JOIN fbs_supplies s ON s.id=o.supply_id JOIN tenants t ON t.id=s.tenant_id JOIN products p ON p.id=o.product_id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id WHERE (s.status IN ('done','in_delivery') OR s.delivered_at IS NOT NULL) AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL ORDER BY t.name,s.created_at,o.id", 'orphan_movements': "SELECT m.id,t.name tenant,m.product_id,m.storage_location_id,m.quantity_delta,m.created_at,m.transfer_group_id FROM inventory_movements m JOIN tenants t ON t.id=m.tenant_id WHERE m.movement_type='fbs_shipment' AND NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.shipment_movement_id=m.id OR l.reversal_movement_id=m.id) ORDER BY m.created_at", 'unload_schema': "SELECT table_name,column_name FROM information_schema.columns WHERE table_name IN ('marketplace_unload_requests','marketplace_unload_lines') ORDER BY 1,ordinal_position"}
async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  await s.execute(text("SET LOCAL statement_timeout='60s'"))
  for key,q in QUERIES.items():
   print(json.dumps({key:[dict(r) for r in (await s.execute(text(q))).mappings()]},ensure_ascii=False,default=str),flush=True)
  await s.rollback()
asyncio.run(main())
