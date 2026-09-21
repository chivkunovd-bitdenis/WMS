"""Read-only requests against synthetic wms501_api seeded by api_performance_probe.py."""
import asyncio,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
os.environ['DATABASE_URL']='postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_api'
os.environ['JWT_SECRET_KEY']='synthetic-audit-only-not-a-real-secret-501'
os.environ['WMS_DATA_DIR']=str(ROOT/'.audit-runtime/api-data')
os.environ['CELERY_BROKER_URL']='memory://'
from httpx import ASGITransport,AsyncClient
from sqlalchemy import select,event
from app.main import create_app
from app.db.session import SessionLocal,engine
from app.models.user import User
from app.models.tenant import Tenant
from app.services.tokens import create_access_token
from app.services.login_rate_limit import reset_rate_limit_state

async def main():
    async with SessionLocal() as s:
        u=(await s.scalars(select(User).join(Tenant,User.tenant_id==Tenant.id).where(Tenant.name=='Audit 0'))).one()
        token=create_access_token(user_id=u.id,tenant_id=u.tenant_id,role=u.role,seller_id=None)
    counts=[]
    def count(*args):counts.append(1)
    event.listen(engine.sync_engine,'before_cursor_execute',count)
    out={'baseline':'3e125074','method':'synthetic 10000-product tenant; ASGI JWT+PG; resolver only, no write/DOM/network/device; one burst per combination'}
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://audit') as c:
        async def scan():
            start=time.perf_counter()
            r=await c.get('/operations/scan/resolve',params={'code':'T0-00009999'},headers={'Authorization':'Bearer '+token})
            assert r.status_code==200,r.text
            return round((time.perf_counter()-start)*1000,2)
        await scan()
        counts.clear()
        out['single_scan_ms']=await scan()
        out['single_scan_sql_count']=len(counts)
        samples=[await scan() for _ in range(50)]
        out['50_sequential_scan_ms']={'p50':sorted(samples)[24],'p95':sorted(samples)[47],'max':max(samples)}
        out['20_concurrent_scan_ms']=await asyncio.gather(*(scan() for _ in range(20)))
        reset_rate_limit_state()
        async def login():
            r=await c.post('/auth/login',json={'email':'not-present-wms501@example.com','password':'synthetic-invalid'})
            assert r.status_code == 401, r.text
            return r.status_code
        mixed=await asyncio.gather(*(login() for _ in range(5)),scan())
        out['scan_with_5_concurrent_http_logins_ms']=mixed[-1]
        out['mixed_login_http_statuses']=mixed[:-1]
    event.remove(engine.sync_engine,'before_cursor_execute',count)
    (ROOT/'docs/evidence/WMS-501/scan-api-results.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
    await engine.dispose()
asyncio.run(main())
