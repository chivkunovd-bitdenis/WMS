"""WMS-121 · server-side защита от «протащенного» выбора между контекстами.

Фронт обязан чистить выбранные UUID при смене селлера/маркетплейса/склада/
вкладки (см. `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, effect на
sellerId/marketplace/wbWarehouseId/statusGroup). Здесь проверяем, что если
клиент всё-таки прислал в массовое действие микс UUID из разных контекстов
— сервер откажет, а не создаст поставку под чужого продавца/маркетплейс.

Такой отказ уже реализован в `validate_supply_composition` и переиспользован
в `create_supply_from_orders`; тест фиксирует поведение, чтобы будущие правки
не превратили жёсткий отказ в тихую «нормализацию».
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_supply_service as supply_svc


def _order(
    *,
    tenant: Tenant,
    seller: Seller,
    warehouse: Warehouse,
    product: Product,
    wb_order_id: int,
    marketplace: str = "wb",
) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace=marketplace,
        wb_order_id=wb_order_id,
        wb_warehouse_id=501,
        status=FBS_ORDER_STATUS_NEW,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        supplier_status="new",
        cargo_type="normal",
    )


async def _seed_two_sellers(session: AsyncSession) -> tuple[Tenant, list[FbsOrder]]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Tenant", slug=f"wms121-{suffix}")
    seller_a = Seller(tenant=tenant, name="Seller A")
    seller_b = Seller(tenant=tenant, name="Seller B")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code=f"wh-{suffix}")
    product_a = Product(
        tenant=tenant, seller=seller_a, name="Product A", sku_code=f"SKU-A-{suffix}"
    )
    product_b = Product(
        tenant=tenant, seller=seller_b, name="Product B", sku_code=f"SKU-B-{suffix}"
    )
    session.add_all([tenant, seller_a, seller_b, warehouse, product_a, product_b])
    await session.flush()
    order_a = _order(
        tenant=tenant, seller=seller_a, warehouse=warehouse, product=product_a, wb_order_id=911_001
    )
    order_b = _order(
        tenant=tenant, seller=seller_b, warehouse=warehouse, product=product_b, wb_order_id=911_002
    )
    session.add_all([order_a, order_b])
    await session.commit()
    return tenant, [order_a, order_b]


@pytest.mark.asyncio
async def test_wms121_cross_seller_selection_is_rejected(db_session: AsyncSession) -> None:
    """Микс UUID двух селлеров → отказ `order_incompatible`, а не тихое склеивание."""
    tenant, (order_a, order_b) = await _seed_two_sellers(db_session)

    async with httpx.AsyncClient() as client:
        with pytest.raises(supply_svc.FbsSupplyError) as exc_info:
            await supply_svc.create_supply_from_orders(
                db_session,
                tenant.id,
                name="Cross seller supply",
                order_ids=[order_a.id, order_b.id],
                planned_delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
                planned_destination=None,
                idempotency_key=f"wms121-cross-{uuid.uuid4().hex[:8]}",
                http_client=client,
            )
    assert exc_info.value.code == "order_incompatible"
    reasons = set(exc_info.value.context.get("reasons") or [])
    # Разные seller_id дают в контексте reason `different_seller`, иначе можно
    # случайно проглотить регрессию и получить создание под первым попавшимся
    # селлером. (`_issue_context` кладёт коды в `reasons`, см.
    # fbs_supply_service.py:247.)
    assert "different_seller" in reasons


@pytest.mark.asyncio
async def test_wms121_cross_marketplace_selection_is_rejected(db_session: AsyncSession) -> None:
    """WB-UUID + Ozon-UUID → отказ `order_incompatible`."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Tenant", slug=f"wms121-mp-{suffix}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code=f"wh-mp-{suffix}")
    product = Product(tenant=tenant, seller=seller, name="Product", sku_code=f"SKU-MP-{suffix}")
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    order_wb = _order(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        wb_order_id=912_001,
        marketplace="wb",
    )
    order_ozon = _order(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        wb_order_id=912_002,
        marketplace="ozon",
    )
    db_session.add_all([order_wb, order_ozon])
    await db_session.commit()

    async with httpx.AsyncClient() as client:
        with pytest.raises(supply_svc.FbsSupplyError) as exc_info:
            await supply_svc.create_supply_from_orders(
                db_session,
                tenant.id,
                name="Cross marketplace supply",
                order_ids=[order_wb.id, order_ozon.id],
                planned_delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
                planned_destination=None,
                idempotency_key=f"wms121-mp-{uuid.uuid4().hex[:8]}",
                http_client=client,
            )
    assert exc_info.value.code == "order_incompatible"
    reasons = set(exc_info.value.context.get("reasons") or [])
    assert "different_marketplace" in reasons
