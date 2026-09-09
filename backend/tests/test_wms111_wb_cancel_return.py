"""WMS-111 + WMS-112: automatic WB return document on cancel-after-transfer.

These tests exercise only the code path — no real WB webhook is fired in this
session. The contract they defend:

  * cancel BEFORE transfer never creates a return document;
  * cancel AFTER transfer creates ONE return document, and a retry with the
    same wb_order_id does NOT create a duplicate;
  * the created document leaves stock alone (posted_qty stays 0, no inventory
    movements) — physical acceptance is a separate operator action;
  * cancel-time is stored honestly: from WB payload's `cancelledAt` when
    present, otherwise the moment WMS observed the cancel, and the source is
    recorded next to it so a reader can always tell them apart.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_NEW,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_cancel_return_document_service import (
    CANCEL_TIME_SOURCE_RECEIVED_AT,
    CANCEL_TIME_SOURCE_WB_PAYLOAD,
    cancel_return_marker,
    cancel_time_from_row,
    ensure_cancel_return_document,
    has_cancel_return_marker,
    maybe_create_cancel_return_document,
    was_transferred,
)
from app.services.inbound_intake_service import OPERATION_TYPE_RETURN, STATUS_DRAFT


async def _seed_tenant(session: AsyncSession, *, suffix: str) -> uuid.UUID:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=f"Tenant {suffix}",
        slug=f"tenant-{suffix}",
        billing_enabled_from=date(2020, 1, 1),
    )
    session.add(tenant)
    await session.flush()
    return tenant.id


async def _seed_warehouse(session: AsyncSession, tenant_id: uuid.UUID, suffix: str) -> uuid.UUID:
    wh = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=f"WH {suffix}",
        code=f"wh-{suffix[-8:]}",
    )
    session.add(wh)
    await session.flush()
    return wh.id


async def _seed_seller(session: AsyncSession, tenant_id: uuid.UUID, suffix: str) -> uuid.UUID:
    seller = Seller(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=f"Seller {suffix}",
    )
    session.add(seller)
    await session.flush()
    return seller.id


async def _seed_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    suffix: str,
) -> uuid.UUID:
    product = Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=f"Product {suffix}",
        sku_code=f"SKU-{suffix}",
        wb_barcode=f"BAR-{suffix}",
    )
    session.add(product)
    await session.flush()
    return product.id


async def _seed_supply(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    handed_over: bool,
    handover_at: datetime,
) -> FbsSupply:
    supply = FbsSupply(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="wb",
        name="Test supply",
        delivery_type="warehouse_sc",
        status=FBS_SUPPLY_STATUS_IN_DELIVERY if handed_over else FBS_SUPPLY_STATUS_ASSEMBLING,
        delivered_at=handover_at if handed_over else None,
    )
    session.add(supply)
    await session.flush()
    if handed_over:
        session.add(
            FbsWbOperation(
                tenant_id=tenant_id,
                seller_id=seller_id,
                operation_kind="supply_deliver",
                idempotency_key=f"wms111-{supply.id}",
                local_entity_type="fbs_supply",
                local_entity_id=supply.id,
                state="confirmed",
                confirmed_at=handover_at,
                request_summary_json={},
            )
        )
        await session.flush()
    return supply


async def _seed_order(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    supply: FbsSupply | None,
    wb_order_id: int,
    status: str = FBS_ORDER_STATUS_NEW,
) -> FbsOrder:
    now = datetime.now(UTC)
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        marketplace="wb",
        wb_order_id=wb_order_id,
        wb_barcode=f"BAR-{wb_order_id}",
        wb_article=f"ART-{wb_order_id}",
        supply_id=supply.id if supply is not None else None,
        status=status,
        created_at_wb=now - timedelta(hours=3),
        deadline_at=now + timedelta(days=1),
        mapping_status="mapped",
        reserve_status="reserved",
    )
    session.add(order)
    await session.flush()
    # After flush, if we need FbsWbOperation to point at THIS specific order id,
    # rewrite the summary so `confirmed_order_handover_dates` finds it via ledger
    # or via the supply.seller/marketplace match. The supply-based path already
    # works because we set supply.delivered_at and supply.seller_id matches.
    return order


async def _run_transaction(fn: Any) -> Any:
    async with SessionLocal() as session:
        result = await fn(session)
        await session.commit()
        return result


@pytest.mark.asyncio
async def test_cancel_time_from_row_prefers_wb_payload() -> None:
    """WB payload's cancelledAt is stored verbatim, marked as wb_payload."""
    row = {"cancelledAt": "2026-09-08T10:11:12+00:00"}
    ct = cancel_time_from_row(row)
    assert ct.source == CANCEL_TIME_SOURCE_WB_PAYLOAD
    assert ct.at == datetime(2026, 9, 8, 10, 11, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_cancel_time_from_row_falls_back_to_received_at() -> None:
    """No cancelledAt in payload → received-at with the received_at marker."""
    fixed = datetime(2026, 9, 10, 5, 6, 7, tzinfo=UTC)
    ct = cancel_time_from_row(None, received_at=fixed)
    assert ct.source == CANCEL_TIME_SOURCE_RECEIVED_AT
    assert ct.at == fixed
    # Row present but empty of known keys → same fallback.
    ct2 = cancel_time_from_row({"unrelated": "x"}, received_at=fixed)
    assert ct2.source == CANCEL_TIME_SOURCE_RECEIVED_AT
    assert ct2.at == fixed


@pytest.mark.asyncio
async def test_cancel_time_from_row_ignores_unparseable_cancelled_at() -> None:
    """Garbage value falls back to received_at rather than silently sending it as wb_payload."""
    fixed = datetime(2026, 9, 10, 8, 9, 0, tzinfo=UTC)
    ct = cancel_time_from_row({"cancelledAt": "not-a-date"}, received_at=fixed)
    assert ct.source == CANCEL_TIME_SOURCE_RECEIVED_AT
    assert ct.at == fixed


@pytest.mark.asyncio
async def test_cancel_before_transfer_creates_no_return_document(
    db_session: AsyncSession,
) -> None:
    """No handover ever happened → no return document, ever."""
    suffix = uuid.uuid4().hex[:12]
    handover_at = datetime.now(UTC) - timedelta(hours=1)

    async def seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
        tenant_id = await _seed_tenant(session, suffix=suffix)
        wh_id = await _seed_warehouse(session, tenant_id, suffix)
        seller_id = await _seed_seller(session, tenant_id, suffix)
        product_id = await _seed_product(session, tenant_id, seller_id, suffix)
        supply = await _seed_supply(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            handed_over=False,
            handover_at=handover_at,
        )
        order = await _seed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            product_id=product_id,
            supply=supply,
            wb_order_id=911001,
        )
        return tenant_id, order.id

    tenant_id, order_id = await _run_transaction(seed)

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert not await was_transferred(session, order)
        result = await maybe_create_cancel_return_document(session, order)
        await session.commit()
    assert result is None

    async with SessionLocal() as session:
        # No document was created.
        n = await session.scalar(
            select(func.count()).select_from(InboundIntakeRequest).where(
                InboundIntakeRequest.tenant_id == tenant_id,
                InboundIntakeRequest.operation_type == OPERATION_TYPE_RETURN,
            )
        )
        assert int(n or 0) == 0
        # Marker was not set either.
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert not has_cancel_return_marker(order)


@pytest.mark.asyncio
async def test_cancel_after_transfer_creates_return_document_once_and_no_stock_change(
    db_session: AsyncSession,
) -> None:
    """WB payload's cancelledAt → doc stored with wb_payload source; no stock touched."""
    suffix = uuid.uuid4().hex[:12]
    handover_at = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    cancelled_at_wb = datetime(2026, 8, 22, 15, 30, 0, tzinfo=UTC)

    async def seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        tenant_id = await _seed_tenant(session, suffix=suffix)
        wh_id = await _seed_warehouse(session, tenant_id, suffix)
        seller_id = await _seed_seller(session, tenant_id, suffix)
        product_id = await _seed_product(session, tenant_id, seller_id, suffix)
        supply = await _seed_supply(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            handed_over=True,
            handover_at=handover_at,
        )
        order = await _seed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            product_id=product_id,
            supply=supply,
            wb_order_id=911002,
        )
        return tenant_id, order.id, product_id

    tenant_id, order_id, product_id = await _run_transaction(seed)

    # Baseline: no inventory rows exist for this seed.
    async with SessionLocal() as session:
        n_bal = await session.scalar(
            select(func.count()).select_from(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
            )
        )
        n_mov = await session.scalar(
            select(func.count()).select_from(InventoryMovement).where(
                InventoryMovement.tenant_id == tenant_id,
            )
        )
        assert int(n_bal or 0) == 0
        assert int(n_mov or 0) == 0

    # First cancel with a WB cancelledAt in the row.
    row = {"cancelledAt": cancelled_at_wb.isoformat()}
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert await was_transferred(session, order)
        req1 = await maybe_create_cancel_return_document(session, order, row=row)
        await session.commit()
    assert req1 is not None
    request_id_1 = req1.id

    # Verify document properties.
    async with SessionLocal() as session:
        req = await session.get(InboundIntakeRequest, request_id_1)
        assert req is not None
        assert req.operation_type == OPERATION_TYPE_RETURN
        assert req.marketplace == "wildberries"
        assert req.status == STATUS_DRAFT
        assert req.seller_id is not None
        # Lines: exactly the shipped product, expected qty > 0, posted qty 0.
        lines = list(
            (
                await session.execute(
                    select(InboundIntakeLine).where(
                        InboundIntakeLine.request_id == request_id_1
                    )
                )
            ).scalars()
        )
        assert len(lines) == 1
        line = lines[0]
        assert line.product_id == product_id
        assert line.expected_qty == 1
        assert line.actual_qty is None
        assert line.posted_qty == 0
        # Marker is recorded and points at this request.
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        marker = cancel_return_marker(order)
        assert marker is not None
        assert marker["inbound_request_id"] == str(request_id_1)
        assert marker["wb_order_id"] == 911002
        assert marker["cancelled_at_source"] == CANCEL_TIME_SOURCE_WB_PAYLOAD
        # Stored cancelled_at equals the WB value (ISO round-trip).
        assert datetime.fromisoformat(
            marker["cancelled_at"].replace("Z", "+00:00")
        ) == cancelled_at_wb

    # Retry: second call must NOT create a duplicate.
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        req2 = await maybe_create_cancel_return_document(session, order, row=row)
        await session.commit()
    assert req2 is not None
    assert req2.id == request_id_1

    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.count()).select_from(InboundIntakeRequest).where(
                InboundIntakeRequest.tenant_id == tenant_id,
                InboundIntakeRequest.operation_type == OPERATION_TYPE_RETURN,
            )
        )
        assert int(total or 0) == 1

    # Retry with a different WB payload MUST NOT create another doc — the natural
    # idempotency key is the WB order id, not the payload contents.
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        req3 = await maybe_create_cancel_return_document(session, order, row={})
        await session.commit()
    assert req3 is not None
    assert req3.id == request_id_1

    # Stock: no InventoryBalance rows, no InventoryMovement rows appeared.
    async with SessionLocal() as session:
        n_bal = await session.scalar(
            select(func.count()).select_from(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
            )
        )
        n_mov = await session.scalar(
            select(func.count()).select_from(InventoryMovement).where(
                InventoryMovement.tenant_id == tenant_id,
            )
        )
        assert int(n_bal or 0) == 0
        assert int(n_mov or 0) == 0


@pytest.mark.asyncio
async def test_cancel_after_transfer_received_at_when_wb_omits_field(
    db_session: AsyncSession,
) -> None:
    """No cancelledAt in payload → stored moment is the received-at, marker `received_at`."""
    suffix = uuid.uuid4().hex[:12]
    handover_at = datetime(2026, 8, 25, 8, 0, 0, tzinfo=UTC)
    received_at = datetime(2026, 8, 25, 9, 15, 0, tzinfo=UTC)

    async def seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
        tenant_id = await _seed_tenant(session, suffix=suffix)
        wh_id = await _seed_warehouse(session, tenant_id, suffix)
        seller_id = await _seed_seller(session, tenant_id, suffix)
        product_id = await _seed_product(session, tenant_id, seller_id, suffix)
        supply = await _seed_supply(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            handed_over=True,
            handover_at=handover_at,
        )
        order = await _seed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=wh_id,
            product_id=product_id,
            supply=supply,
            wb_order_id=911003,
        )
        return tenant_id, order.id

    _tenant_id, order_id = await _run_transaction(seed)

    # WB row without cancelledAt: pass an explicit received_at into the helper.
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        req = await maybe_create_cancel_return_document(
            session,
            order,
            row={"wbStatus": "canceled"},
            received_at=received_at,
        )
        await session.commit()
    assert req is not None

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        marker = cancel_return_marker(order)
        assert marker is not None
        assert marker["cancelled_at_source"] == CANCEL_TIME_SOURCE_RECEIVED_AT
        assert datetime.fromisoformat(
            marker["cancelled_at"].replace("Z", "+00:00")
        ) == received_at


@pytest.mark.asyncio
async def test_ensure_return_doc_no_warehouse_returns_none(
    db_session: AsyncSession,
) -> None:
    """Order without a warehouse can't be returned — return None, not create broken doc."""
    suffix = uuid.uuid4().hex[:12]

    async def seed(session: AsyncSession) -> uuid.UUID:
        tenant_id = await _seed_tenant(session, suffix=suffix)
        # Warehouse row is created to satisfy tenant integrity, then not used —
        # the order deliberately has warehouse_id=None to hit that guard branch.
        await _seed_warehouse(session, tenant_id, suffix)
        seller_id = await _seed_seller(session, tenant_id, suffix)
        product_id = await _seed_product(session, tenant_id, seller_id, suffix)
        now = datetime.now(UTC)
        order = FbsOrder(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=None,
            product_id=product_id,
            marketplace="wb",
            wb_order_id=911004,
            wb_barcode=f"BAR-{suffix}",
            wb_article=f"ART-{suffix}",
            supply_id=None,
            status=FBS_ORDER_STATUS_CANCELLED,
            created_at_wb=now - timedelta(hours=3),
            deadline_at=now + timedelta(days=1),
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        return order.id

    order_id = await _run_transaction(seed)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        ct = cancel_time_from_row(None)
        req = await ensure_cancel_return_document(session, order, cancel_time=ct)
        await session.commit()
    assert req is None
