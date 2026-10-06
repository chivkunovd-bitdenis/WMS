"""One bounded owner-authorized carriage status refresh; run inside production API.

Reads Ozon first. Only closed, nonpartial, already-handed-over WMS supplies in
the explicit scope can move in_delivery -> done. No handoff/stock/billing calls.
Default is read-only. --apply is required for the short local transaction.
"""
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models.fbs_supply import FbsSupply
from app.models.seller import Seller
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_provider_factory import build_ozon_provider

TENANT = uuid.UUID('7b98a8aa-c03c-4649-9677-a645be45c622')
SELLER = uuid.UUID('115c765e-bafa-4909-8dfd-0681f15cc620')
IDS = {uuid.UUID(x) for x in (
    'a76fdfc4-e806-4da0-a8b5-e8d97d5d6151',
    '9d1aefa9-9b61-41e4-9268-3dcae6a0a43e',
    '7f710af5-d34c-4562-b98b-173e68408001',
    'b2300a8a-ebeb-4d99-887e-62533f3a335e',
    'c2633720-6a01-4b59-a1cf-8eb074bb2ce6',
    'c04e6053-573a-4d7c-b051-e3fc3b8d70f6',
    'cb97ca23-3d08-4bb9-9ba8-ca136eef88f8',
    'c5db320d-fbae-4669-b363-81b8a858538c',
    'c5d1a19f-2a9b-4725-ae14-e36e5afa1014',
)}


async def main():
    observed_at = datetime.now(UTC)
    async with SessionLocal() as session:
        seller = await session.get(Seller, SELLER)
        assert seller and seller.tenant_id == TENANT and 'Бугаев' in seller.name
        supplies = list(await session.scalars(select(FbsSupply).where(
            FbsSupply.id.in_(IDS), FbsSupply.tenant_id == TENANT,
            FbsSupply.seller_id == SELLER, FbsSupply.marketplace == 'ozon',
        )))
        assert {s.id for s in supplies} == IDS
        snapshots = {s.id: {
            'id': str(s.id), 'name': s.name, 'before': s.status,
            'external': s.external_supply_id or s.wb_supply_id,
            'delivered_at': s.delivered_at.isoformat() if s.delivered_at else None,
        } for s in supplies}
        cid, key = await MarketplaceAccountService(session).stored_credentials(TENANT, SELLER)
    provider = build_ozon_provider()
    for entry in snapshots.values():
        external = entry['external']
        if not str(external).isdigit():
            entry['skip_reason'] = 'no_confirmed_carriage_id'
            continue
        raw = await provider.call(client_id=cid, api_key=key,
            path='/v1/carriage/get', payload={'carriage_id': int(external)})
        assert raw.get('carriage_id') == int(external)
        entry['ozon'] = {k: raw.get(k) for k in (
            'carriage_id', 'status', 'is_partial',
            'has_postings_for_next_carriage', 'updated_at')}
        entry['eligible'] = (
            raw.get('status') == 'closed' and raw.get('is_partial') is False
            and raw.get('has_postings_for_next_carriage') is False
            and entry['delivered_at'] is not None
            and entry['before'] in ('in_delivery', 'done')
        )
    print(json.dumps({'phase': 'preflight', 'observed_at': observed_at.isoformat(),
        'supplies': list(snapshots.values())}, ensure_ascii=False), flush=True)
    if '--apply' not in sys.argv:
        return
    # Only the carrier status changes. Customer-delivery/order statuses keep
    # their independent meaning. Lock and revalidate after all network reads.
    changed = []
    async with SessionLocal() as session:
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        rows = list(await session.scalars(select(FbsSupply).where(
            FbsSupply.id.in_(IDS), FbsSupply.tenant_id == TENANT,
            FbsSupply.seller_id == SELLER, FbsSupply.marketplace == 'ozon',
        ).order_by(FbsSupply.id).with_for_update()))
        assert {s.id for s in rows} == IDS
        for row in rows:
            prior = snapshots[row.id]
            assert (row.external_supply_id or row.wb_supply_id) == prior['external']
            assert row.delivered_at and row.delivered_at.isoformat() == prior['delivered_at']
            assert row.status in (prior['before'], 'done')
            if prior.get('eligible') and row.status == 'in_delivery':
                row.status = 'done'
                row.last_wb_sync_at = observed_at
                changed.append(str(row.id))
        assert all(isinstance(obj, FbsSupply) for obj in session.dirty)
        assert not session.new and not session.deleted
        await session.commit()
    async with SessionLocal() as session:
        after = list(await session.scalars(select(FbsSupply).where(FbsSupply.id.in_(IDS))))
        for row in after:
            expected = 'done' if snapshots[row.id].get('eligible') else snapshots[row.id]['before']
            assert row.status == expected
        print(json.dumps({'phase': 'committed_readback', 'changed': changed,
            'supplies': [{'id': str(s.id), 'name': s.name, 'status': s.status,
                         'last_sync': s.last_wb_sync_at.isoformat() if s.last_wb_sync_at else None}
                         for s in after]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'result': 'not_confirmed'}), flush=True)
        raise SystemExit(1)
