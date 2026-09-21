"""Synthetic fixtures only; refuses any database other than this disposable audit DB."""
import asyncio, json, os, uuid
from pathlib import Path
assert os.environ.get('DATABASE_URL') == 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_load2'
from app.models import Base
from app.db.session import engine, SessionLocal
from app.models.tenant import Tenant
from app.models.seller import Seller
from app.models.user import User
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.inbound_intake import InboundIntakeRequest, InboundIntakeLine
from app.services.tokens import create_access_token
from app.services.passwords import hash_password
ROOT=Path(__file__).resolve().parents[3]
async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    fixtures=[]
    password_hash=hash_password('Synthetic-audit-501')
    for n,size in enumerate([24875]+[200]*12):
        tid,sid,uid,wid=uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
        pids=[uuid.uuid4() for _ in range(size)]
        async with SessionLocal() as s:
            s.add(Tenant(id=tid,name=f'Load tenant {n}',slug=f'load-{tid}'))
            await s.flush()
            s.add(Seller(id=sid,tenant_id=tid,name=f'Load seller {n}'))
            s.add(User(id=uid,tenant_id=tid,email=f'load{n}@example.invalid',password_hash=password_hash,role='fulfillment_admin'))
            s.add(Warehouse(id=wid,tenant_id=tid,name='Load warehouse',code=f'L{n}'))
            await s.flush()
            for start in range(0,size,1000):
                await s.execute(Product.__table__.insert(),[
                    {'id':pids[i],'tenant_id':tid,'seller_id':sid,'name':f'Load product {i}','sku_code':f'L{n}-{i:08d}','wb_barcode':f'{n:03d}{i:010d}'}
                    for i in range(start,min(start+1000,size))])
            docs=[]
            for _ in range(10):
                rid,lid=uuid.uuid4(),uuid.uuid4()
                s.add(InboundIntakeRequest(id=rid,tenant_id=tid,warehouse_id=wid,seller_id=sid,status='receiving',planned_box_count=1))
                await s.flush()
                s.add(InboundIntakeLine(id=lid,request_id=rid,product_id=pids[0],expected_qty=100000,actual_qty=0))
                docs.append({'id':str(rid),'line_id':str(lid)})
            await s.commit()
            fixtures.append({'token':create_access_token(user_id=uid,tenant_id=tid,role='fulfillment_admin',seller_id=None),'product_id':str(pids[0]),'barcode':f'{n:03d}{0:010d}','docs':docs})
    (ROOT/'.audit-runtime/load-fixtures.json').write_text(json.dumps(fixtures))
    await engine.dispose()
    print('Seeded 13 tenants, 27275 products, 13 users, 130 receiving documents; credentials kept only in ignored runtime.')
asyncio.run(main())
