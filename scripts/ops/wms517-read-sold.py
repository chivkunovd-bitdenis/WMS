#!/usr/bin/env python3
"""Read AVpack WB sales through the existing application; never prepare/submit.

Runs the accepted reader in an ephemeral Python process in the API container.
No files are installed on the server. Application settings stay inside the
container. The result includes row IDs and CIS hashes, never credentials or
signatures. Redis request slots/completed-report cache are the reader's normal
bookkeeping; business tables are only read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELLER = "0b8da5d8-f43a-42f5-a2ec-43173ea844bd"
TENANT = "d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe"
ACCEPTED_HASHES = {
    'app.services.wb_sales_report': '247825c8f13fac3ef05e9bc4ccafd37cc6924bd8d0163080737c4614d3f3817a',
    'wms517_audit_repository': '42a8b2830584e81e38bda9e95aca15cc296458703e47bdd4452702139a307994',
}

REMOTE = r'''
import asyncio, hashlib, json, sys, types, uuid
from collections import Counter
from datetime import UTC, datetime
from sqlalchemy import select
from app.db.session import SessionLocal, engine

# Exact accepted source is interpreted in this process only, not installed.
for name, source in SOURCES.items():
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, '<accepted-wms517-reader>', 'exec'), module.__dict__)

from app.services import wb_sales_report as reader
from wms517_audit_repository import WithdrawalScope, eligible_rows
from app.models.seller import Seller
from app.models.billing import BillingProfile
from app.models.marking_withdrawal import WithdrawalItem, WithdrawalOperation

trace = []
native_client = reader.httpx.AsyncClient
async def observe(response):
    entry = {'dateFrom': response.request.url.params.get('dateFrom'),
             'flag': response.request.url.params.get('flag'),
             'status': response.status_code, 'at': datetime.now(UTC).isoformat()}
    if response.status_code == 200:
        await response.aread()
        try:
            page = json.loads(response.content, parse_int=reader._json_integer,
                              parse_float=str, parse_constant=str)
            if isinstance(page, list):
                entry['rows'] = len(page)
                entry['terminal_empty'] = not page
                if page and isinstance(page[-1], dict):
                    entry['lastChangeDate'] = page[-1].get('lastChangeDate')
                entry['kinds'] = dict(Counter(str(x.get('saleID', ''))[:1]
                                              for x in page if isinstance(x, dict)))
        except (ValueError, UnicodeDecodeError):
            entry['invalid_json'] = True
    trace.append(entry)
    print(json.dumps({'page': entry}, ensure_ascii=False), flush=True)

class ObservedClient(native_client):
    def __init__(self, **kwargs):
        super().__init__(event_hooks={'response': [observe]}, **kwargs)

reader.httpx.AsyncClient = ObservedClient

async def main():
    result = {'seller_id': SELLER, 'tenant_id': TENANT, 'started_at': datetime.now(UTC).isoformat(),
              'complete': False, 'external_actions': 'GET supplier/sales only',
              'requests': trace, 'source_sha256': SOURCE_HASHES}
    seller_id, tenant_id = uuid.UUID(SELLER), uuid.UUID(TENANT)
    scope = WithdrawalScope(tenant_id, seller_id, uuid.UUID(int=0))
    try:
        async with SessionLocal() as session:
            seller = await session.scalar(select(Seller).where(Seller.id == seller_id,
                                                               Seller.tenant_id == tenant_id))
            if seller is None:
                raise ValueError('exact_seller_not_found')
            result['seller_name'] = seller.name
            profile = await session.scalar(select(BillingProfile).where(
                BillingProfile.seller_id == seller_id, BillingProfile.tenant_id == tenant_id))
            result['participant_inn_present'] = bool(profile and profile.inn)
            candidates = (await session.execute(eligible_rows(scope))).all()
            orders = {order.id: reader.SalesOrder(order.id, order.wb_rid, order.created_at_wb)
                      for marking, order, supply in candidates}
            result['candidate_count'] = len(candidates)
            result['distinct_order_count'] = len(orders)
            report = await reader.read_sales_report(session, tenant_id=tenant_id,
                seller_id=seller_id, orders=list(orders.values()), fresh=True)
            # Refresh local eligibility after vendor waits, as preparation does.
            candidates = (await session.execute(eligible_rows(scope))).all()
            claimed = set(await session.scalars(select(WithdrawalItem.marking_id)
                .join(WithdrawalOperation, WithdrawalOperation.id == WithdrawalItem.operation_id)
                .where(WithdrawalOperation.seller_id == seller_id,
                       WithdrawalOperation.tenant_id == tenant_id, WithdrawalItem.holds_claim.is_(True))))
            rows = []
            for marking, order, supply in candidates:
                sale = report.by_rid.get(order.wb_rid)
                row = {'marking_id': str(marking.id), 'order_id': str(order.id),
                       'srid': order.wb_rid, 'cis_sha256': hashlib.sha256(marking.value.encode()).hexdigest(),
                       'active_claim': marking.id in claimed, 'sold': sale is not None}
                if sale is not None:
                    row['sale'] = {key: sale.get(key) for key in
                                   ('saleID', 'date', 'lastChangeDate', 'finishedPrice')}
                    try:
                        row['product_cost_kopecks'] = reader.sale_cost(sale)
                    except reader.WbPriceDataError as exc:
                        row['price_error'] = exc.code
                else:
                    evidence = report.exclusion_evidence(order)
                    row['exclusion'] = evidence['code']
                    row['source_kinds'] = [str(x.get('saleID', ''))[:1]
                                           for x in evidence['raw_sales']]
                rows.append(row)
            result.update(complete=not report.coverage_missing, received_at=report.received_at.isoformat(),
                          date_from=report.date_from, pages=report.pages, source_row_count=report.row_count,
                          coverage_missing=[str(x) for x in report.coverage_missing], rows=rows,
                          sold_count=sum(x['sold'] for x in rows),
                          ready_count=sum(x['sold'] and not x['active_claim'] and 'price_error' not in x
                                          for x in rows),
                          unique_cis_count=len({x['cis_sha256'] for x in rows}),
                          exclusion_counts=dict(Counter(x.get('exclusion', x.get('price_error', 'sale'))
                                                        for x in rows)))
    except Exception as exc:
        # Do not serialize arbitrary exceptions, settings, HTTP headers or body.
        result['error_type'] = type(exc).__name__
        if isinstance(exc, reader.WbSalesError):
            result['error_code'] = str(exc)
    finally:
        result['finished_at'] = datetime.now(UTC).isoformat()
        await engine.dispose()
    print('WMS517_RESULT=' + json.dumps(result, ensure_ascii=False, default=str), flush=True)

asyncio.run(main())
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@194.87.96.144')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = {
        'app.services.wb_sales_report': (ROOT / 'backend/app/services/wb_sales_report.py').read_text(),
        'wms517_audit_repository': (ROOT / 'backend/app/db/withdrawal_repository.py').read_text(),
    }
    hashes = {name: hashlib.sha256(source.encode()).hexdigest() for name, source in sources.items()}
    if hashes != ACCEPTED_HASHES:
        raise SystemExit('Reader differs from the accepted WMS-517 product; review it before running.')
    prefix = (f'SOURCES = {sources!r}\nSOURCE_HASHES = {hashes!r}\n'
              f'SELLER = {SELLER!r}\nTENANT = {TENANT!r}\n')
    process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', args.host,
                                'docker exec -i wms_prod-api-1 python -'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(prefix + REMOTE)
    process.stdin.close()
    saved = False
    for line in process.stdout:
        if line.startswith('WMS517_RESULT='):
            result = json.loads(line.removeprefix('WMS517_RESULT='))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({key: value for key, value in result.items() if key != 'rows'},
                             ensure_ascii=False, indent=2), flush=True)
            saved = True
        elif line.startswith('{"page":'):
            print(line.rstrip(), flush=True)
    code = process.wait()
    if code or not saved:
        # stderr may contain connection settings: report a type/status only.
        raise SystemExit(f'Remote read failed: exit={code}, result_saved={saved}')


if __name__ == '__main__':
    main()
