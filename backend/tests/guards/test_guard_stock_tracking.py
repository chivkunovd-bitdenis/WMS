"""G-STOCK-4: external completion is not a local stock document."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import fbs_tracking_service as tracking
from app.services.wildberries_fbs_client import MarketplaceSupplyDetails
from tests.guards.stock_helpers import check, moves, seed_fbs, total


@pytest.mark.asyncio
async def test_g_stock_4_wb_done_never_writes_off(db_session, monkeypatch):
    """G-STOCK-4 · WMS-632 · решение владельца 02.10.2026:
    «Нам не надо списывать остаток, если поставку закрыли в кабинете WB».
    """
    ctx, actor, _ = await seed_fbs(db_session)
    monkeypatch.setattr(
        tracking, "_resolve_marketplace_api_token", AsyncMock(return_value="test-token")
    )
    monkeypatch.setattr(
        tracking,
        "fetch_marketplace_supply_details",
        AsyncMock(
            return_value=MarketplaceSupplyDetails(
                supply_id=ctx.supply.wb_supply_id, name="Guard", done=True
            )
        ),
    )
    async with httpx.AsyncClient() as client:
        for _ in range(2):
            result = await tracking.sync_supply_tracking(
                db_session, ctx.tenant.id, ctx.supply.id, client, actor_user_id=actor.id
            )
            await db_session.commit()
            check(result.supply_status, "done", "опрос сохраняет закрытый статус WB")
            check(
                await total(db_session, ctx.product.id),
                10,
                "закрытие в WB не списывает остаток WMS",
            )
            check(
                len(await moves(db_session, ctx.product.id, "fbs_shipment")),
                0,
                "автоопрос не создаёт проведённую отгрузку",
            )
            check(ctx.supply.delivered_at, None, "WB done не подделывает проведение в WMS")
