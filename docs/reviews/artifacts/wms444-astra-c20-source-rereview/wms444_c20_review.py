import asyncio,json,sys
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
sys.path.insert(0,str(Path('docs/reviews/artifacts/wms444-astra-review').resolve()))
from wms444_astra_review import Base,fixture,snapshot,collect,boxes,pkg,MarketplaceUnloadBoxLine,MarketplaceUnloadPickAllocation,InventoryBalance
from app.models.billing import BillingLedgerEntry
from app.models.inventory_movement import InventoryMovement
URL='postgresql+psycopg_async://deniscivkunov@localhost:5432/wms444_astra_c20_final_20260913'
engine=create_async_engine(URL);sf=async_sessionmaker(engine,expire_on_commit=False)

async def snap(s,t,task,p,r):
    state=await snapshot(s,t,task,p,r)
    state['boxes']=list((await s.execute(select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity),0),func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity_packed),0),func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity_source_known),0)).where(MarketplaceUnloadBoxLine.product_id==p.id))).one())
    state['movements']=await s.scalar(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.product_id==p.id))
    state['ledger']=await s.scalar(select(func.count()).select_from(BillingLedgerEntry).where(BillingLedgerEntry.tenant_id==t.id))
    return state

async def main():
    async with engine.begin() as c:
        assert (await c.execute(select(func.current_database()))).scalar_one()=='wms444_astra_c20_final_20260913'
        await c.run_sync(Base.metadata.create_all)
    # Original P1, including retry and billing after a fresh recollection.
    async with sf() as s:
        t,w,a,p,r,task,b,line,locs=await fixture(s,[(1,0)],total=3)
        s.add_all([MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=2),MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
        line.qty_confirmed_packed=1;line.qty_packed_in_task=1;await s.commit()
        await collect.collect_into_box(s,t.id,r.id,box_id=b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=a.id);await s.commit()
        stages=[]
        for qty in [2,0,0]:
            await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=qty,actor_user_id=a.id)
            stages.append(await snap(s,t,task,p,r))
        assert [x['boxes'][0] for x in stages]==[2,0,0]
        assert [x['balance'][0] for x in stages]==[1,3,3]
        assert stages[1]==stages[2]
        await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=a.id)
        fresh=await snap(s,t,task,p,r)
        completed=await pkg.complete_task(s,t.id,task.id,acting_user_id=a.id)
        assert fresh['confirmed']==0 and fresh['work']==1 and completed.billing_earned_kopecks==700
        print(json.dumps({'case':'original-c20-repeat-recollect','stages':stages,'fresh':fresh,'earned':completed.billing_earned_kopecks}))
    # Deleting boxed ready source while another, unboxed, unpacked source remains.
    for other_unpacked,old_unknown in [(2,0),(1,1)]:
        async with sf() as s:
            t,w,a,p,r,task,b,line,locs=await fixture(s,[(0,2),(other_unpacked,0),(0,0)],total=2+other_unpacked+old_unknown)
            if old_unknown:
                s.add_all([MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=1),MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[2].id,quantity=1)])
                line.qty_confirmed_packed=1;line.qty_packed_in_task=0;await s.commit()
            await collect.collect_into_box(s,t.id,r.id,box_id=b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2,actor_user_id=a.id);await s.commit()
            await collect.record_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[1].id,quantity=other_unpacked,actor_user_id=a.id)
            before=await snap(s,t,task,p,r)
            ids=[SimpleNamespace(id=obj.id) for obj in [t,task,p,r]]
            try:
                await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=0,actor_user_id=a.id)
                result='ok'
            except Exception as exc:
                result=getattr(exc,'code',type(exc).__name__);await s.rollback()
            after=await snap(s,*ids)
            assert result=='ok' and after['boxes']==[old_unknown,0,0],after
            assert after['confirmed']==old_unknown and after['work']==0,after
            assert after['balance']==[2,2] and after['movements']==before['movements']+1,after
            assert after['ledger']==0
            print(json.dumps({'case':'remove-boxed-packed-keep-unboxed-unpacked','other_unpacked':other_unpacked,'historical':old_unknown,'before':before,'result':result,'after':after,'expected_boxes':[old_unknown,0,0]}))
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
