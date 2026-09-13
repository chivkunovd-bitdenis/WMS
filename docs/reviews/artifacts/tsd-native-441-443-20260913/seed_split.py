"""Fresh synthetic document and second owned employee for native split acceptance."""
import asyncio,json,os,uuid
from pathlib import Path
from sqlalchemy import select,text
from app.db.session import SessionLocal
from app.models.user import User
from app.services import inbound_intake_service as intake
from app.services.catalog_service import create_location
from app.services.passwords import hash_password
async def main():
 old=json.loads((Path(__file__).parents[1]/'tsd-final-package-20260913/native-fixture.json').read_text())
 async with SessionLocal() as db:
  assert await db.scalar(text('select current_database()'))=='wms_tsd_20260913'
  tenant=uuid.UUID(old['tenant_id']); wh=uuid.UUID(old['warehouse_id'])
  actor_b=User(tenant_id=tenant,email=None,full_name='Final Boris Split 5da311',job_title='Split operator B',role='fulfillment_admin',password_hash=hash_password(os.environ['WMS_SPLIT_PASSWORD']))
  db.add(actor_b);await db.flush()
  a=await create_location(db,tenant,wh,code='FINAL-SPLIT-A-5da311');b=await create_location(db,tenant,wh,code='FINAL-SPLIT-B-5da311')
  doc=await intake.create_request(db,tenant,warehouse_id=wh,seller_id=uuid.UUID(old['seller_id']))
  await intake.add_line(db,tenant,doc.id,product_id=uuid.UUID(old['product_id']),expected_qty=3)
  await intake.complete_receiving(db,tenant,doc.id,actor_user_id=uuid.UUID(old['user_id']))
  await db.commit()
  out={**old,'inbound_id':str(doc.id),'inbound_number':doc.document_number,'actor_a_id':old['user_id'],'actor_b_id':str(actor_b.id),'actor_b_name':actor_b.full_name,'cell_a_id':str(a.id),'cell_a_barcode':a.barcode,'cell_b_id':str(b.id),'cell_b_barcode':b.barcode}
  out.pop('orders',None);Path(__file__).with_name('fixture.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
asyncio.run(main())
