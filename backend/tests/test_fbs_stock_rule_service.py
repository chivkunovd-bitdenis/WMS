"""Правило остатка FBS: доля свободного остатка вместо сохранённого числа.

TC-NEW-FBS-RULE-001: доля считается от свободного остатка на момент публикации.
TC-NEW-FBS-RULE-002: сумма долей по складам не может превысить сто процентов.
TC-NEW-FBS-RULE-003: массовое присвоение отказывает на товарах разных продавцов.
TC-NEW-FBS-RULE-004: товар без доли продолжает публиковаться по старому числу.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
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


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
    )
    session.add_all(
        [seed.tenant, seed.seller, seed.warehouse, seed.product, location, balance]
    )
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
    amounts = await publish_amounts_for_binding(
        db_session, seed.bindings[0], [seed.product]
    )
    # Ожидаемо: публикация берёт 126, а не сохранённое когда-то число.
    assert amounts == {seed.product.id: 126}


@pytest.mark.asyncio
async def test_product_without_rule_keeps_old_stored_number(
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
    quantities = await _resolve_publish_quantities(
        db_session, seed.bindings[0], [seed.product]
    )
    # Тогда он публикуется по-старому: выкатка не требует настроить всех сразу.
    assert quantities == {seed.product.id: 17}
