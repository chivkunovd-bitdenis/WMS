"""WMS-338 / WMS-341 / WMS-329 · pool.quantity — операторский потолок, не счётчик.

Контракт владельца:
    "FbsBindingStockPool.quantity = OPERATOR-SET CAP. Only operator changes it.
    Publish min(cap, free_stock). No journals, no counters, no reservation ledger,
    no recharges."

Проверки четырёх прежних мутаций потолка и расчёта публикации:

    1) резервирование FBS-заказа НЕ трогает pool.quantity
    2) отмена до передачи НЕ трогает pool.quantity
    3) инвентаризационная недостача НЕ трогает pool.quantity
    4) передача без резерва НЕ трогает pool.quantity
       (apply_fbs_supply_write_off)
    5) изменение свободного остатка проходит в публикацию как min(cap, free)
       (через fbs_stock_rule_service.split_amounts)

Если следующий агент восстановит один из этих расходов — тесты остановят
слияние. Не удалять и не смягчать без прямого нового решения владельца.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_NO_STOCK,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_INVENTORY_COUNT, InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import inventory_service
from app.services.fbs_stock_rule_service import FbsRule, get_rule_view, split_amounts

WB_WAREHOUSE_ID = 501001
OPERATOR_CAP = 5


@dataclass
class _Scenario:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    binding: FbsWarehouseBinding
    location: StorageLocation
    product: Product
    pool: FbsBindingStockPool


async def _seed(
    session: AsyncSession,
    *,
    on_hand: int,
    units_mode: bool = True,
) -> _Scenario:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(id=uuid.uuid4(), name="T", slug=f"t-{suffix}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="S")
    warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="WH",
        code=f"wh-{suffix}",
    )
    binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=WB_WAREHOUSE_ID,
        wms_warehouse_id=warehouse.id,
        marketplace="wb",
        is_active=True,
        stock_sync_enabled=True,
        served=True,
    )
    location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code=f"CELL-{suffix}",
        barcode=f"BC-{suffix}",
    )
    product = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Товар",
        sku_code=f"SKU-{suffix}",
        fbs_stock_sync_enabled=True,
        fbs_units_mode=units_mode,
        fbs_percent=100 if not units_mode else None,
    )
    session.add_all([tenant, seller, warehouse, binding, location, product])
    await session.flush()
    balance = InventoryBalance(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        storage_location_id=location.id,
        product_id=product.id,
        quantity=on_hand,
        quantity_unpacked=on_hand,
        quantity_packed=0,
    )
    pool = FbsBindingStockPool(
        tenant_id=tenant.id,
        binding_id=binding.id,
        product_id=product.id,
        quantity=OPERATOR_CAP,
        percent=None,
    )
    session.add_all([balance, pool])
    await session.commit()
    await session.refresh(pool)
    return _Scenario(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        binding=binding,
        location=location,
        product=product,
        pool=pool,
    )


def _fbs_order(scen: _Scenario, *, wb_order_id: int) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=scen.tenant.id,
        seller_id=scen.seller.id,
        warehouse_id=scen.warehouse.id,
        product_id=scen.product.id,
        marketplace="wb",
        wb_order_id=wb_order_id,
        wb_warehouse_id=WB_WAREHOUSE_ID,
        status=FBS_ORDER_STATUS_NEW,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_NO_STOCK,
    )


async def _reload_pool_quantity(session: AsyncSession, pool_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(FbsBindingStockPool.quantity).where(FbsBindingStockPool.id == pool_id)
        )
        or 0
    )


@pytest.mark.asyncio
async def test_reservation_does_not_change_operator_cap(db_session: AsyncSession) -> None:
    """WMS-338: резерв заказа больше не расходует операторский потолок.

    Раньше update_fbs_order_reservation в units-mode делал
    `pool.quantity -= required[pid]`. Это был второй счётчик той же величины,
    что уже выражена свободным остатком; на инциденте 04.09.2026 разъезд
    двух счётчиков сожрал 335 единиц.
    """
    scen = await _seed(db_session, on_hand=10)
    order = _fbs_order(scen, wb_order_id=1000001)
    db_session.add(order)
    await db_session.flush()

    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=True)
    await db_session.commit()

    view = await get_rule_view(db_session, scen.tenant.id, scen.product.id)
    assert (view.on_hand, view.reserved, view.free_stock) == (10, 1, 9)
    assert await db_session.scalar(select(func.count()).select_from(FbsOrderReservation)) == 1

    cap = await _reload_pool_quantity(db_session, scen.pool.id)
    assert cap == OPERATOR_CAP, (
        "pool.quantity — операторский потолок, резерв заказа не должен его "
        f"расходовать; было {OPERATOR_CAP}, стало {cap}"
    )


@pytest.mark.asyncio
async def test_cancel_before_transfer_does_not_change_operator_cap(
    db_session: AsyncSession,
) -> None:
    """WMS-338/329: снятие резерва до передачи не возвращает ничего в потолок.

    Раньше отмена делала `pool.quantity += reservation.quantity`. Возвращать
    некуда: сам резерв уже перестал держать свободный остаток, и следующая
    публикация уедет как min(cap, free) без отдельной прибавки.
    """
    scen = await _seed(db_session, on_hand=10)
    order = _fbs_order(scen, wb_order_id=1000002)
    db_session.add(order)
    await db_session.flush()

    # 1. Ставим резерв. По WMS-338 потолок не тронется.
    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=True)
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(FbsOrderReservation)) == 1
    assert (await get_rule_view(db_session, scen.tenant.id, scen.product.id)).free_stock == 9
    cap_after_reserve = await _reload_pool_quantity(db_session, scen.pool.id)
    assert cap_after_reserve == OPERATOR_CAP

    # 2. Снимаем резерв. По WMS-338 потолок опять не тронется.
    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=False)
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(FbsOrderReservation)) == 0
    assert (await get_rule_view(db_session, scen.tenant.id, scen.product.id)).free_stock == 10
    cap = await _reload_pool_quantity(db_session, scen.pool.id)
    assert cap == OPERATOR_CAP, (
        "Отмена резерва до передачи не имеет права возвращать что-либо в "
        f"операторский потолок; было {OPERATOR_CAP}, стало {cap}"
    )


@pytest.mark.asyncio
async def test_inventory_shortage_does_not_change_operator_cap(
    db_session: AsyncSession,
) -> None:
    """WMS-338: атрибуция шортажа операторскому потолку — только показ.

    Раньше _deduct_inventory_from_fbs делал `pool.quantity -= take` при
    инвентаризационной недостаче. Само число оператора не расходуется —
    физическое уменьшение баланса пойдёт через движение, а публикация возьмёт
    min(cap, свободный) на следующем тике.
    """
    scen = await _seed(db_session, on_hand=5)
    pool_id = scen.pool.id

    # Прямой вызов приватного расчёта: он же используется в реальной
    # инвентаризации при выявлении недостачи. Здесь важен только тот факт,
    # что pool.quantity не меняется на самом расчёте.
    pools = list(
        (
            await db_session.scalars(
                select(FbsBindingStockPool).where(
                    FbsBindingStockPool.product_id == scen.product.id
                )
            )
        ).all()
    )
    assert pools and pools[0].quantity == OPERATOR_CAP

    deductions = await inventory_service._deduct_inventory_from_fbs(
        db_session,
        product=scen.product,
        warehouse_id=scen.warehouse.id,
        shortage=3,
    )
    await db_session.commit()

    cap = await _reload_pool_quantity(db_session, pool_id)
    assert cap == OPERATOR_CAP, (
        "Инвентаризационная недостача не расходует операторский потолок; "
        f"было {OPERATOR_CAP}, стало {cap}"
    )
    assert deductions == [(scen.product.id, None, 3)]
    # Exercise the real inventory movement, not just its explanatory breakdown.
    await inventory_service.record_movement_and_adjust_balance(
        db_session, tenant_id=scen.tenant.id, product_id=scen.product.id,
        storage_location_id=scen.location.id, quantity_delta=-3,
        movement_type=MOVEMENT_TYPE_INVENTORY_COUNT, actor_user_id=None,
    )
    await db_session.commit()
    view = await get_rule_view(db_session, scen.tenant.id, scen.product.id)
    assert (view.on_hand, view.reserved, view.free_stock, view.published_now) == (2, 0, 2, 2)
    assert await _reload_pool_quantity(db_session, pool_id) == OPERATOR_CAP


@pytest.mark.asyncio
async def test_transfer_without_reserve_does_not_change_operator_cap(
    db_session: AsyncSession,
) -> None:
    """WMS-338: apply_fbs_supply_write_off без резерва не расходует потолок.

    Раньше при передаче без резерва в units-mode код вычислял «незарезервированную»
    часть и делал `pool.quantity = max(0, pool.quantity - unreserved)`. Убрано:
    физическое списание уменьшит баланс через record_movement, а публикация
    сама возьмёт min(cap, free) на следующем тике.
    """
    scen = await _seed(db_session, on_hand=10)
    order = _fbs_order(scen, wb_order_id=1000003)
    db_session.add(order)
    await db_session.flush()
    pool_id = scen.pool.id

    # Заранее занесли товар в ячейку в _seed. Списываем 2 без резерва.
    await inventory_service.apply_fbs_supply_write_off(
        db_session,
        tenant_id=scen.tenant.id,
        product_id=scen.product.id,
        storage_location_id=scen.location.id,
        quantity=2,
        actor_user_id=None,
        allow_negative=False,
        fbs_order_id=order.id,
    )
    await db_session.commit()

    view = await get_rule_view(db_session, scen.tenant.id, scen.product.id)
    assert (view.on_hand, view.free_stock) == (8, 8)
    assert await db_session.scalar(select(func.sum(InventoryMovement.quantity_delta))) == -2
    cap = await _reload_pool_quantity(db_session, pool_id)
    assert cap == OPERATOR_CAP, (
        "Передача без резерва не расходует операторский потолок; "
        f"было {OPERATOR_CAP}, стало {cap}"
    )


@pytest.mark.asyncio
async def test_apply_fbs_supply_write_off_still_rejects_foreign_order(
    db_session: AsyncSession,
) -> None:
    """WMS-338: удаление мутации не сняло защиту от подложенного fbs_order_id.

    Мы больше не грызём чужой потолок, но должны отказаться списывать чужой
    физический товар: sanity-check заказа сохранён и продолжает падать, если
    fbs_order_id принадлежит другому арендатору.
    """
    scen = await _seed(db_session, on_hand=10)
    # Второй арендатор с собственным заказом.
    other = await _seed(db_session, on_hand=10)
    other_order = _fbs_order(other, wb_order_id=2000001)
    db_session.add(other_order)
    await db_session.commit()

    with pytest.raises(ValueError, match="fbs order not found"):
        await inventory_service.apply_fbs_supply_write_off(
            db_session,
            tenant_id=scen.tenant.id,
            product_id=scen.product.id,
            storage_location_id=scen.location.id,
            quantity=1,
            actor_user_id=None,
            allow_negative=False,
            fbs_order_id=other_order.id,
        )


@pytest.mark.asyncio
async def test_publication_is_min_cap_and_free_stock(
    db_session: AsyncSession,
) -> None:
    """WMS-338/341: публикация — арифметика min(cap, free), без счётчиков.

    Проверяем модель поведения через split_amounts: при свободном ниже потолка
    в кабинет уедет свободный, при свободном выше — потолок. Никаких журналов
    и никаких мутаций потолка от самого расчёта.
    """
    scen = await _seed(db_session, on_hand=10)
    bindings = [scen.binding]
    pool_rows = {scen.binding.id: scen.pool}

    rule = FbsRule(
        publish=True,
        publish_ozon=False,
        same_everywhere=True,
        percent=0,
        units_mode=True,
    )

    # free = 10, cap = 5 → уедет 5 (cap).
    published = split_amounts(rule, 10, bindings, pool_rows=pool_rows)
    assert published[scen.binding.id] == OPERATOR_CAP

    # free = 2, cap = 5 → уедет 2 (free).
    published = split_amounts(rule, 2, bindings, pool_rows=pool_rows)
    assert published[scen.binding.id] == 2

    # free = 0, cap = 5 → уедет 0.
    published = split_amounts(rule, 0, bindings, pool_rows=pool_rows)
    assert published[scen.binding.id] == 0

    # Само число оператора split_amounts трогать не имеет права.
    cap = await _reload_pool_quantity(db_session, scen.pool.id)
    assert cap == OPERATOR_CAP


@pytest.mark.asyncio
async def test_concurrent_orders_reserve_last_unit_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real PostgreSQL contention, proven with pg_blocking_pids, not SQLite SQL."""
    assert db_session.bind is not None
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL via WMS_TEST_DATABASE_URL")
    monkeypatch.setattr(inventory_service, "schedule_seller_stock_publish", lambda *_: None)
    scen = await _seed(db_session, on_hand=1)
    orders = [_fbs_order(scen, wb_order_id=n) for n in (300001, 300002)]
    db_session.add_all(orders)
    await db_session.commit()
    order_ids = [order.id for order in orders]
    first_locked, release_first, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_lock = inventory_service.lock_stock_product
    second_pid: list[int] = []

    async def observed_lock(session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID):
        result = await original_lock(session, tenant_id, product_id)
        if session.info.get("first"):
            first_locked.set()
            await asyncio.wait_for(release_first.wait(), 10)
        return result

    monkeypatch.setattr(inventory_service, "lock_stock_product", observed_lock)

    async def reserve(index: int) -> None:
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
            session.info["first"] = index == 0
            order = await session.get(FbsOrder, order_ids[index])
            assert order is not None
            if index == 1:
                second_pid.append(int(await session.scalar(text("select pg_backend_pid()"))))
                second_started.set()
            await inventory_service.update_fbs_order_reservation(session, order, reserve=True)
            await session.commit()

    first = asyncio.create_task(reserve(0))
    second = None
    try:
        await asyncio.wait_for(first_locked.wait(), 10)
        second = asyncio.create_task(reserve(1))
        await asyncio.wait_for(second_started.wait(), 10)
        blocked = False
        for _ in range(200):
            blocked = bool(await db_session.scalar(
                text("select cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": second_pid[0]},
            ))
            if blocked:
                break
            await asyncio.sleep(0.01)
        assert blocked, "second transaction never waited on the real Product row lock"
    finally:
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first, *([second] if second else [])), 10)
    assert await db_session.scalar(select(func.sum(FbsOrderReservation.quantity))) == 1
    statuses = (await db_session.scalars(
        select(FbsOrder.reserve_status).where(FbsOrder.id.in_(order_ids))
    )).all()
    assert sorted(statuses) == ["no_stock", "reserved"]
    view = await get_rule_view(db_session, scen.tenant.id, scen.product.id)
    assert (view.on_hand, view.reserved, view.free_stock, view.published_now) == (1, 1, 0, 0)
    assert await _reload_pool_quantity(db_session, scen.pool.id) == OPERATOR_CAP
