"""Регрессии списания FBS по фактически упакованному составу заказа."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import (
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    PACK_STATUS_PACKED,
    RESERVE_STATUS_NO_STOCK,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import WB_OPERATION_STATE_CONFIRMED, FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_shipment_service as shipment_service
from app.services.fbs_ozon_packaging_service import write_off_order as write_off_ozon_order
from app.services.fbs_shipment_service import _write_off_delivered_orders_once
from app.services.fbs_shipment_source_service import (
    FbsShipmentSourcePlan,
    FbsShipmentSourceRequest,
    plan_fbs_shipment_sources,
)
from app.services.ozon_fbs_sync_service import _apply_status


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
class _ShipmentCase:
    tenant_id: uuid.UUID
    supply: FbsSupply
    order: FbsOrder
    product_ids: tuple[uuid.UUID, ...]
    location_ids: tuple[uuid.UUID, ...]
    initial_quantity: int
    operation: FbsWbOperation


async def _seed_packed_order(
    session: AsyncSession,
    quantities: tuple[int, ...],
    *,
    marketplace: str = "ozon",
) -> _ShipmentCase:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="PR140 shipment", slug=f"pr140-shipment-{suffix}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(
        tenant=tenant,
        name=f"{marketplace.upper()} FBS",
        code=f"{marketplace}-pr140-{suffix}",
    )
    task = PackagingTask(tenant=tenant, warehouse=warehouse, status="done")
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace=marketplace,
        wb_supply_id=f"PENDING-{suffix}",
        name=f"Packed {marketplace.upper()} supply",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        supply=supply,
        marketplace=marketplace,
        external_order_id=f"{marketplace}-posting-{suffix}",
        wb_order_id=-int(suffix, 16) if marketplace == "ozon" else int(suffix, 16),
        status=FBS_ORDER_STATUS_PACKED,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_NO_STOCK,
        pack_status=PACK_STATUS_PACKED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    session.add_all([tenant, seller, warehouse, task, supply, order])
    await session.flush()
    supply.packaging_task_id = task.id

    initial_quantity = 5
    products: list[Product] = []
    locations: list[StorageLocation] = []
    lines: list[PackagingTaskLine] = []
    for index, quantity in enumerate(quantities):
        product = Product(
            tenant=tenant,
            seller=seller,
            name=f"Product {index}",
            sku_code=f"PR140-{suffix}-{index}",
        )
        location = StorageLocation(
            tenant=tenant,
            warehouse=warehouse,
            code=f"CELL-{suffix}-{index}",
            barcode=f"LOC-{suffix}-{index}",
        )
        session.add_all([product, location])
        await session.flush()
        line = PackagingTaskLine(
            task=task,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=quantity,
            qty_packed_in_task=quantity,
        )
        position = FbsOrderProduct(
            order=order,
            product_id=product.id,
            ozon_sku=10_000 + index,
            offer_id=f"offer-{index}",
            name=product.name,
            quantity=quantity,
            picked_quantity=quantity,
            position_index=index,
        )
        balance = InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity=initial_quantity,
            quantity_unpacked=0,
            quantity_packed=initial_quantity,
        )
        session.add_all([line, position, balance])
        products.append(product)
        locations.append(location)
        lines.append(line)
    await session.flush()
    order.product_id = products[0].id

    packed_units = [
        {
            "product_id": str(product.id),
            "packaging_task_line_id": str(line.id),
            "storage_location_id": str(location.id),
            "idempotency_key": f"packed-{product.id}-{unit}",
            "packed_at": now.isoformat(),
        }
        for product, location, line, quantity in zip(
            products, locations, lines, quantities, strict=True
        )
        for unit in range(quantity)
    ]
    session.add(
        FbsPackagingFulfillment(
            tenant_id=tenant.id,
            fbs_order_id=order.id,
            packaging_task_id=task.id,
            packaging_task_line_id=lines[0].id,
            fulfilled_at=now,
            pack_idempotency_key=f"packed-{suffix}",
            ozon_packed_units_json=packed_units,
        )
    )
    operation = FbsWbOperation(
        tenant_id=tenant.id,
        seller_id=seller.id,
        operation_kind="supply_deliver",
        idempotency_key=f"deliver-{suffix}",
        state="pending",
    )
    session.add(operation)
    await session.commit()
    await session.refresh(operation)

    loaded_order = (
        await session.execute(
            select(FbsOrder)
            .where(FbsOrder.id == order.id)
            .options(selectinload(FbsOrder.product_positions))
        )
    ).scalar_one()
    loaded_supply = await session.get(FbsSupply, supply.id)
    assert loaded_supply is not None
    return _ShipmentCase(
        tenant_id=tenant.id,
        supply=loaded_supply,
        order=loaded_order,
        product_ids=tuple(product.id for product in products),
        location_ids=tuple(location.id for location in locations),
        initial_quantity=initial_quantity,
        operation=operation,
    )


async def _write_off_case(session: AsyncSession, case: _ShipmentCase) -> None:
    source_plan: FbsShipmentSourcePlan | None = None
    if case.order.marketplace == "wb":
        assert case.order.product_id is not None
        source_plan = await plan_fbs_shipment_sources(
            session,
            tenant_id=case.tenant_id,
            supply_warehouse_id=case.supply.warehouse_id,
            requests=[
                FbsShipmentSourceRequest(
                    fbs_order_id=case.order.id,
                    product_id=case.order.product_id,
                    quantity=1,
                )
            ],
        )
    await _write_off_delivered_orders_once(
        session,
        case.supply,
        [case.order],
        None,
        source_plan=source_plan,
        operation=case.operation,
    )


async def _balances(session: AsyncSession, case: _ShipmentCase) -> dict[uuid.UUID, int]:
    rows = (
        await session.execute(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == case.tenant_id,
                InventoryBalance.product_id.in_(case.product_ids),
            )
        )
    ).scalars()
    return {row.product_id: int(row.quantity) for row in rows}


@pytest.mark.asyncio
async def test_ozon_two_products_are_written_off_from_their_packed_locations(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-SHIPMENT-COMPOSITION-001
    case = await _seed_packed_order(db_session, (1, 1))

    await _write_off_case(db_session, case)

    assert await _balances(db_session, case) == {
        product_id: case.initial_quantity - 1 for product_id in case.product_ids
    }
    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert ledger is not None
    assert ledger.shipment_movement_id is not None
    assert {
        (position["product_id"], position["storage_location_id"], position["quantity"])
        for position in ledger.ozon_positions_json or []
    } == {
        (str(product_id), str(location_id), 1)
        for product_id, location_id in zip(
            case.product_ids, case.location_ids, strict=True
        )
    }


@pytest.mark.asyncio
async def test_ozon_quantity_above_one_is_written_off_in_full(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-SHIPMENT-COMPOSITION-002
    case = await _seed_packed_order(db_session, (3,))

    await _write_off_case(db_session, case)

    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity - 3
    }
    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert ledger is not None
    assert ledger.quantity == 3
    assert (ledger.ozon_positions_json or [])[0]["quantity"] == 3


@pytest.mark.asyncio
async def test_ozon_cancellation_restores_every_written_off_position(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-SHIPMENT-COMPOSITION-003
    case = await _seed_packed_order(db_session, (2, 3))
    await _write_off_case(db_session, case)

    await _apply_status(db_session, case.order, "cancelled")
    await db_session.flush()

    assert await _balances(db_session, case) == {
        product_id: case.initial_quantity for product_id in case.product_ids
    }
    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert ledger is not None
    assert ledger.reversed_at is not None
    movements = list(
        (
            await db_session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.tenant_id == case.tenant_id,
                    InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(int(movement.quantity_delta) for movement in movements) == [-3, -2, 2, 3]


@pytest.mark.asyncio
async def test_ozon_single_packed_unit_keeps_the_previous_one_unit_result(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-SHIPMENT-COMPOSITION-004
    case = await _seed_packed_order(db_session, (1,))

    await _write_off_case(db_session, case)

    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity - 1
    }
    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert ledger is not None
    assert ledger.quantity == 1


@pytest.mark.asyncio
async def test_ozon_packaging_write_off_then_delivery_debits_stock_once(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-OZON-WRITE-OFF-001: старый упаковочный вызов оставляет
    # доставке заполненную ссылку на движение, поэтому повторного расхода нет.
    case = await _seed_packed_order(db_session, (1,))

    ledger = await write_off_ozon_order(
        db_session,
        tenant_id=case.tenant_id,
        order=case.order,
        actor_user_id=None,
    )
    await _write_off_case(db_session, case)

    assert ledger.shipment_movement_id is not None
    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity - 1
    }
    movements = list(
        (
            await db_session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.tenant_id == case.tenant_id,
                    InventoryMovement.product_id == case.product_ids[0],
                    InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                )
            )
        )
        .scalars()
        .all()
    )
    assert [(movement.id, int(movement.quantity_delta)) for movement in movements] == [
        (ledger.shipment_movement_id, -1)
    ]


@pytest.mark.asyncio
async def test_wb_delivery_keeps_single_write_off_path(db_session: AsyncSession) -> None:
    # TC-NEW-FBS-OZON-WRITE-OFF-002: защита Ozon не меняет прежний путь WB.
    case = await _seed_packed_order(db_session, (1,), marketplace="wb")

    await _write_off_case(db_session, case)
    await _write_off_case(db_session, case)

    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert ledger is not None
    assert ledger.shipment_movement_id is not None
    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity - 1
    }
    movements = list(
        (
            await db_session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.tenant_id == case.tenant_id,
                    InventoryMovement.product_id == case.product_ids[0],
                    InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                )
            )
        )
        .scalars()
        .all()
    )
    assert [(movement.id, int(movement.quantity_delta)) for movement in movements] == [
        (ledger.shipment_movement_id, -1)
    ]


@pytest.mark.asyncio
async def test_wb_confirmed_checkpoint_replays_local_write_off_without_replanning(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = await _seed_packed_order(db_session, (1,), marketplace="wb")
    assert case.order.product_id is not None
    source_plan = await plan_fbs_shipment_sources(
        db_session,
        tenant_id=case.tenant_id,
        supply_warehouse_id=case.supply.warehouse_id,
        requests=[
            FbsShipmentSourceRequest(
                fbs_order_id=case.order.id,
                product_id=case.order.product_id,
                quantity=1,
            )
        ],
    )
    original_apply = shipment_service._apply_local_delivered

    async def crash_after_checkpoint(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated local crash")

    monkeypatch.setattr(shipment_service, "_apply_local_delivered", crash_after_checkpoint)
    with pytest.raises(RuntimeError, match="simulated local crash"):
        await shipment_service._persist_confirmed_delivery(
            db_session,
            case.supply,
            [case.order],
            case.operation,
            None,
            source_plan,
        )
    await db_session.rollback()

    checkpointed_operation = await db_session.get(FbsWbOperation, case.operation.id)
    ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert checkpointed_operation is not None
    assert checkpointed_operation.state == WB_OPERATION_STATE_CONFIRMED
    assert ledger is not None
    assert ledger.shipment_movement_id is None
    assert ledger.storage_location_id == source_plan.resolutions[0].storage_location_id

    reloaded_supply = await db_session.get(FbsSupply, case.supply.id)
    assert reloaded_supply is not None
    checkpoint = await shipment_service._load_checkpointed_wb_delivery(
        db_session,
        reloaded_supply,
        checkpointed_operation,
    )
    assert checkpoint is not None
    checkpointed_orders, checkpointed_plan = checkpoint
    monkeypatch.setattr(shipment_service, "_apply_local_delivered", original_apply)
    await shipment_service._persist_confirmed_delivery(
        db_session,
        reloaded_supply,
        checkpointed_orders,
        checkpointed_operation,
        None,
        checkpointed_plan,
    )

    replayed_ledger = await db_session.scalar(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id == case.order.id
        )
    )
    assert replayed_ledger is not None
    assert replayed_ledger.shipment_movement_id is not None
    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity - 1
    }


@pytest.mark.asyncio
async def test_ozon_cancelled_after_packaging_is_not_written_off_again(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-OZON-WRITE-OFF-003: отмена сторнирует старое упаковочное
    # списание, а доставочный обработчик не создаёт новый расход отменённого заказа.
    case = await _seed_packed_order(db_session, (1,))
    await write_off_ozon_order(
        db_session,
        tenant_id=case.tenant_id,
        order=case.order,
        actor_user_id=None,
    )

    await _apply_status(db_session, case.order, "cancelled")
    await _write_off_case(db_session, case)

    assert await _balances(db_session, case) == {
        case.product_ids[0]: case.initial_quantity
    }
    movements = list(
        (
            await db_session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.tenant_id == case.tenant_id,
                    InventoryMovement.product_id == case.product_ids[0],
                    InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(int(movement.quantity_delta) for movement in movements) == [-1, 1]
