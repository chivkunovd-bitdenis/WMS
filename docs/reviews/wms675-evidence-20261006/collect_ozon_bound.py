"""WMS-675 evidence utility. Run ONLY in the normal configured WMS backend.

Uses the existing account service internally. No credentials on CLI or output,
no WMS commit/sync, no external mutation, no retries. Each run is a new directory.
The Seller API read named `get` uses HTTP POST; it does not ship/change postings.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
TENANT = 'b80a893b-ab87-42b6-8fd7-6d41502c900f'
SELLER = 'cf6d31c5-944b-4382-af34-636ca9aa8cc3'
SUPPLY = 'b82d1e9a-30d2-4d7b-b52d-9775c3d266e3'
WAREHOUSE = '2d968c65-4a8d-414e-9076-0f201c2dba63'
ENDPOINT = '/v3/posting/fbs/get'
NUMBER = re.compile(r'^[0-9]{1,20}-[0-9]{1,10}-[0-9]{1,10}$')
MAX_CARDS = 124
SAFE_CODES = frozenset({'live_transport_disabled', 'unexpected_provider_host', 'not_live_transport',
    'invalid_seed_plan', 'seed_scope_mismatch', 'requires_normal_postgresql_backend',
    'supply_scope_mismatch', 'draft_composition_changed', 'warehouse_scope_mismatch',
    'missing_result', 'missing_products', 'invalid_product', 'invalid_sku', 'invalid_quantity',
    'invalid_related_postings', 'invalid_related_numbers', 'duplicate_related_numbers',
    'invalid_cancellation', 'missing_status', 'posting_identity_mismatch', 'ozon_not_connected'})


def failure_code(exc):
    code = getattr(exc, 'code', None)
    if isinstance(code, str) and code in SAFE_CODES:
        return code
    if type(exc) in (RuntimeError, ValueError) and str(exc) in SAFE_CODES:
        return str(exc)
    return 'details_suppressed'


SCALARS = ('posting_number', 'order_id', 'order_number', 'status', 'substatus',
           'tpl_integration_type', 'integration_type_flow', 'in_process_at',
           'shipment_date', 'delivering_date', 'fact_delivery_date')


def now():
    return datetime.now(timezone.utc).isoformat()


def projection(raw):
    """Allowlist only. Never persist raw response, customer, marks or errors."""
    if not isinstance(raw, dict) or not isinstance(raw.get('result'), dict):
        raise ValueError('missing_result')
    card = raw['result']
    result = {k: v for k in SCALARS if isinstance((v := card.get(k)), (str, int, bool)) or k in card and v is None}
    products = card.get('products')
    if not isinstance(products, list):
        raise ValueError('missing_products')
    result['products'] = []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError('invalid_product')
        sku, qty = product.get('sku'), product.get('quantity')
        if isinstance(sku, bool) or not isinstance(sku, (int, str)) or not str(sku).isdigit():
            raise ValueError('invalid_sku')
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError('invalid_quantity')
        row = {'sku': sku, 'quantity': qty}
        if isinstance(product.get('offer_id'), str):
            row['offer_id'] = product['offer_id']
        result['products'].append(row)
    related = card.get('related_postings')
    if related is not None and not isinstance(related, dict):
        raise ValueError('invalid_related_postings')
    links = (related or {}).get('related_posting_numbers', [])
    weights = card.get('related_weight_postings', [])
    for values in (links, weights):
        if not isinstance(values, list) or any(not isinstance(v, str) or not NUMBER.fullmatch(v) for v in values):
            raise ValueError('invalid_related_numbers')
        if len(set(values)) != len(values):
            raise ValueError('duplicate_related_numbers')
    result['related_postings'] = {'related_posting_numbers': links}
    result['related_postings_present'] = 'related_postings' in card and isinstance(related, dict)
    result['related_weight_postings'] = weights
    cancellation = card.get('cancellation')
    if cancellation is not None:
        if not isinstance(cancellation, dict):
            raise ValueError('invalid_cancellation')
        result['cancellation'] = {k: v for k in ('cancel_reason_id', 'cancellation_type', 'cancelled_after_ship')
                                  if isinstance((v := cancellation.get(k)), (str, int, bool))}
    if not isinstance(result.get('status'), str) or not result['status']:
        raise ValueError('missing_status')
    return result


def save(directory, name, value):
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    target = directory / name
    temporary = directory / (name + '.part')
    temporary.write_bytes(payload)
    temporary.replace(target)
    return hashlib.sha256(payload).hexdigest()


async def collect(directory, manifest):
    # Deferred imports let offline projection checks run without app settings.
    import httpx
    from sqlalchemy import text
    from app.core.settings import settings
    from app.db.session import SessionLocal
    from app.services.marketplace_account_service import MarketplaceAccountService
    from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
    from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled

    if not ozon_live_api_enabled():
        raise RuntimeError('live_transport_disabled')
    base = urlsplit(settings.ozon_seller_api_base)
    if (base.scheme, base.netloc, base.path.rstrip('/')) != ('https', 'api-seller.ozon.ru', '') or base.query or base.fragment:
        raise RuntimeError('unexpected_provider_host')
    provider = build_ozon_provider()
    if not isinstance(provider.transport, HttpxOzonMarketplaceTransport):
        raise RuntimeError('not_live_transport')
    plan = json.loads((HERE / 'ozon_read_plan.json').read_text())
    seeds = [r['posting_number'] for r in plan['requests']]
    if len(seeds) != 31 or len(set(seeds)) != 31 or any(not NUMBER.fullmatch(n) for n in seeds):
        raise RuntimeError('invalid_seed_plan')
    if any(plan.get(k) != v for k, v in [('tenant_id', TENANT), ('seller_id', SELLER), ('supply_id', SUPPLY)]):
        raise RuntimeError('seed_scope_mismatch')
    params = {'tenant': uuid.UUID(TENANT), 'seller': uuid.UUID(SELLER), 'supply': uuid.UUID(SUPPLY)}
    async with SessionLocal() as session:
        if session.bind.dialect.name != 'postgresql':
            raise RuntimeError('requires_normal_postgresql_backend')
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        supply = (await session.execute(text("SELECT id,tenant_id,seller_id,warehouse_id,marketplace,source,status FROM fbs_supplies WHERE id=:supply AND tenant_id=:tenant AND seller_id=:seller"), params)).mappings().one_or_none()
        if supply is None or supply['marketplace'] != 'ozon' or supply['source'] != 'wms' or str(supply['warehouse_id']) != WAREHOUSE:
            raise RuntimeError('supply_scope_mismatch')
        positions = (await session.execute(text("SELECT o.id AS order_id,o.external_order_id,o.status,o.wb_status,o.supplier_status,o.warehouse_id,p.id AS position_id,p.product_id,p.ozon_sku,p.offer_id,p.quantity,p.reserved_quantity FROM fbs_orders o JOIN fbs_order_products p ON p.order_id=o.id WHERE o.tenant_id=:tenant AND o.seller_id=:seller AND o.supply_id=:supply AND o.marketplace='ozon' ORDER BY o.external_order_id,p.id"), params)).mappings().all()
        if len(positions) != 31 or {p['external_order_id'] for p in positions} != set(seeds):
            raise RuntimeError('draft_composition_changed')
        if any(p['warehouse_id'] != supply['warehouse_id'] for p in positions):
            raise RuntimeError('warehouse_scope_mismatch')
        # Credential use stays inside the normal application boundary.
        client_id, api_key = await MarketplaceAccountService(session).stored_credentials(params['tenant'], params['seller'])
        snapshot = {'captured_at': now(), 'supply': {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in supply.items()},
                    'positions': [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in p.items()} for p in positions]}
        await session.rollback()  # End DB snapshot before any network wait.
    manifest['scope_snapshot_sha256'] = save(directory, 'scope_snapshot.json', snapshot)
    queue, seen = list(seeds), set()
    metadata = {}

    async def response_hook(response):
        # Deliberately no request headers, request body, response body or URL.
        metadata.update(http_status=response.status_code, server_date=response.headers.get('Date'))

    async with httpx.AsyncClient(event_hooks={'response': [response_hook]}) as client:
        provider.transport = HttpxOzonMarketplaceTransport(client=client)
        while queue and len(seen) < MAX_CARDS:
            number = queue.pop(0)
            if number in seen:
                continue
            seen.add(number)
            metadata.clear()
            entry = {'posting_number': number, 'started_at_utc': now(), 'endpoint': ENDPOINT,
                     'semantic_operation': 'read', 'http_method': 'POST'}
            try:
                raw = await provider.call(client_id=client_id, api_key=api_key, path=ENDPOINT,
                    payload={'posting_number': number, 'with': plan['requests'][0]['with']})
                card = projection(raw)
                if card['posting_number'] != number:
                    raise ValueError('posting_identity_mismatch')
                links = card['related_postings']['related_posting_numbers'] + card['related_weight_postings']
                for child in links:
                    if child not in seen and child not in queue:
                        queue.append(child)
                entry.update(status='ok', card=card)
                if not card['products'] or not card['related_postings_present']:
                    entry.update(status='unknown', failure_code='incomplete_products_or_split')
            except Exception as exc:
                entry.update(status='unknown', error_type=type(exc).__name__, failure_code=failure_code(exc))
                # Raw provider payload/message may contain sensitive data.
            entry.update(metadata)
            entry['finished_at_utc'] = now()
            filename = 'posting-' + number + '.json'
            digest = save(directory, filename, entry)
            manifest['requests'].append({'posting_number': number, 'file': filename, 'sha256': digest, 'status': entry['status']})
            save(directory, 'manifest.json', manifest)
    manifest['unread_postings'] = queue
    manifest['finished_at_utc'] = now()
    manifest['execution_status'] = ('READ_COMPLETE_REQUIRES_ACCOUNTING_PLAN' if not queue and all(r['status'] == 'ok' for r in manifest['requests']) else 'INCOMPLETE_UNKNOWN_NO_MUTATION')
    save(directory, 'manifest.json', manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='NEW directory for sanitized evidence; existing directories are refused')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'tenant_id': TENANT, 'seller_id': SELLER, 'supply_id': SUPPLY,
                'started_at_utc': now(), 'execution_status': 'STARTED_NOT_PROOF', 'requests': [],
                'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'seed_plan_sha256': hashlib.sha256((HERE / 'ozon_read_plan.json').read_bytes()).hexdigest()}
    save(args.output, 'manifest.json', manifest)
    try:
        asyncio.run(collect(args.output, manifest))
    except Exception as exc:
        manifest.update(execution_status='NOT_COMPLETED_NO_MUTATION', error_type=type(exc).__name__, failure_code=failure_code(exc), finished_at_utc=now())
        save(args.output, 'manifest.json', manifest)
    print(json.dumps({'execution_status': manifest['execution_status'], 'cards': len(manifest['requests']), 'output': str(args.output)}))
    return 0 if manifest['execution_status'] == 'READ_COMPLETE_REQUIRES_ACCOUNTING_PLAN' else 2


if __name__ == '__main__':
    sys.exit(main())
