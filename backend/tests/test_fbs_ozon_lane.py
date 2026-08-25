"""S-03 provider boundaries for the existing FBS operator flow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import MAPPING_STATUS_MAPPED, RESERVE_STATUS_RESERVED, FbsOrder
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_supply_validator_service import validate_supply_composition


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_supply_preflight_rejects_mixed_marketplaces(db_session: AsyncSession) -> None:
    """TC-S03-OZON-001: a physical FBS supply belongs to exactly one marketplace."""
    tenant = Tenant(name="S-03 marketplace test", slug=f"s03-{uuid.uuid4().hex[:12]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()

    now = datetime.now(UTC)
    wb_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace="wb",
        external_order_id="wb-1",
        wb_order_id=1,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    ozon_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace="ozon",
        external_order_id="ozon-1",
        wb_order_id=2,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add_all([wb_order, ozon_order])
    await db_session.commit()

    result = await validate_supply_composition(
        db_session,
        tenant.id,
        [wb_order.id, ozon_order.id],
        planned_delivery_type="warehouse_sc",
    )

    assert {issue.code for issue in result.issues} >= {"different_marketplace"}
