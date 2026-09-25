import asyncio,json
from itertools import permutations
from wms444_c20_review import sf,engine,fixture,snap,collect,boxes,pkg,MarketplaceUnloadBoxLine,MarketplaceUnloadPickAllocation

def stock(kind,quantity):
    return (quantity,0) if kind=='unpacked' else (0,quantity) if kind=='packed' else (0,0)

async def main():
    outcomes=[]
    for boxed_class,unboxed_class in permutations(['packed','unpacked','unknown'],2):
        async with sf() as s:
            t,w,a,p,r,task,b,line,locs=await fixture(s,[stock(boxed_class,2),stock(unboxed_class,2)],total=4)
            if boxed_class=='unknown':
                s.add_all([MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=2),MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
                line.qty_confirmed_packed=1;line.qty_packed_in_task=1;await s.commit()
            else:
                await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2,actor_user_id=a.id)
            if unboxed_class=='unknown':
                s.add(MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[1].id,quantity=2));await s.commit()
            else:
                await collect.record_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[1].id,quantity=2,actor_user_id=a.id)
            before=await snap(s,t,task,p,r)
            await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=0,actor_user_id=a.id)
            after=await snap(s,t,task,p,r)
            assert after['boxes']==[0,0,0] and after['total']==0,after
            assert after['alloc']==[2,2 if unboxed_class=='packed' else 0],after
            assert after['balance']==[2,2 if boxed_class=='packed' else 0],after
            assert after['movements']==before['movements']+1 and after['ledger']==0,after
            # Absolute retry does not reverse stock again or revive a historical result.
            await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=0,actor_user_id=a.id)
            assert await snap(s,t,task,p,r)==after
            outcomes.append({'removed_boxed':boxed_class,'kept_unboxed':unboxed_class,'pass':True})
    print(json.dumps({'case':'all-six-source-class-crossovers','outcomes':outcomes}))
    # Covered partial composition stays unchanged for each source class.
    outcomes=[]
    for kind in ['packed','unpacked','unknown']:
        async with sf() as s:
            t,w,a,p,r,task,b,line,locs=await fixture(s,[stock(kind,2)],total=2)
            if kind=='unknown':
                s.add_all([MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=1),MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2)])
                line.qty_confirmed_packed=1;line.qty_packed_in_task=0;await s.commit()
            else:
                await collect.record_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2,actor_user_id=a.id)
                await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=a.id)
            before=await snap(s,t,task,p,r)
            await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=1,actor_user_id=a.id)
            after=await snap(s,t,task,p,r)
            assert after['boxes']==before['boxes'] and after['boxes'][0]==1,after
            assert after['balance']==[1,1 if kind=='packed' else 0],after
            assert after['movements']==before['movements']+1 and after['ledger']==0
            outcomes.append({'class':kind,'boxes':after['boxes'],'ready':after['confirmed'],'work':after['work']})
    print(json.dumps({'case':'covered-partial-each-source-class','outcomes':outcomes}))
    # Removing known-unpacked from a mixed box must restore only old work baseline.
    async with sf() as s:
        t,w,a,p,r,task,b,line,locs=await fixture(s,[(2,0),(0,0)],total=3)
        s.add_all([MarketplaceUnloadBoxLine(box_id=b.id,product_id=p.id,quantity=1),MarketplaceUnloadPickAllocation(request_id=r.id,product_id=p.id,storage_location_id=locs[1].id,quantity=1)])
        line.qty_packed_in_task=1;await s.commit()
        await boxes.add_manual_qty_to_box(s,t.id,b.id,product_id=p.id,storage_location_id=locs[0].id,quantity=2,actor_user_id=a.id)
        await collect.set_pick_allocation(s,t.id,r.id,product_id=p.id,storage_location_id=locs[0].id,quantity=0,actor_user_id=a.id)
        after=await snap(s,t,task,p,r)
        assert after['boxes']==[1,0,0] and after['confirmed']==0 and after['work']==1,after
        complete=await pkg.complete_task(s,t.id,task.id,acting_user_id=a.id)
        assert complete.billing_units_packed==1 and complete.billing_earned_kopecks==700
        print(json.dumps({'case':'restore-only-historical-work','after':after,'earned':complete.billing_earned_kopecks}))
    await engine.dispose()

asyncio.run(main())
