"""WMS-530: один расчёт «Остаток / Резерв / Доступно» на организацию.

Проверки C1-C3 и C15 из docs/requirements/WMS-530.md: одни и те же три числа
у всех потребителей (каталог, окно «Остаток для FBS», бронь заказа FBS,
отгрузка на МП, инвентаризация), расположение (склад/зона/тара, включая
несколько реальных складов и склад брака) не исключает строку и не блокирует
работу, и одновременная бронь последней единицы не создаёт вторую бронь.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
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
    product_ids_with_any_reserve,
)
from app.services.fbs_stock_rule_service import get_rule_views
from app.services.marketplace_unload_service import (
    MarketplaceUnloadError,
    add_line,
    confirm_request,
    create_request,
    list_available_products,
)
from app.services.sorting_location_service import SORTING_LOCATION_CODE


@pytest.fixture(autouse=True)
def _no_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inventory_service, "schedule_seller_stock_publish", lambda *a: None)


async def _base_seed(session: AsyncSession) -> dict[str, object]:
    """Организация с тремя рабочими складами и складом брака.

    WMS-516 закрывает старый marketplace-псевдосклад (`fbs-wb-*`) и вообще
    любой неоперационный склад, кроме `__DEFECT__`, для новых физических
    записей: держать там реальный остаток в фикстуре больше нельзя, это сама
    по себе несовместимость с новыми guard-триггерами, а не продуктовый
    регресс. Третий обычный склад сохраняет проверяемую суть R1/R4/R9/R11 —
    остаток считается одинаково независимо от того, на каком реальном складе
    лежит товар.
    """
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
    warehouse_c = Warehouse(tenant_id=tenant.id, name="Склад В", code=f"c-{uuid.uuid4().hex[:6]}")
    session.add_all([user, seller, warehouse_a, warehouse_b, warehouse_c])
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
        "warehouse_c": warehouse_c,
        "product": product,
    }


async def _seed_defect_balance(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    defect_location_id: uuid.UUID,
    quantity: int,
) -> None:
    """Place a starting balance directly in the tenant's defect location.

    The WMS-516 guard accepts a physical write to `__DEFECT__` only inside the
    same transaction-local grant the real defect/return flow uses (see
    `defect_warehouse_service.defect_service_write`); a plain `session.add`
    after `get_or_create_defect_location` has already returned is exactly the
    unprivileged write the guard is meant to reject. This mirrors that grant
    for test setup instead of routing every fixture through the full
    putaway/return service call.
    """
    postgres = session.get_bind().dialect.name == "postgresql"
    async with session.begin_nested():
        if postgres:
            await session.execute(
                text("SELECT set_config('wms.defect_tenant', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id,
            storage_location_id=defect_location_id, quantity=quantity,
        ))
        await session.flush()


@pytest.mark.asyncio
async def test_c1_balance_spread_across_places_matches_everywhere(
    db_session: AsyncSession,
) -> None:
    """R1, R4, R9, R11, R14: 21 штук в разных местах — Остаток 21 везде."""
    session = db_session
    seed = await _base_seed(session)
    tenant, product = seed["tenant"], seed["product"]
    warehouse_a, warehouse_b, warehouse_c = (
        seed["warehouse_a"],
        seed["warehouse_b"],
        seed["warehouse_c"],
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
    cell_c = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_c.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([cell_a, sorting_a, cell_b, cell_c])
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
                storage_location_id=cell_c.id,
                quantity=2,
            ),
        ]
    )
    await session.flush()
    await _seed_defect_balance(session, tenant.id, product.id, defect_loc.id, 1)
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
        # WMS-530 review R15 note: no product_id here on purpose. A real Ozon
        # order carries its product only through FbsOrderProduct positions,
        # and reserving via update_fbs_order_reservation must go through the
        # per-position FbsOrderProductReservation path below, not the WB
        # single-product FbsOrderReservation fallback.
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
    await session.flush()
    session.add(
        FbsOrderProduct(
            order_id=ozon_order.id,
            product_id=product.id,
            ozon_sku=1,
            position_index=0,
            quantity=1,
        )
    )
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
        # Whichever side won took the real path for its marketplace: WB через
        # FbsOrderReservation, Ozon — через позиционный FbsOrderProductReservation.
        wb_reservations = (
            await check_session.scalars(
                select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == wb_order_id)
            )
        ).all()
        ozon_reservations = (
            await check_session.scalars(
                select(FbsOrderProductReservation).where(
                    FbsOrderProductReservation.order_product_id.in_(
                        select(FbsOrderProduct.id).where(FbsOrderProduct.order_id == ozon_order_id)
                    )
                )
            )
        ).all()
        assert len(wb_reservations) + len(ozon_reservations) == 1


@pytest.mark.asyncio
async def test_f1_new_line_in_confirmed_mp_unload_gets_reserved(
    db_session: AsyncSession,
) -> None:
    """Ревью Astra F1 (P1): строка, добавленная в подтверждённую отгрузку на

    МП, обязана получить резерв немедленно, иначе единицу можно продать
    дважды — одну и ту же единицу видят свободной и МП-документ, и бронь
    другого заказа FBS.
    """
    from datetime import date

    session = db_session
    seed = await _base_seed(session)
    tenant, seller = seed["tenant"], seed["seller"]
    warehouse_a, warehouse_b = seed["warehouse_a"], seed["warehouse_b"]
    product_q = seed["product"]
    product_p = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="P",
        sku_code=f"P-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_percent=100,
    )
    session.add(product_p)
    await session.flush()
    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(cell_a)
    await session.flush()
    session.add_all(
        [
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product_p.id,
                storage_location_id=cell_a.id,
                quantity=1,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product_q.id,
                storage_location_id=cell_a.id,
                quantity=1,
            ),
        ]
    )
    await session.commit()
    tenant_id, seller_id = tenant.id, seller.id
    warehouse_a_id, warehouse_b_id = warehouse_a.id, warehouse_b.id
    product_p_id, product_q_id = product_p.id, product_q.id

    # Each lifecycle step below uses its own fresh session, exactly like the
    # API does one per request — this reproduces Astra's scenario faithfully
    # instead of relying on a single session's identity-map staleness.
    async with SessionLocal() as s1:
        req = await create_request(
            s1, tenant_id, warehouse_id=warehouse_b_id, seller_id=seller_id, marketplace="ozon"
        )
        req_id = req.id
    async with SessionLocal() as s2:
        await add_line(s2, tenant_id, req_id, product_id=product_q_id, quantity=1)
    async with SessionLocal() as s3:
        req = await confirm_request(s3, tenant_id, req_id, planned_shipment_date=date(2026, 6, 1))
        assert req.status == "confirmed"

    async with SessionLocal() as s4:
        totals_after_confirm = await organization_stock_totals_by_product(
            s4, tenant_id, [product_q_id]
        )
        assert totals_after_confirm[product_q_id].available == 0

    # WMS-530 review F1: add P to the already-confirmed document.
    async with SessionLocal() as s5:
        await add_line(
            s5, tenant_id, req_id, product_id=product_p_id, quantity=1, allow_ff_confirmed=True
        )

    async with SessionLocal() as s6:
        totals_after_add = await organization_stock_totals_by_product(s6, tenant_id, [product_p_id])
        assert totals_after_add[product_p_id].reserved == 1
        assert totals_after_add[product_p_id].available == 0

        reservations = (
            await s6.scalars(
                select(MarketplaceUnloadReservation).where(
                    MarketplaceUnloadReservation.product_id == product_p_id
                )
            )
        ).all()
        assert len(reservations) == 1
        assert reservations[0].quantity == 1

    # A competing WB order for the same unit must now see no_stock, not reserved.
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    async with SessionLocal() as s7:
        wb_order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product_p_id,
            warehouse_id=warehouse_a_id,
            wb_order_id=990010,
            created_at_wb=now,
            deadline_at=now,
            mapping_status="mapped",
            reserve_status="not_published",
            status="new",
        )
        s7.add(wb_order)
        await s7.commit()
        await inventory_service.update_fbs_order_reservation(s7, wb_order, reserve=True)
        assert wb_order.reserve_status == "no_stock"


@pytest.mark.asyncio
async def test_f2_rule_view_shows_negative_available_not_clamped(
    db_session: AsyncSession,
) -> None:
    """Ревью Astra F2 (P2): окно «Остаток для FBS» показывает Доступно как

    есть, включая отрицательное (R3/D3) — только основа для публикации и
    split_amounts обрезается нулём, а не то, что видит оператор на экране.
    """
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
    # A manual reserve above on-hand is a legitimate D3 state (inventory count
    # can shrink on-hand under a live manual reserve).
    session.add(
        StockDirection(tenant_id=tenant.id, product_id=product.id, name="Перебор", quantity=2)
    )
    binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=1,
        wms_warehouse_id=warehouse_a.id,
        is_active=True,
        stock_sync_enabled=True,
        served=True,
    )
    session.add(binding)
    await session.commit()

    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert (
        totals[product.id].on_hand,
        totals[product.id].reserved,
        totals[product.id].available,
    ) == (
        1,
        2,
        -1,
    )

    view = (await get_rule_views(session, tenant.id, [product.id]))[product.id]
    assert view.on_hand == 1
    assert view.reserved == 2
    assert view.free_stock == -1
    assert view.published_now == 0
    binding_view = view.by_binding[binding.id]
    assert binding_view.on_hand == 1
    assert binding_view.reserved == 2
    assert binding_view.free_stock == -1
    assert binding_view.published_now == 0


@pytest.mark.asyncio
async def test_f3_worklist_availability_is_per_order_not_per_list(
    db_session: AsyncSession,
) -> None:
    """Ревью Astra F3 (P2): доступное каждого заказа не зависит ни от состава

    списка заказов, переданного в расчёт, ни от заказов-соседей одного товара
    на одном складе — у каждого заказа своя собственная бронь и число.
    """
    from datetime import UTC, datetime

    from app.services.fbs_worklist_service import _load_availability_by_order

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
            tenant_id=tenant.id, product_id=product.id, storage_location_id=cell_a.id, quantity=2
        )
    )
    await session.commit()

    now = datetime.now(UTC)

    def _new_order(warehouse: Warehouse, wb_order_id: int) -> FbsOrder:
        return FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            wb_order_id=wb_order_id,
            created_at_wb=now,
            deadline_at=now,
            mapping_status="mapped",
            reserve_status="not_published",
            status="new",
        )

    order_a = _new_order(warehouse_a, 990020)
    order_b = _new_order(warehouse_b, 990021)
    session.add_all([order_a, order_b])
    await session.flush()
    await session.commit()
    await inventory_service.update_fbs_order_reservation(session, order_a, reserve=True)
    await inventory_service.update_fbs_order_reservation(session, order_b, reserve=True)
    assert order_a.reserve_status == "reserved"
    assert order_b.reserve_status == "reserved"

    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert (
        totals[product.id].on_hand,
        totals[product.id].reserved,
        totals[product.id].available,
    ) == (
        2,
        2,
        0,
    )

    both = await _load_availability_by_order(session, tenant.id, [order_a, order_b])
    assert both[order_a.id] == 1
    assert both[order_b.id] == 1

    # Same order, alone in the list: its own number must not change.
    only_a = await _load_availability_by_order(session, tenant.id, [order_a])
    assert only_a[order_a.id] == 1


@pytest.mark.asyncio
async def test_f4a_count_without_address_storage_includes_defect(
    db_session: AsyncSession,
) -> None:
    """Ревью Astra F4-А (P2): без адресного хранения инвентаризация всего

    товара включает штатный склад брака (R1/D2), а не только сортировку.
    """
    session = db_session
    seed = await _base_seed(session)
    tenant, product = seed["tenant"], seed["product"]
    warehouse_a = seed["warehouse_a"]
    tenant.address_storage_enabled = False
    sorting_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(sorting_a)
    await session.flush()
    defect_loc = await get_or_create_defect_location(session, tenant.id)
    session.add(
        InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=sorting_a.id,
            quantity=5,
        ),
    )
    await session.flush()
    await _seed_defect_balance(session, tenant.id, product.id, defect_loc.id, 1)
    await session.commit()

    totals = await organization_stock_totals_by_product(session, tenant.id, [product.id])
    assert totals[product.id].on_hand == 6

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
    assert sum(line.expected_quantity for line in count.lines) == 6


@pytest.mark.asyncio
async def test_f4b_count_without_address_storage_spans_two_warehouses(
    db_session: AsyncSession,
) -> None:
    """Ревью Astra F4-Б (P2): без адресного хранения остаток на двух рабочих

    складах не блокирует создание общего документа инвентаризации (R9/R11).
    """
    session = db_session
    seed = await _base_seed(session)
    tenant, product = seed["tenant"], seed["product"]
    warehouse_a, warehouse_b = seed["warehouse_a"], seed["warehouse_b"]
    tenant.address_storage_enabled = False
    sorting_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    sorting_b = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_b.id,
        code=SORTING_LOCATION_CODE,
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([sorting_a, sorting_b])
    await session.flush()
    session.add_all(
        [
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=sorting_a.id,
                quantity=1,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=sorting_b.id,
                quantity=1,
            ),
        ]
    )
    await session.commit()

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
    assert sum(line.expected_quantity for line in count.lines) == 2
    assert count.warehouse_id is None


@pytest.mark.asyncio
async def test_r15_fbs_races_mp_unload_add_line_to_confirmed(
    db_session: AsyncSession,
) -> None:
    """R15/review F1: PostgreSQL-гонка настоящего конкурентного исполнения —

    одновременно бронь заказа FBS WB и добавление той же единицы новой
    строкой в уже подтверждённую отгрузку на МП (allow_ff_confirmed). Ровно
    одна сторона получает единицу; включает F1 в реальную конкуренцию, а не
    только в последовательное воспроизведение.
    """
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL row lock concurrency")
    session = db_session
    seed = await _base_seed(session)
    tenant, seller, product_p = seed["tenant"], seed["seller"], seed["product"]
    warehouse_a, warehouse_b = seed["warehouse_a"], seed["warehouse_b"]
    product_q = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Q",
        sku_code=f"Q-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_percent=100,
    )
    session.add(product_q)
    await session.flush()
    cell_a = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse_a.id,
        code="A-01",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    session.add(cell_a)
    await session.flush()
    session.add_all(
        [
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product_p.id,
                storage_location_id=cell_a.id,
                quantity=1,
            ),
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product_q.id,
                storage_location_id=cell_a.id,
                quantity=1,
            ),
        ]
    )
    await session.commit()
    tenant_id, seller_id = tenant.id, seller.id
    warehouse_a_id, warehouse_b_id = warehouse_a.id, warehouse_b.id
    product_p_id, product_q_id = product_p.id, product_q.id

    from datetime import date

    async with SessionLocal() as s1:
        req = await create_request(
            s1, tenant_id, warehouse_id=warehouse_b_id, seller_id=seller_id, marketplace="ozon"
        )
        req_id = req.id
    async with SessionLocal() as s2:
        await add_line(s2, tenant_id, req_id, product_id=product_q_id, quantity=1)
    async with SessionLocal() as s3:
        await confirm_request(s3, tenant_id, req_id, planned_shipment_date=date(2026, 6, 1))

    async def _add_p_to_confirmed() -> str:
        async with SessionLocal() as s:
            try:
                await add_line(
                    s, tenant_id, req_id, product_id=product_p_id, quantity=1,
                    allow_ff_confirmed=True,
                )
                return "line_added"
            except MarketplaceUnloadError as exc:
                return f"line_rejected:{exc.code}"

    async def _reserve_wb_order() -> str:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        async with SessionLocal() as s, s.begin():
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_p_id,
                warehouse_id=warehouse_a_id,
                wb_order_id=990030,
                created_at_wb=now,
                deadline_at=now,
                mapping_status="mapped",
                reserve_status="not_published",
                status="new",
            )
            s.add(order)
            await s.flush()
            await inventory_service.update_fbs_order_reservation(s, order, reserve=True)
            return order.reserve_status

    line_result, wb_result = await asyncio.gather(_add_p_to_confirmed(), _reserve_wb_order())

    # Exactly one side claimed the unit.
    line_won = line_result == "line_added"
    wb_won = wb_result == "reserved"
    assert line_won != wb_won, (line_result, wb_result)

    async with SessionLocal() as check_session:
        totals = await organization_stock_totals_by_product(
            check_session, tenant_id, [product_p_id]
        )
        assert totals[product_p_id].reserved == 1
        assert totals[product_p_id].available == 0


@pytest.mark.asyncio
async def test_orphan_reserved_product_shows_in_summary_without_balance_row(
    async_client: AsyncClient,
) -> None:
    """Дополнение к ревью (найдено фронт-исполнителем в браузере): товар с

    активной бронью, но без единой строки InventoryBalance (полностью
    списан/отгружен, а бронь ещё не снята), должен показать Остаток 0 /
    Резерв N / Доступно -N в сводке каталога/кабинета продавца — как и
    окно «Остаток для FBS», а не молча пропасть (R3/R4).
    """
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Orphan reserve",
            "slug": f"orphan-reserve-{suffix}",
            "admin_email": f"orphan-reserve-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Seller"}
    )
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(seller.json()["id"])
    product_resp = await async_client.post(
        "/products",
        headers=admin_headers,
        json={"name": "Orphan", "sku_code": f"ORPHAN-{suffix}", "seller_id": str(seller_id)},
    )
    assert product_resp.status_code == 200, product_resp.text
    product_id = uuid.UUID(product_resp.json()["id"])

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        product.fbs_stock_sync_enabled = True
        product.fbs_percent = 100
        location = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code="A-01",
            barcode=f"BC-{uuid.uuid4().hex[:8]}",
        )
        session.add(location)
        await session.flush()
        balance = InventoryBalance(
            tenant_id=tenant_id, product_id=product_id, storage_location_id=location.id, quantity=1
        )
        session.add(balance)
        await session.commit()

        from datetime import UTC, datetime

        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            wb_order_id=990040,
            created_at_wb=now,
            deadline_at=now,
            mapping_status="mapped",
            reserve_status="not_published",
            status="new",
        )
        session.add(order)
        await session.flush()
        await session.commit()
        await inventory_service.update_fbs_order_reservation(session, order, reserve=True)
        assert order.reserve_status == "reserved"
        await session.commit()

        # Simulate "fully written off, reserve still open": delete the only
        # balance row outright, not just zero its quantity.
        await session.delete(balance)
        await session.commit()

        # The service-level helper finds the orphan directly.
        orphans = await product_ids_with_any_reserve(session, tenant_id, seller_id=seller_id)
        assert product_id in orphans

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=admin_headers,
    )
    assert summary.status_code == 200, summary.text
    row = next(
        (r for r in summary.json() if r["product_id"] == str(product_id)), None
    )
    assert row is not None, "orphan reserved product must not disappear from the summary"
    assert row["quantity"] == 0
    assert row["reserved"] == 1
    assert row["available"] == -1
