"""WMS-501 audit evidence only. Requires explicitly disposable PostgreSQL.

Run from backend with -p tests.conftest. Assertions describe current behavior,
including defects, so a passing test is evidence of reproduction, not correctness.
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import select

assert '127.0.0.1:55451/wms501_scanning' in os.environ.get('WMS_TEST_DATABASE_URL', '')

from app.db.session import SessionLocal
from app.models.user import User
from app.models.inbound_intake import InboundIntakeDistributionLine
from app.models.storage_location import StorageLocation
from app.services import inbound_intake_service as svc
from app.services.tokens import create_access_token
from tests.test_inbound_intake_service_be01 import _auth_ids, _setup_request


async def setup(client):
    tenant, actor = await _auth_ids(client)
    rid, pid = await _setup_request(client, tenant, expected_qty=50)
    async with SessionLocal() as db:
        user = await db.get(User, actor)
        token = create_access_token(user_id=actor, tenant_id=tenant, role=user.role)
    return tenant, actor, rid, pid, {'Authorization': f'Bearer {token}'}


@pytest.mark.asyncio
async def test_receiving_replayed_http_attempt_counts_twice(async_client):
    tenant, actor, rid, pid, headers = await setup(async_client)
    headers['Idempotency-Key'] = 'audit-same-network-attempt'
    endpoint = f'/operations/inbound-intake-requests/{rid}/receiving/scan'
    body = {'barcode': 'audit-hint', 'product_id': str(pid)}
    first = await async_client.post(endpoint, json=body, headers=headers)
    second = await async_client.post(endpoint, json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()['actual_qty'] == 1
    assert second.json()['actual_qty'] == 2
    print('REPRO: identical HTTP attempt, same Idempotency-Key: actual_qty 1 -> 2')


@pytest.mark.asyncio
async def test_twenty_scans_same_login_are_not_lost(async_client):
    tenant, actor, rid, pid, headers = await setup(async_client)
    endpoint = f'/operations/inbound-intake-requests/{rid}/receiving/scan'
    results = await asyncio.gather(*[
        async_client.post(endpoint, json={'barcode': 'audit-hint', 'product_id': str(pid)}, headers=headers)
        for _ in range(20)
    ])
    assert all(response.status_code == 200 for response in results)
    async with SessionLocal() as db:
        req = await svc.get_request(db, tenant, rid)
        assert req.lines[0].actual_qty == 20
    print('CHECK: 20 parallel scans with same test login, final actual_qty=20')


@pytest.mark.asyncio
async def test_stale_absolute_quantity_overwrites_committed_scan(async_client):
    tenant, actor, rid, pid, headers = await setup(async_client)
    async with SessionLocal() as db:
        req = await svc.begin_receiving(db, tenant, rid, actor_user_id=actor)
        line_id = req.lines[0].id
        await svc.set_line_actual_qty(db, tenant, rid, line_id, actual_qty=5)
    response = await async_client.post(
        f'/operations/inbound-intake-requests/{rid}/receiving/scan',
        json={'barcode': 'audit-hint', 'product_id': str(pid)}, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()['actual_qty'] == 6
    # Device B submits its formerly loaded absolute count after device A's scan.
    stale = await async_client.patch(
        f'/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual',
        json={'actual_qty': 5}, headers=headers,
    )
    assert stale.status_code == 200
    assert stale.json()['actual_qty'] == 5
    print('REPRO: stale absolute quantity after committed scan: 5 -> 6 -> 5 without conflict')


@pytest.mark.asyncio
async def test_stale_distribution_snapshot_erases_other_editor(async_client):
    tenant, actor, rid, pid, headers = await setup(async_client)
    async with SessionLocal() as db:
        req = await svc.begin_receiving(db, tenant, rid, actor_user_id=actor)
        await svc.set_line_actual_qty(db, tenant, rid, req.lines[0].id, actual_qty=5)
        req = await svc.complete_receiving(db, tenant, rid, actor_user_id=actor)
        a = StorageLocation(id=uuid.uuid4(), tenant_id=tenant, warehouse_id=req.warehouse_id, code='AUDIT-A', barcode='AUDIT-A')
        b = StorageLocation(id=uuid.uuid4(), tenant_id=tenant, warehouse_id=req.warehouse_id, code='AUDIT-B', barcode='AUDIT-B')
        db.add_all([a, b]); await db.commit()
        aid, bid = a.id, b.id
    async with SessionLocal() as db:
        await svc.replace_distribution_lines(db, tenant, rid, lines=[(None, pid, aid, 1)])
    async with SessionLocal() as db:
        await svc.replace_distribution_lines(db, tenant, rid, lines=[(None, pid, bid, 1)])
    async with SessionLocal() as db:
        rows = list((await db.scalars(select(InboundIntakeDistributionLine).where(InboundIntakeDistributionLine.request_id == rid))).all())
        assert [(row.storage_location_id, row.quantity) for row in rows] == [(bid, 1)]
    print('REPRO: draft distribution snapshot B silently replaces A; A row absent')
