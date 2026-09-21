"""Synthetic authenticated local API timing; no external service or production data."""
import asyncio
import json
import os
from pathlib import Path
import time
import uuid
ROOT=Path(__file__).resolve().parents[3]
os.environ['DATABASE_URL']='postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_api'
os.environ['JWT_SECRET_KEY']='synthetic-audit-only-not-a-real-secret-501'
os.environ['WMS_DATA_DIR']=str(ROOT/'.audit-runtime/api-data')
os.environ['CELERY_BROKER_URL']='memory://'
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from app.db.session import engine,SessionLocal
from app.models import Base
from app.models.tenant import Tenant
from app.models.seller import Seller
from app.models.product import Product
from app.models.user import User
from app.main import create_app
from app.services.tokens import create_access_token
from app.services.passwords import hash_password

async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    tokens=[]
    ph=hash_password('synthetic-audit-account')
    for n,size in enumerate([10000]+[1000]*9):
        tid,sid,uid=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
        async with SessionLocal() as s:
            s.add(Tenant(id=tid,name=f'Audit {n}',slug=f'audit-{tid}'))
            await s.flush()
            s.add(Seller(id=sid,tenant_id=tid,name=f'Audit seller {n}'))
            s.add(User(id=uid,tenant_id=tid,email=f'{uid}@example.invalid',role='fulfillment_admin',password_hash=ph))
            await s.flush()
            await s.execute(Product.__table__.insert(),[
                {'id':uuid.uuid4(),'tenant_id':tid,'seller_id':sid,'name':f'Product {i}',
                 'sku_code':f'T{n}-{i:08d}','wb_barcode':f'{n:03d}{i:010d}'} for i in range(size)])
            await s.commit()
        tokens.append(create_access_token(user_id=uid,tenant_id=tid,role='fulfillment_admin',seller_id=None))
    out={'baseline':'3e125074','method':'ASGITransport with real JWT+DB; 10 tenants, 19000 products. No socket/browser/TLS. ORM schema, no migrations. Single run per scenario.'}
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://audit') as client:
        async def req(path,index):
            start=time.perf_counter()
            r=await client.get(path,headers={'Authorization':'Bearer '+tokens[index]})
            return {'status':r.status_code,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'bytes':len(r.content)}
        for path in ['/products','/products/ff-catalog','/products/ff-catalog-page?limit=100','/auth/me']:
            await req(path,0) # warm-up
            out[f'10000_products_single:{path}']=await req(path,0)
        out['same_account_5_concurrent_products']=await asyncio.gather(*(req('/products',0) for _ in range(5)))
        out['10_tenants_concurrent_products']=await asyncio.gather(*(req('/products',i) for i in range(10)))
        out['same_account_5_concurrent_page']=await asyncio.gather(*(req('/products/ff-catalog-page?limit=100',0) for _ in range(5)))
    (ROOT/'docs/evidence/WMS-501/api-performance-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    await engine.dispose()
asyncio.run(main())
