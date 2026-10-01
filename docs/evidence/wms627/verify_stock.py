import asyncio,json,uuid,httpx
from sqlalchemy import select,text
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.fbs_order import FbsOrder
from app.services.fbs_stock_rule_service import publish_amounts_for_binding
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token
from app.services.wildberries_client import fetch_marketplace_stocks
async def main():
 t=uuid.UUID('82b36645-8662-497f-9631-a0743994632c'); seller=uuid.UUID('68dd641b-c5cc-4e0a-8057-015eca180d0e')
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  bind=await s.get(FbsWarehouseBinding,uuid.UUID('65ef376a-9252-4120-9a6d-4a1b8826b536'))
  supply_ids=[uuid.UUID(x) for x in ['1b16d0b1-6ccd-451c-b3af-aaf95f484caf','c8fa8549-6ff4-4bd4-85ca-9a87c316ac1f']]
  products=list((await s.scalars(select(Product).where(Product.id.in_(select(FbsOrder.product_id).where(FbsOrder.supply_id.in_(supply_ids)))))).all())
  target=await publish_amounts_for_binding(s,bind,products)
  token=await get_decrypted_marketplace_token(s,t,seller)
  keyed={int(p.wb_chrt_id):(p,target[p.id]) for p in products if p.id in target and p.wb_chrt_id}
  async with httpx.AsyncClient(timeout=40) as c:
   amounts=await fetch_marketplace_stocks(c,api_token=token,warehouse_id=bind.wb_warehouse_id,chrt_ids=list(keyed),marketplace_api_base='https://marketplace-api.wildberries.ru') if keyed else []
  actual={a.chrt_id:a.amount for a in amounts}
  mismatches=[{'sku':p.sku_code,'expected':q,'wb':actual.get(k)} for k,(p,q) in keyed.items() if actual.get(k,0)!=q]
  print(json.dumps({'section':'WB_stocks_readback','warehouse':bind.wb_warehouse_id,'affected_products':len(products),'published_products_checked':len(keyed),'expected_sum':sum(q for p,q in keyed.values()),'wb_sum':sum(actual.values()),'mismatches':mismatches},ensure_ascii=False))
  queries={
   'stock':"SELECT sum(b.quantity) AS seller_stock,sum(b.quantity) FILTER (WHERE l.code='__SORTING__') AS sorting_stock,sum(greatest(b.quantity,0)) FILTER (WHERE l.code='__SORTING__') AS sorting_positive FROM inventory_balances b JOIN products p ON p.id=b.product_id JOIN storage_locations l ON l.id=b.storage_location_id WHERE p.seller_id='68dd641b-c5cc-4e0a-8057-015eca180d0e'",
   'ledger':"SELECT su.wb_supply_id,count(*) AS ledger_count,sum(m.quantity_delta) AS stock_delta FROM fbs_shipment_reversal_ledger le JOIN fbs_orders o ON o.id=le.fbs_order_id JOIN fbs_supplies su ON su.id=o.supply_id JOIN inventory_movements m ON m.id=le.shipment_movement_id WHERE su.wb_supply_id IN ('WB-GI-285910955','WB-GI-285911018') GROUP BY 1"
  }
  for k,q in queries.items(): print(json.dumps({k:[dict(x) for x in (await s.execute(text(q))).mappings()]},default=str))
  await s.rollback()
asyncio.run(main())
