from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_stock_pool_debit import FbsStockPoolDebit
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from scripts.cleanup_fbs_stub_test_orders import (
    CleanupBlockedError,
    delete_orders,
    ensure_orders_are_safe_to_delete,
)


@pytest.mark.asyncio
async def test_cleanup_refuses_order_linked_to_supply() -> None:
    session = AsyncMock()
    order = SimpleNamespace(
        id=uuid.uuid4(),
        supply_id=uuid.uuid4(),
    )

    with pytest.raises(CleanupBlockedError, match="belong to FBS supplies"):
        await ensure_orders_are_safe_to_delete(session, [order])

    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_refuses_order_with_stock_pool_debit() -> None:
    session = AsyncMock()
    session.scalar.return_value = 1
    order = SimpleNamespace(
        id=uuid.uuid4(),
        supply_id=None,
    )

    with pytest.raises(CleanupBlockedError, match="stock-pool debits"):
        await ensure_orders_are_safe_to_delete(session, [order])

    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_allows_unlinked_order_without_stock_pool_debit() -> None:
    session = AsyncMock()
    session.scalar.side_effect = [0, 0, 0]
    order = SimpleNamespace(
        id=uuid.uuid4(),
        supply_id=None,
    )

    await ensure_orders_are_safe_to_delete(session, [order])

    assert session.scalar.await_count == 3


async def _seed_cleanup_order() -> tuple[
    FbsOrder,
    FbsBindingStockPool,
    StorageLocation,
]:
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        tenant = Tenant(name="Cleanup tenant", slug=f"cleanup-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Cleanup seller")
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Cleanup warehouse",
            code=f"cleanup-{uuid.uuid4().hex[:8]}",
        )
        session.add_all([seller, warehouse])
        await session.flush()
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Cleanup product",
            sku_code=f"cleanup-{uuid.uuid4().hex[:8]}",
        )
        location = StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code="CLEANUP-LOC",
            barcode=f"cleanup-loc-{uuid.uuid4().hex[:8]}",
        )
        binding = FbsWarehouseBinding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            wb_warehouse_id=990001,
            wms_warehouse_id=warehouse.id,
        )
        session.add_all([product, location, binding])
        await session.flush()
        pool = FbsBindingStockPool(
            tenant_id=tenant.id,
            binding_id=binding.id,
            product_id=product.id,
            quantity=7,
        )
        order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            wb_order_id=990000000001,
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
            mapping_status="mapped",
            reserve_status="no_stock",
        )
        session.add_all([pool, order])
        await session.commit()
        return order, pool, location


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe_relation", ["debit", "reversal", "marking"])
async def test_cleanup_db_guard_preserves_order_and_accounting_rows(
    async_client: AsyncClient,
    unsafe_relation: str,
) -> None:
    assert async_client.base_url == "http://test"
    order, pool, location = await _seed_cleanup_order()

    async with SessionLocal() as session:
        stored_order = await session.get(FbsOrder, order.id)
        assert stored_order is not None
        if unsafe_relation == "debit":
            relation = FbsStockPoolDebit(
                tenant_id=stored_order.tenant_id,
                pool_id=pool.id,
                order_id=stored_order.id,
                quantity_debited=3,
            )
        elif unsafe_relation == "reversal":
            relation = FbsShipmentReversalLedger(
                tenant_id=stored_order.tenant_id,
                fbs_order_id=stored_order.id,
                product_id=stored_order.product_id,
                storage_location_id=location.id,
                quantity=1,
            )
        else:
            relation = FbsOrderMarking(
                tenant_id=stored_order.tenant_id,
                order_id=stored_order.id,
                kind="sgtin",
                value=f"cleanup-{uuid.uuid4().hex}",
            )
        session.add(relation)
        await session.commit()

        with pytest.raises(CleanupBlockedError):
            await delete_orders(session, [stored_order])

        assert await session.get(FbsOrder, stored_order.id) is not None
        stored_pool = await session.get(FbsBindingStockPool, pool.id)
        assert stored_pool is not None
        assert stored_pool.quantity == 7

        relation_model = {
            "debit": FbsStockPoolDebit,
            "reversal": FbsShipmentReversalLedger,
            "marking": FbsOrderMarking,
        }[unsafe_relation]
        assert await session.get(relation_model, relation.id) is not None


@pytest.mark.asyncio
async def test_cleanup_reloads_locked_order_before_supply_check(
    async_client: AsyncClient,
) -> None:
    assert async_client.base_url == "http://test"
    order, _, _ = await _seed_cleanup_order()

    async with SessionLocal() as session:
        stale_order = await session.get(FbsOrder, order.id)
        assert stale_order is not None
        assert stale_order.supply_id is None
        supply = FbsSupply(
            tenant_id=stale_order.tenant_id,
            seller_id=stale_order.seller_id,
            warehouse_id=stale_order.warehouse_id,
            wb_supply_id=f"WB-GI-{uuid.uuid4().hex[:10]}",
            name="Cleanup guarded supply",
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        await session.execute(
            update(FbsOrder)
            .where(FbsOrder.id == stale_order.id)
            .values(supply_id=supply.id)
            .execution_options(synchronize_session=False)
        )
        assert stale_order.supply_id is None

        with pytest.raises(CleanupBlockedError, match="belong to FBS supplies"):
            await delete_orders(session, [stale_order])

        assert await session.get(FbsOrder, stale_order.id) is not None
