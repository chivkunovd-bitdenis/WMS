"""Read back durable synthetic counts; append a 500-line barcode-only shared-document probe."""
import asyncio, importlib.util, json, os, uuid
from pathlib import Path
assert os.environ.get('DATABASE_URL') == 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_load2'
from sqlalchemy import select,func
from app.db.session import SessionLocal,engine
from app.models.inbound_intake import InboundIntakeLine,InboundIntakeRequest
from app.models.product import Product
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('load_probe',Path(__file__).with_name('socket-load-probe.py'))
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
async def main():
    ids=[uuid.UUID(d['id']) for f in probe.FIX for d in f['docs']]
    async def count():
        async with SessionLocal() as s:
            return int(await s.scalar(select(func.sum(InboundIntakeLine.actual_qty)).where(InboundIntakeLine.request_id.in_(ids))) or 0)
    primary=json.loads((ROOT/'docs/evidence/WMS-501/socket-load-results.json').read_text())
    expected=sum(s['by_kind']['scan_write']['statuses'].get('200',0) for s in primary['scenarios'])
    before=await count()
    out={'primary_successful_scan_posts':expected,'primary_durable_sum_actual_qty':before,'primary_equal':before==expected,'initial_all_actual_qty':0,'documents_checked':len(ids),'limitation':'Aggregate quantity equality only; no per-attempt idempotency contract or per-document event matching.'}
    async with SessionLocal() as s:
        rid=uuid.UUID(probe.FIX[0]['docs'][0]['id'])
        tid=await s.scalar(select(InboundIntakeRequest.tenant_id).where(InboundIntakeRequest.id==rid))
        pids=(await s.scalars(select(Product.id).where(Product.tenant_id==tid,Product.id!=uuid.UUID(probe.FIX[0]['product_id'])).limit(499))).all()
        s.add_all([InboundIntakeLine(request_id=rid,product_id=p,expected_qty=10,actual_qty=0) for p in pids])
        await s.commit()
    async with probe.httpx.AsyncClient(base_url=probe.BASE,timeout=35,limits=probe.httpx.Limits(max_connections=150,max_keepalive_connections=150)) as c:
        out['supplement']=await probe.scenario(c,'barcode_only_500lines_shared25',25,'shared',barcode_only=True)
    after=await count()
    out['supplement_durable_increment']=after-before
    out['supplement_successful_scan_posts']=out['supplement']['by_kind']['scan_write']['statuses'].get('200',0)
    out['supplement_equal']=out['supplement_durable_increment']==out['supplement_successful_scan_posts']
    (ROOT/'docs/evidence/WMS-501/socket-load-readback.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2));await engine.dispose()
asyncio.run(main())
