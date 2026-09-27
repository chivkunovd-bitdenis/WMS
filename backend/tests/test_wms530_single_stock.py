"""WMS-530: один расчёт «Остаток / Резерв / Доступно» на организацию.

Проверки C1-C3 и C15 из docs/requirements/WMS-530.md: одни и те же три числа
у всех потребителей (каталог, окно «Остаток для FBS», бронь заказа FBS,
отгрузка на МП, инвентаризация), расположение (склад/зона/тара, включая
legacy-псевдосклад и склад брака) не исключает строку и не блокирует работу,
и одновременная бронь последней единицы не создаёт вторую бронь.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.stock_direction import StockDirection
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_count_service, inventory_service
from app.services.defect_warehouse_service import get_or_create_defect_location
from app.services.fbs_stock_availability_service import (
    organization_stock_totals_by_product,
)
from app.services.fbs_stock_rule_service import get_rule_views
from app.services.marketplace_unload_service import list_available_products
from app.services.sorting_location_service import SORTING_LOCATION_CODE


@pytest.fixture(autouse=True)
def _no_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inventory_service, "schedule_seller_stock_publish", lambda *a: None)


async def _base_seed(session: AsyncSession) -> dict[str, object]:
    """Организация с двумя рабочими складами, старым псевдоскладом и складом брака."""
    tenant = Tenant(name="WMS-530", slug=f"wms530-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"wms530-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        role="fulfillment_admin",
    )
    seller = Seller(tenant_id=tenant.id, name="Seller S1")
    warehouse_a = Warehouse(tenant_id=tenant.id, name="Склад А", code=f"a-{uuid.uuid4().hex[:6]}")
    warehouse_b = Warehouse(tenant_id=tenant.id, name="Склад Б", code=f"b-{uuid.uuid4().hex[:6]}")
    legacy = Warehouse(
        tenant_id=tenant.id,
        name="FBS WB 999",
        code="fbs-wb-999",
        is_operational=False,
    )
    session.add_all([user, seller, warehouse_a, warehouse_b, legacy])
    await session.flush()
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="P1",
        sku_code=f"P1-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_percent=100,
    )
    session.add(product)
    await session.flush()
    return {
        "tenant": tenant,
        "seller": seller,
        "warehouse_a": warehouse_a,
        "warehouse_b": warehouse_b,
        "legacy": legacy,
        "product": product,
    }


@pytest.mark.asyncio
async def test_c1_balance_spread_across_places_matches_everywhere(
    db_session: AsyncSession,
) -> None:
    """R1, R4, R9, R11, R14: 21 штук в разных местах — Остаток 21 везде."""
    session = db_session
    seed = await _base_seed(session)
    tenant, product = seed["tenant"], seed["product"]
    warehouse_a, warehouse_b, legacy = (
        seed["warehouse_a"],
        seed["warehouse_b"],
        seed["legacy"],
    )

    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    sorting_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    cell_b = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_b.id,
        code="B-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    legacy_loc = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=legacy.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([cell_a, sorting_a, cell_b, legacy_loc])
    await session.flush()
    box = WarehouseBox(
        tenant_id=tenant.id,
        warehouse_id=warehouse_b.id,
        storage_location_id=cell_b.id,
        internal_barcode=f"BOX-{uuid.uuid4().hex[:8]}",
    )
    session.add(box)
    await session.flush()
    defect_loc = await get_or_create_defect_location(session, tenant.id)

    session.add_all(
        [
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=cell_a.id,
                quantity=10,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=sorting_a.id,
                quantity=5,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=cell_b.id,
                quantity=3,
                container_id=box.id,
                container_kind="box",
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=legacy_loc.id,
                quantity=2,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=defect_loc.id,
                quantity=1,
            ),
        ]
    )
    await session.commit()

    # R1/R4: одно и то же Остаток = 21 из общего расчёта...
    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert totals[product.id].on_hand == 21
    # D2: 1 штука брака входит в Остаток и в Резерв — Доступно её не включает.
    assert totals[product.id].reserved == 1
    assert totals[product.id].available == 20

    # ...и из окна «Остаток для FBS» (никаких привязок ещё нет — просто те же числа).
    views = await get_rule_views(session, tenant.id, [product.id])
    view = views[product.id]
    assert (view.on_hand, view.reserved, view.free_stock) == (21, 1, 20)

    # R9: инвентаризация "на весь остаток товара" видит сумму "Числится" = 21.
    user_id = await session.scalar(select(User.id).where(User.tenant_id == tenant.id))
    assert user_id is not None
    count = await inventory_count_service.create_count(
        session,
        tenant.id,
        user_id=user_id,
        source=inventory_count_service.SOURCE_OBJECT,
        object_scope=inventory_count_service.CountObject(type="product", id=product.id),
        filters=None,
        comment=None,
    )
    total_expected = sum(line.expected_quantity for line in count.lines)
    assert total_expected == 21

    # R11: перемещение 3 шт со склада Б на А — расположение, остаток не меняет.
    balance_b = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.product_id == product.id,
            InventoryBalance.storage_location_id == cell_b.id,
        )
    )
    assert balance_b is not None
    balance_b.quantity -= 3
    balance_a = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.product_id == product.id,
            InventoryBalance.storage_location_id == cell_a.id,
        )
    )
    assert balance_a is not None
    balance_a.quantity += 3
    await session.commit()

    totals_after_move = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert totals_after_move[product.id].on_hand == 21
    assert totals_after_move[product.id].available == 20


@pytest.mark.asyncio
async def test_c2_reserve_composition_lifecycle_matches_everywhere(
    db_session: AsyncSession,
) -> None:
    """R2, R3, R4, R7, R8: состав Резерва и его снятие видны одинаково всюду."""
    session = db_session
    seed = await _base_seed(session)
    tenant, seller, product = seed["tenant"], seed["seller"], seed["product"]
    warehouse_a, warehouse_b = seed["warehouse_a"], seed["warehouse_b"]

    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(cell_a)
    await session.flush()
    session.add(
        InventoryBalance(
            tenant_id=tenant.id, product_id=product.id, storage_location_id=cell_a.id, quantity=20
        )
    )

    # Отгрузка на МП: план 4, собрано 1 (собранное уже списано и снято с брони).
    mp_request = MarketplaceUnloadRequest(
        tenant_id=tenant.id,
        warehouse_id=warehouse_b.id,
        seller_id=seller.id,
        status="collecting",
        ff_modified=False,
        has_discrepancy=False,
    )
    session.add(mp_request)
    await session.flush()
    mp_line = MarketplaceUnloadLine(request_id=mp_request.id, product_id=product.id, quantity=4)
    session.add(mp_line)
    await session.flush()
    session.add(
        MarketplaceUnloadReservation(
            tenant_id=tenant.id,
            marketplace_unload_line_id=mp_line.id,
            product_id=product.id,
            warehouse_id=warehouse_b.id,
            quantity=3,
        )
    )

    # Заказ FBS WB на 1 шт, склад заказа — Б (доступность — организации, R7).
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        warehouse_id=warehouse_b.id,
        wb_order_id=990001,
        created_at_wb=mp_request.created_at,
        deadline_at=mp_request.created_at,
        mapping_status="mapped",
        reserve_status="not_published",
        status="new",
    )
    session.add(order)
    await session.flush()
    session.add(
        FbsOrderReservation(
            tenant_id=tenant.id,
            fbs_order_id=order.id,
            product_id=product.id,
            warehouse_id=warehouse_b.id,
            quantity=1,
        )
    )

    # Заказ Ozon с позицией на 2 шт.
    ozon_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        external_order_id="ozon-c2",
        warehouse_id=warehouse_a.id,
        wb_order_id=-1,
        wb_warehouse_id=1,
        created_at_wb=mp_request.created_at,
        deadline_at=mp_request.created_at,
        mapping_status="mapped",
        reserve_status="not_published",
        status="new",
    )
    session.add(ozon_order)
    await session.flush()
    ozon_position = FbsOrderProduct(
        order_id=ozon_order.id, product_id=product.id, ozon_sku=1, position_index=0, quantity=2
    )
    session.add(ozon_position)
    await session.flush()
    session.add(
        FbsOrderProductReservation(
            tenant_id=tenant.id,
            order_product_id=ozon_position.id,
            product_id=product.id,
            warehouse_id=warehouse_a.id,
            quantity=2,
        )
    )

    # Ручное направление на 3 шт.
    session.add(
        StockDirection(tenant_id=tenant.id, product_id=product.id, name="Наборы", quantity=3)
    )

    # Старая «Отгрузка»: черновик на 1 шт.
    outbound = OutboundShipmentRequest(
        tenant_id=tenant.id, warehouse_id=warehouse_a.id, seller_id=seller.id, status="draft"
    )
    session.add(outbound)
    await session.flush()
    outbound_line = OutboundShipmentLine(
        request_id=outbound.id, product_id=product.id, quantity=1, shipped_qty=0
    )
    session.add(outbound_line)
    await session.flush()
    await inventory_service.sync_outbound_line_reservation(
        session, tenant.id, outbound, outbound_line
    )
    await session.commit()

    # Остаток 20, Резерв 3(МП)+1(WB)+2(Ozon)+3(направление)+1(старая Отгрузка)=10, Доступно 10.
    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert totals[product.id].on_hand == 20
    assert totals[product.id].reserved == 10
    assert totals[product.id].available == 10

    # Тот же товар из окна «Остаток для FBS».
    view = (await get_rule_views(session, tenant.id, [product.id]))[product.id]
    assert (view.on_hand, view.reserved, view.free_stock) == (20, 10, 10)

    # Список отгрузки на МП: этот же документ видит доступное с учётом СВОЕЙ
    # брони (3 шт) — вернуть свою бронь означает больше, чем 10, ровно на неё.
    products_for_own_request = await list_available_products(
        session,
        tenant.id,
        warehouse_id=warehouse_b.id,
        seller_id=seller.id,
        exclude_request_id=mp_request.id,
    )
    own_row = next(row for row in products_for_own_request if row.product_id == product.id)
    assert own_row.available == 13

    # Список для НОВОГО документа (без исключения) видит обычные 10.
    products_for_new_request = await list_available_products(
        session, tenant.id, warehouse_id=warehouse_a.id, seller_id=seller.id
    )
    new_row = next(row for row in products_for_new_request if row.product_id == product.id)
    assert new_row.available == 10


@pytest.mark.asyncio
async def test_r15_retry_import_does_not_double_reserve(db_session: AsyncSession) -> None:
    """R15: повтор той же операции не создаёт вторую бронь."""
    session = db_session
    seed = await _base_seed(session)
    tenant, seller, product = seed["tenant"], seed["seller"], seed["product"]
    warehouse_a = seed["warehouse_a"]
    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(cell_a)
    await session.flush()
    session.add(
        InventoryBalance(
            tenant_id=tenant.id, product_id=product.id, storage_location_id=cell_a.id, quantity=1
        )
    )
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        warehouse_id=warehouse_a.id,
        wb_order_id=990002,
        created_at_wb=None,
        deadline_at=None,
        mapping_status="mapped",
        reserve_status="not_published",
        status="new",
    )
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    order.created_at_wb = now
    order.deadline_at = now
    session.add(order)
    await session.flush()
    await session.commit()

    await inventory_service.update_fbs_order_reservation(session, order, reserve=True)
    await session.commit()
    assert order.reserve_status == "reserved"
    # Повтор доставки импорта того же заказа: та же операция вызывается снова.
    await inventory_service.update_fbs_order_reservation(session, order, reserve=True)
    await session.commit()

    reservations = (
        await session.scalars(
            select(inventory_service.FbsOrderReservation).where(
                inventory_service.FbsOrderReservation.fbs_order_id == order.id
            )
        )
    ).all()
    assert len(reservations) == 1
    assert reservations[0].quantity == 1
    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert totals[product.id].available == 0


@pytest.mark.asyncio
async def test_r15_concurrent_reservations_last_unit_only_one_wins(
    db_session: AsyncSession,
) -> None:
    """R15 (C15): Доступно = 1, одновременно WB и Ozon — ровно одна бронь."""
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL row lock concurrency")
    session = db_session
    seed = await _base_seed(session)
    tenant, seller, product = seed["tenant"], seed["seller"], seed["product"]
    warehouse_a, warehouse_b = seed["warehouse_a"], seed["warehouse_b"]
    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(cell_a)
    await session.flush()
    session.add(
        InventoryBalance(
            tenant_id=tenant.id, product_id=product.id, storage_location_id=cell_a.id, quantity=1
        )
    )
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    wb_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        warehouse_id=warehouse_b.id,
        wb_order_id=990003,
        created_at_wb=now,
        deadline_at=now,
        mapping_status="mapped",
        reserve_status="not_published",
        status="new",
    )
    ozon_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        marketplace="ozon",
        external_order_id="ozon-race",
        warehouse_id=warehouse_a.id,
        wb_order_id=-2,
        wb_warehouse_id=2,
        created_at_wb=now,
        deadline_at=now,
        mapping_status="mapped",
        reserve_status="not_published",
        status="new",
    )
    session.add_all([wb_order, ozon_order])
    await session.commit()
    wb_order_id, ozon_order_id, tenant_id = wb_order.id, ozon_order.id, tenant.id

    async def _reserve(order_id: uuid.UUID) -> str:
        async with SessionLocal() as own_session, own_session.begin():
            order = await own_session.get(FbsOrder, order_id)
            assert order is not None
            await inventory_service.update_fbs_order_reservation(own_session, order, reserve=True)
            return order.reserve_status

    results = await asyncio.gather(_reserve(wb_order_id), _reserve(ozon_order_id))
    assert sorted(results) == ["no_stock", "reserved"]

    async with SessionLocal() as check_session:
        totals = await organization_stock_totals_by_product(check_session, tenant_id, [product.id])
        assert totals[product.id].available == 0
        reserved_orders = (
            await check_session.scalars(
                select(FbsOrder.id).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.reserve_status == "reserved",
                )
            )
        ).all()
        assert len(reserved_orders) == 1
