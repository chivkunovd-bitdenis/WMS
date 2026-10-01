"""Reconcile the frozen, independently audited missing WB order set.

Default is full transactional rehearsal and rollback. Excludes subsequent
inventory counts, intake after shipment, legacy ledgers and ownership changes.
"""
import asyncio,json,sys,uuid
from collections import Counter
from datetime import datetime
import httpx
from sqlalchemy import select,text
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_wb_operation import FbsWbOperation
from app.services.fbs_shipment_service import _write_off_delivered_orders_once
from app.services.fbs_shipment_source_service import plan_fbs_shipment_sources,FbsShipmentSourceRequest
from app.services.document_event_service import record_document_event
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token
from app.services.wildberries_fbs_client import fetch_marketplace_supply_details,fetch_marketplace_supply_order_ids

async def main():
 targets=json.loads(sys.argv[1]);apply='--apply' in sys.argv
 assert len(targets)==35 and len({r['order_id'] for r in targets})==35
 by_supply={}
 for row in targets:by_supply.setdefault(uuid.UUID(row['supply_id']),[]).append(row)
 # Fresh read-only marketplace verification before any database locks.
 async with SessionLocal() as s:
  async with httpx.AsyncClient(timeout=30) as c:
   for sid,rows in by_supply.items():
    su=await s.get(FbsSupply,sid);assert su and su.wb_supply_id==rows[0]['wb_supply_id']
    token=await get_decrypted_marketplace_token(s,su.tenant_id,su.seller_id)
    detail=await fetch_marketplace_supply_details(c,api_token=token,supply_id=su.wb_supply_id,marketplace_api_base='https://marketplace-api.wildberries.ru')
    ids=await fetch_marketplace_supply_order_ids(c,api_token=token,supply_id=su.wb_supply_id,marketplace_api_base='https://marketplace-api.wildberries.ru')
    assert detail.done and all(r['wb_order_id'] in ids for r in rows)
  await s.rollback()
 async with SessionLocal() as s:
  await s.execute(text("SET LOCAL lock_timeout='8s'"))
  await s.execute(text("SET LOCAL statement_timeout='90s'"))
  supplies=list((await s.scalars(select(FbsSupply).where(FbsSupply.id.in_(by_supply)).order_by(FbsSupply.id).with_for_update())).all())
  order_ids=[uuid.UUID(r['order_id']) for r in targets]
  orders=list((await s.scalars(select(FbsOrder).where(FbsOrder.id.in_(order_ids)).order_by(FbsOrder.id).with_for_update())).all())
  assert len(orders)==35
  existing=list((await s.scalars(select(FbsShipmentReversalLedger).where(FbsShipmentReversalLedger.fbs_order_id.in_(order_ids)).with_for_update())).all())
  if existing:
   assert len(existing)==35 and all(l.shipment_movement_id and not l.reversed_at for l in existing),'Partial prior application; stop'
   print(json.dumps({'mode':'already_applied','count':35}));await s.rollback();return
  products=sorted({o.product_id for o in orders},key=str)
  await s.execute(text('SELECT id FROM products WHERE id=ANY(:p) ORDER BY id FOR UPDATE'),{'p':products})
  before=await s.scalar(text('SELECT sum(quantity) FROM inventory_balances WHERE product_id=ANY(:p)'),{'p':products})
  indexed={str(o.id):o for o in orders}
  for r in targets:
   o=indexed[r['order_id']];assert str(o.product_id)==r['product_id'] and o.wb_order_id==r['wb_order_id'] and o.status!='cancelled' and str(o.supply_id)==r['supply_id']
   closed=datetime.fromisoformat(r['wb_closed_at'].replace('Z','+00:00'))
   changed=await s.scalar(text("SELECT count(*) FROM inventory_movements WHERE product_id=:p AND created_at>:closed AND movement_type IN ('inventory_count','ownership_transfer_out')"),{'p':o.product_id,'closed':closed})
   assert changed==0,'Subsequent stock reset/ownership change; stop'
  modes=Counter();negative=0
  for su in supplies:
   selected=[o for o in orders if o.supply_id==su.id]
   assert all(o.tenant_id==su.tenant_id and o.seller_id==su.seller_id for o in selected)
   plan=await plan_fbs_shipment_sources(s,tenant_id=su.tenant_id,supply_warehouse_id=su.warehouse_id,requests=[FbsShipmentSourceRequest(fbs_order_id=o.id,product_id=o.product_id,quantity=1) for o in selected])
   for item in plan.resolutions:
    modes[item.source_mode]+=1;negative+=item.negative_quantity
   op=FbsWbOperation(tenant_id=su.tenant_id,seller_id=su.seller_id,operation_kind='supply_delivery_reconciliation',idempotency_key='wms627:all:'+str(su.id),local_entity_type='fbs_supply',local_entity_id=su.id,wb_object_id=su.wb_supply_id,wb_object_kind='supply',state='confirmed',request_summary_json={'task':'WMS-627','audited_order_ids':[str(o.id) for o in selected]},response_summary_json={'wb_done':True,'membership_verified':True,'external_mutation':False})
   s.add(op);await s.flush()
   await _write_off_delivered_orders_once(s,su,selected,None,source_plan=plan,operation=op)
   await record_document_event(s,tenant_id=su.tenant_id,document_type='fbs_supply',document_id=su.id,event_type='data_changed',source='system',actor_user_id=None,qty=len(selected),idempotency_key='wms627:all:'+str(su.id),payload_json={'kind':'wms627_audited_missing_writeoff','order_ids':[str(o.id) for o in selected],'operation_id':str(op.id),'subsequent_inventory_counts_excluded':True})
  await s.flush()
  after=await s.scalar(text('SELECT sum(quantity) FROM inventory_balances WHERE product_id=ANY(:p)'),{'p':products})
  count=await s.scalar(text('SELECT count(*) FROM fbs_shipment_reversal_ledger WHERE fbs_order_id=ANY(:ids) AND shipment_movement_id IS NOT NULL'),{'ids':order_ids})
  assert after==before-35 and count==35
  result={'mode':'applied' if apply else 'rollback_verified','orders':35,'supplies':len(supplies),'tenants':dict(Counter(r['tenant'] for r in targets)),'affected_stock_before':before,'affected_stock_after':after,'negative_quantity':negative,'source_modes':dict(modes)}
  if apply:await s.commit()
  else:await s.rollback()
  print(json.dumps(result,ensure_ascii=False,default=str))
asyncio.run(main())
