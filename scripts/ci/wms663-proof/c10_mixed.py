"""Runner-only C10 mixed writer proof; copied beside the frozen tests in CI."""
import asyncio
from copy import deepcopy

import pytest
from sqlalchemy import select
from test_wms663_customs_documents_contract import (
    SKU_ONE, _remote_snapshot, _seed_order, _transport,
)

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.services import ozon_exemplar_documents_service as docs
from app.services import ozon_fbs_process_service as process
from app.services.marketplace_provider import OzonMarketplaceProvider

SET = '/v6/fbs/posting/product/exemplar/set'
SNAPSHOT = '/v6/fbs/posting/product/exemplar/create-or-get'
STATUS = '/v5/fbs/posting/product/exemplar/status'


@pytest.mark.asyncio
async def test_c10_document_claim_blocks_concurrent_marking_without_losing_either(db_session, monkeypatch):
    assert engine.dialect.name == 'postgresql', 'C10 must run on real isolated PostgreSQL, never SKIP'
    order, position, _ = await _seed_order(db_session)
    tenant_id, order_id, position_id = order.tenant_id, order.id, position.id
    marking = FbsOrderMarking(tenant_id=tenant_id, order_id=order_id,
        order_product_id=position_id, kind='sgtin', value='010460000000000121C10MIXED',
        meta_details_json={'exemplar_id': 82})
    db_session.add(marking)
    await db_session.commit()
    marking_id = marking.id
    transport = _transport(status={**_remote_snapshot(), 'status': 'validation_in_process'})
    entered, release = asyncio.Event(), asyncio.Event()
    original = docs.fetch_exemplar_snapshot

    async def gated(*args, **kwargs):
        entered.set()
        await asyncio.wait_for(release.wait(), 10)
        return await original(*args, **kwargs)

    monkeypatch.setattr(docs, 'fetch_exemplar_snapshot', gated)

    async def document_writer():
        async with SessionLocal() as session:
            return await docs.save_exemplar_documents(session, tenant_id=tenant_id,
                order_id=order_id, product_id=SKU_ONE, exemplar_id=81,
                gtd='000/C10-MIXED', is_gtd_absent=False, rnpt=None,
                is_rnpt_absent=True, expected_version=0,
                provider=OzonMarketplaceProvider(transport=transport), client_id='fake', api_key='fake')

    async def marking_writer():
        async with SessionLocal() as session:
            current_order = await session.get(FbsOrder, order_id)
            current_mark = await session.get(FbsOrderMarking, marking_id)
            return await process.submit_marking(session, order=current_order, marking=current_mark,
                provider=OzonMarketplaceProvider(transport=transport), client_id='fake', api_key='fake')

    task = asyncio.create_task(document_writer())
    try:
        await asyncio.wait_for(entered.wait(), 10)
        with pytest.raises(process.OzonFbsProcessError) as caught:
            await asyncio.wait_for(marking_writer(), 10)
        assert caught.value.code == 'ozon_exemplar_documents_conflict'
        assert sum(path == SET for path, _ in transport.endpoint_calls) == 0
    finally:
        release.set()
        await asyncio.wait_for(task, 10)
    writes = [deepcopy(payload) for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 1
    snapshot = deepcopy(writes[0])
    transport.endpoint_responses[SNAPSHOT] = snapshot
    transport.endpoint_responses[STATUS] = {**snapshot, 'status': 'ship_available'}
    async with SessionLocal() as session:
        await docs.resume_exemplar_document_check(session, tenant_id=tenant_id, order_id=order_id,
            provider=OzonMarketplaceProvider(transport=transport), client_id='fake', api_key='fake')
    await marking_writer()
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 2  # two distinct explicit actions, never two writes for the pending version
    a = writes[-1]['products'][0]['exemplars']
    assert a[0]['gtd'] == '000/C10-MIXED'
    assert a[0]['marks'] == _remote_snapshot()['products'][0]['exemplars'][0]['marks']
    assert any(mark['mark'] == '010460000000000121C10MIXED' for mark in a[1]['marks'])
    assert writes[-1]['products'][1] == writes[0]['products'][1]
    async with SessionLocal() as session:
        stored = await session.scalar(select(FbsOrder).where(FbsOrder.id == order_id))
        data = docs.document_data(stored)
        assert data['version'] == 2
        assert data['choices'][f'{SKU_ONE}:81']['gtd'] == '000/C10-MIXED'
        assert await session.get(FbsOrderMarking, marking_id) is not None
    print('C10 mixed: two PG sessions, conflicting marking blocked; explicit continuation preserves GTD/marks/neighbors, SET=2 distinct versions')
