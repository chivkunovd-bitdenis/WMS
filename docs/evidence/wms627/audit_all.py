"""Read-only all-tenant shipment/writeoff audit; no credentials in output."""
import asyncio, json
from sqlalchemy import text
from app.db.session import SessionLocal

QUERIES = {
 'scope': "SELECT count(*) tenants FROM tenants",
 'fbs_summary': """SELECT t.name tenant,s.marketplace,s.status,count(distinct s.id) supplies,count(o.id) orders,
 count(o.id) FILTER (WHERE o.product_id IS NOT NULL AND o.status<>'cancelled') mapped_active,
 count(l.id) FILTER (WHERE l.shipment_movement_id IS NOT NULL) written,
 count(l.id) FILTER (WHERE l.reversed_at IS NOT NULL) reversed,
 count(o.id) FILTER (WHERE o.product_id IS NOT NULL AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL) missing
 FROM fbs_supplies s JOIN tenants t ON t.id=s.tenant_id LEFT JOIN fbs_orders o ON o.supply_id=s.id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id
 GROUP BY 1,2,3 ORDER BY 1,2,3""",
 'fbs_missing': """SELECT t.name tenant, se.name seller,s.id,s.tenant_id,s.seller_id,s.warehouse_id,s.wb_supply_id,s.marketplace,s.source,s.status,s.created_at,s.delivered_at,s.updated_at,
 count(o.id) orders,count(o.id) FILTER (WHERE o.product_id IS NOT NULL AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL) missing,
 count(o.id) FILTER (WHERE EXISTS(SELECT 1 FROM fbs_order_picks p WHERE p.fbs_order_id=o.id AND p.undone_at IS NULL)) active_picks
 FROM fbs_supplies s JOIN tenants t ON t.id=s.tenant_id JOIN sellers se ON se.id=s.seller_id JOIN fbs_orders o ON o.supply_id=s.id LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id
 WHERE s.status IN ('done','in_delivery') OR s.delivered_at IS NOT NULL
 GROUP BY t.name,se.name,s.id HAVING count(o.id) FILTER (WHERE o.product_id IS NOT NULL AND o.status<>'cancelled' AND l.shipment_movement_id IS NULL AND l.reversed_at IS NULL)>0
 ORDER BY t.name,s.created_at""",
 'outbound_mismatches': """SELECT t.name tenant,r.id,l.id line,l.shipped_qty,coalesce(-sum(m.quantity_delta),0) movement_qty
 FROM outbound_shipment_requests r JOIN tenants t ON t.id=r.tenant_id JOIN outbound_shipment_lines l ON l.request_id=r.id LEFT JOIN inventory_movements m ON m.outbound_shipment_line_id=l.id
 GROUP BY t.name,r.id,l.id HAVING l.shipped_qty<>coalesce(-sum(m.quantity_delta),0)""",
 'outbound_scope': 'SELECT count(distinct request_id) documents,count(*) lines,sum(shipped_qty) shipped FROM outbound_shipment_lines',
}
async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  await s.execute(text("SET LOCAL statement_timeout='60s'"))
  for key,q in QUERIES.items():
   print(json.dumps({key:[dict(r) for r in (await s.execute(text(q))).mappings()]},ensure_ascii=False,default=str),flush=True)
  await s.rollback()
asyncio.run(main())
