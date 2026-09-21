"""WMS-501 audit evidence. Run with -p conftest, backend/tests on PYTHONPATH.
These tests intentionally ASSERT existing defects, not desired product behavior.
Never point WMS_TEST_DATABASE_URL at anything except a disposable audit DB.
"""
import json
import os
import re
from pathlib import Path

# Fail closed before any test fixtures can drop/rebuild a schema. Never derive
# this URL from a generic DATABASE_URL or permit a caller's production database.
assert os.environ.get("WMS_TEST_DATABASE_URL") == (
    "postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation"
), "WMS-501 isolation probes require the dedicated disposable audit PostgreSQL DB"

from fastapi.routing import APIRoute
from app.main import create_app
from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.storage_location import StorageLocation
from app.services.tokens import create_access_token
from test_wms488_catalog_isolation import _headers, _seed

OUT = Path(__file__).parent

async def test_permission_bypass_recent_movements(async_client):
    users, products, wh = await _seed()
    async with SessionLocal() as session:
        loc = StorageLocation(tenant_id=wh.tenant_id, warehouse_id=wh.id, code='AUDIT', barcode='AUDIT')
        session.add(loc)
        session.add(SellerStaffPermissions(user_id=users['a'].id, can_products=False))
        await session.flush()
        for key in ('a', 'b'):
            session.add(InventoryMovement(tenant_id=wh.tenant_id, product_id=products[key].id,
                seller_id=products[key].seller_id, storage_location_id=loc.id, warehouse_id=wh.id,
                quantity_delta=7, movement_type='inbound_intake'))
        await session.commit()
    observed=[]
    for actor in ('staff', 'a'):
        headers=_headers(users[actor])
        denied=await async_client.get('/operations/inventory-balances/summary', headers=headers)
        leaked=await async_client.get('/operations/inventory-movements', headers=headers)
        assert denied.status_code == 403, denied.text
        assert leaked.status_code == 200, leaked.text
        ids={row['product_id'] for row in leaked.json()}
        expected={str(products[x].id) for x in (('a','b') if actor=='staff' else ('a',))}
        assert ids == expected
        observed.append({'actor':actor,'inventory_summary':403,'movements':200,
                         'disclosed_product_count':len(ids),'foreign_tenant_disclosed':False})
    (OUT/'isolation-permission-repro.json').write_text(json.dumps(observed,indent=2)+'\n')

async def test_signed_token_tenant_sub_mismatch_denied(async_client):
    users, _, _ = await _seed()
    token=create_access_token(user_id=users['admin'].id, tenant_id=users['foreign'].tenant_id,
                              role='fulfillment_admin')
    response=await async_client.get('/products',headers={'Authorization':f'Bearer {token}'})
    assert response.status_code==403
    assert response.json()['detail']=='tenant_mismatch'

async def test_all_runtime_protected_routes_deny_missing_auth(async_client):
    public={'/health','/auth/login','/auth/login-by-name','/auth/register','/auth/set-password',
            '/auth/request-password-reset','/operations/print/pairing'}
    # Only read route metadata for public APIs; do not invoke public registration or resets.
    app=create_app()
    inventory=[]
    def routes(router):
        for item in router.routes:
            if isinstance(item, APIRoute):
                yield item
            elif hasattr(item, "original_router"):
                yield from routes(item.original_router)
    for route in routes(app):
        def dependencies(dep):
            names=[]
            for child in dep.dependencies:
                names.append(getattr(child.call,'__name__',str(child.call)))
                names.extend(dependencies(child))
            return names
        names=sorted(set(dependencies(route.dependant)))
        for method in sorted(route.methods):
            row={'path':route.path,'method':method,'handler':route.endpoint.__module__+'.'+route.endpoint.__name__,
                 'auth_dependencies':names}
            inventory.append(row)
            if route.path in public:
                row['anonymous_check']='public-not-invoked'
                continue
            target=re.sub(r'\{[^}]+\}', '11111111-1111-4111-8111-111111111111', route.path)
            response=await async_client.request(method,target,json={} if method in {'POST','PUT','PATCH'} else None)
            row['anonymous_status']=response.status_code
            assert response.status_code in (401,403), (row,response.text)
    assert len(inventory) > 400, 'Empty or partial route traversal must never pass'
    (OUT/'isolation-runtime-route-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')

async def test_database_allows_mismatched_tenant_product_reference(async_client):
    """Defense-in-depth gap, not an API exploit: inject a corrupt link directly."""
    users, products, wh = await _seed()
    async with SessionLocal() as session:
        loc = StorageLocation(tenant_id=wh.tenant_id, warehouse_id=wh.id, code='BAD-LINK', barcode='BAD-LINK')
        session.add(loc)
        await session.flush()
        session.add(InventoryMovement(tenant_id=wh.tenant_id,
            product_id=products['foreign'].id, seller_id=products['foreign'].seller_id,
            storage_location_id=loc.id, warehouse_id=wh.id,
            quantity_delta=1, movement_type='inbound_intake'))
        # PostgreSQL accepts a product FK referencing another tenant because
        # this table has separate FKs, not the composite (tenant_id, product_id).
        await session.commit()
    response=await async_client.get('/operations/inventory-movements', headers=_headers(users['admin']))
    assert response.status_code==200
    assert response.json()[0]['sku_code']==products['foreign'].sku_code
    (OUT/'isolation-corrupt-reference-repro.json').write_text(json.dumps({
        'precondition':'Direct audit DB insertion of an inconsistent tenant/product relation',
        'api_mutation_path_proven':False,'postgres_rejected_inconsistent_relation':False,
        'read_api_returned_foreign_sku':True,'production_data_checked':False},indent=2)+'\n')

async def test_non_avpack_seller_can_read_another_sellers_job(async_client):
    from app.models.background_job import BackgroundJob
    from app.models.tenant import Tenant
    users, _, _ = await _seed()
    observed=[]
    for job_type, payload, result in [
        ('wildberries_cards_sync', {'seller_id':str(users['b'].seller_id)}, {'private_seller_b_marker':17}),
        ('movements_digest', {}, {'movement_counts_by_type':{'inbound_intake':123},'total_movements':123}),
    ]:
        async with SessionLocal() as session:
            job=BackgroundJob(tenant_id=users['a'].tenant_id,job_type=job_type,status='failed',
                payload_json=payload,result_json=result,error_message='synthetic-private-diagnostic')
            session.add(job)
            await session.commit()
        response=await async_client.get(f'/operations/background-jobs/{job.id}',headers=_headers(users['a']))
        assert response.status_code==200, response.text
        assert response.json()['result_json']==result
        assert response.json()['error_message']=='synthetic-private-diagnostic'
        foreign=await async_client.get(f'/operations/background-jobs/{job.id}',headers=_headers(users['foreign']))
        assert foreign.status_code==404, foreign.text
        observed.append({'job_type':job_type,'unauthorized_same_tenant_seller_status':200,
            'foreign_tenant_status':404,'result_and_raw_error_disclosed':True})
    # Exact AVpack slug is the implementation's special gate, not a general seller gate.
    async with SessionLocal() as session:
        tenant=await session.get(Tenant, users['a'].tenant_id)
        tenant.slug='avpack-9uczh'
        await session.commit()
    avpack=await async_client.get(f'/operations/background-jobs/{job.id}',headers=_headers(users['a']))
    assert avpack.status_code==404
    (OUT/'isolation-jobs-repro.json').write_text(json.dumps({
        'precondition':'Authenticated ordinary seller knows another job UUID within own tenant',
        'can_manage_seller_shops':False,'grants_added':False,'cases':observed,
        'exact_avpack_slug_control_status':404},indent=2)+'\n')
