import asyncio,json
from wms444_final_matrix import sf,engine,setup,snap,collect,pkg

async def main():
    async with sf() as s:
        t,w,a,p,r,task,b,line,locs,bl=await setup(s)
        await collect.remove_from_box(s,t.id,r.id,box_id=b.id,line_id=bl.id,quantity=1,actor_user_id=a.id)
        first=await snap(s,t,task,p,r)
        repeated=await snap(s,t,task,p,r)
        done=await pkg.complete_task(s,t.id,task.id,acting_user_id=a.id)
        assert first==repeated
        assert [first['confirmed'],first['work'],first['baseline']]==[1,1,[1,0]]
        assert done.billing_units_packed==1 and done.billing_earned_kopecks==700 and done.completed_by_user_id==a.id
        print(json.dumps({'case':'C19-partial-complete','state':first,'repeat_read_equal':first==repeated,'units':done.billing_units_packed,'earned_kopecks':done.billing_earned_kopecks,'actor_ok':done.completed_by_user_id==a.id}))
    await engine.dispose()

asyncio.run(main())
