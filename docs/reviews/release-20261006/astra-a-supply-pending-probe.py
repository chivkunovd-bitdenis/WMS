"""Audit-only deterministic observation of the pre-existing WMS-272 claim window."""
import asyncio
import json
import uuid
import pytest
from sqlalchemy import select, func
from tests.test_fbs_supply_from_orders import (
    _register_ff_admin, _setup_seller_with_token, _create_product, _create_ready_order,
)
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_supply_service as service

@pytest.mark.asyncio
async def test_pending_claim_preserves_single_winner_and_later_conflict(async_client, monkeypatch):
    monkeypatch.setattr(settings, 'e2e_mock_wb_marketplace_supplies', True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get('/auth/me', headers=headers)
    tenant_id = uuid.UUID(me.json()['tenant_id'])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(async_client, headers, suffix)
    product = await _create_product(async_client, headers, seller_id, sku=f'race-{suffix[-6:]}')
    order_id = await _create_ready_order(tenant_id, uuid.UUID(seller_id), uuid.UUID(warehouse_id), uuid.UUID(location_id), product, order_id=857001)
    entered, release = asyncio.Event(), asyncio.Event()
    creates, adds = [], []
    real_create, real_add = service.create_marketplace_supply, service._execute_wb_batch_add
    async def create(*args, **kwargs):
        result = await real_create(*args, **kwargs)
        creates.append(result['id'])
        return result
    async def add(*args, **kwargs):
        adds.append(kwargs['wb_supply_id'])
        entered.set()
        await asyncio.wait_for(release.wait(), 10)
        return await real_add(*args, **kwargs)
    monkeypatch.setattr(service, 'create_marketplace_supply', create)
    monkeypatch.setattr(service, '_execute_wb_batch_add', add)
    def payload(name):
        return {'name': name, 'order_ids': [str(order_id)], 'planned_delivery_type':'warehouse_sc', 'idempotency_key':str(uuid.uuid4())}
    a, b = payload('Race A'), payload('Race B')
    task = asyncio.create_task(async_client.post('/operations/fbs-supplies/from-orders', headers=headers, json=a))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        loser = await async_client.post('/operations/fbs-supplies/from-orders', headers=headers, json=b)
        print('PENDING_RESPONSE', loser.status_code, json.dumps(loser.json(), ensure_ascii=False))
        assert loser.status_code == 503
        detail = loser.json()['detail']
        assert detail['code'] == 'operation_in_progress'
        assert detail['retryable'] is True
        assert detail['context']['operation_state'] == 'pending_confirmation'
        async with SessionLocal() as session:
            operations = list((await session.scalars(select(FbsWbOperation))).all())
            supplies = list((await session.scalars(select(FbsSupply))).all())
            assert len(operations) == len(supplies) == 1
            assert operations[0].state == 'pending_confirmation'
            assert str(operations[0].id) == detail['context']['operation_id']
            assert str(supplies[0].id) == detail['context']['supply_id']
            assert supplies[0].wb_supply_id == detail['context']['wb_supply_id']
        release.set()
        winner = await task
        assert winner.status_code == 201, winner.text
        later = await async_client.post('/operations/fbs-supplies/from-orders', headers=headers, json=b)
        print('AFTER_CONFIRM_RESPONSE', later.status_code, json.dumps(later.json(), ensure_ascii=False))
        assert later.status_code == 409
        assert later.json()['detail']['code'] == 'order_incompatible'
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            operations = list((await session.scalars(select(FbsWbOperation))).all())
            supply_count = await session.scalar(select(func.count()).select_from(FbsSupply))
            assert supply_count == len(operations) == 1
            assert operations[0].state == 'confirmed'
            assert order.supply_id == operations[0].local_entity_id
            assert order.status == 'in_supply'
            assert len(creates) == len(adds) == 1
            print('FINAL_INVARIANTS', json.dumps({'supplies':supply_count,'operations':len(operations),'operation_state':operations[0].state,'order_status':order.status,'create_calls':len(creates),'add_calls':len(adds)}))
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
