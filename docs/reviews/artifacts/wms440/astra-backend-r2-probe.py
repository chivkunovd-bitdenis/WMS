"""Independent WMS-440 re-review probes; asserts the observed states."""
import uuid
import pytest
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.inventory_movement import InventoryMovement
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services.tokens import decode_access_token
from tests.test_wms440_ff_intake import _setup, BASE

@pytest.mark.asyncio
async def test_new_completion_identity_in_sorting_is_not_saved(async_client, monkeypatch):
    h, wid, sid, pid = await _setup(async_client)
    rid = (await async_client.post(BASE, headers=h, json={'warehouse_id':wid,'seller_id':sid})).json()['id']
    await async_client.post(f'{BASE}/{rid}/lines', headers=h, json={'product_id':pid,'expected_qty':3})
    first = {'mutation_id':str(uuid.uuid4())}
    second = {'mutation_id':str(uuid.uuid4())}
    assert (await async_client.post(f'{BASE}/{rid}/complete-receiving',headers=h,json=first)).json()['status']=='sorting'
    async def unavailable_schedule(*args, **kwargs):
        raise RuntimeError('Synthetic marking scheduler unavailable')
    with monkeypatch.context() as patch:
        patch.setattr('app.services.inbound_marking_service.schedule_check', unavailable_schedule)
        assert (await async_client.post(f'{BASE}/{rid}/complete-receiving',headers=h,json=second)).json()['status']=='sorting'
    async with SessionLocal() as db:
        receipt = await db.scalar(select(DocumentEvent).where(DocumentEvent.idempotency_key=='inbound:complete:'+second['mutation_id']))
        assert receipt is None
    assert (await async_client.post(f'{BASE}/{rid}/reopen-receiving',headers=h)).json()['status']=='receiving'
    # The original committing identity is correctly recognized.
    assert (await async_client.post(f'{BASE}/{rid}/complete-receiving',headers=h,json=first)).json()['status']=='receiving'
    # But the other successful identity is lost and now re-posts.
    assert (await async_client.post(f'{BASE}/{rid}/complete-receiving',headers=h,json=second)).json()['status']=='sorting'
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta)))==3
    print('OBSERVED: first identity remains protected, second successful identity is absent; stale second retry posts 3')

@pytest.mark.asyncio
async def test_ozon_alias_scoping_and_ambiguous_container_scan(async_client):
    h, wid, sid, pid = await _setup(async_client)
    tenant=uuid.UUID(decode_access_token(h['Authorization'].split()[1])['tenant_id'])
    other_sid=(await async_client.post('/sellers',headers=h,json={'name':'other seller'})).json()['id']
    h2, _wid2, sid2, pid2=await _setup(async_client)
    tenant2=uuid.UUID(decode_access_token(h2['Authorization'].split()[1])['tenant_id'])
    async def product(owner, sku):
        response=await async_client.post('/products',headers=h,json={'name':sku,'sku_code':sku,'seller_id':owner,'length_mm':1,'width_mm':1,'height_mm':1})
        assert response.status_code==200,response.text
        return response.json()['id']
    pb=await product(sid,'review-r2-b')
    pc=await product(other_sid,'review-r2-c')
    code='OZN-REVIEW-R2-SHARED'
    async with SessionLocal() as db:
        for tid,owner,product_id in [(tenant,sid,pid),(tenant,sid,pb),(tenant,other_sid,pc),(tenant2,sid2,pid2)]:
            db.add(ProductMarketplaceLink(tenant_id=tid,seller_id=uuid.UUID(owner),product_id=uuid.UUID(product_id),marketplace='ozon',external_barcodes=[code]))
        await db.commit()
    rows=(await async_client.get('/products/linked-wb-catalog',headers=h,params={'seller_id':sid,'search':code})).json()
    assert {row['id'] for row in rows}=={pid,pb}
    assert all(code in row['marketplace_bindings'][0]['external_barcodes'] for row in rows)
    rid=(await async_client.post(BASE,headers=h,json={'warehouse_id':wid,'seller_id':sid})).json()['id']
    for product_id in [pid,pb]:
        assert (await async_client.post(f'{BASE}/{rid}/lines',headers=h,json={'product_id':product_id,'expected_qty':3})).status_code==201
    box=(await async_client.post(f'{BASE}/{rid}/boxes',headers=h,json={'quantity':1})).json()
    bid=box[0]['id'] if isinstance(box,list) else box['id']
    place=(await async_client.post(f'{BASE}/{rid}/cargo-places',headers=h,json={'quantity':1})).json()[0]['id']
    for kind, cid in [('boxes',bid),('cargo-places',place)]:
        result=await async_client.post(f'{BASE}/{rid}/{kind}/{cid}/scan',headers=h,json={'barcode':code,'mutation_id':str(uuid.uuid4())})
        assert result.status_code==200,result.text
        body=result.json()
        selected=body['product_id'] if 'product_id' in body else body['lines'][0]['product_id']
        assert selected in {pid,pb}
    print('OBSERVED: catalog correctly isolates owner/tenant; ambiguous code is silently accepted into box and cargo place')
