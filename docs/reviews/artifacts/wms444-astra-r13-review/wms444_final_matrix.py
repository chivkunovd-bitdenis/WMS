import asyncio,json,sys
from pathlib import Path
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
sys.path.insert(0,str(Path('docs/reviews/artifacts/wms444-astra-review').resolve()))
from wms444_astra_review import Base,fixture,snapshot,collect,boxes,pkg,MarketplaceUnloadBoxLine,MarketplaceUnloadPickAllocation,InventoryBalance
from app.models.billing import BillingLedgerEntry
from app.services import marketplace_unload_service as unload
URL='postgresql+psycopg_async://deniscivkunov@localhost:5432/wms444_astra_final_20260913'
engine=create_async_engine(URL);sf=async_sessionmaker(engine,expire_on_commit=False)

async def setup(s,ready=1,work=1,fresh=1,packed=0):
    t,w,a,p,r,task,b,line,locs=await fixture(s,[(fresh,packed)],total=2+fresh+packed)
    bl=MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=2)
    s.add_all([bl,MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
    line.qty_confirmed_packed=ready;line.qty_packed_in_task=work;await s.commit()
    if fresh+packed:
        await collect.collect_into_box(s,t.id,r.id,box_id=b.id,storage_location_id=locs[0].id,product_id=p.id,quantity=fresh+packed,actor_user_id=a.id)
        await s.commit()
    return t,w,a,p,r,task,b,line,locs,bl

async def snap(s,t,task,p,r):
    row=await snapshot(s,t,task,p,r)
    loaded=await pkg.get_task(s,t.id,task.id)
    row['baseline']=[loaded.lines[0].qty_legacy_confirmed_packed,loaded.lines[0].qty_legacy_packed_in_task]
    row['ledger']=await s.scalar(select(func.count()).select_from(BillingLedgerEntry).where(BillingLedgerEntry.tenant_id==t.id))
    return row

async def main():
    async with engine.begin() as c:
        assert (await c.execute(select(func.current_database()))).scalar_one()=='wms444_astra_final_20260913'
        await c.run_sync(Base.metadata.create_all)
    passed=0
    for ready in [0,1,2]:
        for fresh,packed in [(0,0),(1,0),(0,1)]:
            for steps in [[1,1],[2]]:
                async with sf() as s:
                    t,w,a,p,r,task,b,line,locs,bl=await setup(s,ready,2-ready,fresh,packed)
                    remaining=2
                    for qty in steps:
                        await collect.remove_from_box(s,t.id,r.id,box_id=b.id,line_id=bl.id,quantity=qty,actor_user_id=a.id)
                        remaining-=qty
                        state=await snap(s,t,task,p,r)
                        expected=[min(ready,remaining)+packed,remaining-min(ready,remaining)+fresh]
                        assert [state['confirmed'],state['work']]==expected,(ready,fresh,packed,steps,state,expected)
                        assert state['ledger']==0
                    # New unpacked pick from returned stock must not revive old ready.
                    await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=a.id)
                    state=await snap(s,t,task,p,r)
                    assert [state['confirmed'],state['work']]==[packed,fresh+1],state
                    completed=await pkg.complete_task(s,t.id,task.id,acting_user_id=a.id)
                    assert completed.billing_units_packed==fresh+1 and completed.billing_earned_kopecks==(fresh+1)*700
                    await pkg.complete_task(s,t.id,task.id,acting_user_id=a.id)
                    await unload.cancel_request(s,t.id,r.id,performer_id=a.id)
                    state=await snap(s,t,task,p,r)
                    assert state['alloc']==[0,0] and state['balance']==[2+fresh+packed,packed] and state['ledger']==0,state
                    passed+=1
    print(json.dumps({'case':'ready-first-delete-recollect-cancel-matrix','passed':passed,'initial_ready':[0,1,2],'fresh':['none','unpacked1','packed1'],'delete':['1+1','2'],'staff_rate':700,'seller_ledger':0}))
    # S2: old pre-pick transfers without manufacturing source knowledge.
    async with sf() as s:
        t,w,a,p,r,task,b,line,locs=await fixture(s,[(0,0)],total=3)
        alloc=MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3)
        s.add(alloc);await s.commit()
        bl=await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3,actor_user_id=a.id)
        assert bl.quantity_source_known==0 and bl.quantity_packed==0
        await collect.remove_from_box(s,t.id,r.id,box_id=b.id,line_id=bl.id,quantity=3,actor_user_id=a.id)
        state=await snap(s,t,task,p,r)
        assert state['alloc']==[0,0] and state['balance']==[3,0] and state['total']==0,state
        print(json.dumps({'case':'S2-historical-prepick-place-remove','state':state}))
    # Existing absolute pick/set is the other quantity-edit route.
    async with sf() as s:
        t,w,a,p,r,task,b,line,locs,bl=await setup(s)
        before=await snap(s,t,task,p,r)
        await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2,actor_user_id=a.id)
        partial=await snap(s,t,task,p,r)
        await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=0,actor_user_id=a.id)
        zero=await snap(s,t,task,p,r)
        print(json.dumps({'case':'absolute-pick-set-partial-zero','before':before,'partial':partial,'zero':zero}))
    await engine.dispose()

if __name__=='__main__':
    asyncio.run(main())
