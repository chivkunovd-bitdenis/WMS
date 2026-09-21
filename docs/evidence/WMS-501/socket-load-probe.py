"""Bounded real-socket mixed load against loopback audit API only, never production."""
import asyncio, collections, json, time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[3]
FIX=json.loads((ROOT/'.audit-runtime/load-fixtures.json').read_text())
BASE='http://127.0.0.1:18452'
def stats(rows):
    values=sorted(r['ms'] for r in rows)
    return {'requests':len(rows),'statuses':dict(collections.Counter(str(r['status']) for r in rows)),
            **({f'p{p}_ms':round(values[min(len(values)-1,int(len(values)*p/100))],2) for p in [50,95,99]} if values else {}),
            'max_ms':round(max(values),2) if values else None}
async def scenario(client,name,users,mode,duration=15,full_catalog=False,barcode_only=False):
    rows=[];stop=time.perf_counter()+duration;start=time.perf_counter()
    async def request(kind,method,path,fixture,body=None):
        t=time.perf_counter()
        try:
            r=await client.request(method,path,headers={'Authorization':'Bearer '+fixture['token']},json=body)
            status=r.status_code
            error=r.text[:180] if status>=400 else None
        except httpx.HTTPError as e:
            status=type(e).__name__;error=str(e)
        rows.append({'kind':kind,'ms':(time.perf_counter()-t)*1000,'status':status,**({'error':error} if error else {})})
    async def operator(i):
        f=FIX[0 if mode=='shared' else i%len(FIX)]
        doc=f['docs'][0 if mode=='shared' else (i//len(FIX))%10]
        step=i%5
        while time.perf_counter()<stop:
            if step%5<3:
                body={'barcode':f['barcode']}
                if not barcode_only:
                    body['product_id']=f['product_id']
                await request('scan_write','POST',f"/operations/inbound-intake-requests/{doc['id']}/receiving/scan",f,body)
            elif step%5==3:
                await request('scan_resolve','GET','/operations/scan/resolve?code='+f['barcode'],f)
            else:
                await request('catalog_page','GET','/products/ff-catalog-page?limit=100',f)
            step+=1
            await asyncio.sleep(0.2)
    async def interference():
        while time.perf_counter()<stop:
            await request('full_catalog','GET','/products',FIX[0])
            await asyncio.sleep(2)
    await asyncio.gather(*(operator(i) for i in range(users)),*([interference()] if full_catalog else []))
    elapsed=time.perf_counter()-start
    return {'name':name,'operators':users,'mode':mode,'requested_duration_s':duration,'elapsed_s':round(elapsed,2),'requests_per_s':round(len(rows)/elapsed,2),'all':stats(rows),
            'by_kind':{k:stats([r for r in rows if r['kind']==k]) for k in sorted(set(r['kind'] for r in rows))},'errors':[r for r in rows if r['status']!=200][:20]}
async def main():
    out={'method':'Single uvicorn process, actual loopback HTTP sockets, real PostgreSQL, synthetic 27275 products across 13 tenants (largest24875), 130 docs, 200ms think time. Native macOS hardware; not a production capacity certification. Closed-loop workers reduce offered load under delay; each tier15s, not a soak test. Scans60%, resolver20%, page20%.','scenarios':[]}
    async with httpx.AsyncClient(base_url=BASE,timeout=35,limits=httpx.Limits(max_connections=150,max_keepalive_connections=150)) as c:
        for name,users,mode,full in [('single',1,'multi',False),('multi10',10,'multi',False),('multi25',25,'multi',False),('multi50',50,'multi',False),('multi100',100,'multi',False),('shared25',25,'shared',False),('multi25_catalog',25,'multi',True)]:
            result=await scenario(c,name,users,mode,full_catalog=full)
            out['scenarios'].append(result)
            (ROOT/'docs/evidence/WMS-501/socket-load-results.json').write_text(json.dumps(out,indent=2)+'\n')
            print(json.dumps(result),flush=True)
    print('Successful scan writes',sum(s['by_kind']['scan_write']['statuses'].get('200',0) for s in out['scenarios']))
if __name__=='__main__':
    asyncio.run(main())
