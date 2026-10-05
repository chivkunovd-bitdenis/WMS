"""Supplemental developer probe. Frozen tests are neither changed nor replaced.

Run from backend: PYTHONPATH=.:tests python ../docs/reviews/wms663-developer/check_recovery.py
conftest forces an isolated test database before app imports.
"""
import asyncio

import conftest
from app.db.session import SessionLocal
from app.services.ozon_exemplar_documents_service import (
    document_data,
    document_order,
    resume_exemplar_document_check,
    save_exemplar_documents,
)
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    SKU_ONE,
    _AppliedThenLostTransport,
    _remote_snapshot,
    _seed_order,
    _transport,
)


async def main():
    await conftest._rebuild_schema()
    async with SessionLocal() as session:
        order, _, _ = await _seed_order(session)
        # Immutable identities are captured before AsyncSession.expire_all().
        tenant_id, order_id = order.tenant_id, order.id
        transport = _transport()
        transport.endpoint_response_queues['/v5/fbs/posting/product/exemplar/status'] = [
            {'posting_number': POSTING_NUMBER, 'status': 'validation_in_process', 'products': []},
            {'posting_number': POSTING_NUMBER, 'status': 'ship_available', 'products': [
                {'product_id': SKU_ONE, 'exemplars': [{'exemplar_id': 81,
                    'gtd': '001/ABC-09', 'is_gtd_absent': False, 'rnpt': '',
                    'is_rnpt_absent': True, 'gtd_check_status': '', 'rnpt_check_status': '',
                    'gtd_error_codes': [], 'rnpt_error_codes': []}]}]},
        ]
        provider = OzonMarketplaceProvider(transport=transport)
        saved = await save_exemplar_documents(session, tenant_id=tenant_id, order_id=order_id,
            product_id=SKU_ONE, exemplar_id=81, gtd='001/ABC-09', is_gtd_absent=False,
            rnpt=None, is_rnpt_absent=True, expected_version=0,
            provider=provider, client_id='client', api_key='key')
        assert saved['state'] == 'checking'
        session.expire_all()
        resumed = await resume_exemplar_document_check(session, tenant_id=tenant_id,
            order_id=order_id, provider=provider, client_id='client', api_key='key')
        assert resumed['state'] == 'accepted'
        assert sum(path.endswith('/exemplar/set') for path, _ in transport.endpoint_calls) == 1
    async with SessionLocal() as session:
        order = await document_order(session, tenant_id, order_id)
        data = document_data(order)
        assert data['state'] == 'accepted'
        assert data['choices'][f'{SKU_ONE}:81']['gtd'] == '001/ABC-09'
        assert data['choices'][f'{SKU_ONE}:81']['is_rnpt_absent'] is True
    async with SessionLocal() as session:
        order, _, _ = await _seed_order(session)
        tenant_id, order_id = order.tenant_id, order.id
        transport = _AppliedThenLostTransport(endpoint_responses={
            '/v6/fbs/posting/product/exemplar/create-or-get': _remote_snapshot(),
            '/v5/fbs/posting/product/exemplar/status': {
                'posting_number': POSTING_NUMBER, 'status': 'update_available',
                'products': _remote_snapshot()['products']},
        })
        provider = OzonMarketplaceProvider(transport=transport)
        saved = await save_exemplar_documents(session, tenant_id=tenant_id, order_id=order_id,
            product_id=SKU_ONE, exemplar_id=81, gtd='NEW-GTD', is_gtd_absent=False,
            rnpt=None, is_rnpt_absent=False, expected_version=0,
            provider=provider, client_id='client', api_key='key')
        assert saved['state'] == 'unknown'
        try:
            await save_exemplar_documents(session, tenant_id=tenant_id, order_id=order_id,
                product_id=SKU_ONE, exemplar_id=81, gtd='OTHER-GTD', is_gtd_absent=False,
                rnpt=None, is_rnpt_absent=False, expected_version=saved['version'],
                provider=provider, client_id='client', api_key='key')
        except OzonFbsProcessError as error:
            assert error.code == 'ozon_exemplar_documents_conflict'
        else:
            raise AssertionError('old update_available must not release an unknown write')
        assert sum(path.endswith('/exemplar/set') for path, _ in transport.endpoint_calls) == 1
    print('Unknown write + old update_available: kept unknown; next Save read status; no repeat set.')
    print('Supplemental recovery: accepted after expiry + new session; one set; exact choice persisted.')
    await conftest.engine.dispose()


asyncio.run(main())
