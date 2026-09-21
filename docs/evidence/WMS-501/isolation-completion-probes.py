"""Additional real-route resource-scope audit. Synthetic rows, no product edits."""
import os
assert os.environ.get('WMS_TEST_DATABASE_URL') == 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation2', 'Disposable audit DB required'
import hashlib,json,uuid
from datetime import UTC,datetime,timedelta
from pathlib import Path
import pytest
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Base
from app.models.inbound_intake import InboundIntakeRequest,InboundIntakeLine,InboundIntakeBox,InboundIntakeCargoPlace
from app.models.outbound_shipment import OutboundShipmentRequest,OutboundShipmentLine
from app.models.marketplace_unload import MarketplaceUnloadRequest,MarketplaceUnloadLine,MarketplaceUnloadBox
from app.models.packaging_task import PackagingTask,PackagingTaskLine
from app.models.inventory_count import InventoryCount,InventoryCountLine
from app.models.inventory_balance import InventoryBalance
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from test_wms488_catalog_isolation import _seed,_headers
OUT=Path(__file__).parent
I='/operations/inbound-intake-requests'
U='/operations/marketplace-unload-requests'
O='/operations/outbound-shipment-requests'
C='/operations/inventory-counts'
P='/operations/packaging-tasks'
F='/operations/fbs-supplies'

async def seed_resources():
    users,products,_=await _seed()
    result={}
    async with SessionLocal() as session:
        for key,prod in [('own',products['a']),('sibling',products['b']),('foreign',products['foreign'])]:
            wh=Warehouse(tenant_id=prod.tenant_id,name='Audit '+key,code=key)
            session.add(wh); await session.flush()
            loc=StorageLocation(tenant_id=prod.tenant_id,warehouse_id=wh.id,code='A',barcode='AUDIT-'+key)
            session.add(loc); await session.flush()
            inbound=InboundIntakeRequest(tenant_id=prod.tenant_id,warehouse_id=wh.id,seller_id=prod.seller_id,status='receiving')
            outbound=OutboundShipmentRequest(tenant_id=prod.tenant_id,warehouse_id=wh.id,seller_id=prod.seller_id,status='draft')
            unload=MarketplaceUnloadRequest(tenant_id=prod.tenant_id,warehouse_id=wh.id,seller_id=prod.seller_id,status='draft')
            pack=PackagingTask(tenant_id=prod.tenant_id,warehouse_id=wh.id,status='in_progress')
            count=InventoryCount(tenant_id=prod.tenant_id,warehouse_id=wh.id,seller_id=prod.seller_id,source='planned',created_by_user_id=users['admin'].id if key!='foreign' else users['foreign'].id)
            supply=FbsSupply(tenant_id=prod.tenant_id,warehouse_id=wh.id,seller_id=prod.seller_id,name='Audit '+key,delivery_type='warehouse',status='assembling')
            session.add_all([inbound,outbound,unload,pack,count,supply]); await session.flush()
            il=InboundIntakeLine(request_id=inbound.id,product_id=prod.id,expected_qty=10,actual_qty=5,storage_location_id=loc.id)
            box=InboundIntakeBox(tenant_id=prod.tenant_id,request_id=inbound.id,box_number=1,internal_barcode='BOX-'+key.upper())
            cargo=InboundIntakeCargoPlace(tenant_id=prod.tenant_id,request_id=inbound.id,place_number=1,internal_barcode='CARGO-'+key.upper())
            ol=OutboundShipmentLine(request_id=outbound.id,product_id=prod.id,quantity=2,storage_location_id=loc.id)
            ul=MarketplaceUnloadLine(request_id=unload.id,product_id=prod.id,quantity=2)
            ub=MarketplaceUnloadBox(request_id=unload.id,box_preset='60x40x40')
            pl=PackagingTaskLine(task_id=pack.id,product_id=prod.id,storage_location_id=loc.id,qty_total=10)
            cl=InventoryCountLine(count_id=count.id,product_id=prod.id,storage_location_id=loc.id,expected_quantity=10)
            order=FbsOrder(tenant_id=prod.tenant_id,seller_id=prod.seller_id,warehouse_id=wh.id,product_id=prod.id,
                supply_id=supply.id,wb_order_id=100+len(result),mapping_status='mapped',reserve_status='reserved',
                created_at_wb=datetime.now(UTC),deadline_at=datetime.now(UTC)+timedelta(days=1))
            balance=InventoryBalance(tenant_id=prod.tenant_id,product_id=prod.id,storage_location_id=loc.id,quantity=10,quantity_unpacked=10,quantity_packed=0)
            session.add_all([il,box,cargo,ol,ul,ub,pl,cl,order,balance]); await session.flush()
            result[key]={name:str(obj.id) for name,obj in dict(warehouse=wh,location=loc,product=prod,inbound=inbound,
                inbound_line=il,box=box,cargo=cargo,outbound=outbound,outbound_line=ol,unload=unload,
                unload_line=ul,unload_box=ub,pack=pack,pack_line=pl,count=count,count_line=cl,supply=supply,order=order,balance=balance).items()}
            result[key].update(seller=str(prod.seller_id),barcode=prod.wb_barcode)
        await session.commit()
    return users,result

async def snapshot():
    async with SessionLocal() as session:
        values={}
        for table in Base.metadata.sorted_tables:
            rows=(await session.execute(select(table))).all()
            serialized=sorted(json.dumps(dict(r._mapping),default=str,sort_keys=True) for r in rows)
            values[table.name]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(serialized).encode()).hexdigest()}
        return values

async def run_cases(client,headers,cases,name):
    before=await snapshot(); results=[]
    for label,method,path,body in cases:
        try:
            response=await client.request(method,path,headers=headers,json=body)
            data=response.json() if 'json' in response.headers.get('content-type','') else {}
            detail=data.get('detail') if isinstance(data,dict) else None
            results.append({'case':label,'method':method,'path':path,'status':response.status_code,'detail':detail})
        except Exception as exc:
            results.append({'case':label,'method':method,'path':path,'status':'exception','exception':type(exc).__name__,'message':str(exc)[:250]})
    after=await snapshot()
    changed=[key for key in before if before[key]!=after[key]]
    failures=[x for x in results if x['status'] not in (403,404,409,422)]
    invalid=[x for x in results if isinstance(x.get('detail'),list)]
    (OUT/f'isolation-completion-{name}.json').write_text(json.dumps({'cases':results,'changed_tables':changed,'unacceptable_responses':len(failures),'schema_validation_only':len(invalid)},ensure_ascii=False,indent=2)+'\n')
    assert not changed, changed
    assert not failures, failures
    assert not invalid, invalid

async def test_cross_tenant_root_mutations(async_client):
    users,allrows=await seed_resources(); d=allrows['foreign']; cases=[]
    def add(label,method,path,body=None): cases.append((label,method,path,body))
    ir=f"{I}/{d['inbound']}"; ur=f"{U}/{d['unload']}"; ou=f"{O}/{d['outbound']}"; pc=f"{P}/{d['pack']}"; co=f"{C}/{d['count']}"; fs=f"{F}/{d['supply']}"
    for root in [ir,ur,ou,pc,co,fs]: add('foreign root read','GET',root)
    for path in ['begin-receiving','boxes','cargo-places','complete-receiving','reopen-receiving','verify','submit','post','distribution-complete','distribution-reopen']:
        add('foreign receiving command','POST',ir+'/'+path,{} if path!='cargo-places' else {'quantity':1})
    add('foreign receiving scan','POST',ir+'/receiving/scan',{'barcode':d['barcode']})
    add('foreign receiving line','POST',ir+'/receiving/lines',{'product_id':d['product'],'actual_qty':1})
    add('foreign receiving distribution scan','POST',ir+'/distribution-scan',{'barcode':d['barcode']})
    add('foreign receiving planned edit','PATCH',ir,{'waybill_number':'AUDIT-MUTATION'})
    for endpoint in ['actual','defective','expected']:
        add('foreign receiving line edit','PATCH',ir+f"/lines/{d['inbound_line']}/{endpoint}",{endpoint+'_qty':1})
    add('foreign box','PATCH',ir+f"/boxes/{d['box']}/damaged",{'is_damaged':True})
    add('foreign inventory line batch','PUT',co+'/lines',{'lines':[{'line_id':d['count_line'],'actual_quantity':0}]})
    add('foreign inventory post','POST',co+'/post',{})
    add('foreign inventory cancel','DELETE',co)
    for suffix in ['submit','post']: add('foreign outbound command','POST',ou+'/'+suffix,{})
    add('foreign outbound delete line','DELETE',ou+f"/lines/{d['outbound_line']}")
    add('foreign outbound line location','PATCH',ou+f"/lines/{d['outbound_line']}",{'storage_location_id':d['location']})
    for suffix in ['plan','unplan','cancel','confirm','submit','ship']: add('foreign unload command','POST',ur+'/'+suffix,{})
    add('foreign unload batch','PUT',ur+'/lines',{'lines':[{'product_id':d['product'],'quantity':1}]})
    add('foreign unload box','POST',ur+f"/boxes/{d['unload_box']}/close",{})
    add('foreign unload delete line','DELETE',ur+f"/lines/{d['unload_line']}")
    add('foreign pack scan','POST',pc+'/scan',{'barcode':d['barcode']})
    for suffix in ['cancel','undo-last','complete']: add('foreign pack command','POST',pc+'/'+suffix,{})
    for suffix in ['confirm-packed','mark-prepacked','pack','product-label-printed']:
        add('foreign packaging line','POST',pc+f"/lines/{d['pack_line']}/{suffix}",{'quantity':1})
    for suffix in ['start-work','honest-sign-skip','delivery-preflight','deliver','sync-tracking','markings/sync']:
        add('foreign FBS command','POST',fs+'/'+suffix,{'idempotency_key':str(uuid.uuid4())})
    add('foreign FBS pick','POST',fs+'/pick/scan',{'barcode':d['barcode']})
    add('foreign FBS undo','POST',fs+f"/pick/{d['order']}/undo",{'idempotency_key':str(uuid.uuid4())})
    add('foreign FBS date','PATCH',fs+'/planned-shipment-date',{'planned_shipment_date':'2026-10-01'})
    add('foreign FBS order markings','GET',f"/operations/fbs-orders/{d['order']}/markings")
    add('foreign warehouse edit','PATCH',f"/warehouses/{d['warehouse']}",{'name':'AUDIT-MUTATION'})
    await run_cases(async_client,_headers(users['admin']),cases,'root-results')

async def test_own_parent_foreign_children_and_mixed_batches(async_client):
    users,rows=await seed_resources(); a=rows['own']; cases=[]
    for kind in ['sibling','foreign']:
        b=rows[kind]; ir=f"{I}/{a['inbound']}"; ur=f"{U}/{a['unload']}"; ou=f"{O}/{a['outbound']}"; pc=f"{P}/{a['pack']}"; co=f"{C}/{a['count']}"
        def add(label,method,path,body=None): cases.append((kind+': '+label,method,path,body))
        for endpoint in ['actual','defective','expected']:
            add('other-document line','PATCH',ir+f"/lines/{b['inbound_line']}/{endpoint}",{endpoint+'_qty':1})
        add('other-document box','PATCH',ir+f"/boxes/{b['box']}/damaged",{'is_damaged':True})
        add('other-document box label','POST',ir+f"/boxes/{b['box']}/mark-label-printed",{})
        add('other-document cargo label','POST',ir+f"/cargo-places/{b['cargo']}/mark-label-printed",{})
        add('other-document box scan','POST',ir+f"/boxes/{b['box']}/scan",{'barcode':a['barcode'],'product_id':a['product']})
        add('other-document cargo scan','POST',ir+f"/cargo-places/{b['cargo']}/scan",{'barcode':a['barcode'],'product_id':a['product']})
        add('other-document outbound line','DELETE',ou+f"/lines/{b['outbound_line']}")
        add('other-document outbound location','PATCH',ou+f"/lines/{b['outbound_line']}",{'storage_location_id':a['location']})
        add('other-document pack line','POST',pc+f"/lines/{b['pack_line']}/pack",{'quantity':1})
        add('mixed count lines','PUT',co+'/lines',{'lines':[{'line_id':a['count_line'],'actual_quantity':1},{'line_id':b['count_line'],'actual_quantity':9}]})
        add('other-document unload line','DELETE',ur+f"/lines/{b['unload_line']}")
        add('other-document unload box','POST',ur+f"/boxes/{b['unload_box']}/close",{})
    b=rows['foreign']
    for field in ['from_storage_location_id','to_storage_location_id','product_id']:
        body={'from_storage_location_id':a['location'],'to_storage_location_id':rows['sibling']['location'],'product_id':a['product'],'quantity':1}
        body[field]=b['product' if field=='product_id' else 'location']
        cases.append(('foreign stock transfer reference','POST','/operations/stock-transfer',body))
    cases.append(('foreign inventory create object','POST',C,{'source':'object','object':{'type':'product','id':b['product']}}))
    cases.append(('foreign inventory create warehouse','POST',C,{'source':'planned','filters':{'warehouse_id':b['warehouse'],'all':True}}))
    cases.append(('mixed unload product batch','PUT',f"{U}/{a['unload']}/lines",{'lines':[{'product_id':a['product'],'quantity':1},{'product_id':b['product'],'quantity':1}]}))
    await run_cases(async_client,_headers(users['admin']),cases,'nested-results')

async def test_owned_controls_and_package_lookup(async_client):
    users,rows=await seed_resources(); a=rows['own']; b=rows['foreign']; headers=_headers(users['admin'])
    results=[]
    for prefix,key in [(I,'inbound'),(U,'unload'),(O,'outbound'),(P,'pack'),(C,'count'),(F,'supply')]:
        response=await async_client.get(f'{prefix}/{a[key]}',headers=headers)
        results.append({'case':'owned '+key,'status':response.status_code})
        assert response.status_code==200,response.text
    response=await async_client.patch(f"{I}/{a['inbound']}/boxes/{a['box']}/damaged",headers=headers,json={'is_damaged':True})
    results.append({'case':'owned box mutation','status':response.status_code})
    assert response.status_code==200,response.text
    async with SessionLocal() as session:
        assert (await session.get(InboundIntakeBox,uuid.UUID(a['box']))).is_damaged is True
        assert (await session.get(InboundIntakeBox,uuid.UUID(b['box']))).is_damaged is False
    before=await snapshot()
    for barcode,expected in [('BOX-own',200),('BOX-foreign',404),('CARGO-foreign',404),('NONEXISTENT-AUDIT',404)]:
        response=await async_client.get('/operations/inbound-packages/lookup',params={'barcode':barcode},headers=headers)
        results.append({'case':'package '+barcode,'status':response.status_code})
        assert response.status_code==expected,response.text
    listed=await async_client.get('/operations/inbound-packages',headers=headers)
    assert listed.status_code==200,listed.text
    assert not {'BOX-FOREIGN','CARGO-FOREIGN'}.intersection(x['internal_barcode'] for x in listed.json())
    results.append({'case':'package list excludes foreign','status':listed.status_code})
    assert await snapshot()==before
    (OUT/'isolation-completion-controls-results.json').write_text(json.dumps(results,indent=2)+'\n')

async def test_tracking_same_marketplace_id_valid_postgres_parents(async_client,monkeypatch):
    """Replay existing regression with actual FK parents, no product monkeypatch."""
    import test_fbs_tracking_supply_done_rate_limit as original
    from app.models.tenant import Tenant
    from app.models.seller import Seller
    original_seed=original._seed_supply
    async def seed_valid_parents(**kwargs):
        async with SessionLocal() as session:
            tid=kwargs['tenant_id']; sid=kwargs['seller_id']; wid=kwargs['warehouse_id']
            session.add(Tenant(id=tid,name='Tracking audit',slug='audit-'+tid.hex)); await session.flush()
            session.add(Seller(id=sid,tenant_id=tid,name='Tracking audit')); await session.flush()
            session.add(Warehouse(id=wid,tenant_id=tid,name='Tracking audit',code='audit')); await session.commit()
        return await original_seed(**kwargs)
    monkeypatch.setattr(original,'_seed_supply',seed_valid_parents)
    await original.test_same_wb_supply_id_in_two_tenants_is_isolated(async_client,monkeypatch)

async def test_billing_composite_foreign_keys_postgres(async_client,monkeypatch):
    import test_billing_tariff_matrix as original
    monkeypatch.setenv('WMS_TARIFF_MATRIX_POSTGRES_URL',os.environ['WMS_TEST_DATABASE_URL'])
    await original.test_postgresql_composite_ledger_line_foreign_keys_reject_foreign_tenant()

async def test_billing_scope_constraints_postgres(async_client,monkeypatch):
    import test_billing_tariff_matrix as original
    monkeypatch.setenv('WMS_TARIFF_MATRIX_POSTGRES_URL',os.environ['WMS_TEST_DATABASE_URL'])
    await original.test_postgresql_v2_scope_check_rejects_invalid_direct_inserts()
