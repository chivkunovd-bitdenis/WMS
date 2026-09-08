"""WMS-092: skip is informational; saved labels remain printable after handoff."""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from test_fbs_packing_selection import inventory_snapshot, seed_selection
from test_fbs_shipment_warehouse_sc import _mock_actual_composition_from_local_links

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import MarkingCode
from app.services import fbs_order_tape_print_service as tape_svc


@pytest.mark.asyncio
@pytest.mark.parametrize('reprint', [False, True])
async def test_skip_pack_handoff_reuses_saved_code_without_new_pool_or_wb_write(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, reprint: bool,
) -> None:
    monkeypatch.setattr(settings, 'e2e_mock_wb_marketplace_supplies', True)
    _mock_actual_composition_from_local_links(monkeypatch)
    headers, supply_id, orders = await seed_selection(async_client)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        for seeded in orders:
            order = await session.get(FbsOrder, seeded.order_id)
            assert order is not None
            order.wb_supply_id = supply.wb_supply_id
        await session.execute(delete(FbsPackagingFulfillment).where(
            FbsPackagingFulfillment.packaging_task_id == supply.packaging_task_id,
        ))
        await session.commit()
        pool_before = list((await session.execute(select(MarkingCode.id, MarkingCode.status)
                                                 .order_by(MarkingCode.id))).all())
    allocate = AsyncMock(side_effect=AssertionError('skip must not issue a new code'))
    attach = AsyncMock(side_effect=AssertionError('saved print must not resend metadata'))
    monkeypatch.setattr(tape_svc.mc_svc, 'print_codes_for_packaging_line', allocate)
    monkeypatch.setattr(tape_svc.marking_svc, 'attach_order_meta_to_wb_and_sync', attach)
    base = f'/operations/fbs-supplies/{supply_id}'
    before = await inventory_snapshot()
    for _ in range(2):
        skipped = await async_client.post(base + '/honest-sign-skip', headers=headers)
        assert skipped.status_code == 200, skipped.text
        assert skipped.json()['supply']['honest_sign_skipped'] is True
        assert skipped.json()['blockers'] == []
        assert await inventory_snapshot() == before
    packed = await async_client.post(
        f'/operations/packaging-tasks/{orders[0].packaging_task_id}/pack-all-and-complete',
        headers=headers,
    )
    assert packed.status_code == 200, packed.text
    after_pack = await inventory_snapshot()
    assert after_pack[:3] == before[:3]
    preflight = await async_client.post(base + '/delivery-preflight', headers=headers)
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()['can_deliver'] is True
    body = {'idempotency_key': str(uuid.uuid4()),
            'confirmed_preflight_version': preflight.json()['version']}
    delivered = await async_client.post(base + '/deliver', headers=headers, json=body)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()['supply']['status'] == 'in_delivery'
    shipped = await inventory_snapshot()
    assert sorted(row[1] for row in shipped[0]) == [7, 9, 9]
    assert shipped[1] == []
    assert shipped[2] == before[2] + 5
    repeated = await async_client.post(base + '/deliver', headers=headers, json=body)
    assert repeated.status_code == 200, repeated.text
    assert await inventory_snapshot() == shipped
    printed = await async_client.post(base + '/order-print-tape', headers=headers, json={
        'order_ids': [str(order.order_id) for order in orders],
        'layout_json': {'units': [{'block': 'cz', 'copies': 2}]},
        'allow_partial': False, 'include_order_qr': False, 'reprint': reprint,
    })
    assert printed.status_code == 200, printed.text
    result = printed.json()
    assert result['order_errors'] == []
    assert result['shortage'] == 0
    by_id = {row['order_id']: row for row in result['orders']}
    assert by_id[str(orders[0].order_id)]['codes'] == ['010460043993125321KIZUSED085']
    for seeded in orders[1:]:
        assert by_id[str(seeded.order_id)]['codes'] == []
        assert by_id[str(seeded.order_id)]['requires_honest_sign'] is False
    assert await inventory_snapshot() == shipped
    async with SessionLocal() as session:
        assert list((await session.execute(select(MarkingCode.id, MarkingCode.status)
                                          .order_by(MarkingCode.id))).all()) == pool_before
    allocate.assert_not_awaited()
    attach.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('source, linked', [('operator', True), ('pool', False)])
async def test_skipped_supply_does_not_replace_unprintable_saved_marking(
    monkeypatch: pytest.MonkeyPatch, source: str, linked: bool,
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    order = SimpleNamespace(
        id=uuid.uuid4(), wb_order_id=12, product_id=uuid.uuid4(),
        product=SimpleNamespace(requires_honest_sign=True), required_meta_json=['sgtin'],
    )
    supply = SimpleNamespace(
        marketplace='wb', status='in_delivery', packaging_task_id=uuid.uuid4(),
        document_number='WMS-092', honest_sign_skipped_at=datetime.now(UTC),
        orders=[order, SimpleNamespace(id=uuid.uuid4())],
    )
    marking = SimpleNamespace(source=source, marking_code=SimpleNamespace() if linked else None)
    monkeypatch.setattr(tape_svc, '_load_supply', AsyncMock(return_value=supply))
    monkeypatch.setattr(
        tape_svc, '_line_by_product', AsyncMock(return_value={order.product_id: object()}),
    )
    monkeypatch.setattr(tape_svc, '_existing_sgtin_marking', lambda _: marking)
    allocate = AsyncMock()
    attach = AsyncMock()
    monkeypatch.setattr(tape_svc.mc_svc, 'print_codes_for_packaging_line', allocate)
    monkeypatch.setattr(tape_svc.marking_svc, 'attach_order_meta_to_wb_and_sync', attach)
    result = await tape_svc.print_fbs_order_tape(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), order_ids=[order.id],
        layout={'units': [{'block': 'cz', 'copies': 1}]},
        allow_partial=False, include_order_qr=False, reprint=False,
        actor_user_id=uuid.uuid4(), http_client=SimpleNamespace(),
    )
    assert result.orders == []
    assert result.order_errors[0].code == (
        'operator_kiz_print_forbidden' if source == 'operator' else 'nothing_to_reprint'
    )
    allocate.assert_not_awaited()
    attach.assert_not_awaited()
