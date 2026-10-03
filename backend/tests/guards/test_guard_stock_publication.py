"""G-STOCK-8: publication cap and independent marketplace settings."""

from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.models.inventory_balance import InventoryBalance
from app.services import fbs_stock_sync_service as stock_sync
from app.services.fbs_stock_publish_service import publish_seller_stocks_now
from app.services.fbs_stock_rule_service import (
    FbsRule,
    get_rule_view,
    publish_amounts_for_binding,
    set_rule_for_products,
)
from app.services.fbs_warehouse_binding_service import set_binding_stock_pool_quantity
from app.services.inventory_service import record_movement_and_adjust_balance
from tests.guards.stock_helpers import check
from tests.test_fbs_stock_rule_service import _ozon_binding, _seed


@pytest.mark.asyncio
async def test_g_stock_8_publication_min_cap_free_and_marketplace_settings(db_session, monkeypatch):
    """G-STOCK-8 · WMS-632 · решение владельца 02.10.2026:
    «Публикуемый остаток FBS: min(лимит оператора, свободный остаток)».
    """
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish", lambda *_: None
    )
    monkeypatch.setattr(
        "app.services.inventory_service.schedule_seller_stock_publish", lambda *_: None
    )
    monkeypatch.setattr(
        stock_sync, "_resolve_marketplace_api_token", AsyncMock(return_value="test-token")
    )
    published = []

    async def wb_put(_client, _url, **kwargs):
        published.append(kwargs["json"]["stocks"])
        return httpx.Response(204)

    async def wb_readback(*_args, **_kwargs):
        return [
            stock_sync.MarketplaceStockAmount(chrt_id=row["chrtId"], amount=row["amount"])
            for row in published[-1]
        ]

    monkeypatch.setattr(httpx.AsyncClient, "put", wb_put)
    monkeypatch.setattr(stock_sync, "fetch_marketplace_stocks", wb_readback)
    seed = await _seed(db_session, on_hand=12)
    ozon = await _ozon_binding(db_session, seed, wb_warehouse_id=501001)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            publish_ozon=True,
            same_everywhere=False,
            percent=0,
            units_mode=True,
            units_by_warehouse={"wb:501001": 10, "ozon:501001": 2},
        ),
    )
    for binding, amount, expected in [
        (seed.bindings[0], 8, {"wb:501001": 8, "ozon:501001": 2}),
        (ozon, 1, {"wb:501001": 8, "ozon:501001": 1}),
        (seed.bindings[0], 10, {"wb:501001": 10, "ozon:501001": 1}),
    ]:
        await set_binding_stock_pool_quantity(
            db_session, seed.tenant.id, seed.seller.id, binding.id, seed.product.id, amount
        )
        view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
        check(
            view.rule.units_by_warehouse,
            expected,
            "настройка одной площадки сохраняет настройку другой",
        )
    balance = await db_session.scalar(
        select(InventoryBalance).where(InventoryBalance.product_id == seed.product.id)
    )
    for delta, expected in [(0, 10), (-5, 7), (-7, 0)]:
        if delta:
            await record_movement_and_adjust_balance(
                db_session,
                tenant_id=seed.tenant.id,
                product_id=seed.product.id,
                storage_location_id=balance.storage_location_id,
                quantity_delta=delta,
                movement_type="inventory_count",
                actor_user_id=None,
            )
        amounts = await publish_amounts_for_binding(db_session, seed.bindings[0], [seed.product])
        check(
            amounts.get(seed.product.id, 0), expected, "публикация равна min(10, свободный остаток)"
        )
        await db_session.commit()
        sent_before = len(published)
        await publish_seller_stocks_now(seed.tenant.id, seed.seller.id, marketplace="wb")
        check(len(published), sent_before + 1, "публикация действительно вызвала WB transport")
        check(
            published[-1],
            [{"chrtId": 777, "amount": expected}],
            "в WB отправлен min(10, свободный остаток)",
        )
        view = await get_rule_view(db_session, seed.tenant.id, seed.product.id)
        check(
            view.rule.units_by_warehouse["wb:501001"],
            10,
            "снижение остатка не расходует сохранённый лимит",
        )
