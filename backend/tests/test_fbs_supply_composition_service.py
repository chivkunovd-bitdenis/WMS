from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_supply_composition_service as composition_service


def _order(
    *,
    tenant: Tenant,
    seller: Seller,
    warehouse: Warehouse,
    product: Product,
    wb_order_id: int,
    supply: FbsSupply | None,
) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supply_id=supply.id if supply is not None else None,
        wb_supply_id=supply.wb_supply_id if supply is not None else None,
        wb_order_id=wb_order_id,
        wb_warehouse_id=501,
        status=(FBS_ORDER_STATUS_PACKED if supply is not None else FBS_ORDER_STATUS_ASSEMBLING),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_packed_supply_absorbs_late_known_wb_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Composition tenant", slug=f"composition-{suffix}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code=f"wh-{suffix}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"SKU-{suffix}",
    )
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="wb",
        wb_supply_id=f"WB-{suffix}",
        name="Packed supply",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add_all([tenant, seller, warehouse, product, supply])
    await db_session.flush()
    existing = _order(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        wb_order_id=800_001,
        supply=supply,
    )
    late = _order(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        wb_order_id=800_002,
        supply=None,
    )
    db_session.add_all([existing, late])
    await db_session.commit()

    async def actual_order_ids(*args: object, **kwargs: object) -> list[int]:
        return [800_002, 800_001]

    monkeypatch.setattr(
        composition_service,
        "fetch_wb_supply_order_ids",
        actual_order_ids,
    )
    async with httpx.AsyncClient() as client:
        result = await composition_service.reconcile_actual_wb_supply_composition(
            db_session,
            tenant.id,
            supply.id,
            http_client=client,
            api_token="test-token",
        )

    assert result.wb_order_ids == (800_001, 800_002)
    assert result.delta.linked_order_ids == (800_002,)
    assert {order.id for order in result.active_orders} == {existing.id, late.id}
    assert result.discrepancies == ()
    assert late.supply_id == supply.id
    assert late.wb_supply_id == supply.wb_supply_id
    assert late.status == FBS_ORDER_STATUS_ASSEMBLING


@pytest.mark.asyncio
async def test_actual_composition_never_moves_order_from_another_supply(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Composition tenant", slug=f"composition-move-{suffix}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code=f"wh-move-{suffix}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"SKU-MOVE-{suffix}",
    )
    target = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="wb",
        wb_supply_id=f"WB-TARGET-{suffix}",
        name="Target",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    other = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="wb",
        wb_supply_id=f"WB-OTHER-{suffix}",
        name="Other",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add_all([tenant, seller, warehouse, product, target, other])
    await db_session.flush()
    order = _order(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        wb_order_id=801_001,
        supply=other,
    )
    db_session.add(order)
    await db_session.commit()

    async def actual_order_ids(*args: object, **kwargs: object) -> list[int]:
        return [801_001]

    monkeypatch.setattr(
        composition_service,
        "fetch_wb_supply_order_ids",
        actual_order_ids,
    )
    async with httpx.AsyncClient() as client:
        result = await composition_service.reconcile_actual_wb_supply_composition(
            db_session,
            tenant.id,
            target.id,
            http_client=client,
            api_token="test-token",
        )

    assert result.active_orders == ()
    assert [item.code for item in result.discrepancies] == ["order_in_other_supply"]
    assert order.supply_id == other.id
    assert order.wb_supply_id == other.wb_supply_id
