"""ORM tests for FBS warehouse binding and stock sync models.

TC-NEW-FBS-STOCK-003: binding uniqueness and separate WB warehouse/office fields.
TC-NEW-FBS-STOCK-004: unmapped order keeps warehouse_id null and reserve status constant.
TC-NEW-FBS-STOCK-010: per-item sync state and unique (binding_id, chrt_id).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_sellers import _binding_out
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
)
from app.models.fbs_stock_sync_item import (
    FBS_STOCK_SYNC_STATUSES,
    STOCK_SYNC_STATUS_CONFIRMED,
    STOCK_SYNC_STATUS_PENDING,
    FbsStockSyncItem,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_warehouse_binding_service import (
    FbsWarehouseBindingError,
    set_binding_stock_pool_quantity,
)


async def _seed_tenant_seller_warehouses(
    session: AsyncSession,
) -> tuple[Tenant, Seller, Warehouse, Warehouse]:
    tenant = Tenant(id=uuid.uuid4(), name="Tenant", slug=f"t-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    wh_a = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="FBS A",
        code=f"wh-a-{uuid.uuid4().hex[:6]}",
    )
    wh_b = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="FBS B",
        code=f"wh-b-{uuid.uuid4().hex[:6]}",
    )
    session.add_all([tenant, seller, wh_a, wh_b])
    await session.commit()
    return tenant, seller, wh_a, wh_b


def _binding(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    wms_warehouse_id: uuid.UUID,
) -> FbsWarehouseBinding:
    return FbsWarehouseBinding(
        tenant_id=tenant_id,
        seller_id=seller_id,
        wb_warehouse_id=wb_warehouse_id,
        wms_warehouse_id=wms_warehouse_id,
    )


@pytest.mark.parametrize("served, stock_sync_enabled", [(True, False), (False, True)])
def test_ozon_binding_api_output_keeps_provider_identity(
    served: bool, stock_sync_enabled: bool,
) -> None:
    """TC-NEW-OZON-STOCK-002: UI gets Ozon identity without WB inference."""
    binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        marketplace="ozon",
        external_warehouse_id="ozon-warehouse-1",
        wb_warehouse_id=501001,
        wms_warehouse_id=uuid.uuid4(),
        is_active=True,
        served=served,
        stock_sync_enabled=stock_sync_enabled,
    )

    result = _binding_out(binding)

    assert result.marketplace == "ozon"
    assert result.external_warehouse_id == "ozon-warehouse-1"

    assert result.served is served
    assert result.stock_sync_enabled is stock_sync_enabled


@pytest.mark.asyncio
async def test_binding_unique_seller_wb_warehouse(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-003: duplicate WB warehouse per seller is rejected."""
    tenant, seller, wh_a, wh_b = await _seed_tenant_seller_warehouses(db_session)
    db_session.add(
        _binding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            wb_warehouse_id=501001,
            wms_warehouse_id=wh_a.id,
        )
    )
    await db_session.commit()

    db_session.add(
        _binding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            wb_warehouse_id=501001,
            wms_warehouse_id=wh_b.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_binding_allows_one_wms_warehouse_for_many_wb_warehouses(
    db_session: AsyncSession,
) -> None:
    """Pool 1, item 5 (HANDOFF-POLISH.md): one physical WMS warehouse feeds
    every WB warehouse address for a seller, so no DB uniqueness on
    (seller_id, wms_warehouse_id) — the former constraint blocked live-order
    binding on staging (PUT .../warehouse-bindings/1155120 -> 409
    wms_warehouse_already_bound)."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    db_session.add(
        _binding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            wb_warehouse_id=501001,
            wms_warehouse_id=wh_a.id,
        )
    )
    await db_session.commit()

    db_session.add(
        _binding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            wb_warehouse_id=501002,
            wms_warehouse_id=wh_a.id,
        )
    )
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(FbsWarehouseBinding).where(
                    FbsWarehouseBinding.seller_id == seller.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.wb_warehouse_id for row in rows} == {501001, 501002}
    assert all(row.wms_warehouse_id == wh_a.id for row in rows)


@pytest.mark.asyncio
async def test_one_physical_unit_cannot_be_allocated_to_wb_and_ozon(
    db_session: AsyncSession,
) -> None:
    """TC-NEW-OZON-STOCK-001: marketplace bindings share one physical FBS pool."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Shared unit",
        sku_code=f"SHARED-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_stock_limit=1,
    )
    wb_binding = _binding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=501101,
        wms_warehouse_id=wh_a.id,
    )
    ozon_binding = _binding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=501102,
        wms_warehouse_id=wh_a.id,
    )
    ozon_binding.marketplace = "ozon"
    ozon_binding.external_warehouse_id = "ozon-warehouse-1"
    db_session.add_all([product, wb_binding, ozon_binding])
    await db_session.commit()

    await set_binding_stock_pool_quantity(
        db_session,
        tenant.id,
        seller.id,
        wb_binding.id,
        product.id,
        1,
    )

    with pytest.raises(FbsWarehouseBindingError) as error:
        await set_binding_stock_pool_quantity(
            db_session,
            tenant.id,
            seller.id,
            ozon_binding.id,
            product.id,
            1,
        )

    assert error.value.code == "pool_quota_exceeded"


@pytest.mark.asyncio
async def test_fbs_order_wb_warehouse_separate_from_office(
    db_session: AsyncSession,
) -> None:
    """TC-NEW-FBS-STOCK-003: warehouseId and officeId are stored independently."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=wh_a.id,
        wb_order_id=900001,
        wb_office_id=42,
        wb_warehouse_id=501001,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MISSING,
        reserve_status=RESERVE_STATUS_WAREHOUSE_UNMAPPED,
        status=FBS_ORDER_STATUS_NEW,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    assert order.wb_office_id == 42
    assert order.wb_warehouse_id == 501001
    assert order.warehouse_id == wh_a.id


@pytest.mark.asyncio
async def test_fbs_order_unmapped_warehouse_nullable(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-004: unknown WB warehouse → warehouse_id null, explicit status."""
    tenant, seller, _wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=None,
        wb_order_id=900002,
        wb_office_id=99,
        wb_warehouse_id=777888,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MISSING,
        reserve_status=RESERVE_STATUS_WAREHOUSE_UNMAPPED,
        status=FBS_ORDER_STATUS_NEW,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    assert order.warehouse_id is None
    assert order.warehouse is None
    assert order.reserve_status == "warehouse_unmapped"
    assert order.reserve_status == RESERVE_STATUS_WAREHOUSE_UNMAPPED


@pytest.mark.asyncio
async def test_stock_sync_item_unique_binding_chrt(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-010: duplicate chrtId per binding is rejected."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    binding = _binding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=501001,
        wms_warehouse_id=wh_a.id,
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)

    db_session.add(
        FbsStockSyncItem(
            binding_id=binding.id,
            chrt_id=555001,
            last_target_amount=5,
            last_confirmed_amount=5,
            status=STOCK_SYNC_STATUS_CONFIRMED,
        )
    )
    await db_session.commit()

    db_session.add(
        FbsStockSyncItem(
            binding_id=binding.id,
            chrt_id=555001,
            last_target_amount=0,
            status=STOCK_SYNC_STATUS_PENDING,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_stock_sync_item_status_and_amounts(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-010: per-item target/confirmed amounts and status values."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    binding = _binding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=501001,
        wms_warehouse_id=wh_a.id,
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)

    item = FbsStockSyncItem(
        binding_id=binding.id,
        chrt_id=555002,
        last_target_amount=0,
        last_confirmed_amount=0,
        status=STOCK_SYNC_STATUS_CONFIRMED,
        last_error_code=None,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    assert item.last_target_amount == 0
    assert item.last_confirmed_amount == 0
    assert item.status in FBS_STOCK_SYNC_STATUSES


@pytest.mark.asyncio
async def test_binding_lease_and_sync_metadata(db_session: AsyncSession) -> None:
    """Binding stores lease and last sync diagnostics for orchestration service."""
    tenant, seller, wh_a, _wh_b = await _seed_tenant_seller_warehouses(db_session)
    now = datetime.now(UTC)
    binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=501001,
        wms_warehouse_id=wh_a.id,
        lease_until=now + timedelta(minutes=5),
        last_sync_status="confirmed",
        last_sync_at=now,
        last_error_code=None,
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)

    assert binding.lease_until is not None
    assert binding.last_sync_status == "confirmed"
    assert binding.last_sync_at is not None
    assert binding.last_sync_at.replace(tzinfo=UTC) == now
