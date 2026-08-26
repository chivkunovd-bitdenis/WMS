from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.operation_fact import OperationFact
from app.services.operation_fact_service import (
    OperationFactError,
    OperationFactLineInput,
    record_marketplace_unload,
    record_packaging_event,
    write_operation_fact,
)


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()
    session.begin_nested = Mock(side_effect=_nested_transaction)
    return session


@asynccontextmanager
async def _nested_transaction():
    yield


@pytest.mark.asyncio
async def test_writer_creates_immutable_fact_with_item_lines() -> None:
    session = _session()
    session.scalar = AsyncMock(return_value=None)
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    product_id = uuid.uuid4()

    fact = await write_operation_fact(
        session,
        tenant_id=tenant_id,
        operation_code="fbs_pick",
        source_kind="fbs_order_pick_event",
        source_event_id=uuid.uuid4(),
        idempotency_key="pick:1",
        seller_id=uuid.uuid4(),
        seller_name_snapshot="Seller",
        warehouse_id=uuid.uuid4(),
        marketplace="wb",
        document_type="fbs_supply",
        document_id=uuid.uuid4(),
        document_number_snapshot="S-1",
        actor_user_id=actor_id,
        actor_name_snapshot="picker@example.test",
        occurred_at=datetime.now(UTC),
        item_quantity=1,
        lines=[
            OperationFactLineInput(
                product_id=product_id,
                sku_snapshot="sku",
                product_name_snapshot="Product",
                item_quantity=1,
            )
        ],
    )

    assert isinstance(fact, OperationFact)
    assert fact.source == "user"
    assert fact.actor_user_id == actor_id
    assert fact.item_quantity == 1
    assert len(fact.lines) == 1
    assert fact.lines[0].product_id == product_id
    session.add.assert_called_once_with(fact)


@pytest.mark.asyncio
async def test_writer_returns_existing_source_tuple_without_duplicate() -> None:
    session = _session()
    existing = OperationFact(
        tenant_id=uuid.uuid4(),
        operation_code="fbs_pick",
        source_kind="fbs_order_pick_event",
        source_event_id=uuid.uuid4(),
        document_type="fbs_supply",
        document_id=uuid.uuid4(),
        source="system",
        occurred_at=datetime.now(UTC),
        item_quantity=1,
    )
    session.scalar = AsyncMock(return_value=existing)

    result = await write_operation_fact(
        session,
        tenant_id=existing.tenant_id,
        operation_code=existing.operation_code,
        source_kind=existing.source_kind,
        source_event_id=existing.source_event_id,
        document_type=existing.document_type,
        document_id=existing.document_id,
        occurred_at=existing.occurred_at,
        item_quantity=1,
    )

    assert result is existing
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_writer_rejects_user_source_without_actor_and_mismatched_lines() -> None:
    session = _session()
    session.scalar = AsyncMock(return_value=None)
    kwargs = dict(
        session=session,
        tenant_id=uuid.uuid4(),
        operation_code="inbound_completed",
        source_kind="inbound_intake_request",
        source_event_id=uuid.uuid4(),
        document_type="inbound_intake",
        document_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        item_quantity=2,
    )
    with pytest.raises(OperationFactError, match="user_actor_required"):
        await write_operation_fact(**kwargs, source="user")
    with pytest.raises(OperationFactError, match="line_quantity_mismatch"):
        await write_operation_fact(
            **kwargs,
            lines=[
                OperationFactLineInput(
                    product_id=None, sku_snapshot=None, product_name_snapshot=None, item_quantity=1
                )
            ],
        )


@pytest.mark.asyncio
async def test_marketplace_cancel_retry_returns_same_reversal_and_preserves_actor() -> None:
    tenant_id = uuid.uuid4()
    request_id = uuid.uuid4()
    completed_by = uuid.uuid4()
    cancelled_by = uuid.uuid4()
    product_id = uuid.uuid4()
    product = SimpleNamespace(
        id=product_id,
        seller_id=uuid.uuid4(),
        sku_code="unload-sku",
        name="Unload product",
        seller=SimpleNamespace(name="Seller"),
    )
    request = SimpleNamespace(
        id=request_id,
        tenant_id=tenant_id,
        seller_id=product.seller_id,
        seller=product.seller,
        warehouse_id=uuid.uuid4(),
        marketplace="wb",
        document_number="U-1",
        lines=[SimpleNamespace(product_id=product_id, product=product)],
    )
    shipped_session = _session()
    shipped_session.scalar = AsyncMock(side_effect=[None, None])
    shipped = await record_marketplace_unload(
        shipped_session,
        request=request,
        distributed={product_id: 2},
        occurred_at=datetime.now(UTC),
        performer_id=completed_by,
    )
    shipped.id = uuid.uuid4()
    reversal_session = _session()
    reversal_session.scalar = AsyncMock(side_effect=[shipped.id, None, None, shipped])
    reversal = await record_marketplace_unload(
        reversal_session,
        request=request,
        distributed={product_id: 2},
        occurred_at=datetime.now(UTC),
        performer_id=cancelled_by,
        reversal=True,
    )
    retry_session = _session()
    retry_session.scalar = AsyncMock(return_value=reversal)
    retried = await record_marketplace_unload(
        retry_session,
        request=request,
        distributed={product_id: 2},
        occurred_at=datetime.now(UTC),
        performer_id=uuid.uuid4(),
        reversal=True,
    )

    assert reversal.reversal_of_id == shipped.id
    assert reversal.actor_user_id == cancelled_by
    assert retried is reversal
    assert retry_session.add.call_count == 0


@pytest.mark.asyncio
async def test_packaging_event_source_tuple_does_not_create_duplicate() -> None:
    tenant_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = SimpleNamespace(
        id=product_id,
        seller_id=uuid.uuid4(),
        sku_code="pack-sku",
        name="Pack product",
        seller=SimpleNamespace(name="Seller"),
    )
    task = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        warehouse_id=uuid.uuid4(),
        document_number="P-1",
    )
    event = SimpleNamespace(
        id=uuid.uuid4(),
        action="manual_pack",
        quantity=1,
        product=product,
        product_id=product_id,
        created_by_user_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )
    line = SimpleNamespace(product=product)
    session = _session()
    session.scalar = AsyncMock(side_effect=[None, None, None])
    fact = await record_packaging_event(session, task=task, event=event, line=line)
    retry_session = _session()
    retry_session.scalar = AsyncMock(side_effect=[None, fact])
    retried = await record_packaging_event(retry_session, task=task, event=event, line=line)

    assert retried is fact
    assert retry_session.add.call_count == 0
