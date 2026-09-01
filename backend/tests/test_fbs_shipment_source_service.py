from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FbsSupply,
)
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.fbs_shipment_source_service import (
    FbsShipmentSourceRequest,
    plan_fbs_shipment_sources,
    reversal_source_from_ledger,
)
from app.services.sorting_location_service import SORTING_LOCATION_CODE


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@dataclass(frozen=True)
class _Context:
    tenant: Tenant
    seller: Seller
    supply_warehouse: Warehouse
    other_warehouse: Warehouse
    product: Product
    supply: FbsSupply
    supply_sorting: StorageLocation
    supply_address: StorageLocation
    other_sorting: StorageLocation


async def _seed_context(session: AsyncSession) -> _Context:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Source tenant", slug=f"source-{suffix}")
    seller = Seller(tenant=tenant, name="Seller")
    supply_warehouse = Warehouse(
        tenant=tenant,
        name="Supply warehouse",
        code=f"supply-{suffix}",
    )
    other_warehouse = Warehouse(
        tenant=tenant,
        name="Other warehouse",
        code=f"other-{suffix}",
    )
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"SKU-{suffix}",
    )
    supply_sorting = StorageLocation(
        tenant=tenant,
        warehouse=supply_warehouse,
        code=SORTING_LOCATION_CODE,
        barcode=f"SORT-SUPPLY-{suffix}",
    )
    supply_address = StorageLocation(
        tenant=tenant,
        warehouse=supply_warehouse,
        code="A-01-01",
        barcode=f"ADDR-SUPPLY-{suffix}",
    )
    other_sorting = StorageLocation(
        tenant=tenant,
        warehouse=other_warehouse,
        code=SORTING_LOCATION_CODE,
        barcode=f"SORT-OTHER-{suffix}",
    )
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=supply_warehouse,
        wb_supply_id=f"WB-{suffix}",
        name="Supply",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    session.add_all(
        [
            tenant,
            seller,
            supply_warehouse,
            other_warehouse,
            product,
            supply_sorting,
            supply_address,
            other_sorting,
            supply,
        ]
    )
    await session.flush()
    return _Context(
        tenant=tenant,
        seller=seller,
        supply_warehouse=supply_warehouse,
        other_warehouse=other_warehouse,
        product=product,
        supply=supply,
        supply_sorting=supply_sorting,
        supply_address=supply_address,
        other_sorting=other_sorting,
    )


def _balance(
    context: _Context,
    location: StorageLocation,
    *,
    container_kind: str | None = None,
    container_id: uuid.UUID | None = None,
) -> InventoryBalance:
    return InventoryBalance(
        tenant_id=context.tenant.id,
        product_id=context.product.id,
        storage_location_id=location.id,
        container_kind=container_kind,
        container_id=container_id,
        quantity=1,
        quantity_unpacked=1,
        quantity_packed=0,
    )


def _order(context: _Context, *, wb_order_id: int) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=context.tenant.id,
        seller_id=context.seller.id,
        warehouse_id=context.supply_warehouse.id,
        product_id=context.product.id,
        supply_id=context.supply.id,
        wb_order_id=wb_order_id,
        status=FBS_ORDER_STATUS_IN_SUPPLY,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_manual_pick_wins_and_keeps_exact_container_for_reversal(
    db_session: AsyncSession,
) -> None:
    context = await _seed_context(db_session)
    order = _order(context, wb_order_id=700_001)
    manual_box = WarehouseBox(
        tenant_id=context.tenant.id,
        warehouse_id=context.supply_warehouse.id,
        storage_location_id=context.supply_address.id,
        internal_barcode=f"BOX-{uuid.uuid4().hex[:8]}",
        container_kind="box",
    )
    db_session.add_all([order, manual_box])
    await db_session.flush()
    db_session.add_all(
        [
            _balance(context, context.supply_sorting),
            _balance(
                context,
                context.supply_address,
                container_kind="box",
                container_id=manual_box.id,
            ),
            FbsOrderPick(
                tenant_id=context.tenant.id,
                fbs_order_id=order.id,
                fbs_supply_id=context.supply.id,
                product_id=context.product.id,
                source_storage_location_id=context.supply_address.id,
                source_container_kind="box",
                source_container_id=manual_box.id,
                sorting_storage_location_id=context.supply_sorting.id,
                picked_at=datetime.now(UTC),
                scan_idempotency_key=f"manual-{order.id}",
            ),
        ]
    )
    await db_session.flush()

    plan = await plan_fbs_shipment_sources(
        db_session,
        tenant_id=context.tenant.id,
        supply_warehouse_id=context.supply_warehouse.id,
        requests=[
            FbsShipmentSourceRequest(
                fbs_order_id=order.id,
                product_id=context.product.id,
                quantity=1,
            )
        ],
    )

    resolution = plan.resolutions[0]
    assert resolution.source_mode == "manual_pick"
    assert resolution.storage_location_id == context.supply_address.id
    assert resolution.container_kind == "box"
    assert resolution.container_id == manual_box.id
    assert resolution.positive_quantity == 1
    assert resolution.negative_quantity == 0

    ledger = FbsShipmentReversalLedger(
        tenant_id=context.tenant.id,
        fbs_order_id=order.id,
        product_id=context.product.id,
        storage_location_id=resolution.storage_location_id,
        source_warehouse_id=resolution.source_warehouse_id,
        container_kind=resolution.container_kind,
        container_id=resolution.container_id,
        source_mode=resolution.source_mode,
        quantity=resolution.quantity,
    )
    reversal = reversal_source_from_ledger(ledger)
    assert reversal.storage_location_id == context.supply_address.id
    assert reversal.container_kind == "box"
    assert reversal.container_id == manual_box.id
    assert reversal.quantity == 1


@pytest.mark.asyncio
async def test_auto_source_priority_and_in_plan_consumption(
    db_session: AsyncSession,
) -> None:
    context = await _seed_context(db_session)
    sorting_box = WarehouseBox(
        tenant_id=context.tenant.id,
        warehouse_id=context.supply_warehouse.id,
        storage_location_id=context.supply_sorting.id,
        internal_barcode=f"BOX-{uuid.uuid4().hex[:8]}",
        container_kind="box",
    )
    address_box = WarehouseBox(
        tenant_id=context.tenant.id,
        warehouse_id=context.supply_warehouse.id,
        storage_location_id=context.supply_address.id,
        internal_barcode=f"BOX-{uuid.uuid4().hex[:8]}",
        container_kind="box",
    )
    db_session.add_all([sorting_box, address_box])
    await db_session.flush()
    db_session.add_all(
        [
            _balance(context, context.supply_sorting),
            _balance(
                context,
                context.supply_sorting,
                container_kind="box",
                container_id=sorting_box.id,
            ),
            _balance(context, context.supply_address),
            _balance(
                context,
                context.supply_address,
                container_kind="box",
                container_id=address_box.id,
            ),
            _balance(context, context.other_sorting),
        ]
    )
    await db_session.flush()
    requests = [
        FbsShipmentSourceRequest(
            fbs_order_id=uuid.uuid4(),
            product_id=context.product.id,
            quantity=1,
        )
        for _ in range(6)
    ]

    plan = await plan_fbs_shipment_sources(
        db_session,
        tenant_id=context.tenant.id,
        supply_warehouse_id=context.supply_warehouse.id,
        requests=requests,
    )

    assert [item.source_mode for item in plan.resolutions] == [
        "sorting_loose",
        "sorting_container",
        "storage_loose",
        "storage_container",
        "sorting_loose",
        "forced_negative",
    ]
    assert [item.source_warehouse_id for item in plan.resolutions[:4]] == [
        context.supply_warehouse.id,
    ] * 4
    assert plan.resolutions[4].source_warehouse_id == context.other_warehouse.id
    assert plan.resolutions[5].storage_location_id == context.supply_sorting.id
    assert plan.resolutions[5].positive_quantity == 0
    assert plan.resolutions[5].shortage_quantity == 1
    assert plan.resolutions[5].negative_quantity == 1
    assert plan.resolutions[5].allow_negative is True


@pytest.mark.asyncio
async def test_forced_negative_uses_supply_sorting_without_balance(
    db_session: AsyncSession,
) -> None:
    context = await _seed_context(db_session)

    plan = await plan_fbs_shipment_sources(
        db_session,
        tenant_id=context.tenant.id,
        supply_warehouse_id=context.supply_warehouse.id,
        requests=[
            FbsShipmentSourceRequest(
                fbs_order_id=uuid.uuid4(),
                product_id=context.product.id,
                quantity=1,
            )
        ],
    )

    resolution = plan.resolutions[0]
    assert resolution.source_mode == "forced_negative"
    assert resolution.source_warehouse_id == context.supply_warehouse.id
    assert resolution.storage_location_id == context.supply_sorting.id
    assert resolution.container_kind is None
    assert resolution.container_id is None
    assert resolution.positive_quantity == 0
    assert resolution.shortage_quantity == 1
    assert resolution.negative_quantity == 1
    assert plan.has_shortage is True
