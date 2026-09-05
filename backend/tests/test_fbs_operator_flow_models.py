"""ORM constraint tests for FBS operator flow models (FBSFLOW-010).

TC-NEW-FBS-OP-001: duplicate WB operation idempotency rejected.
TC-NEW-FBS-OP-002: duplicate active pick per order rejected.
TC-NEW-FBS-OP-003: duplicate active packaging fulfillment per order rejected.
TC-NEW-FBS-OP-004: new FbsOrder defaults for operator sub-statuses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MISSING,
    PACK_STATUS_PENDING,
    PICK_STATUS_PENDING,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    STICKER_STATUS_NOT_REQUESTED,
    FbsOrder,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_SUPPLY_STATUS_DRAFT, FbsSupply
from app.models.fbs_wb_operation import WB_OPERATION_STATE_PENDING, FbsWbOperation
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse


async def _seed_operator_context(
    session: AsyncSession,
) -> tuple[
    Tenant,
    Seller,
    Warehouse,
    Product,
    StorageLocation,
    StorageLocation,
    FbsSupply,
    FbsOrder,
    PackagingTask,
    PackagingTaskLine,
]:
    tenant = Tenant(id=uuid.uuid4(), name="Tenant", slug=f"t-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="WH",
        code=f"wh-{uuid.uuid4().hex[:6]}",
    )
    product = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Product",
        sku_code=f"SKU-{uuid.uuid4().hex[:6]}",
    )
    source_loc = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code="A-01-01",
        barcode=f"LOC-{uuid.uuid4().hex[:8]}",
    )
    sorting_loc = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code="__SORTING__",
        barcode=f"SORT-{uuid.uuid4().hex[:8]}",
    )
    now = datetime.now(UTC)
    supply = FbsSupply(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        wb_supply_id=f"WB-{uuid.uuid4().hex[:6]}",
        name="Supply",
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supply_id=supply.id,
        wb_order_id=800001,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MISSING,
        reserve_status=RESERVE_STATUS_WAREHOUSE_UNMAPPED,
        status=FBS_ORDER_STATUS_NEW,
    )
    task = PackagingTask(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        status="draft",
    )
    line = PackagingTaskLine(
        id=uuid.uuid4(),
        task_id=task.id,
        product_id=product.id,
        storage_location_id=sorting_loc.id,
        qty_total=1,
        qty_suggested_packed=0,
        qty_confirmed_packed=0,
        qty_packed_in_task=0,
        qty_marking_printed=0,
    )
    session.add_all(
        [
            tenant,
            seller,
            warehouse,
            product,
            source_loc,
            sorting_loc,
            supply,
            order,
            task,
            line,
        ]
    )
    await session.commit()
    return tenant, seller, warehouse, product, source_loc, sorting_loc, supply, order, task, line


def _pick(
    *,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    supply: FbsSupply,
    product: Product,
    source_loc: StorageLocation,
    sorting_loc: StorageLocation,
    scan_key: str,
) -> FbsOrderPick:
    return FbsOrderPick(
        tenant_id=tenant_id,
        fbs_order_id=order.id,
        fbs_supply_id=supply.id,
        source_storage_location_id=source_loc.id,
        sorting_storage_location_id=sorting_loc.id,
        product_id=product.id,
        picked_at=datetime.now(UTC),
        scan_idempotency_key=scan_key,
    )


@pytest.mark.asyncio
async def test_fbs_order_operator_status_defaults(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-OP-004: new orders expose pending/not_requested sub-statuses."""
    tenant = Tenant(id=uuid.uuid4(), name="Tenant", slug=f"t-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_order_id=800002,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MISSING,
        reserve_status=RESERVE_STATUS_WAREHOUSE_UNMAPPED,
        status=FBS_ORDER_STATUS_NEW,
    )
    db_session.add_all([tenant, seller, order])
    await db_session.commit()
    await db_session.refresh(order)

    assert order.pick_status == PICK_STATUS_PENDING
    assert order.pack_status == PACK_STATUS_PENDING
    assert order.sticker_status == STICKER_STATUS_NOT_REQUESTED
    assert order.picked_at is None
    assert order.packed_at is None


@pytest.mark.asyncio
async def test_wb_operation_duplicate_idempotency(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-OP-001: duplicate (seller, kind, idempotency_key) is rejected."""
    tenant = Tenant(id=uuid.uuid4(), name="Tenant", slug=f"t-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    db_session.add_all([tenant, seller])
    await db_session.commit()

    key = f"idempotency-{uuid.uuid4().hex}"
    db_session.add(
        FbsWbOperation(
            tenant_id=tenant.id,
            seller_id=seller.id,
            operation_kind="create_supply",
            idempotency_key=key,
            state=WB_OPERATION_STATE_PENDING,
        )
    )
    await db_session.commit()

    db_session.add(
        FbsWbOperation(
            tenant_id=tenant.id,
            seller_id=seller.id,
            operation_kind="create_supply",
            idempotency_key=key,
            state=WB_OPERATION_STATE_PENDING,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_active_pick_rejected(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-OP-002: second active pick for the same order is rejected."""
    if engine.dialect.name != "postgresql":
        pytest.skip("partial unique index enforced on PostgreSQL only")

    (
        tenant,
        _seller,
        _warehouse,
        product,
        source_loc,
        sorting_loc,
        supply,
        order,
        _task,
        _line,
    ) = await _seed_operator_context(db_session)

    db_session.add(
        _pick(
            tenant_id=tenant.id,
            order=order,
            supply=supply,
            product=product,
            source_loc=source_loc,
            sorting_loc=sorting_loc,
            scan_key="scan-1",
        )
    )
    await db_session.commit()

    db_session.add(
        _pick(
            tenant_id=tenant.id,
            order=order,
            supply=supply,
            product=product,
            source_loc=source_loc,
            sorting_loc=sorting_loc,
            scan_key="scan-2",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_active_fulfillment_rejected(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-OP-003: second active fulfillment for the same order is rejected."""
    if engine.dialect.name != "postgresql":
        pytest.skip("partial unique index enforced on PostgreSQL only")

    (
        tenant,
        _seller,
        _warehouse,
        _product,
        _source_loc,
        sorting_loc,
        _supply,
        order,
        task,
        line,
    ) = await _seed_operator_context(db_session)
    now = datetime.now(UTC)

    db_session.add(
        FbsPackagingFulfillment(
            tenant_id=tenant.id,
            fbs_order_id=order.id,
            packaging_task_id=task.id,
            packaging_task_line_id=line.id,
            fulfilled_at=now,
            pack_idempotency_key="pack-1",
        )
    )
    await db_session.commit()

    other_task = PackagingTask(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=task.warehouse_id,
        status="draft",
    )
    other_line = PackagingTaskLine(
        id=uuid.uuid4(),
        task_id=other_task.id,
        product_id=line.product_id,
        storage_location_id=sorting_loc.id,
        qty_total=1,
        qty_suggested_packed=0,
        qty_confirmed_packed=0,
        qty_packed_in_task=0,
        qty_marking_printed=0,
    )
    db_session.add_all([other_task, other_line])
    await db_session.flush()

    db_session.add(
        FbsPackagingFulfillment(
            tenant_id=tenant.id,
            fbs_order_id=order.id,
            packaging_task_id=other_task.id,
            packaging_task_line_id=other_line.id,
            fulfilled_at=now,
            pack_idempotency_key="pack-2",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
