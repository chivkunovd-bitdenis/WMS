"""One fresh local final-review fixture; no real accounts or external calls."""
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta, date
from pathlib import Path
from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.models.seller import Seller
from app.models.billing import BillingTariffVersion
from app.models.fbs_order import FbsOrder
from app.services import inbound_intake_service as intake
from app.services.catalog_service import create_warehouse, create_location, create_product
from app.services.passwords import hash_password
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding, DEFAULT_WB_WAREHOUSE_ID

async def main():
    suffix=uuid.uuid4().hex[:6]
    async with SessionLocal() as db:
        assert await db.scalar(text('select current_database()'))=='wms_tsd_20260913'
        tenant=Tenant(name=f'Final review {suffix}',slug=f'final-review-{suffix}',billing_enabled_from=date(2020,1,1))
        db.add(tenant); await db.flush()
        actor=User(tenant_id=tenant.id,email=None,full_name=f'Final Astra {suffix}',job_title='Final review operator',role='fulfillment_admin',password_hash=hash_password(os.environ['WMS_FINAL_PASSWORD']))
        seller=Seller(tenant_id=tenant.id,name=f'Final seller {suffix}')
        db.add_all([actor,seller]); await db.flush()
        for code,rate in [('inbound',1000),('return',1200),('marketplace_outbound',2000),('packing',3000),('fbs_order',4000)]:
            db.add(BillingTariffVersion(tenant_id=tenant.id,service_code=code,unit='item',amount=rate,valid_from=date(2020,1,1)))
        wh=await create_warehouse(db,tenant.id,name=f'Final warehouse {suffix}',code=f'FINAL-{suffix}')
        cell=await create_location(db,tenant.id,wh.id,code=f'FINAL-CELL-{suffix}')
        product=await create_product(db,tenant.id,name=f'Final native item {suffix}',sku_code=f'FINAL-SKU-{suffix}',seller_id=seller.id,length_mm=10,width_mm=10,height_mm=10)
        doc=await intake.create_request(db,tenant.id,warehouse_id=wh.id,seller_id=seller.id)
        await intake.add_line(db,tenant.id,doc.id,product_id=product.id,expected_qty=3)
        doc=await intake.complete_receiving(db,tenant.id,doc.id,actor_user_id=actor.id)
        assert doc.status=='sorting'
        await seed_fbs_warehouse_binding(db,tenant_id=tenant.id,seller_id=seller.id,wms_warehouse_id=wh.id)
        orders=[]; now=datetime.now(UTC)
        for mi,market in enumerate(('wb','ozon')):
            for i,state in enumerate(('new','in_supply','assembling','packed','in_delivery','sorted','done','cancelled','defect','external_processing')):
                row=FbsOrder(tenant_id=tenant.id,seller_id=seller.id,warehouse_id=wh.id,product_id=product.id,marketplace=market,external_order_id=f'FINAL-{suffix}-{market}-{state}',wb_order_id=9440000+mi*100+i,wb_nm_id=1,wb_chrt_id=1,wb_barcode=f'FINAL-{suffix}',wb_article=f'{market}-{state}',wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,status=state,supplier_status='new' if state=='new' else 'awaiting_deliver',created_at_wb=now-timedelta(days=60+i),deadline_at=now-timedelta(days=1),mapping_status='mapped',reserve_status='no_stock')
                db.add(row); await db.flush(); orders.append({'id':str(row.id),'marketplace':market,'status':state,'wb_order_id':row.wb_order_id})
        await db.commit()
        manifest={'tenant_id':str(tenant.id),'organization':tenant.slug,'user_id':str(actor.id),'full_name':actor.full_name,'seller_id':str(seller.id),'warehouse_id':str(wh.id),'cell_id':str(cell.id),'cell_barcode':cell.barcode,'product_id':str(product.id),'inbound_id':str(doc.id),'inbound_number':doc.document_number,'expected_units':3,'expected_amount_kopecks':3000,'orders':orders}
        Path(__file__).with_name('native-fixture.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in manifest.items() if k!='orders'},ensure_ascii=False))

asyncio.run(main())
