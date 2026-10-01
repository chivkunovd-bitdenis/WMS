"""Read-only all-tenant shipment/writeoff audit; no credentials in output."""
import asyncio, json
from sqlalchemy import text
from app.db.session import SessionLocal

QUERIES = {'classify': "SELECT t.name tenant,s.marketplace,s.source,(l.id IS NOT NULL) ledger_exists,(l.ozon_positions_json IS NOT NULL) ozon_positions, count(*) n,min(s.created_at) earliest,max(s.created_at) latest FROM fbs_orders o JOIN fbs_supplies s ON s.id=o.supply_id JOIN tenants t ON t.id=s.tenant_id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id WHERE (s.status IN ('done','in_delivery') OR s.delivered_at IS NOT NULL) AND o.product_id IS NOT NULL AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4", 'legacy_movement_totals': "SELECT t.name tenant,m.movement_type,count(*) n,sum(m.quantity_delta) qty,min(m.created_at),max(m.created_at) FROM inventory_movements m JOIN tenants t ON t.id=m.tenant_id WHERE m.movement_type='fbs_shipment' AND NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.shipment_movement_id=m.id OR l.reversal_movement_id=m.id) GROUP BY 1,2", 'artmaks_operations': "SELECT operation_kind,state,error_code,local_entity_id,created_at,confirmed_at FROM fbs_wb_operations WHERE local_entity_id IN ('1b16d0b1-6ccd-451c-b3af-aaf95f484caf','c8fa8549-6ff4-4bd4-85ca-9a87c316ac1f') ORDER BY created_at", 'ozon_ledgers': "SELECT o.id,o.external_order_id,o.status,o.wb_status,l.id ledger,l.quantity,l.ozon_positions_json,s.id supply FROM fbs_orders o JOIN fbs_supplies s ON s.id=o.supply_id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id WHERE s.tenant_id=(SELECT id FROM tenants WHERE name='Бамбук') AND s.status IN ('done','in_delivery') AND l.shipment_movement_id IS NULL"}
async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  await s.execute(text("SET LOCAL statement_timeout='60s'"))
  for key,q in QUERIES.items():
   print(json.dumps({key:[dict(r) for r in (await s.execute(text(q))).mappings()]},ensure_ascii=False,default=str),flush=True)
  await s.rollback()
asyncio.run(main())
