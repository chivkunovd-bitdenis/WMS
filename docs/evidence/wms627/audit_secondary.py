"""Read-only all-tenant shipment/writeoff audit; no credentials in output."""
import asyncio, json
from sqlalchemy import text
from app.db.session import SessionLocal

QUERIES = {'fbo_scope': 'SELECT t.name tenant,r.status,count(*) documents FROM marketplace_unload_requests r JOIN tenants t ON t.id=r.tenant_id GROUP BY 1,2 ORDER BY 1,2', 'fbo_posted_missing': 'SELECT t.name tenant,r.id,r.status,r.shipped_at,(SELECT sum(l.quantity) FROM marketplace_unload_lines l WHERE l.request_id=r.id) expected,(SELECT sum(-m.quantity_delta) FROM inventory_movements m WHERE m.marketplace_unload_request_id=r.id) written FROM marketplace_unload_requests r JOIN tenants t ON t.id=r.tenant_id WHERE r.shipped_at IS NOT NULL AND NOT EXISTS(SELECT 1 FROM inventory_movements m WHERE m.marketplace_unload_request_id=r.id AND m.quantity_delta<0)', 'ledger_operations': "SELECT t.name tenant,s.wb_supply_id,l.id,l.fbs_order_id,l.product_id,l.quantity,l.created_at,l.source_mode,op.operation_kind,op.state,op.error_code,op.created_at op_created FROM fbs_shipment_reversal_ledger l JOIN fbs_orders o ON o.id=l.fbs_order_id JOIN fbs_supplies s ON s.id=o.supply_id JOIN tenants t ON t.id=s.tenant_id LEFT JOIN fbs_wb_operations op ON op.id=l.wb_operation_id WHERE l.shipment_movement_id IS NULL AND l.reversed_at IS NULL AND s.status IN ('done','in_delivery') ORDER BY l.created_at", 'artmaks_tatarchuk_movements': "SELECT m.movement_type,count(*) movements,sum(m.quantity_delta) qty,min(m.created_at),max(m.created_at) FROM inventory_movements m JOIN products p ON p.id=m.product_id WHERE p.seller_id='664a3b9f-2368-4987-8f82-56c3fb730a09' GROUP BY 1"}
async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  await s.execute(text("SET LOCAL statement_timeout='60s'"))
  for key,q in QUERIES.items():
   print(json.dumps({key:[dict(r) for r in (await s.execute(text(q))).mappings()]},ensure_ascii=False,default=str),flush=True)
  await s.rollback()
asyncio.run(main())
