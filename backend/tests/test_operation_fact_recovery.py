from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.operation_fact import OperationFact
from app.services.operation_fact_recovery_service import existing_operation_fact_count
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
