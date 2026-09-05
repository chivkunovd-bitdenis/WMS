"""Правило остатка FBS: доля свободного остатка вместо сохранённого числа.

TC-NEW-FBS-RULE-001: доля считается от свободного остатка на момент публикации.
TC-NEW-FBS-RULE-002: сумма долей по складам не может превысить сто процентов.
TC-NEW-FBS-RULE-003: массовое присвоение отказывает на товарах разных продавцов.
TC-NEW-FBS-RULE-004: товар без доли не публикуется, старое число игнорируется.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_stock_rule_service import (
    FbsRule,
    FbsStockRuleError,
    amount_from_percent,
    get_rule_view,
    get_rule_views,
    publish_amounts_for_binding,
    set_rule_for_products,
    split_amounts,
    validate_rule,
)
from app.services.fbs_stock_sync_service import _resolve_publish_quantities
from app.services.stock_direction_service import create_stock_direction


class _Seed:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    bindings: list[FbsWarehouseBinding]
    product: Product


@pytest.fixture(autouse=True)
def _do_not_dispatch_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish",
        lambda *_args: None,
    )


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


def test_amount_from_percent_rounds_down() -> None:
    # Дано: свободно 324 штуки и доля 50%. Ожидаемо: 162 штуки.
    assert amount_from_percent(324, 50) == 162
    # Округление вниз: недодать безопаснее, чем продать то, чего нет.
    assert amount_from_percent(7, 30) == 2
    # Негатив: нечего отдавать — ноль, а не отрицательное число.
    assert amount_from_percent(0, 100) == 0
    assert amount_from_percent(-5, 50) == 0


def test_validate_rule_rejects_sum_over_hundred() -> None:
    # Дано: свои доли по двум складам, 100% и 70%.
    rule = FbsRule(
        publish=True,
        same_everywhere=False,
        percent=0,
        by_warehouse={1: 100, 2: 70},
    )
    # Когда правило проверяют. Тогда: отказ — столько товара просто нет.
    with pytest.raises(FbsStockRuleError) as exc:
        validate_rule(rule, served_warehouse_count=2)
    assert exc.value.code == "percent_sum_exceeded"

    # Ограничение действует и на «одинаково везде»: 60% на два склада это 120%.
    same = FbsRule(publish=True, same_everywhere=True, percent=60, by_warehouse={})
    with pytest.raises(FbsStockRuleError):
        validate_rule(same, served_warehouse_count=2)
    # А на одном складе те же 60% допустимы.
    validate_rule(same, served_warehouse_count=1)


def test_validate_rule_rejects_off_step_percent() -> None:
    # Негатив: ползунок ходит шагом в десять процентов, 55 задать нельзя.
    rule = FbsRule(publish=True, same_everywhere=True, percent=55, by_warehouse={})
    with pytest.raises(FbsStockRuleError) as exc:
        validate_rule(rule, served_warehouse_count=1)
    assert exc.value.code == "invalid_percent"


def test_split_amounts_never_exceeds_free_stock() -> None:
    # Дано: правило в базе даёт в сумме больше ста процентов — так бывает, когда
    # склад отметили нашим уже после сохранения правила.
    bindings = [
        FbsWarehouseBinding(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            seller_id=uuid.uuid4(),
            wb_warehouse_id=wb_id,
            wms_warehouse_id=uuid.uuid4(),
        )
        for wb_id in (1, 2)
    ]
    rule = FbsRule(publish=True, same_everywhere=True, percent=100, by_warehouse={})
    amounts = split_amounts(rule, 100, bindings)
    # Ожидаемо: в сумме ровно свободный остаток, а не двести штук.
    assert sum(amounts.values()) == 100
    assert amounts[bindings[0].id] == 100
    assert amounts[bindings[1].id] == 0


@pytest.mark.asyncio
async def test_rule_view_shows_three_numbers(db_session: AsyncSession) -> None:
    # Дано: 420 штук на складе, правило «половина свободного остатка».
    seed = await _seed(db_session, on_hand=420)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(publish=True, same_everywhere=True, percent=50, by_warehouse={}),
    )
    # Когда экран запрашивает правило.
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    # Тогда видно все три числа и то, что уйдёт в WB прямо сейчас.
    assert view.on_hand == 420
    assert view.reserved == 0
    assert view.free_stock == 420
    assert view.published_now == 210
    assert view.rule.percent == 50


@pytest.mark.asyncio
async def test_rule_view_counts_global_direction_reserve_once_across_warehouses(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-RULE-GLOBAL-RESERVE-001
    # Дано два физических склада по 100 штук и один глобальный резерв направления
    # 30. Когда экран суммирует склады, тогда резерв виден один раз: 30, а не 60.
    seed = await _seed(db_session, on_hand=100)
    second_warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        name="WH 2",
        code=f"wh-{uuid.uuid4().hex[:6]}",
    )
    second_location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        warehouse_id=second_warehouse.id,
        code=f"CELL-{uuid.uuid4().hex[:6]}",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all(
        [
            second_warehouse,
            second_location,
            InventoryBalance(
                id=uuid.uuid4(),
                tenant_id=seed.tenant.id,
                storage_location_id=second_location.id,
                product_id=seed.product.id,
                quantity=100,
            ),
            FbsWarehouseBinding(
                id=uuid.uuid4(),
                tenant_id=seed.tenant.id,
                seller_id=seed.seller.id,
                wb_warehouse_id=501002,
                wms_warehouse_id=second_warehouse.id,
                is_active=True,
                stock_sync_enabled=True,
                served=True,
            ),
        ]
    )
    await db_session.commit()
    await create_stock_direction(
        db_session,
        seed.tenant.id,
        seed.product.id,
        name="Глобальный резерв",
        quantity=30,
        is_fbs=False,
    )

    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)

    assert view.on_hand == 200
    assert view.reserved == 30
    assert view.free_stock == 170


@pytest.mark.asyncio
async def test_rule_view_keeps_single_warehouse_direction_math(
    db_session: AsyncSession,
) -> None:
    # TC-NEW-FBS-RULE-GLOBAL-RESERVE-002
    # Ограничение: для одного склада прежняя правильная арифметика не меняется.
    seed = await _seed(db_session, on_hand=100)
    await create_stock_direction(
        db_session,
        seed.tenant.id,
        seed.product.id,
        name="Глобальный резерв",
        quantity=30,
        is_fbs=False,
    )

    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)

    assert view.on_hand == 100
    assert view.reserved == 30
    assert view.free_stock == 70


@pytest.mark.asyncio
async def test_bulk_rule_views_match_single_rule_math(db_session: AsyncSession) -> None:
    # TC-NEW-FBS-RULE-BULK-READ-001
    # Дано два товара одного продавца на общем складе. Когда правила читаются
    # пачкой, тогда остаток и публикуемое количество совпадают с одиночным
    # расчётом для каждого товара.
    seed = await _seed(db_session, on_hand=420)
    location = await db_session.scalar(
        select(StorageLocation).where(
            StorageLocation.tenant_id == seed.tenant.id,
            StorageLocation.warehouse_id == seed.warehouse.id,
        )
    )
    assert location is not None
    second_product = Product(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        name="Second product",
        sku_code=f"SKU-{uuid.uuid4().hex[:8]}",
        wb_chrt_id=778,
        fbs_stock_sync_enabled=True,
    )
    db_session.add_all(
        [
            second_product,
            InventoryBalance(
                id=uuid.uuid4(),
                tenant_id=seed.tenant.id,
                storage_location_id=location.id,
                product_id=second_product.id,
                quantity=80,
            ),
        ]
    )
    await db_session.commit()
    product_ids = [second_product.id, seed.product.id]
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        product_ids,
        FbsRule(publish=True, same_everywhere=True, percent=50, by_warehouse={}),
    )

    bulk = await get_rule_views(db_session, seed.tenant.id, product_ids)
    singles = {
        product_id: await get_rule_view(db_session, seed.tenant.id, product_id)
        for product_id in product_ids
    }

    assert bulk == singles
    assert bulk[second_product.id].published_now == 40
    assert bulk[seed.product.id].published_now == 210


@pytest.mark.asyncio
async def test_bulk_rule_rejects_mixed_sellers(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    other_seller = Seller(id=uuid.uuid4(), tenant_id=seed.tenant.id, name="Other")
    other_product = Product(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=other_seller.id,
        name="Other product",
        sku_code=f"SKU-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all([other_seller, other_product])
    await db_session.commit()

    # Негатив: у разных продавцов свои склады, один процент разложился бы не туда.
    with pytest.raises(FbsStockRuleError) as exc:
        await set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id, other_product.id],
            FbsRule(publish=True, same_everywhere=True, percent=50, by_warehouse={}),
        )
    assert exc.value.code == "mixed_sellers"


@pytest.mark.asyncio
async def test_publish_takes_number_from_rule(db_session: AsyncSession) -> None:
    # Дано: правило «30% свободного остатка», на складе 420 штук.
    seed = await _seed(db_session, on_hand=420)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(publish=True, same_everywhere=True, percent=30, by_warehouse={}),
    )
    amounts = await publish_amounts_for_binding(db_session, seed.bindings[0], [seed.product])
    # Ожидаемо: публикация берёт 126, а не сохранённое когда-то число.
    assert amounts == {seed.product.id: 126}


@pytest.mark.asyncio
async def test_rule_save_enables_active_served_bindings_and_schedules_publish(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await _seed(db_session, wb_warehouse_ids=(501001, 501002))
    for binding in seed.bindings:
        binding.stock_sync_enabled = False
    await db_session.commit()

    scheduled: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish",
        lambda _session, tenant_id, seller_id: scheduled.append((tenant_id, seller_id)),
    )

    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(publish=False, same_everywhere=True, percent=50, by_warehouse={}),
    )

    await db_session.refresh(seed.product)
    assert seed.product.fbs_stock_sync_enabled is False
    assert seed.product.fbs_percent == 50
    for binding in seed.bindings:
        await db_session.refresh(binding)
        assert binding.is_active is True
        assert binding.served is True
        assert binding.stock_sync_enabled is True
    assert scheduled == [(seed.tenant.id, seed.seller.id)]


@pytest.mark.asyncio
async def test_product_without_rule_ignores_old_stored_number(
    db_session: AsyncSession,
) -> None:
    # Дано: товар, которому долю ещё не настроили, но старое распределение есть.
    seed = await _seed(db_session, on_hand=420)
    db_session.add(
        FbsBindingStockPool(
            tenant_id=seed.tenant.id,
            binding_id=seed.bindings[0].id,
            product_id=seed.product.id,
            quantity=17,
        )
    )
    await db_session.commit()
    # Когда публикация собирает числа.
    quantities = await _resolve_publish_quantities(db_session, seed.bindings[0], [seed.product])
    # Тогда товар не попадает в публикацию: старое абсолютное число больше не источник.
    assert quantities == {}


# --- Режим «остаток по штукам» -------------------------------------------
#
# TC-NEW-FBS-UNITS-001: числа по складам публикуются как есть, без доли.
# TC-NEW-FBS-UNITS-002: заказ съедает квоту только своего склада.
# TC-NEW-FBS-UNITS-003: отмена до передачи возвращает квоту.
# TC-NEW-FBS-UNITS-004: отмена после передачи квоту не возвращает.
# TC-NEW-FBS-UNITS-005: сумма больше свободного остатка не сохраняется.
# TC-NEW-FBS-UNITS-006: приёмка квоту не поднимает.


async def _units_seed(session: AsyncSession, *, on_hand: int = 1000) -> _Seed:
    seed = await _seed(session, on_hand=on_hand, wb_warehouse_ids=(501001, 501002))
    seed.product.fbs_units_mode = True
    await session.commit()
    return seed


async def _allocate(session: AsyncSession, seed: _Seed, amounts: dict[int, int]) -> None:
    await set_rule_for_products(
        session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            same_everywhere=False,
            percent=0,
            units_mode=True,
            units_by_warehouse=amounts,
        ),
    )


def _yesterday() -> datetime:
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) - timedelta(days=1)


async def _place_order(
    session: AsyncSession,
    seed: _Seed,
    wb_warehouse_id: int,
    *,
    status: str = "new",
    shipped: bool = False,
    created_at: datetime | None = None,
) -> None:
    """Заказ этого склада WB — ровно то, что создаёт импорт из Wildberries."""
    from datetime import UTC, datetime

    from app.models.fbs_order import FbsOrder
    from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger

    now = datetime.now(UTC)
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        product_id=seed.product.id,
        wb_order_id=int(uuid.uuid4().int % 10**12),
        wb_warehouse_id=wb_warehouse_id,
        warehouse_id=seed.warehouse.id,
        created_at_wb=now,
        deadline_at=now,
        mapping_status="mapped",
        reserve_status="reserved",
        status=status,
    )
    order.created_at = created_at if created_at is not None else now
    session.add(order)
    await session.flush()

    from app.services.inventory_service import update_fbs_order_reservation

    await update_fbs_order_reservation(session, order, reserve=True)
    if shipped:
        session.add(
            FbsShipmentReversalLedger(
                tenant_id=seed.tenant.id,
                fbs_order_id=order.id,
                product_id=seed.product.id,
                storage_location_id=uuid.uuid4(),
                quantity=1,
                shipment_movement_id=uuid.uuid4(),
            )
        )
    if status == "cancelled" or shipped:
        await update_fbs_order_reservation(session, order, reserve=False)
    await session.commit()


@pytest.mark.asyncio
async def test_units_mode_publishes_numbers_as_given(db_session: AsyncSession) -> None:
    # Дано: свободно 1000, оператор раздал 200 и 300 по двум складам WB.
    seed = await _units_seed(db_session)
    await _allocate(db_session, seed, {501001: 200, 501002: 300})

    # Когда считаем, что уедет. Тогда: ровно заданные числа, доля не участвует.
    amounts = await _resolve_publish_quantities(db_session, seed.bindings[0], [seed.product])
    assert amounts[seed.product.id] == 200
    amounts = await _resolve_publish_quantities(db_session, seed.bindings[1], [seed.product])
    assert amounts[seed.product.id] == 300


@pytest.mark.asyncio
async def test_units_quota_is_eaten_only_by_its_own_warehouse(
    db_session: AsyncSession,
) -> None:
    # Дано: по 200 на каждый склад, и два заказа пришли с ПЕРВОГО склада.
    seed = await _units_seed(db_session)
    await _allocate(db_session, seed, {501001: 200, 501002: 200})
    await _place_order(db_session, seed, 501001)
    await _place_order(db_session, seed, 501001)

    # Тогда: у первого склада осталось 198, у второго по-прежнему 200.
    # Соседний склад в чужое число залезть не может.
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse[501001] == 198
    assert view.units_remaining_by_warehouse[501002] == 200


@pytest.mark.asyncio
async def test_cancelled_before_handover_returns_quota(
    db_session: AsyncSession,
) -> None:
    # Дано: заказ пришёл и отменился ДО передачи поставки — товар не уезжал.
    seed = await _units_seed(db_session)
    await _allocate(db_session, seed, {501001: 200, 501002: 0})
    await _place_order(db_session, seed, 501001, status="cancelled")

    # Тогда: число вернулось само, без отдельного события. Отменённый до
    # передачи заказ товар не унёс, значит и число не потратил.
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse[501001] == 200


@pytest.mark.asyncio
async def test_cancelled_after_handover_keeps_quota_spent(
    db_session: AsyncSession,
) -> None:
    # Дано: заказ отменился уже ПОСЛЕ передачи — списание проведено, товар уехал.
    seed = await _units_seed(db_session)
    await _allocate(db_session, seed, {501001: 200, 501002: 0})
    await _place_order(db_session, seed, 501001, status="cancelled", shipped=True)

    # Тогда: число остаётся потраченным. Возврат в остаток — отдельным
    # документом, то же правило, что и для физического остатка
    # (OWN-2026-08-31-06).
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse[501001] == 199


@pytest.mark.asyncio
async def test_old_orders_do_not_eat_a_freshly_set_number(
    db_session: AsyncSession,
) -> None:
    """Заказ старше числа его не трогает — сторожевой тест против 04.09.2026.

    В тот день шестичасовой обход истории за 30 дней принёс заказы за 26-28
    августа, журнал расхода записал их как свежие продажи, и по трём продавцам
    335 штук перестали предлагаться покупателям. Отсчёт идёт от даты ЗАКАЗА, а
    не от даты, когда мы что-то о нём записали.
    """
    # Дано: заказ пришёл вчера, а число оператор задал сегодня.
    seed = await _units_seed(db_session)
    await _place_order(db_session, seed, 501001, created_at=_yesterday())
    await _allocate(db_session, seed, {501001: 200, 501002: 0})

    # Тогда: число целое. Августовский заказ съесть сегодняшнее не может.
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse[501001] == 200


@pytest.mark.asyncio
async def test_inventory_deducts_allocation_and_receiving_does_not_restore_it(
    db_session: AsyncSession,
) -> None:
    from app.models.inventory_movement import (
        MOVEMENT_TYPE_INBOUND_INTAKE,
        MOVEMENT_TYPE_INVENTORY_COUNT,
    )
    from app.services.inventory_service import record_movement_and_adjust_balance

    seed = await _units_seed(db_session, on_hand=150)
    await _allocate(db_session, seed, {501001: 150, 501002: 0})
    balance = await db_session.scalar(
        select(InventoryBalance).where(InventoryBalance.product_id == seed.product.id)
    )
    assert balance is not None
    for delta, kind in [(-30, MOVEMENT_TYPE_INVENTORY_COUNT), (30, MOVEMENT_TYPE_INBOUND_INTAKE)]:
        await record_movement_and_adjust_balance(
            db_session,
            tenant_id=seed.tenant.id,
            product_id=seed.product.id,
            storage_location_id=balance.storage_location_id,
            quantity_delta=delta,
            movement_type=kind,
            actor_user_id=None,
        )
        await db_session.commit()
        view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
        assert view.units_remaining_by_warehouse[501001] == 120
        assert view.published_now == 120


@pytest.mark.asyncio
async def test_units_sum_over_free_stock_is_rejected(db_session: AsyncSession) -> None:
    # Дано: свободно 1000, а оператор пытается раздать 600 и 600.
    seed = await _units_seed(db_session)
    with pytest.raises(FbsStockRuleError) as exc:
        await _allocate(db_session, seed, {501001: 600, 501002: 600})
    # Тогда: отказ. Склады делят один и тот же физический остаток.
    assert exc.value.code == "units_sum_exceeded"


@pytest.mark.asyncio
async def test_receiving_does_not_raise_units_quota(db_session: AsyncSession) -> None:
    # Дано: раздали по 20, потом приехала приёмка — свободный остаток вырос.
    seed = await _units_seed(db_session, on_hand=100)
    await _allocate(db_session, seed, {501001: 20, 501002: 20})
    balance = (
        await db_session.execute(
            select(InventoryBalance).where(InventoryBalance.product_id == seed.product.id)
        )
    ).scalar_one()
    balance.quantity = 1100
    await db_session.commit()

    # Тогда: свободный остаток новый, а числа по складам прежние — сами они не
    # растут, поднимать их оператор должен руками. Это и есть разница с долей.
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.free_stock == 1100
    assert view.units_remaining_by_warehouse[501001] == 20
    assert view.published_now == 40


@pytest.mark.asyncio
async def test_zero_edit_cancel_and_repeated_events_preserve_reserve(
    db_session: AsyncSession,
) -> None:
    from app.models.fbs_order import FbsOrder
    from app.services.inventory_service import update_fbs_order_reservation
    from app.services.marketplace_unload_service import _available_product_qty_in_warehouse

    seed = await _units_seed(db_session, on_hand=400)
    await _allocate(db_session, seed, {501001: 100, 501002: 200})
    await _place_order(db_session, seed, 501002)
    order = (await db_session.scalars(select(FbsOrder))).one()
    await update_fbs_order_reservation(db_session, order, reserve=True)
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse == {501001: 100, 501002: 199}
    assert (
        await _available_product_qty_in_warehouse(
            db_session, seed.tenant.id, seed.warehouse.id, seed.product.id
        )
        == 100
    )
    await _allocate(db_session, seed, {501001: 100, 501002: 0})
    await update_fbs_order_reservation(db_session, order, reserve=False)
    await update_fbs_order_reservation(db_session, order, reserve=False)
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse == {501001: 100, 501002: 1}
    assert view.on_hand == 400
    assert view.reserved == 0


@pytest.mark.asyncio
async def test_inventory_uses_ordinary_stock_then_fbs(db_session: AsyncSession) -> None:
    from app.models.inventory_movement import MOVEMENT_TYPE_INVENTORY_COUNT
    from app.services.inventory_service import record_movement_and_adjust_balance
    from app.services.marketplace_unload_service import _available_product_qty_in_warehouse

    seed = await _units_seed(db_session, on_hand=400)
    await _allocate(db_session, seed, {501001: 100, 501002: 200})
    await _place_order(db_session, seed, 501002)
    location_id = await db_session.scalar(
        select(InventoryBalance.storage_location_id).where(
            InventoryBalance.product_id == seed.product.id
        )
    )
    assert location_id is not None
    for delta, physical, available in [(-20, 380, 299), (-130, 250, 249)]:
        await record_movement_and_adjust_balance(
            db_session,
            tenant_id=seed.tenant.id,
            product_id=seed.product.id,
            storage_location_id=location_id,
            quantity_delta=delta,
            movement_type=MOVEMENT_TYPE_INVENTORY_COUNT,
            actor_user_id=None,
        )
        await db_session.commit()
        view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
        assert view.on_hand == physical
        assert view.published_now == available
        assert view.reserved == 1
    assert (
        await _available_product_qty_in_warehouse(
            db_session, seed.tenant.id, seed.warehouse.id, seed.product.id
        )
        == 0
    )


@pytest.mark.asyncio
async def test_switching_modes_preserves_reserves(db_session: AsyncSession) -> None:
    from app.models.fbs_order import FbsOrder
    from app.services.inventory_service import update_fbs_order_reservation

    seed = await _units_seed(db_session, on_hand=400)
    await _allocate(db_session, seed, {501001: 100, 501002: 200})
    await _place_order(db_session, seed, 501002)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            same_everywhere=False,
            percent=0,
            by_warehouse={501001: 20, 501002: 30},
        ),
    )
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.reserved == 1
    assert view.published_now == 79 + 119
    await _allocate(db_session, seed, {501001: 0, 501002: 0})
    order = (await db_session.scalars(select(FbsOrder))).one()
    await update_fbs_order_reservation(db_session, order, reserve=False)
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.units_remaining_by_warehouse[501002] == 1


@pytest.mark.asyncio
async def test_ozon_reserves_product_quantities_atomically(db_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    from app.models.fbs_order import FbsOrder, FbsOrderProduct
    from app.services.inventory_service import update_fbs_order_reservation

    seed = await _units_seed(db_session, on_hand=400)
    seed.bindings[1].marketplace = "ozon"
    seed.bindings[1].external_warehouse_id = "555"
    await _allocate(db_session, seed, {501001: 100, 501002: 200})
    second = Product(
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        sku_code="second",
        name="Trousers",
        fbs_units_mode=True,
    )
    db_session.add(second)
    await db_session.flush()
    pool = FbsBindingStockPool(
        tenant_id=seed.tenant.id, binding_id=seed.bindings[1].id, product_id=second.id, quantity=0
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        product_id=seed.product.id,
        marketplace="ozon",
        external_order_id="ozon-3",
        mapping_status="mapped",
        reserve_status="no_stock",
        wb_order_id=-123,
        wb_warehouse_id=501002,
        warehouse_id=seed.warehouse.id,
        created_at_wb=now,
        deadline_at=now,
        status="new",
    )
    db_session.add_all([pool, order])
    await db_session.flush()
    db_session.add_all(
        [
            FbsOrderProduct(
                order_id=order.id,
                product_id=seed.product.id,
                ozon_sku=123,
                position_index=0,
                quantity=2,
            ),
            FbsOrderProduct(
                order_id=order.id,
                product_id=second.id,
                ozon_sku=456,
                position_index=1,
                quantity=1,
            ),
        ]
    )
    await db_session.flush()
    await update_fbs_order_reservation(db_session, order, reserve=True)
    assert order.reserve_status == "no_stock"
    assert (await get_rule_view(db_session, seed.tenant.id, seed.product.id)).published_now == 300
    pool.quantity = 1
    await update_fbs_order_reservation(db_session, order, reserve=True)
    await update_fbs_order_reservation(db_session, order, reserve=True)
    assert order.reserve_status == "reserved"
    assert pool.quantity == 0
    assert (await get_rule_view(db_session, seed.tenant.id, seed.product.id)).published_now == 298
    await update_fbs_order_reservation(db_session, order, reserve=False)
    await update_fbs_order_reservation(db_session, order, reserve=False)
    assert pool.quantity == 1
    assert (await get_rule_view(db_session, seed.tenant.id, seed.product.id)).published_now == 300


@pytest.mark.asyncio
async def test_available_stock_migration_keeps_current_remainder(db_session: AsyncSession) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    seed = await _units_seed(db_session, on_hand=400)
    await _allocate(db_session, seed, {501001: 200, 501002: 200})
    await _place_order(db_session, seed, 501001)
    await _place_order(db_session, seed, 501001)
    await db_session.execute(
        text("ALTER TABLE fbs_binding_stock_pools ADD COLUMN allocated_at DATETIME")
    )
    await db_session.execute(
        text(
            "UPDATE fbs_binding_stock_pools SET quantity = 200, "
            "allocated_at = '2000-01-01 00:00:00'"
        )
    )

    def migrate(session: Session) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/20260905_0252_fbs_available_stock.py"
        )
        spec = importlib.util.spec_from_file_location("fbs_available_migration", path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(session.connection())):
            migration.upgrade()

    await db_session.run_sync(migrate)
    db_session.expire_all()
    quantities = (
        await db_session.execute(
            text(
                "SELECT b.wb_warehouse_id, p.quantity FROM fbs_binding_stock_pools p "
                "JOIN fbs_warehouse_bindings b ON b.id = p.binding_id ORDER BY b.wb_warehouse_id"
            )
        )
    ).all()
    assert quantities == [(501001, 198), (501002, 200)]


# --- Ozon рядом с Wildberries --------------------------------------------
#
# WMS-341: отдельного пула под Ozon заводить не нужно — он уже отдельный,
#          потому что `FbsBindingStockPool` висит на привязке, а привязка знает
#          свою площадку. Общий у площадок только потолок.
# WMS-342: правило доли, сохранённое для Wildberries, не смеет обнулять то,
#          что выделено на Ozon.
# WMS-350: сумма долей по всем складам ВСЕХ площадок — не больше ста процентов.
# WMS-351: остаток уезжает на Ozon тем же расчётом, что и на Wildberries, и
#          одну физическую единицу двум площадкам не обещает.


async def _ozon_binding(
    session: AsyncSession,
    seed: _Seed,
    *,
    wb_warehouse_id: int,
    is_active: bool = True,
    served: bool = True,
) -> FbsWarehouseBinding:
    """Привязка озоновского склада того же продавца к тому же складу WMS."""
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
    await session.commit()
    return binding


@pytest.mark.asyncio
async def test_share_rule_keeps_allocation_the_rule_does_not_reach(
    db_session: AsyncSession,
) -> None:
    """WMS-342: перевод на долю обнуляет только то, чем правило распоряжается.

    Раньше обнуление искало строки по одному товару и тенанту и выгребало ВСЁ,
    включая привязки площадки, которой это правило не касается. Оператор
    сохранял долю для Wildberries — и молча стирал штуки, выделенные на Ozon.
    """
    seed = await _units_seed(db_session, on_hand=400)
    # Привязка Ozon выключена, поэтому в правило она не попадает: `_seller_bindings`
    # берёт только активные. Ровно этот случай и был дырой — строку никто не
    # проверял, а обнуляли её всё равно.
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=900101, is_active=False)
    db_session.add(
        FbsBindingStockPool(
            tenant_id=seed.tenant.id,
            binding_id=ozon.id,
            product_id=seed.product.id,
            quantity=40,
        )
    )
    await _allocate(db_session, seed, {501001: 100, 501002: 60})

    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(publish=True, same_everywhere=True, percent=30, by_warehouse={}),
    )

    pools = {
        row.binding_id: row.quantity
        for row in (
            await db_session.scalars(
                select(FbsBindingStockPool).where(FbsBindingStockPool.product_id == seed.product.id)
            )
        ).all()
    }
    # Склады Wildberries правило перечисляет — их выделение вернулось в общий
    # остаток, как и было задумано при переходе на долю.
    assert pools[seed.bindings[0].id] == 0
    assert pools[seed.bindings[1].id] == 0
    # А озоновское выделение правило не трогало и трогать не имело права.
    assert pools[ozon.id] == 40


@pytest.mark.asyncio
async def test_percent_ceiling_counts_wb_and_ozon_together(
    db_session: AsyncSession,
) -> None:
    """WMS-350: сто процентов — на все склады всех площадок разом, а не на каждую."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=900201)

    with pytest.raises(FbsStockRuleError) as over:
        await set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            FbsRule(
                publish=True,
                same_everywhere=False,
                percent=0,
                by_warehouse={501001: 60, 900201: 60},
            ),
        )
    assert over.value.code == "percent_sum_exceeded"

    # Ровно сто в сумме — принимается: это и есть весь свободный остаток.
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            same_everywhere=False,
            percent=0,
            by_warehouse={501001: 60, 900201: 40},
        ),
    )
    view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.by_warehouse == {501001: 60, 900201: 40}
    assert view.free_stock == 100
    assert view.published_now == 100
    assert ozon.marketplace == "ozon"


@pytest.mark.asyncio
async def test_same_everywhere_counts_the_ozon_warehouse_too(
    db_session: AsyncSession,
) -> None:
    """WMS-350: «одинаково по всем складам» — это и озоновские склады тоже.

    Доля при этой галке применяется к КАЖДОМУ обслуживаемому складу, поэтому с
    появлением второй площадки тот же процент даёт вдвое больший расход.
    """
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=900301)

    with pytest.raises(FbsStockRuleError) as over:
        await set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            FbsRule(publish=True, same_everywhere=True, percent=60, by_warehouse={}),
        )
    assert over.value.code == "percent_sum_exceeded"
    assert over.value.context == {"total": 120}


@pytest.mark.asyncio
async def test_one_physical_unit_is_never_promised_to_both_marketplaces(
    db_session: AsyncSession,
) -> None:
    """WMS-341/351: площадки черпают из одной бочки, а не каждая из своей.

    Это причина, по которой `_seller_bindings` не фильтрует по маркетплейсу.
    С фильтром Wildberries взял бы свои сто процентов свободного остатка, Ozon —
    свои сто процентов того же остатка, и одну и ту же единицу пообещали бы
    двум покупателям.
    """
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=900401)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            same_everywhere=False,
            percent=0,
            by_warehouse={501001: 60, 900401: 40},
        ),
    )

    wb_amounts = await publish_amounts_for_binding(db_session, seed.bindings[0], [seed.product])
    ozon_amounts = await publish_amounts_for_binding(db_session, ozon, [seed.product])
    assert wb_amounts == {seed.product.id: 60}
    assert ozon_amounts == {seed.product.id: 40}
    # Сумма ровно равна свободному остатку, а не вдвое больше него.
    assert wb_amounts[seed.product.id] + ozon_amounts[seed.product.id] == 100


@pytest.mark.asyncio
async def test_rule_refuses_when_two_marketplaces_share_a_warehouse_number(
    db_session: AsyncSession,
) -> None:
    """Номер склада — единственный ключ правила, и совпасть он у площадок может.

    База разводит склады по маркетплейсу, а правило адресует их числом. Пока
    числа совпадают, доля Wildberries легла бы заодно и на Ozon, поэтому
    отказываем на вводе, а не пишем наугад.
    """
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=501001)

    with pytest.raises(FbsStockRuleError) as collision:
        await set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            FbsRule(publish=True, same_everywhere=True, percent=50, by_warehouse={}),
        )
    assert collision.value.code == "warehouse_id_collision"
    assert collision.value.context == {"wb_warehouse_ids": [501001]}


@pytest.mark.parametrize("free,expected", [(0, [0, 0]), (10, [8, 2]), (20, [8, 8])])
def test_units_publication_caps_combined_marketplaces_after_outbound(free, expected) -> None:
    """Outbound reserves/movements must not leave stale allocated units publishable."""
    bindings = [
        FbsWarehouseBinding(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            seller_id=uuid.uuid4(),
            wb_warehouse_id=index,
            wms_warehouse_id=uuid.uuid4(),
            marketplace=market,
        )
        for index, market in ((1, "wildberries"), (2, "ozon"))
    ]
    rule = FbsRule(
        publish=True,
        same_everywhere=False,
        percent=0,
        by_warehouse={},
        units_mode=True,
        units_by_warehouse={1: 8, 2: 8},
    )
    amounts = split_amounts(rule, free, bindings)
    assert [amounts[binding.id] for binding in bindings] == expected
    assert rule.units_by_warehouse == {1: 8, 2: 8}
