"""Safe, synthetic WMS-501 probes. Only a fresh, dedicated local audit DB.
Run from backend with this checkout on PYTHONPATH. Never points at runtime .env.
"""
import asyncio
import json
import os
from pathlib import Path
import statistics
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
os.environ['DATABASE_URL'] = 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_parent'
os.environ['JWT_SECRET_KEY'] = 'synthetic-audit-only-not-a-real-secret-501'
os.environ['WMS_DATA_DIR'] = str(ROOT / '.audit-runtime/parent-data')
os.environ['CELERY_BROKER_URL'] = 'memory://'
from sqlalchemy import event, text
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.tenant import Tenant
from app.models.seller import Seller
from app.models.product import Product
from app.services.catalog_service import list_products
from app.services.auth_service import login, AuthError


def stats(values):
    values = sorted(values)
    return {'n': len(values), 'median_ms': round(statistics.median(values), 2),
            'p95_ms': round(values[max(0, int(len(values)*.95)-1)], 2),
            'max_ms': round(max(values), 2)}


async def heartbeat_during(fn):
    gaps = []
    done = False
    async def heartbeat():
        while not done:
            start = time.perf_counter()
            await asyncio.sleep(.005)
            gaps.append((time.perf_counter()-start)*1000)
    task = asyncio.create_task(heartbeat())
    await asyncio.sleep(.015)
    start = time.perf_counter()
    result = await fn()
    duration = (time.perf_counter()-start)*1000
    await asyncio.sleep(.015)
    done = True
    await task
    return {'elapsed_ms': round(duration,2), 'heartbeat_gap': stats(gaps), 'result':result}


async def main():
    out = {'baseline':'3e125074d5cb4c38e9107f864c3075f4f1f224cd',
           'method':'synthetic local PostgreSQL; ORM metadata schema; NOT production capacity or browser timing'}
    async with engine.begin() as conn:
        # Fresh dedicated DB: create only, never drop existing schemas.
        await conn.run_sync(Base.metadata.create_all)
        out['postgres'] = await conn.scalar(text('select version()'))
    out['pool'] = {'size':engine.pool.size(), 'max_overflow':engine.pool._max_overflow,
                   'timeout_s':engine.pool.timeout()}
    for n in [1, 15, 30, 60]:
        async def query():
            start=time.perf_counter()
            async with SessionLocal() as s:
                await s.execute(text('select pg_sleep(0.05)'))
            return (time.perf_counter()-start)*1000
        out[f'pool_concurrent_{n}_50ms_query'] = stats(await asyncio.gather(*(query() for _ in range(n))))
    # Exact starvation reproduction: occupy all connections, then submit fast SELECT 1.
    held = [await engine.connect() for _ in range(15)]
    async def release():
        await asyncio.sleep(.5)
        await asyncio.gather(*(c.close() for c in held))
    release_task=asyncio.create_task(release())
    start=time.perf_counter()
    async with SessionLocal() as s:
        await s.execute(text('select 1'))
    out['select1_behind_15_held_connections_ms']=round((time.perf_counter()-start)*1000,2)
    await release_task
    for n in [1,5]:
        async def attempt():
            async with SessionLocal() as s:
                try:
                    await login(s,email='nonexistent-501@example.invalid',password='synthetic-invalid')
                except AuthError:
                    return 'invalid_credentials'
        out[f'login_{n}_concurrent_eventloop'] = await heartbeat_during(
            lambda: asyncio.gather(*(attempt() for _ in range(n))))
    tid, sid = uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as s:
        s.add(Tenant(id=tid,name='Synthetic audit',slug='audit-'+str(tid)))
        await s.flush()
        s.add(Seller(id=sid,tenant_id=tid,name='Synthetic seller'))
        await s.commit()
    query_counts = []
    def count_query(*args): query_counts.append(1)
    event.listen(engine.sync_engine, 'before_cursor_execute', count_query)
    for size in [100, 1000, 10000]:
        async with SessionLocal() as s:
            current = int(await s.scalar(text('select count(*) from products where tenant_id=:tid'),{'tid':tid}))
            await s.execute(Product.__table__.insert(),[
                {'id':uuid.uuid4(),'tenant_id':tid,'seller_id':sid,
                 'name':f'Audit product {i}','sku_code':f'AUDIT-{i:08d}',
                 'wb_barcode':f'999{i:010d}'} for i in range(current,size)])
            await s.commit()
        for limit in [None,50]:
            for search in [None,'AUDIT-00009999']:
                query_counts.clear()
                async def read():
                    async with SessionLocal() as s:
                        rows = await list_products(s,tid,limit=limit,search=search)
                        return len(rows)
                sample = await heartbeat_during(read)
                sample['sql_count']=len(query_counts)
                out[f'catalog_{size}_limit_{limit}_search_{search}']=sample
    event.remove(engine.sync_engine, 'before_cursor_execute', count_query)
    output=ROOT/'docs/evidence/WMS-501/performance-results.json'
    output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(out,indent=2,ensure_ascii=False))
    await engine.dispose()

if __name__ == '__main__': asyncio.run(main())
