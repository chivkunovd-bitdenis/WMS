"""S-03 provider boundaries for the existing FBS operator flow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_orders import _run_blocked_ozon_fake
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import MAPPING_STATUS_MAPPED, RESERVE_STATUS_RESERVED, FbsOrder
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_print_asset_service import fetch_order_label_rows_for_marketplace
from app.services.fbs_supply_validator_service import validate_supply_composition
from app.services.marketplace_provider import MarketplaceProviderError, provider_error_message


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


@pytest.mark.asyncio
async def test_order_label_dispatch_uses_only_selected_marketplace_adapter() -> None:
    wb_fetch = AsyncMock(return_value=[{"orderId": 1}])
    ozon_fetch = AsyncMock(return_value=[{"posting_number": "ozon-1"}])

    rows = await fetch_order_label_rows_for_marketplace(
        "ozon",
        external_order_ids=["ozon-1"],
        wb_fetch=wb_fetch,
        ozon_fetch=ozon_fetch,
    )

    assert rows == [{"posting_number": "ozon-1"}]
    wb_fetch.assert_not_awaited()
    ozon_fetch.assert_awaited_once_with(["ozon-1"])


@pytest.mark.asyncio
async def test_order_label_fake_preserves_human_ozon_403_code7() -> None:
    error = MarketplaceProviderError("ozon", 403, {"code": 7})
    ozon_fetch = AsyncMock(side_effect=error)

    with pytest.raises(MarketplaceProviderError) as caught:
        await fetch_order_label_rows_for_marketplace(
            "ozon",
            external_order_ids=["ozon-1"],
            wb_fetch=AsyncMock(),
            ozon_fetch=ozon_fetch,
        )

    assert provider_error_message(caught.value) == (
        "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."
    )


@pytest.mark.asyncio
async def test_manual_sync_fake_returns_human_ozon_403_code7() -> None:
    with pytest.raises(HTTPException) as caught:
        await _run_blocked_ozon_fake()

    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "ozon_account_blocked"
    assert caught.value.detail["message"] == (
        "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."
    )
