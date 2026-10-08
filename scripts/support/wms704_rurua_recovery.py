"""WMS-704: exact, one-time local recovery. Default read-only; --apply commits.
No Ozon ship/create/approve, no fabricated packing or inventory writes.
Run inside the existing WMS API environment.
"""
import asyncio, hashlib, json, sys, uuid
from datetime import datetime, timezone
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.document_event import DocumentEvent
from app.models.packaging_task import PackagingTaskLine
from app.services.fbs_supply_service import start_supply_work, list_supply_worklist, planned_shipment_date_for_orders
from app.services.fbs_workspace_service import get_supply_workspace
from app.services.fbs_supply_reconcile_service import create_pending_operation, mark_operation_confirmed
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
from app.services.ozon_fbs_process_service import _posting_readback

TENANT = uuid.UUID("5baaf211-7cb7-495d-9c2b-b42121606bf9")
SELLER = uuid.UUID("c52ef05d-f787-4de5-acc5-76f9736691aa")
WAREHOUSE = uuid.UUID("050fb5f6-dacf-4742-96ec-e9128a73cc81")
PRODUCT = uuid.UUID("7002428c-a513-43af-aadb-b0ff968285a5")
ORDERS = {
 "1f1febff-2ad0-47a8-a3b5-a2bd237f4e43": "0125883568-0126-1",
 "959f0737-f301-47b9-bb56-74cc77f17120": "41767844-0042-2",
 "9d87bd87-6e72-47a1-99f5-0359e3c0d77b": "0157163931-0186-1",
}
IDS = sorted(uuid.UUID(v) for v in ORDERS)
KEY = "WMS-704:ruspro-rurua:three-awaiting-deliver:2026-10-08"
SUPPLY_ID = uuid.uuid5(uuid.NAMESPACE_URL, KEY)
NAME = "FBS Ozon 08.10.2026 · Руруа"
APPLY = "--apply" in sys.argv

def order_snapshot(o):
 return {"id":str(o.id),"posting":o.external_order_id,"status":o.status,
 "supplier_status":o.supplier_status,"wb_status":o.wb_status,
 "supply_id":str(o.supply_id) if o.supply_id else None,
 "reserve_status":o.reserve_status,"pick_status":o.pick_status,"pack_status":o.pack_status,
 "created_at":str(o.created_at),"meta":o.meta_details_json}

async def load(s, lock=False):
 q=select(FbsOrder).where(FbsOrder.tenant_id==TENANT,FbsOrder.seller_id==SELLER,FbsOrder.id.in_(IDS)).options(selectinload(FbsOrder.product_positions)).order_by(FbsOrder.id)
 if lock:q=q.with_for_update()
 rows=list(await s.scalars(q))
 assert len(rows)==3, "exact order count"
 for o in rows:
  assert o.marketplace=="ozon" and o.warehouse_id==WAREHOUSE
  assert o.external_order_id==ORDERS[str(o.id)]
  assert len(o.product_positions)==1
  p=o.product_positions[0]
  assert p.product_id==PRODUCT and str(p.ozon_sku)=="5282514171" and p.quantity==1
 return rows

async def accounting(s):
 params={"t":TENANT,"p":PRODUCT,"ids":[str(x) for x in IDS]}
 queries={
 "balances":"SELECT to_jsonb(b) FROM inventory_balances b WHERE tenant_id=:t AND product_id=:p ORDER BY id",
 "movement_count":"SELECT count(*) FROM inventory_movements WHERE tenant_id=:t AND product_id=:p",
 "ledger":"SELECT to_jsonb(b) FROM fbs_shipment_reversal_ledger b WHERE tenant_id=:t AND fbs_order_id=ANY(CAST(:ids AS uuid[])) ORDER BY id",
 "packing":"SELECT to_jsonb(b) FROM fbs_packaging_fulfillments b WHERE tenant_id=:t AND fbs_order_id=ANY(CAST(:ids AS uuid[])) ORDER BY id"
 }
 return {k:list((await s.execute(text(q),params)).scalars()) for k,q in queries.items()}

async def verify(s, before=None):
 rows=await load(s)
 assert {o.supply_id for o in rows}=={SUPPLY_ID}
 w=await get_supply_workspace(s,TENANT,SUPPLY_ID)
 assert w["supply"]["source"]=="wms" and w["supply"]["marketplace"]=="ozon"
 assert w["supply"]["status"]=="assembling" and w["supply"]["packaging_task_id"]
 assert w["blockers"]==[] and w["stage"]!="tracking"
 assert {o["id"] for o in w["orders"]}=={str(v) for v in IDS}
 task_id=uuid.UUID(w["supply"]["packaging_task_id"])
 lines=list(await s.scalars(select(PackagingTaskLine).where(PackagingTaskLine.task_id==task_id)))
 assert len(lines)==1 and lines[0].product_id==PRODUCT and lines[0].qty_total==3 and lines[0].qty_suggested_packed==0
 page=await list_supply_worklist(s,TENANT,seller_id=SELLER,marketplace="ozon",status_group="active")
 assert any(str(x["id"])==str(SUPPLY_ID) for x in page["items"])
 if before:
  for o in rows:
   old=before[str(o.id)]
   now=order_snapshot(o)
   for key in ["supplier_status","wb_status","reserve_status","pick_status","pack_status","created_at","meta"]:
    assert old[key]==now[key],key
 return {"supply_id":str(SUPPLY_ID),"workspace":w,"task_lines":[{"product_id":str(x.product_id),"quantity":x.qty_total,"suggested_packed":x.qty_suggested_packed} for x in lines],"active_list_contains_supply":True}

async def main():
 remote={}
 async with SessionLocal() as s:
  await s.execute(text("SET TRANSACTION READ ONLY"))
  rows=await load(s)
  if all(o.supply_id==SUPPLY_ID for o in rows):
   result=await verify(s)
   print(json.dumps({"state":"already_applied","verification":result},ensure_ascii=False,default=str))
   await s.rollback();return
  assert all(o.supply_id is None and o.status=="external_processing" and o.wb_status=="awaiting_deliver" for o in rows),"state changed"
  before={str(o.id):order_snapshot(o) for o in rows}
  baseline=await accounting(s)
  assert baseline["ledger"]==[] and baseline["packing"]==[],"existing physical facts"
  assert all(not (o.meta_details_json or {}).get("ozon_assembly") for o in rows)
  cid,key=await MarketplaceAccountService(s).stored_credentials(TENANT,SELLER)
  assert ozon_live_api_enabled()
  provider=build_ozon_provider()
  for o in rows:
   card=(await _posting_readback(provider,client_id=cid,api_key=key,posting_number=o.external_order_id)).result
   assert card and card.posting_number==o.external_order_id
   assert card.status=="awaiting_deliver" and card.substatus=="posting_transferring_to_delivery"
   assert len(card.products)==1 and card.products[0].sku==5282514171 and card.products[0].quantity==1
   assert not card.related_postings or not card.related_postings.related_posting_numbers
   assert card.delivery_method and card.delivery_method.id==1020005025459970
   remote[o.external_order_id]={"status":card.status,"substatus":card.substatus,"method":card.delivery_method.id,"shipment_date":str(card.shipment_date),"sku":5282514171,"quantity":1,"checked_at":datetime.now(timezone.utc).isoformat()}
  assert len({r["shipment_date"] for r in remote.values()})==1
  await s.rollback()
 if not APPLY:
  print(json.dumps({"state":"preflight_pass","supply_id":str(SUPPLY_ID),"before":before,"accounting":baseline,"ozon":remote},ensure_ascii=False,default=str));return
 async with SessionLocal() as s:
  async with s.begin():
   await s.execute(text("SET LOCAL lock_timeout = '5s'"))
   await s.execute(text("SET LOCAL statement_timeout = '30s'"))
   rows=await load(s,lock=True)
   for o in rows:assert order_snapshot(o)==before[str(o.id)],"changed during Ozon read"
   assert await s.get(FbsSupply,SUPPLY_ID) is None
   assert await accounting(s)==baseline,"accounting changed"
   request={"task":"WMS-704","orders":ORDERS,"owner_authorized_recovery":True,"ozon_readback":remote,"original_orders":before}
   op=await create_pending_operation(s,tenant_id=TENANT,seller_id=SELLER,idempotency_key=KEY,request_hash=hashlib.sha256(KEY.encode()).hexdigest(),request_summary=request)
   supply=FbsSupply(id=SUPPLY_ID,tenant_id=TENANT,seller_id=SELLER,warehouse_id=WAREHOUSE,marketplace="ozon",wb_supply_id=f"PENDING-{op.id}",name=NAME,source="wms",status="draft",delivery_type="warehouse_sc",cargo_type=rows[0].cargo_type,planned_shipment_date=await planned_shipment_date_for_orders(s,TENANT,rows))
   s.add(supply);await s.flush()
   for o in rows:o.supply_id=SUPPLY_ID;o.status="in_supply"
   await s.flush()
   await mark_operation_confirmed(s,op,wb_supply_id=supply.wb_supply_id,local_supply_id=SUPPLY_ID,response_summary={"recovered_local_only":True,"external_order_ids":list(ORDERS.values())})
   await start_supply_work(s,TENANT,SUPPLY_ID,actor_user_id=None,http_client=None)
   s.add(DocumentEvent(tenant_id=TENANT,document_type="fbs_supply",document_id=SUPPLY_ID,event_type="document_created",source="system",actor_user_id=None,idempotency_key=KEY,payload_json={"reason":"Разовое восстановление по прямому поручению владельца; без внешней сборки/передачи и движения товара","order_ids":[str(x) for x in IDS],"before":before,"task":"WMS-704"}))
   await s.flush()
   result=await verify(s,before)
   assert await accounting(s)==baseline,"unexpected accounting change"
  print(json.dumps({"state":"applied","at":datetime.now(timezone.utc).isoformat(),"before":before,"ozon":remote,"accounting_unchanged":True,"verification":result},ensure_ascii=False,default=str))
asyncio.run(main())
