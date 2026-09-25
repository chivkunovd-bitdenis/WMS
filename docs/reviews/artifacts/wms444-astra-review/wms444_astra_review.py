"""Independent WMS-444 service probes. Only a dedicated disposable PG database."""
import asyncio
import json
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import Base
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.seller import Seller
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.inventory_balance import InventoryBalance
from app.models.user import User
from app.models.marketplace_unload import MarketplaceUnloadRequest, MarketplaceUnloadLine, MarketplaceUnloadBox, MarketplaceUnloadBoxLine, MarketplaceUnloadPickAllocation
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.services import marketplace_unload_collect_service as collect
from app.services import marketplace_unload_box_service as boxes
from app.services import packaging_task_service as pkg

URL = 'postgresql+psycopg_async://deniscivkunov@localhost:5432/wms444_astra_review_20260913'
engine = create_async_engine(URL)
sf = async_sessionmaker(engine, expire_on_commit=False)

async def fixture(s, sources, total=None):
    tag=uuid.uuid4().hex[:12]
    t=Tenant(name='Astra review',slug='review-'+tag);s.add(t);await s.flush()
    w=Warehouse(tenant_id=t.id,name=tag,code=tag)
    seller=Seller(tenant_id=t.id,name=tag)
    actor=User(tenant_id=t.id,email=tag+'@example.test',password_hash='synthetic-unused',role='fulfillment_staff',packaging_rate_kopecks=700)
    s.add_all([w,seller,actor]);await s.flush()
    p=Product(tenant_id=t.id,seller_id=seller.id,name=tag,sku_code=tag)
    req=MarketplaceUnloadRequest(tenant_id=t.id,warehouse_id=w.id,seller_id=seller.id,marketplace='wb',status='collecting')
    s.add_all([p,req]);await s.flush()
    locs=[]
    for i,(unpacked,packed) in enumerate(sources):
        loc=StorageLocation(tenant_id=t.id,warehouse_id=w.id,code=f'{tag}-{i}',barcode=f'{tag}-{i}')
        s.add(loc);await s.flush();locs.append(loc)
        s.add(InventoryBalance(tenant_id=t.id,product_id=p.id,storage_location_id=loc.id,quantity=unpacked+packed,quantity_unpacked=unpacked,quantity_packed=packed))
    amount=total if total is not None else sum(u+p for u,p in sources)
    s.add(MarketplaceUnloadLine(request_id=req.id,product_id=p.id,quantity=amount))
    task=PackagingTask(tenant_id=t.id,warehouse_id=w.id,marketplace_unload_request_id=req.id,status='draft')
    box=MarketplaceUnloadBox(request_id=req.id,box_preset='60_40_40');s.add_all([task,box]);await s.flush()
    line=PackagingTaskLine(task_id=task.id,product_id=p.id,storage_location_id=locs[0].id,qty_total=amount,qty_suggested_packed=3)
    s.add(line);await s.commit()
    return t,w,actor,p,req,task,box,line,locs

async def snapshot(s,t,task,p,req):
    task=await pkg.get_task(s,t.id,task.id)
    await pkg.sync_mp_task_packed_from_boxes(s,t.id,task);await s.commit()
    alloc=(await s.execute(select(func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity),0),func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity_packed),0)).where(MarketplaceUnloadPickAllocation.request_id==req.id))).one()
    bal=(await s.execute(select(func.coalesce(func.sum(InventoryBalance.quantity),0),func.coalesce(func.sum(InventoryBalance.quantity_packed),0)).where(InventoryBalance.product_id==p.id))).one()
    return {'confirmed':task.lines[0].qty_confirmed_packed,'work':task.lines[0].qty_packed_in_task,'total':pkg.qty_done(task.lines[0]),'alloc':list(alloc),'balance':list(bal)}

async def main():
    async with engine.begin() as c:
        # Dedicated database created by this reviewer, never shared fixtures.
        assert (await c.execute(select(func.current_database()))).scalar_one()=='wms444_astra_review_20260913'
        await c.run_sync(Base.metadata.drop_all);await c.run_sync(Base.metadata.create_all)
    for packed in [0,3,2]:
        async with sf() as s:
            t,w,actor,p,req,task,box,line,locs=await fixture(s,[(3-packed,packed),(0,3)],total=3)
            for _ in range(3):
                await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
            before=await snapshot(s,t,task,p,req)
            await pkg.confirm_line_packed_from_shelf(s,t.id,task.id,line.id)
            await pkg.confirm_line_packed_from_shelf(s,t.id,task.id,line.id)
            done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
            await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
            print(json.dumps({'case':'new-source','source_packed':packed,'state':before,'billing_units':done.billing_units_packed,'earned_kopecks':done.billing_earned_kopecks,'actor_ok':done.completed_by_user_id==actor.id}))
            assert before['confirmed']==packed and before['work']==3-packed
            assert done.billing_units_packed==3-packed and done.billing_earned_kopecks==(3-packed)*700
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,3)])
        # Historical persisted box/allocation after migration's default 0,
        # with legitimate previously confirmed ready quantity.
        s.add_all([MarketplaceUnloadBoxLine(box_id=box.id,product_id=p.id,quantity=3),MarketplaceUnloadPickAllocation(request_id=req.id,product_id=p.id,storage_location_id=locs[0].id,quantity=3)])
        line.qty_confirmed_packed=3;line.qty_packed_in_task=0;await s.commit()
        state=await snapshot(s,t,task,p,req)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=actor.id)
        print(json.dumps({'case':'historical-ready','before':{'confirmed':3,'work':0},'after':state,'earned_kopecks':done.billing_earned_kopecks}))
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,2),(1,0)])
        second=MarketplaceUnloadBox(request_id=req.id,box_preset='60_40_40');s.add(second);await s.commit()
        a=await collect.collect_into_box(s,t.id,req.id,box_id=box.id,storage_location_id=locs[0].id,product_id=p.id,quantity=2,actor_user_id=actor.id)
        b=await collect.collect_into_box(s,t.id,req.id,box_id=second.id,storage_location_id=locs[1].id,product_id=p.id,quantity=1,actor_user_id=actor.id)
        before=await snapshot(s,t,task,p,req)
        await collect.remove_from_box(s,t.id,req.id,box_id=second.id,line_id=b.box_line.id,quantity=1,actor_user_id=actor.id)
        removed=await snapshot(s,t,task,p,req)
        await boxes.add_manual_qty_to_box(s,t.id,second.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=actor.id)
        recollected=await snapshot(s,t,task,p,req)
        print(json.dumps({'case':'remove-unpacked-then-recollect','before':before,'removed':removed,'recollected':recollected}))
    async with sf() as s:
        t,w,actor,p,req,task,box,line,locs=await fixture(s,[(0,3)])
        task.marketplace_unload_request_id=None;await s.commit()
        result=await pkg.confirm_line_packed_from_shelf(s,t.id,task.id,line.id)
        print(json.dumps({'case':'standalone-confirm','confirmed':result.lines[0].qty_confirmed_packed}))
        assert result.lines[0].qty_confirmed_packed==3
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
