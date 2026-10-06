import pytest
from test_wms663_customs_documents_contract import _seed_order, _transport, _remote_snapshot
from test_wms663_owner_absent_batch_contract import kwargs, writes
from app.services import ozon_exemplar_documents_service as docs
from app.services.marketplace_provider import MarketplaceProviderError

@pytest.mark.asyncio
async def test_definite_set_rejection_then_explicit_retry(db_session):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), 'status': 'update_available'})
    path = '/v6/fbs/posting/product/exemplar/set'
    transport.errors[path] = MarketplaceProviderError('ozon', 429, code='fixture_rate_limit')
    first = await docs.save_absent_exemplar_documents(db_session, **kwargs(order, transport), expected_version=0)
    print('FIRST', first['state'], first['absence_selected'], first['version'], len(writes(transport)))
    transport.errors.pop(path)
    again = await docs.save_absent_exemplar_documents(db_session, **kwargs(order, transport), expected_version=first['version'])
    print('RETRY', again['state'], again['absence_selected'], again['version'], len(writes(transport)))
    assert len(writes(transport)) == 2, 'Definite rejected SET should allow a new explicit SET after recovery'
