"""Independent WMS-440 reviewer probes; assertions describe observed defects."""
import uuid
import pytest
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.inventory_movement import InventoryMovement
from app.services.tokens import decode_access_token
from tests.test_wms440_ff_intake import _setup, BASE

@pytest.mark.asyncio
async def test_external_ozon_barcode_is_exposed_but_draft_scans_cannot_resolve(async_client):
    h, wid, sid, pid = await _setup(async_client)
    tenant = uuid.UUID(decode_access_token(h['Authorization'].split()[1])['tenant_id'])
    barcode = '2000000440998'
    async with SessionLocal() as db:
        product = await db.get(Product, uuid.UUID(pid))
        product.wb_nm_id = 4400998
        db.add(ProductMarketplaceLink(tenant_id=tenant, seller_id=uuid.UUID(sid), product_id=uuid.UUID(pid), marketplace='ozon', external_product_id='4400998', external_sku='4400999', external_offer_id='review-ozon', external_barcodes=[barcode]))
        await db.commit()
    searched = (await async_client.get('/products/linked-wb-catalog', headers=h, params={'seller_id':sid, 'search':barcode})).json()
    assert searched == []
    catalog = (await async_client.get('/products/linked-wb-catalog', headers=h, params={'seller_id':sid})).json()
    assert len(catalog) == 1
    row = catalog[0]
    assert set(row['marketplaces']) == {'wb', 'ozon'}
    assert [binding['marketplace'] for binding in row['marketplace_bindings']] == ['ozon']
    assert barcode in row['marketplace_bindings'][0]['external_barcodes']
    # Exact field set read by Android InboundDraftViewModel.scan.
    native_matches = barcode in row['wb_barcodes'] or barcode in [row['wb_primary_barcode'], row['sku_code'], row['ozon_sku'], row['ozon_offer_id']]
    assert native_matches is False
    rid = (await async_client.post(BASE, headers=h, json={'warehouse_id':wid, 'seller_id':sid})).json()['id']
    assert (await async_client.post(f'{BASE}/{rid}/lines', headers=h, json={'product_id':pid,'expected_qty':3})).status_code == 201
    box = await async_client.post(f'{BASE}/{rid}/boxes', headers=h, json={'quantity':1})
    assert box.status_code in [200,201], box.text
    box_body = box.json()
    bid = box_body[0]['id'] if isinstance(box_body,list) else box_body['id']
    result = await async_client.post(f'{BASE}/{rid}/boxes/{bid}/scan', headers=h, json={'barcode':barcode, 'mutation_id':str(uuid.uuid4())})
    assert result.status_code == 404, result.text
    assert 'barcode_unknown' in result.text
    print('OBSERVED: catalog WB/Ozon, bindings Ozon only; native scan filter false; box scan barcode_unknown')

@pytest.mark.asyncio
async def test_completion_retry_after_reopen_posts_again(async_client):
    h, wid, sid, pid = await _setup(async_client)
    rid = (await async_client.post(BASE, headers=h, json={'warehouse_id':wid, 'seller_id':sid})).json()['id']
    await async_client.post(f'{BASE}/{rid}/lines', headers=h, json={'product_id':pid,'expected_qty':3})
    assert (await async_client.post(f'{BASE}/{rid}/complete-receiving', headers=h)).json()['status']=='sorting'
    assert (await async_client.post(f'{BASE}/{rid}/reopen-receiving', headers=h)).json()['status']=='receiving'
    # Exact replay sent by clients when their previous completion response was lost.
    retry = await async_client.post(f'{BASE}/{rid}/complete-receiving', headers=h)
    assert retry.json()['status']=='sorting'
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 3
    print('OBSERVED: replay of old complete closes reopened document and restores arrival 3')
