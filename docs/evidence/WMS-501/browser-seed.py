"""Create synthetic browser fixtures; exact dedicated DB only, resets only the exact disposable audit schema."""
import asyncio,json,os
from pathlib import Path
from sqlalchemy import select
assert os.environ.get('DATABASE_URL')=='postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_browser2'
from app.models import Base
from app.db.session import engine,SessionLocal
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.models.storage_location import StorageLocation
from app.models.marketplace_unload import MarketplaceUnloadRequest,MarketplaceUnloadLine
from app.services.auth_service import register_fulfillment
from app.services.catalog_service import create_product
from app.services import inbound_intake_service as svc
from app.services.tokens import create_access_token
ROOT=Path(__file__).resolve().parents[3]
async def main():
 async with engine.begin() as c:
  await c.run_sync(Base.metadata.drop_all)
  await c.run_sync(Base.metadata.create_all)
 async with SessionLocal() as s:
  user,tenant=await register_fulfillment(s,organization_name='WMS501 Browser Audit',slug='wms501-browser-audit',admin_email='wms501-browser@example.com',password='Wms501-test-only-123')
  wh=(await s.scalars(select(Warehouse).where(Warehouse.tenant_id==tenant.id))).one()
  seller=Seller(tenant_id=tenant.id,name='Browser Synthetic Seller');s.add(seller);await s.commit()
  prod=await create_product(s,tenant.id,name='AUDIT товар для сканирования',sku_code='50100001',seller_id=seller.id,length_mm=10,width_mm=10,height_mm=10)
  prod.wb_barcode='50100001'
  loc=StorageLocation(tenant_id=tenant.id,warehouse_id=wh.id,code='AUDIT-A01',barcode='50199901');s.add(loc);await s.commit()
  fixture={'tenant_id':str(tenant.id),'user_id':str(user.id),'seller_id':str(seller.id),'warehouse_id':str(wh.id),'product_id':str(prod.id),'barcode':'50100001','location_id':str(loc.id),'location_barcode':'50199901','login_email':user.email,'inbounds':{}}
  for label in ['rapid','close_queue','lost_response','sorting']:
   req=await svc.create_request(s,tenant.id,warehouse_id=wh.id,seller_id=seller.id,created_by_seller_id=seller.id)
   line=await svc.add_line(s,tenant.id,req.id,product_id=prod.id,expected_qty=20)
   await svc.patch_request_draft(s,tenant.id,req.id,planned_box_count=1,planned_box_count_set=True)
   await svc.submit_request(s,tenant.id,req.id)
   await svc.begin_receiving(s,tenant.id,req.id,actor_user_id=user.id)
   if label=='sorting':
    await svc.set_line_actual_qty(s,tenant.id,req.id,line.id,actual_qty=20)
    await svc.complete_receiving(s,tenant.id,req.id,actor_user_id=user.id)
   fixture['inbounds'][label]={'id':str(req.id),'line_id':str(line.id)}
  mp=MarketplaceUnloadRequest(tenant_id=tenant.id,warehouse_id=wh.id,seller_id=seller.id,status='draft',marketplace='wb',document_number='AUDIT-OUT-01',display_number='AUDIT-OUT-01')
  s.add(mp);await s.flush();line=MarketplaceUnloadLine(request_id=mp.id,product_id=prod.id,quantity=5);s.add(line);await s.commit()
  fixture['outbound']={'id':str(mp.id),'line_id':str(line.id)}
  (ROOT/'docs/evidence/WMS-501/browser-fixtures.json').write_text(json.dumps(fixture,indent=2)+'\n')
  (ROOT/'.audit-runtime/browser-token').write_text(create_access_token(user_id=user.id,tenant_id=tenant.id,role=user.role,seller_id=None))
 await engine.dispose()
 print(json.dumps(fixture,indent=2))
asyncio.run(main())
