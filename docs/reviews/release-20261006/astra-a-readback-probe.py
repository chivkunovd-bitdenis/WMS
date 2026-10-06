import pytest
from test_wms663_customs_documents_contract import _seed_order, _transport, _remote_snapshot
from test_wms663_owner_absent_batch_contract import kwargs, writes, expected_payload
from app.services import ozon_exemplar_documents_service as docs
from app.services.marketplace_provider import MarketplaceProviderError
SET='/v6/fbs/posting/product/exemplar/set'
STATUS='/v5/fbs/posting/product/exemplar/status'

@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['old_editable', 'empty', 'foreign', 'read_error'])
async def test_refusal_remains_retryable_after_inconclusive_get(db_session, case):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), 'status': 'update_available'})
    transport.errors[SET] = MarketplaceProviderError('ozon', 429, code='definite_refusal')
    rejected = await docs.save_absent_exemplar_documents(db_session, **kwargs(order, transport), expected_version=0)
    transport.errors.pop(SET)
    if case == 'empty':
        transport.endpoint_responses[STATUS] = {'posting_number': order.external_order_id, 'products': []}
    elif case == 'foreign':
        transport.endpoint_responses[STATUS] = {**_remote_snapshot(), 'posting_number': 'different', 'status': 'ship_available'}
    elif case == 'read_error':
        transport.errors[STATUS] = MarketplaceProviderError('ozon', 500, code='read_failed')
    readback = await docs.get_exemplar_documents(db_session, **kwargs(order, transport))
    assert readback['state'] == 'rejected'
    assert readback['version'] == rejected['version']
    assert readback['absence_selected'] is True
    assert len(writes(transport)) == 1
    transport.errors.pop(STATUS, None)
    original = transport.call
    async def accept_new_write(**args):
        result = await original(**args)
        if args['path'] == SET:
            transport.endpoint_responses[STATUS] = {**expected_payload(), 'status': 'ship_available'}
        return result
    transport.call = accept_new_write
    accepted = await docs.save_absent_exemplar_documents(db_session, **kwargs(order, transport), expected_version=readback['version'])
    assert accepted['state'] == 'accepted'
    assert accepted['version'] == 2
    assert writes(transport) == [expected_payload(), expected_payload()]
