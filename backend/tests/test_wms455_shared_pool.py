"""WMS-455 — «общая корзинка»: весь свободный остаток в оба кабинета.

Проверки C4-C7, C9-C13, C15-C17, C21 из docs/requirements/WMS-455.md
(раздел 5), серверная часть. C1-C3, C8, C14, C18-C20, C22 (окно, фронт) —
вне этого файла, их делает исполнитель фронта и проверяет аналитик в
браузере. C11/C12 здесь проверяются на уровне set_rule_for_products
(эквивалент PUT /products/fbs-rule), без HTTP-слоя — контракт тот же
(_rule_from_body/_rule_view_out в app/api/products.py — тонкая обёртка).

Сиды переиспользуют `_seed`/`_ozon_binding` из test_fbs_stock_rule_service.py
(тот же приём, что уже использует test_wms351_marketplace_publication_switches.py):
`_ozon_binding` заводит и активную Ozon-привязку, и ProductMarketplaceLink —
честный «товар на двух площадках», ровно то, что требует R2/R3.
"""

from __future__ import annotations

import asyncio
import contextvars
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_NOT_PUBLISHED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services import fbs_stock_rule_service as rules
from app.services import inventory_service
from tests.test_fbs_stock_rule_service import _ozon_binding, _seed

WB_WAREHOUSE_ID = 501001
OZON_WB_WAREHOUSE_ID = 900455


async def _amounts(session, seed, ozon):
    """(wb_amounts, ozon_amounts) — сокращение часто повторяющейся пары вызовов."""
    wb = await rules.publish_amounts_for_binding(session, seed.bindings[0], [seed.product])
    ozon_amounts = await rules.publish_amounts_for_binding(session, ozon, [seed.product])
    return wb, ozon_amounts


@pytest.fixture(autouse=True)
def _do_not_dispatch_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same convention as test_fbs_stock_rule_service.py: no real background dispatch."""
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.services.inventory_service.schedule_seller_stock_publish",
        lambda *_args: None,
    )


def _wb_order(seed: object, *, wb_order_id: int, product_id: uuid.UUID | None = None) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=seed.tenant.id,  # type: ignore[attr-defined]
        seller_id=seed.seller.id,  # type: ignore[attr-defined]
        warehouse_id=seed.warehouse.id,  # type: ignore[attr-defined]
        product_id=product_id if product_id is not None else seed.product.id,  # type: ignore[attr-defined]
        marketplace="wb",
        wb_order_id=wb_order_id,
        wb_warehouse_id=WB_WAREHOUSE_ID,
        status=FBS_ORDER_STATUS_NEW,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status="no_stock",
    )


def _ozon_order(seed: object, *, wb_order_id: int) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=seed.tenant.id,  # type: ignore[attr-defined]
        seller_id=seed.seller.id,  # type: ignore[attr-defined]
        warehouse_id=seed.warehouse.id,  # type: ignore[attr-defined]
        product_id=None,
        marketplace="ozon",
        wb_order_id=wb_order_id,
        wb_warehouse_id=OZON_WB_WAREHOUSE_ID,
        status=FBS_ORDER_STATUS_NEW,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status="no_stock",
    )


@pytest.mark.asyncio
async def test_c4_each_publishing_direction_gets_the_whole_free_stock(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C4: 100 свободных — WB и Ozon оба получают все 100, а не 60/40."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40},
        ),
    )
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 100}
    assert ozon_amounts == {seed.product.id: 100}

    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is True
    assert view.free_stock == 100
    # WMS-455 решение 6: published_now — то, что уходит в КАЖДОЕ направление
    # (100), а не сумма по направлениям (200).
    assert view.published_now == 100
    # R4: доли из до-режимного сохранения не тронуты и не читаются публикацией.
    assert dict(view.rule.by_warehouse) == {WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}


@pytest.mark.asyncio
async def test_c4_three_bindings_each_get_the_full_free_stock(db_session: AsyncSession) -> None:
    """WMS-455 C4: два склада WB + Ozon — каждый получает всю сотню (решение 5)."""
    seed = await _seed(db_session, on_hand=100, wb_warehouse_ids=(501001, 501002))
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    for binding in [*seed.bindings, ozon]:
        amounts = await rules.publish_amounts_for_binding(db_session, binding, [seed.product])
        assert amounts == {seed.product.id: 100}


@pytest.mark.asyncio
async def test_c4_disabled_marketplace_gets_zero_even_in_shared_pool(
    db_session: AsyncSession,
) -> None:
    """R3: направление площадки с выключенной галкой получает 0, режим её не включает."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=False, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 100}
    # publish_ozon=False -> продукт вообще не публикуемый по Ozon-привязке (как
    # обычно у WMS-456: отсутствие в ответе, а не явный ноль).
    assert ozon_amounts == {}


@pytest.mark.asyncio
async def test_c5_order_on_either_marketplace_reduces_both_directions(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C5/R7: резерв заказа Ozon уменьшает и WB, и Ozon одновременно."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    order = _ozon_order(seed, wb_order_id=5001)
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        FbsOrderProduct(
            order_id=order.id, product_id=seed.product.id, quantity=6, position_index=0,
        )
    )
    await db_session.commit()

    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=True)
    await db_session.commit()
    assert order.reserve_status == RESERVE_STATUS_RESERVED

    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 94}
    assert ozon_amounts == {seed.product.id: 94}

    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=False)
    await db_session.commit()
    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 100}
    assert ozon_amounts == {seed.product.id: 100}

    # Тот же сценарий заказом WB на 1 шт: обе площадки видят 99.
    wb_order = _wb_order(seed, wb_order_id=5002)
    db_session.add(wb_order)
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, wb_order, reserve=True)
    await db_session.commit()
    assert wb_order.reserve_status == RESERVE_STATUS_RESERVED
    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 99}
    assert ozon_amounts == {seed.product.id: 99}


@pytest.mark.asyncio
async def test_c6_reservation_does_not_depend_on_percent_or_units_pool(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C6/R8: not_published не выставляется из-за NULL доли или пустого пула."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    assert ozon is not None
    # fbs_percent остаётся NULL — правило никогда не задавалось долями.
    seed.product.fbs_stock_sync_enabled = True
    seed.product.fbs_ozon_stock_sync_enabled = True
    seed.product.fbs_shared_pool = True
    await db_session.commit()
    assert seed.product.fbs_percent is None

    wb_order = _wb_order(seed, wb_order_id=6001)
    db_session.add(wb_order)
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, wb_order, reserve=True)
    await db_session.commit()
    assert wb_order.reserve_status == RESERVE_STATUS_RESERVED

    ozon_order = _ozon_order(seed, wb_order_id=6002)
    db_session.add(ozon_order)
    await db_session.flush()
    db_session.add(
        FbsOrderProduct(
            order_id=ozon_order.id, product_id=seed.product.id, quantity=1, position_index=0,
        )
    )
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, ozon_order, reserve=True)
    await db_session.commit()
    assert ozon_order.reserve_status == RESERVE_STATUS_RESERVED

    # Вариант: режим штук без пула на складе заказа — тоже не блокирует.
    seed.product.fbs_units_mode = True
    await db_session.commit()
    wb_order_units = _wb_order(seed, wb_order_id=6003)
    db_session.add(wb_order_units)
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, wb_order_units, reserve=True)
    await db_session.commit()
    assert wb_order_units.reserve_status == RESERVE_STATUS_RESERVED


@pytest.mark.asyncio
async def test_c6_without_shared_pool_missing_percent_still_blocks(
    db_session: AsyncSession,
) -> None:
    """Контроль: без режима старое поведение (NULL percent -> not_published) цело."""
    seed = await _seed(db_session, on_hand=100)
    seed.product.fbs_stock_sync_enabled = True
    await db_session.commit()
    assert seed.product.fbs_percent is None

    order = _wb_order(seed, wb_order_id=6101)
    db_session.add(order)
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=True)
    await db_session.commit()
    assert order.reserve_status == RESERVE_STATUS_NOT_PUBLISHED


@pytest.mark.asyncio
async def test_c7_shared_pool_save_ignores_the_hundred_percent_ceiling(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C7: сумма долей/штук 200% не мешает сохранению в режиме."""
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)

    for over_rule in (
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 100, OZON_WB_WAREHOUSE_ID: 100},
            shared_pool=True,
        ),
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=True, percent=100,
            shared_pool=True,
        ),
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            units_mode=True,
            units_by_warehouse={WB_WAREHOUSE_ID: 100, OZON_WB_WAREHOUSE_ID: 100},
            shared_pool=True,
        ),
    ):
        # Не должно поднимать FbsStockRuleError несмотря на явный перебор.
        await rules.set_rule_for_products(
            db_session, seed.tenant.id, [seed.product.id], over_rule,
        )
        view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
        assert view.rule.shared_pool is True
        # R4: поля долей/штук из запроса не записаны — товар ещё ни разу не
        # сохранял долю до этого теста, поэтому она осталась NULL (percent=0
        # по умолчанию FbsRuleView), а не 100.
        assert seed.product.fbs_percent is None
        assert seed.product.fbs_units_mode is False


@pytest.mark.asyncio
async def test_c9_product_without_ozon_link_ignores_shared_pool_request(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C9/R2: товар только WB — режим не пишется, остальное правило цело."""
    seed = await _seed(db_session, on_hand=120)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(publish=True, same_everywhere=True, percent=100, by_warehouse={}),
    )

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, same_everywhere=True, percent=100, by_warehouse={}, shared_pool=True,
        ),
    )

    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is False
    assert view.rule.percent == 100
    assert view.published_now == 120
    await db_session.refresh(seed.product)
    assert seed.product.fbs_shared_pool is False


@pytest.mark.asyncio
async def test_c10_product_without_a_prior_rule_gets_full_free_stock(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C10: товар на двух площадках без прежнего правила (percent NULL)."""
    seed = await _seed(db_session, on_hand=80)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    assert seed.product.fbs_percent is None

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is True
    assert view.free_stock == 80
    assert view.published_now == 80
    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 80}
    assert ozon_amounts == {seed.product.id: 80}


@pytest.mark.asyncio
async def test_c11_bulk_enable_does_not_overwrite_individual_shares(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C11: массовое включение не затирает индивидуальные доли пачки."""
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40},
        ),
    )

    second = Product(
        tenant_id=seed.tenant.id, seller_id=seed.seller.id,
        name="Second", sku_code=f"bulk-{uuid.uuid4().hex[:8]}", fbs_stock_sync_enabled=True,
    )
    db_session.add(second)
    await db_session.flush()
    from app.models.inventory_balance import InventoryBalance
    from app.models.storage_location import StorageLocation

    location = await db_session.scalar(
        select(StorageLocation).where(StorageLocation.warehouse_id == seed.warehouse.id)
    )
    assert location is not None
    db_session.add(
        InventoryBalance(
            tenant_id=seed.tenant.id, storage_location_id=location.id,
            product_id=second.id, quantity=100, quantity_unpacked=100,
        )
    )
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=seed.tenant.id, seller_id=seed.seller.id, product_id=second.id,
            marketplace="ozon", external_offer_id=f"offer-{uuid.uuid4().hex[:8]}", is_active=True,
        )
    )
    await db_session.commit()
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [second.id],
        rules.FbsRule(publish=True, publish_ozon=True, same_everywhere=True, percent=50),
    )

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id, second.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    view_first = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    view_second = await rules.get_rule_view(db_session, seed.tenant.id, second.id)
    assert view_first.rule.shared_pool is True
    assert view_second.rule.shared_pool is True
    assert view_first.published_now == 100
    assert view_second.published_now == 100
    # Индивидуальные доли не затёрты долями/режимом друг друга.
    assert view_first.rule.same_everywhere is False
    assert view_second.rule.same_everywhere is True
    assert view_second.rule.percent == 50


@pytest.mark.asyncio
async def test_c12_mixed_batch_only_the_linked_product_gets_the_mode(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C12: пачка из двухплощадочного и WB-only товара."""
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(publish=True, publish_ozon=True, same_everywhere=True, percent=50),
    )

    wb_only = Product(
        tenant_id=seed.tenant.id, seller_id=seed.seller.id,
        name="WB only", sku_code=f"wbonly-{uuid.uuid4().hex[:8]}", fbs_stock_sync_enabled=True,
        fbs_percent=100, fbs_same_everywhere=True,
    )
    db_session.add(wb_only)
    await db_session.flush()
    from app.models.inventory_balance import InventoryBalance
    from app.models.storage_location import StorageLocation

    location = await db_session.scalar(
        select(StorageLocation).where(StorageLocation.warehouse_id == seed.warehouse.id)
    )
    assert location is not None
    db_session.add(
        InventoryBalance(
            tenant_id=seed.tenant.id, storage_location_id=location.id,
            product_id=wb_only.id, quantity=120, quantity_unpacked=120,
        )
    )
    await db_session.commit()

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id, wb_only.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )

    view_two_marketplaces = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    view_wb_only = await rules.get_rule_view(db_session, seed.tenant.id, wb_only.id)
    assert view_two_marketplaces.rule.shared_pool is True
    assert view_wb_only.rule.shared_pool is False
    assert view_wb_only.rule.percent == 100
    assert view_wb_only.published_now == 120


@pytest.mark.asyncio
async def test_c13_repeated_save_does_not_reschedule_or_touch_bindings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WMS-455 C13: повторное сохранение того же режима не планирует публикацию."""
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    schedule_calls: list[str] = []
    monkeypatch.setattr(
        rules, "schedule_seller_stock_publish", lambda *a: schedule_calls.append(a[3]),
    )
    shared_pool_rule = rules.FbsRule(
        publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
    )
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], shared_pool_rule,
    )
    assert sorted(schedule_calls) == ["ozon", "wb"]
    schedule_calls.clear()
    await db_session.refresh(seed.bindings[0])
    await db_session.refresh(ozon)
    wb_before = (seed.bindings[0].stock_sync_enabled, seed.bindings[0].last_sync_status)
    ozon_before = (ozon.stock_sync_enabled, ozon.last_sync_status)

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], shared_pool_rule,
    )

    assert schedule_calls == []
    await db_session.refresh(seed.bindings[0])
    await db_session.refresh(ozon)
    assert (seed.bindings[0].stock_sync_enabled, seed.bindings[0].last_sync_status) == wb_before
    assert (ozon.stock_sync_enabled, ozon.last_sync_status) == ozon_before


@pytest.mark.asyncio
async def test_c15_replaying_the_same_save_after_a_lost_response_is_a_no_op(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WMS-455 C15: повтор того же PUT после обрыва ответа не публикует дважды."""
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    schedule_calls: list[str] = []
    monkeypatch.setattr(
        rules, "schedule_seller_stock_publish", lambda *a: schedule_calls.append(a[3]),
    )
    shared_pool_rule = rules.FbsRule(
        publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
    )

    # "Первый" запрос доходит и сохраняет, но ответ клиенту потерялся.
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], shared_pool_rule,
    )
    schedule_calls.clear()

    # Клиент, не увидев ответа, повторяет тот же самый PUT.
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], shared_pool_rule,
    )

    assert schedule_calls == []
    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is True
    assert view.published_now == 100


@pytest.mark.asyncio
async def test_c16_two_sessions_saving_the_same_product_leave_one_coherent_state(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WMS-455 C16: два одновременных сохранения — итог целиком одно из двух.

    Реальная блокировка проверяется только под PostgreSQL (advisory-lock и
    SELECT ... FOR UPDATE — no-op на SQLite, см. marketplace_seller_lock_service
    и _session_uses_postgresql). Тест пропускается на SQLite по тому же
    принципу, что test_concurrent_orders_reserve_last_unit_once в
    test_inventory_stock_cap_wms338.py — на SQLite нечего доказывать по замку.

    Барьер привязан к вызывающей ЗАДАЧЕ (contextvar), а не к сессии, которую
    видит marketplace_seller_lock: set_rule_for_products открывает СВОЙ
    отдельный lock_session = AsyncSession(bind=session.bind) и передаёт в лок
    именно его, а не сессию вызывающего кода (см. fbs_stock_rule_service.py,
    set_rule_for_products, блок AsyncExitStack). Раньше барьер читал
    session.info вот этой чужой lock_session — там маркера никогда не было
    (F3 кросс-ревью Astra 17.09.2026), first_locked не выставлялся, и второе
    сохранение не стартовало вовсе. contextvar живёт в контексте asyncio-задачи
    (asyncio.create_task копирует контекст один раз при создании, поэтому
    вызовы из разных задач не видят чужих присвоений) и не зависит от того,
    какой объект AsyncSession дошёл до замка.
    """
    assert db_session.bind is not None
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL via WMS_TEST_DATABASE_URL")
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_a: None)
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40},
        ),
    )

    caller_role: contextvars.ContextVar[str | None] = contextvars.ContextVar(
        "wms455_c16_caller_role", default=None,
    )
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    # Доказывает «второй стартует до освобождения первого» напрямую. Второй
    # вызов сначала пытается захватить ozon — тот же замок, который первый
    # вызов уже держит (set_rule_for_products перебирает площадки в порядке
    # ("ozon", "wb") и держит оба захваченных замка внутри одного
    # AsyncExitStack до самого выхода из функции). На PostgreSQL настоящий
    # cm.__aenter__() второго вызова поэтому заблокируется до освобождения
    # первого. Сигнал должен стоять ДО этого await — иначе он зависит от
    # уже случившегося освобождения и ничего не доказывает (F3, второй круг
    # кросс-ревью Astra 17.09.2026: старый сигнал стоял после await
    # cm.__aenter__() и создавал взаимное ожидание, ломавшееся тайм-аутом).
    second_lock_attempted = asyncio.Event()
    original_lock = rules.marketplace_seller_lock

    def observed_lock(session, seller_id, marketplace, **kwargs):
        cm = original_lock(session, seller_id, marketplace, **kwargs)
        role = caller_role.get()

        class _Wrapped:
            async def __aenter__(self) -> bool:
                if role == "second":
                    second_lock_attempted.set()
                acquired = await cm.__aenter__()
                if role == "first" and marketplace == "wb":
                    first_locked.set()
                    await asyncio.wait_for(release_first.wait(), 10)
                return acquired

            async def __aexit__(self, *exc: object) -> None:
                await cm.__aexit__(*exc)

        return _Wrapped()

    monkeypatch.setattr(rules, "marketplace_seller_lock", observed_lock)

    async def enable_shared_pool() -> None:
        caller_role.set("first")
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
            await rules.set_rule_for_products(
                session, seed.tenant.id, [seed.product.id],
                rules.FbsRule(
                    publish=True, publish_ozon=True, same_everywhere=False, percent=0,
                    shared_pool=True,
                ),
            )

    async def disable_with_shares() -> None:
        caller_role.set("second")
        second_started.set()
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
            await rules.set_rule_for_products(
                session, seed.tenant.id, [seed.product.id],
                rules.FbsRule(
                    publish=True, publish_ozon=True, same_everywhere=False, percent=0,
                    by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40},
                ),
            )

    first_task = asyncio.create_task(enable_shared_pool())
    second_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(first_locked.wait(), 10)
        second_task = asyncio.create_task(disable_with_shares())
        await asyncio.wait_for(second_started.wait(), 10)
        # Второй вызов реально попытался войти в занятый первым замок (не
        # только запустил корутину) — проверяем это ДО release_first, пока
        # первый вызов всё ещё держит оба своих замка, иначе порядок не
        # доказан (см. комментарий у second_lock_attempted выше).
        await asyncio.wait_for(second_lock_attempted.wait(), 10)
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first_task, second_task), 10)
    except BaseException:
        # Барьер не должен оставлять задачи висящими при ошибке ожидания:
        # отпускаем первый вызов и гарантированно завершаем обе задачи, даже
        # если что-то из wait_for выше упало по тайм-ауту.
        release_first.set()
        pending = [task for task in (first_task, second_task) if task is not None]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        raise

    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    # Одно из двух целиком, без частичной записи. Если победил режим — доли
    # 60/40 из постановки не тронуты (R4: включение режима их не трогает).
    assert (view.rule.shared_pool, dict(view.rule.by_warehouse)) in (
        (True, {WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}),
        (False, {WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}),
    )


@pytest.mark.asyncio
async def test_r6_turning_the_mode_off_restores_the_hundred_percent_ceiling(
    db_session: AsyncSession,
) -> None:
    """WMS-455 R6: выключение режима — доли снова проверяются, потолок снова 100%."""
    seed = await _seed(db_session, on_hand=100)
    await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}, shared_pool=True,
        ),
    )
    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is True

    # Тот самый перебор, который отвергается вне режима (сумма 200%).
    with pytest.raises(rules.FbsStockRuleError) as exc:
        await rules.set_rule_for_products(
            db_session, seed.tenant.id, [seed.product.id],
            rules.FbsRule(
                publish=True, publish_ozon=True, same_everywhere=False, percent=0,
                by_warehouse={WB_WAREHOUSE_ID: 100, OZON_WB_WAREHOUSE_ID: 100},
                shared_pool=False,
            ),
        )
    assert exc.value.code == "percent_sum_exceeded"
    # Правило не изменилось: режим остался включённым.
    view_unchanged = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view_unchanged.rule.shared_pool is True

    # A valid 60/40 turns the mode off normally and is recorded as usual.
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}, shared_pool=False,
        ),
    )
    view_off = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view_off.rule.shared_pool is False
    assert dict(view_off.rule.by_warehouse) == {WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40}
    assert view_off.published_now == 100  # 60 + 40


async def _linked_shared_pool_seed(db_session: AsyncSession):
    seed = await _seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=OZON_WB_WAREHOUSE_ID)
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60, OZON_WB_WAREHOUSE_ID: 40},
        ),
    )
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=False, percent=0, shared_pool=True,
        ),
    )
    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.shared_pool is True
    link = await db_session.scalar(
        select(ProductMarketplaceLink).where(
            ProductMarketplaceLink.product_id == seed.product.id,
            ProductMarketplaceLink.marketplace == "ozon",
        )
    )
    assert link is not None
    return seed, ozon, link


@pytest.mark.asyncio
async def test_c17_link_disappearing_falls_back_to_saved_shares(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C17/R2: пропажа связки Ozon откатывает на сохранённые доли (60/40)."""
    seed, ozon, link = await _linked_shared_pool_seed(db_session)

    link.is_active = False
    await db_session.commit()

    view_without_link = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view_without_link.rule.shared_pool is False
    assert view_without_link.rule.publish_ozon is False
    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 60}
    assert ozon_amounts == {}

    # Любое сохранение без связки пишет false в базу явно, не только в ответе.
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id],
        rules.FbsRule(
            publish=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 60}, shared_pool=True,
        ),
    )
    await db_session.refresh(seed.product)
    assert seed.product.fbs_shared_pool is False


@pytest.mark.asyncio
async def test_c17_link_returning_before_any_resave_revives_the_mode(
    db_session: AsyncSession,
) -> None:
    """WMS-455 C17/R2: связка вернулась до пересохранения — режим снова действует."""
    seed, ozon, link = await _linked_shared_pool_seed(db_session)

    # Связка пропадает и сразу возвращается — оператор ничего не пересохранял,
    # колонка products.fbs_shared_pool всё это время оставалась true.
    link.is_active = False
    await db_session.commit()
    view_without_link = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view_without_link.rule.shared_pool is False

    link.is_active = True
    await db_session.commit()
    view_relinked = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view_relinked.rule.shared_pool is True
    wb_amounts, ozon_amounts = await _amounts(db_session, seed, ozon)
    assert wb_amounts == {seed.product.id: 100}
    assert ozon_amounts == {seed.product.id: 100}


def test_c21_split_amounts_ignores_shares_in_shared_pool_mode() -> None:
    """WMS-455 C21: split_amounts — весь остаток каждому публикующему направлению."""
    bindings = [
        FbsWarehouseBinding(
            id=uuid.uuid4(), tenant_id=uuid.uuid4(), seller_id=uuid.uuid4(),
            wb_warehouse_id=501001, wms_warehouse_id=uuid.uuid4(), marketplace="wb",
        ),
        FbsWarehouseBinding(
            id=uuid.uuid4(), tenant_id=uuid.uuid4(), seller_id=uuid.uuid4(),
            wb_warehouse_id=900455, wms_warehouse_id=uuid.uuid4(), marketplace="ozon",
        ),
    ]
    rule = rules.FbsRule(
        publish=True, publish_ozon=False, same_everywhere=False, percent=0,
        by_warehouse={501001: 999, 900455: 999}, shared_pool=True,
    )
    amounts = rules.split_amounts(rule, 100, bindings)
    assert amounts == {bindings[0].id: 100, bindings[1].id: 0}

    rule_both = replace(rule, publish_ozon=True)
    assert rules.split_amounts(rule_both, 100, bindings) == {
        bindings[0].id: 100, bindings[1].id: 100,
    }
    assert rules.split_amounts(rule_both, 0, bindings) == {
        bindings[0].id: 0, bindings[1].id: 0,
    }


def test_c21_validate_rule_never_raises_for_shared_pool() -> None:
    """WMS-455 C21: validate_rule с shared_pool=True не поднимает потолок."""
    over_percent = rules.FbsRule(
        publish=True, same_everywhere=False, percent=0,
        by_warehouse={1: 100, 2: 100}, shared_pool=True,
    )
    rules.validate_rule(over_percent, served_warehouse_count=2)  # must not raise

    over_same = rules.FbsRule(publish=True, same_everywhere=True, percent=100, shared_pool=True)
    rules.validate_rule(over_same, served_warehouse_count=2)  # must not raise

    # Без режима поведение прежнее — 200% всё ещё отказ.
    over_percent_no_mode = replace(over_percent, shared_pool=False)
    with pytest.raises(rules.FbsStockRuleError) as exc:
        rules.validate_rule(over_percent_no_mode, served_warehouse_count=2)
    assert exc.value.code == "percent_sum_exceeded"
