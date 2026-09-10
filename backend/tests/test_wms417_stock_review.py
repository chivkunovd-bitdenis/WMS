"""WMS-417 stock findings: preserve caps, physical publication, and actual WB commit."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import fbs_stock_rule_service as rules
from app.services.fbs_warehouse_binding_service import (
    FbsWarehouseBindingError,
    get_binding_stock_pool_summary,
    set_binding_stock_pool_quantity,
)
from tests.test_fbs_stock_rule_service import _allocate, _ozon_binding, _seed, _units_seed
from tests.test_fbs_stock_sync import _MockStocksTransport


@pytest.fixture(autouse=True)
def no_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_: None)


@pytest.mark.asyncio
async def test_percent_switch_and_legacy_reset_keep_wb_ozon_caps(db_session: AsyncSession) -> None:
    seed = await _units_seed(db_session, on_hand=100)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=9001)
    await _allocate(db_session, seed, {501001: 50, 501002: 0, 9001: 30})
    original = (await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)).rule
    await rules.set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        replace(
            original, units_mode=False, same_everywhere=False, by_warehouse={501001: 20, 9001: 30}
        ),
    )
    await rules.reset_legacy_limits_for_products(db_session, seed.tenant.id, [seed.product.id])
    # Retained caps can exceed stock after depletion, also while percent mode is active.
    balance = await db_session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.product_id == seed.product.id,
        )
    )
    assert balance is not None
    balance.quantity = balance.quantity_unpacked = 40
    await db_session.commit()
    percent = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert percent.rule.units_by_warehouse == original.units_by_warehouse
    assert percent.published_now == 8 + 12
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], replace(percent.rule, units_mode=True)
    )
    restored = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert restored.rule.units_by_warehouse == original.units_by_warehouse
    assert restored.published_now == 40
    assert (
        await db_session.scalar(
            select(FbsBindingStockPool.quantity).where(
                FbsBindingStockPool.binding_id == ozon.id,
            )
        )
        == 30
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("units_mode", [False, True])
async def test_rule_views_match_actual_publication_per_physical_warehouse(
    db_session: AsyncSession,
    units_mode: bool,
) -> None:
    seed = await _seed(db_session, on_hand=3)
    second = Warehouse(tenant_id=seed.tenant.id, code="second", name="Second")
    db_session.add(second)
    await db_session.flush()
    location = StorageLocation(
        tenant_id=seed.tenant.id, warehouse_id=second.id, code="second", barcode="second"
    )
    db_session.add(location)
    await db_session.flush()
    db_session.add(
        InventoryBalance(
            tenant_id=seed.tenant.id,
            product_id=seed.product.id,
            storage_location_id=location.id,
            quantity=3,
            quantity_unpacked=3,
        )
    )
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=9001)
    ozon.wms_warehouse_id = second.id
    seed.product.fbs_units_mode = units_mode
    seed.product.fbs_percent = 50
    seed.product.fbs_same_everywhere = True
    seed.product.fbs_ozon_stock_sync_enabled = True
    for binding in (seed.bindings[0], ozon):
        db_session.add(
            FbsBindingStockPool(
                tenant_id=seed.tenant.id,
                product_id=seed.product.id,
                binding_id=binding.id,
                quantity=5,
                percent=50,
            )
        )
    await db_session.commit()
    # Global named reservations have no warehouse; match the sender's conservative deduction.
    from app.services.stock_direction_service import create_stock_direction

    await create_stock_direction(
        db_session, seed.tenant.id, seed.product.id, name="Named reserve", quantity=1
    )
    actual = 0
    for binding in (seed.bindings[0], ozon):
        actual += (await rules.publish_amounts_for_binding(db_session, binding, [seed.product]))[
            seed.product.id
        ]
    single = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    bulk = (await rules.get_rule_views(db_session, seed.tenant.id, [seed.product.id]))[
        seed.product.id
    ]
    assert single == bulk
    assert (single.on_hand, single.reserved, single.free_stock) == (6, 1, 5)
    assert actual == (4 if units_mode else 2)
    assert single.published_now == actual


@pytest.mark.asyncio
async def test_legacy_set_and_summary_use_free_stock_not_retired_limit(db_session: AsyncSession):
    seed = await _seed(db_session, on_hand=5)
    seed.product.fbs_stock_limit = 0
    await db_session.commit()
    pool = await set_binding_stock_pool_quantity(
        db_session,
        seed.tenant.id,
        seed.seller.id,
        seed.bindings[0].id,
        seed.product.id,
        5,
    )
    assert pool.quantity == 5
    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.rule.units_mode and view.published_now == 5
    summary = await get_binding_stock_pool_summary(
        db_session, seed.tenant.id, seed.seller.id, seed.product.id
    )
    assert (summary["limit"], summary["available"], summary["allocated_total"]) == (5, 5, 5)
    with pytest.raises(FbsWarehouseBindingError) as exc:
        await set_binding_stock_pool_quantity(
            db_session, seed.tenant.id, seed.seller.id, seed.bindings[0].id, seed.product.id, 6
        )
    assert exc.value.code == "pool_quota_exceeded"


@pytest.mark.asyncio
async def test_wb_clear_wrapper_persists_zero_via_actual_callee(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await _seed(db_session, on_hand=5)
    item = FbsStockSyncItem(
        binding_id=seed.bindings[0].id,
        product_id=seed.product.id,
        chrt_id=777,
        last_target_amount=5,
        last_confirmed_amount=5,
        status="confirmed",
    )
    db_session.add(item)
    await db_session.commit()
    transport = _MockStocksTransport()
    transport.stored[777] = 5
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda: client_class(transport=httpx.MockTransport(transport.handler))
    )
    monkeypatch.setattr(
        "app.services.fbs_stock_sync_service._resolve_marketplace_api_token",
        AsyncMock(return_value="synthetic-token"),
    )
    await rules._clear_product_publication(db_session, seed.bindings[0], {seed.product.id})
    # Wrapper session is closed now; read from a completely separate connection.
    async with AsyncSession(bind=db_session.bind) as reread:
        saved = await reread.get(FbsStockSyncItem, item.id)
        assert saved is not None
        assert (saved.last_target_amount, saved.last_confirmed_amount, saved.status) == (
            0,
            0,
            "confirmed",
        )
    await rules._clear_product_publication(db_session, seed.bindings[0], {seed.product.id})
    assert transport.put_attempts == 1
