from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.operation_fact import OperationFact, OperationFactCutover
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.operation_fact_recovery_service import (
    existing_operation_fact_count,
    recover_operation_facts,
)
from app.services.operation_fact_service import OperationFactError, write_operation_fact
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _scan_product,
    _seed_pick_supply,
)


@pytest.mark.asyncio
async def test_recovery_preflight_counts_only_requested_tenant_facts() -> None:
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=range(7))

    result = await existing_operation_fact_count(session, uuid.uuid4())

    assert result == 7
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_key_cannot_be_reused_for_another_source_tuple() -> None:
    tenant_id = uuid.uuid4()
    existing = OperationFact(
        tenant_id=tenant_id,
        operation_code="fbs_pick",
        source_kind="fbs_order_pick_event",
        source_event_id=uuid.uuid4(),
        idempotency_key="retry-key",
        document_type="fbs_supply",
        document_id=uuid.uuid4(),
        source="system",
        occurred_at=datetime.now(UTC),
        item_quantity=1,
    )
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, existing])

    with pytest.raises(OperationFactError, match="idempotency_key_reused"):
        await write_operation_fact(
            session,
            tenant_id=tenant_id,
            operation_code="fbs_pick",
            source_kind="fbs_order_pick_event",
            source_event_id=uuid.uuid4(),
            idempotency_key="retry-key",
            document_type="fbs_supply",
            document_id=uuid.uuid4(),
            occurred_at=datetime.now(UTC),
            item_quantity=1,
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_wb_fbs_pick_undo_and_redo_write_three_real_source_facts(async_client) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BILLING-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"BILLING-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=4))],
        barcode=barcode,
    )
    first = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key="billing-pick-1",
    )
    assert first.status_code == 200, first.text
    undo_key = "billing-undo-1"
    undo = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": undo_key},
    )
    assert undo.status_code == 200, undo.text
    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": undo_key},
    )
    assert retry.status_code == 200, retry.text
    redone = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key="billing-pick-2",
    )
    assert redone.status_code == 200, redone.text

    async with SessionLocal() as session:
        facts = list(
            (
                await session.scalars(
                    select(OperationFact)
                    .where(OperationFact.tenant_id == tenant_id)
                    .order_by(OperationFact.occurred_at, OperationFact.id)
                )
            ).all()
        )

    assert [fact.operation_code for fact in facts] == [
        "fbs_pick",
        "fbs_pick_reversal",
        "fbs_pick",
    ]
    assert facts[1].reversal_of_id == facts[0].id
    assert facts[0].item_quantity == facts[1].item_quantity == facts[2].item_quantity == 1


@pytest.mark.asyncio
async def test_recovery_scopes_durable_unload_and_system_cancel_to_period_and_sources(
    async_client,
) -> None:
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        tenant = Tenant(name="Recovery tenant", slug=f"recovery-{uuid.uuid4().hex[:12]}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Recovery seller")
        warehouse = Warehouse(tenant_id=tenant.id, name="Recovery warehouse", code="RECOVERY")
        session.add_all([seller, warehouse])
        await session.flush()
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Recovery product",
            sku_code=f"RECOVERY-{uuid.uuid4().hex[:12]}",
        )
        session.add(product)
        await session.flush()
        session.add(OperationFactCutover(id=1, occurred_at=now - timedelta(hours=3)))
        selected = MarketplaceUnloadRequest(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            marketplace="wb",
            status="shipped",
            document_number="RECOVERY-SELECTED",
            shipped_at=now - timedelta(minutes=5),
        )
        outside_period = MarketplaceUnloadRequest(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            marketplace="wb",
            status="shipped",
            document_number="RECOVERY-OUTSIDE",
            shipped_at=now - timedelta(hours=2),
        )
        session.add_all([selected, outside_period])
        await session.flush()
        session.add_all(
            [
                MarketplaceUnloadLine(request_id=selected.id, product_id=product.id, quantity=2),
                MarketplaceUnloadLine(
                    request_id=outside_period.id, product_id=product.id, quantity=3
                ),
            ]
        )
        await session.commit()
        tenant_id, selected_id, outside_id = tenant.id, selected.id, outside_period.id

    scope = {"marketplace_unload_request": {selected_id, outside_id}}
    async with SessionLocal() as session:
        first = await recover_operation_facts(
            session,
            tenant_id,
            period_start=now - timedelta(minutes=30),
            period_end=now + timedelta(minutes=30),
            source_event_ids=scope,
        )
        await session.commit()
    assert (first.found, first.created, first.already_present, first.conflicted) == (1, 1, 0, 0)

    async with SessionLocal() as session:
        selected = await session.get(MarketplaceUnloadRequest, selected_id)
        assert selected is not None
        selected.cancelled_at = now
        await session.commit()

    async with SessionLocal() as session:
        second = await recover_operation_facts(
            session,
            tenant_id,
            period_start=now - timedelta(minutes=30),
            period_end=now + timedelta(minutes=30),
            source_event_ids=scope,
        )
        await session.commit()
        facts = list(
            (
                await session.scalars(
                    select(OperationFact)
                    .where(OperationFact.tenant_id == tenant_id)
                    .order_by(OperationFact.operation_code)
                )
            ).all()
        )
    assert (second.found, second.created, second.already_present, second.conflicted) == (2, 1, 1, 0)
    assert [fact.operation_code for fact in facts] == [
        "marketplace_outbound_completed",
        "marketplace_outbound_reversal",
    ]
    assert facts[1].source == "system"
    assert facts[1].actor_user_id is None

    async with SessionLocal() as session:
        repeat = await recover_operation_facts(
            session,
            tenant_id,
            period_start=now - timedelta(minutes=30),
            period_end=now + timedelta(minutes=30),
            source_event_ids=scope,
        )
        await session.commit()
    assert (repeat.found, repeat.created, repeat.already_present, repeat.conflicted) == (2, 0, 2, 0)
