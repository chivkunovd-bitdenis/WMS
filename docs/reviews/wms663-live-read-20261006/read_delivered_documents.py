"""One existing delivered seller-bound posting: info/status only, no retries or WMS writes.

Exact posting/SKU/order provenance: confirmed Bambook WMS-675 evidence.
The original reader remains unchanged; only this bounded target differs.

Run in the existing normal backend process. Credentials remain inside the
account/provider boundary. Stdout contains only sanitized evidence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

TENANT = 'b80a893b-ab87-42b6-8fd7-6d41502c900f'
SELLER = 'cf6d31c5-944b-4382-af34-636ca9aa8cc3'
SUPPLY = 'b82d1e9a-30d2-4d7b-b52d-9775c3d266e3'
WAREHOUSE = '2d968c65-4a8d-414e-9076-0f201c2dba63'
ORDER = '89d0cf5c-8811-4ef7-8420-6aa7037b21c6'
POSTING = '66144885-0156-18'
SKU = 1695128938
INFO = '/v3/posting/fbs/get'
STATUS = '/v5/fbs/posting/product/exemplar/status'
SAFE_STATUS = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,119}$')


def now():
    return datetime.now(timezone.utc).isoformat()


def code(value):
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str) and (not value or SAFE_STATUS.fullmatch(value)):
        return value
    return {'value_type': type(value).__name__, 'value_suppressed': True}


def number(value):
    """Document contents are never published; presence/type/empty/hash suffice."""
    out = {'value_type': type(value).__name__}
    if isinstance(value, str):
        out.update(empty=value == '', length=len(value), sha256=hashlib.sha256(value.encode()).hexdigest())
    return out


def status_projection(raw):
    if not isinstance(raw, dict):
        raise ValueError('unexpected_status_shape')
    if raw.get('posting_number') != POSTING:
        raise ValueError('posting_identity_mismatch')
    out = {'posting_number': POSTING, 'status': code(raw.get('status')), 'products': [],
           'response_keys': sorted(raw), 'field_types': {k: type(v).__name__ for k, v in raw.items()}}
    for product in raw.get('products') or []:
        row = {'product_id': product.get('product_id'), 'exemplars': []}
        if row['product_id'] != SKU:
            raise ValueError('product_scope_mismatch')
        for exemplar in product.get('exemplars') or []:
            item = {'exemplar_id': exemplar.get('exemplar_id'),
                    'present_document_fields': [k for k in (
                        'gtd', 'rnpt', 'is_gtd_absent', 'is_rnpt_absent',
                        'gtd_check_status', 'rnpt_check_status', 'gtd_error_codes', 'rnpt_error_codes'
                    ) if k in exemplar], 'marks_count': len(exemplar.get('marks') or [])}
            for doc in ('gtd', 'rnpt'):
                if doc in exemplar:
                    item[doc] = number(exemplar[doc])
                for key in (f'is_{doc}_absent', f'{doc}_check_status'):
                    if key in exemplar:
                        item[key] = code(exemplar[key])
                key = f'{doc}_error_codes'
                if key in exemplar:
                    values = exemplar[key]
                    item[key] = [code(v) for v in values] if isinstance(values, list) else code(values)
            row['exemplars'].append(item)
        out['products'].append(row)
    return out


async def collect(proof):
    import httpx
    from sqlalchemy import text
    from app.core.settings import settings
    from app.db.session import SessionLocal
    from app.services.marketplace_account_service import MarketplaceAccountService
    from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
    from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled

    base = urlsplit(settings.ozon_seller_api_base)
    if not ozon_live_api_enabled() or (base.scheme, base.netloc, base.path.rstrip('/')) != ('https', 'api-seller.ozon.ru', '') or base.query or base.fragment:
        raise RuntimeError('expected_live_ozon_host_unavailable')
    provider = build_ozon_provider()
    if not isinstance(provider.transport, HttpxOzonMarketplaceTransport):
        raise RuntimeError('expected_live_transport_unavailable')
    params = {k: uuid.UUID(v) for k, v in {'tenant': TENANT, 'seller': SELLER, 'supply': SUPPLY, 'warehouse': WAREHOUSE, 'order': ORDER}.items()}
    async with SessionLocal() as session:
        if session.bind.dialect.name != 'postgresql':
            raise RuntimeError('expected_normal_postgresql_backend')
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        scope = (await session.execute(text('''
            SELECT s.id AS supply_id,s.tenant_id,s.seller_id,s.warehouse_id,s.source,
                   o.id AS order_id,o.external_order_id,o.status AS local_order_status,
                   p.id AS position_id,p.ozon_sku,p.quantity,
                   current_setting('transaction_read_only') AS read_only
            FROM fbs_supplies s JOIN fbs_orders o ON o.supply_id=s.id
            JOIN fbs_order_products p ON p.order_id=o.id
            WHERE s.id=:supply AND s.tenant_id=:tenant AND s.seller_id=:seller
              AND s.warehouse_id=:warehouse AND s.marketplace='ozon' AND s.source='wms'
              AND o.id=:order AND o.tenant_id=:tenant AND o.seller_id=:seller
              AND o.warehouse_id=:warehouse AND o.marketplace='ozon'
        '''), params)).mappings().all()
        if len(scope) != 1 or scope[0]['external_order_id'] != POSTING or scope[0]['ozon_sku'] != SKU or scope[0]['quantity'] != 1 or scope[0]['local_order_status'] != 'done' or scope[0]['read_only'] != 'on':
            raise RuntimeError('exact_posting_scope_mismatch')
        proof['scope_snapshot'] = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in scope[0].items()}
        client_id, api_key = await MarketplaceAccountService(session).stored_credentials(params['tenant'], params['seller'])
        await session.rollback()  # No database transaction spans network calls.
    metadata = {}

    async def response_hook(response):
        metadata.update(http_status=response.status_code, server_date=response.headers.get('Date'))

    async with httpx.AsyncClient(event_hooks={'response': [response_hook]}) as client:
        provider.transport = HttpxOzonMarketplaceTransport(client=client)
        for path in (INFO, STATUS):
            metadata.clear()
            entry = {'posting_number': POSTING, 'endpoint': path, 'http_method': 'POST',
                     'semantic_operation': 'read', 'started_at_utc': now()}
            payload = {'posting_number': POSTING}
            if path == INFO:
                payload['with'] = {'analytics_data': False, 'barcodes': False, 'financial_data': False,
                                   'legal_info': False, 'product_exemplars': False, 'related_postings': False,
                                   'translit': False}
            try:
                raw = await provider.call(client_id=client_id, api_key=api_key, path=path, payload=payload)
                if path == INFO:
                    card = raw.get('result', {})
                    if card.get('posting_number') != POSTING:
                        raise ValueError('posting_identity_mismatch')
                    requirements = card.get('requirements')
                    entry['response'] = {'posting_number': POSTING, 'status': code(card.get('status')),
                        'substatus': code(card.get('substatus')), 'requirements_present': isinstance(requirements, dict),
                        'requirements': {k: v for k, v in (requirements or {}).items()
                                         if k in ('products_requiring_gtd', 'products_requiring_rnpt')},
                        'products': [{'sku': p.get('sku'), 'quantity': p.get('quantity')} for p in card.get('products') or []]}
                else:
                    entry['response'] = status_projection(raw)
                entry['result'] = 'READ_RESPONSE_NOT_ACCEPTANCE'
            except Exception as exc:
                entry.update(result='UNKNOWN', error_type=type(exc).__name__)
                value = getattr(exc, 'payload', {}).get('code') if isinstance(getattr(exc, 'payload', None), dict) else None
                if value is not None:
                    entry['provider_error_code'] = code(value)
                if type(exc) in (RuntimeError, ValueError) and str(exc) in ('posting_identity_mismatch', 'product_scope_mismatch', 'unexpected_status_shape'):
                    entry['failure_code'] = str(exc)
            entry.update(metadata, finished_at_utc=now())
            proof['requests'].append(entry)
    proof['execution_status'] = 'BOUNDED_READ_FINISHED_NOT_C19'


def main():
    proof = {'started_at_utc': now(), 'tenant_id': TENANT, 'seller_id': SELLER,
             'supply_id': SUPPLY, 'order_id': ORDER, 'posting_number': POSTING,
             'execution_status': 'STARTED_NOT_PROOF', 'requests': [],
             'mutation_endpoints_called': [], 'local_commit_called': False, 'retries': 0}
    try:
        asyncio.run(collect(proof))
    except Exception as exc:
        proof.update(execution_status='UNKNOWN_NO_MUTATION', error_type=type(exc).__name__)
    proof['finished_at_utc'] = now()
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
