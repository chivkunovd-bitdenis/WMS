"""Protected stock seeds copied from the original service tests for WMS-652."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FbsSupply,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadLine,
    MarketplaceUnloadRequest,
)
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    get_or_create_sorting_location,
)


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


class _Seed:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    bindings: list[FbsWarehouseBinding]
    product: Product


async def _seed(
    session: AsyncSession,
    *,
    on_hand: int = 420,
    wb_warehouse_ids: tuple[int, ...] = (501001,),
) -> _Seed:
    seed = _Seed()
    seed.tenant = Tenant(id=uuid.uuid4(), name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
    seed.seller = Seller(id=uuid.uuid4(), tenant_id=seed.tenant.id, name="Seller")
    seed.warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        name="WH",
        code=f"wh-{uuid.uuid4().hex[:6]}",
    )
    seed.bindings = [
        FbsWarehouseBinding(
            id=uuid.uuid4(),
            tenant_id=seed.tenant.id,
            seller_id=seed.seller.id,
            wb_warehouse_id=wb_id,
            wms_warehouse_id=seed.warehouse.id,
            is_active=True,
            stock_sync_enabled=True,
            served=True,
        )
        for wb_id in wb_warehouse_ids
    ]
    seed.product = Product(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        name="Product",
        sku_code=f"SKU-{uuid.uuid4().hex[:8]}",
        wb_chrt_id=777,
        fbs_stock_sync_enabled=True,
    )
    location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        warehouse_id=seed.warehouse.id,
        code=f"CELL-{uuid.uuid4().hex[:6]}",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    balance = InventoryBalance(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        storage_location_id=location.id,
        product_id=seed.product.id,
        quantity=on_hand,
        quantity_unpacked=on_hand,
    )
    session.add_all([seed.tenant, seed.seller, seed.warehouse, seed.product, location, balance])
    session.add_all(seed.bindings)
    await session.commit()
    return seed


async def _ozon_binding(
    session: AsyncSession,
    seed: _Seed,
    *,
    wb_warehouse_id: int,
    is_active: bool = True,
    served: bool = True,
) -> FbsWarehouseBinding:
    """Create an Ozon binding and its active product card for the same warehouse."""
    from app.models.product_marketplace_link import ProductMarketplaceLink

    binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        marketplace="ozon",
        external_warehouse_id=str(wb_warehouse_id),
        wb_warehouse_id=wb_warehouse_id,
        wms_warehouse_id=seed.warehouse.id,
        is_active=is_active,
        stock_sync_enabled=True,
        served=served,
    )
    session.add(binding)
    session.add(
        ProductMarketplaceLink(
            tenant_id=seed.tenant.id,
            seller_id=seed.seller.id,
            product_id=seed.product.id,
            marketplace="ozon",
            external_offer_id=f"ozon-offer-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
    )
    await session.commit()
    return binding


class Ctx:
    tenant: Tenant
    warehouse: Warehouse
    actor: User
    product: Product
    location: StorageLocation
    sorting: StorageLocation
    request: MarketplaceUnloadRequest
    box: MarketplaceUnloadBox


async def _fixture(session: AsyncSession, *, stock: int = 10, plan: int = 5) -> Ctx:
    suffix = uuid.uuid4().hex[:8]
    ctx = Ctx()
    ctx.tenant = Tenant(name="WMS-632", slug=f"wms632-fbo-{suffix}")
    session.add(ctx.tenant)
    await session.flush()
    ctx.warehouse = Warehouse(tenant_id=ctx.tenant.id, name="W", code=f"w632-{suffix}")
    seller = Seller(tenant_id=ctx.tenant.id, name="seller")
    ctx.actor = User(
        tenant_id=ctx.tenant.id,
        email=f"wms632-{suffix}@example.test",
        password_hash="unused",
        role="fulfillment_admin",
    )
    session.add_all((ctx.warehouse, seller, ctx.actor))
    await session.flush()
    ctx.product = Product(
        tenant_id=ctx.tenant.id, seller_id=seller.id, name="P", sku_code=f"wms632-{suffix}"
    )
    ctx.location = StorageLocation(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.warehouse.id,
        code=f"A-{suffix}",
        barcode=f"A-{suffix}",
    )
    ctx.request = MarketplaceUnloadRequest(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.warehouse.id,
        seller_id=seller.id,
        marketplace="ozon",
        status="confirmed",
        planned_shipment_date=(datetime.now(UTC) + timedelta(days=1)).date(),
    )
    session.add_all((ctx.product, ctx.location, ctx.request))
    await session.flush()
    ctx.sorting = await get_or_create_sorting_location(session, ctx.tenant.id, ctx.warehouse.id)
    line = MarketplaceUnloadLine(
        request_id=ctx.request.id, product_id=ctx.product.id, quantity=plan
    )
    session.add(line)
    await session.flush()
    session.add(
        MarketplaceUnloadReservation(
            tenant_id=ctx.tenant.id,
            marketplace_unload_line_id=line.id,
            product_id=ctx.product.id,
            warehouse_id=ctx.warehouse.id,
            quantity=plan,
        )
    )
    session.add(
        InventoryBalance(
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            quantity=stock,
            quantity_unpacked=stock,
            quantity_packed=0,
        )
    )
    ctx.box = MarketplaceUnloadBox(request_id=ctx.request.id, box_preset="60_40_40")
    session.add(ctx.box)
    await session.commit()
    return ctx
