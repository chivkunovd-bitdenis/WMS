"""Wildberries legacy client — trbx delete mock contract."""

from __future__ import annotations

import httpx
import pytest

from app.core.settings import settings
from app.services import wildberries_client as wb_mod
from app.services.wildberries_client import (
    create_marketplace_supply_trbx,
    delete_marketplace_supply_trbx,
    fetch_marketplace_supply_trbx_list,
)


@pytest.mark.asyncio
async def test_mock_trbx_delete_removes_only_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    wb_mod._mock_trbx_by_supply.clear()

    async with httpx.AsyncClient() as client:
        created = await create_marketplace_supply_trbx(
            client,
            api_token="token",
            supply_id="WB-SUP-1",
            amount=2,
        )
        assert len(created) == 2

        await delete_marketplace_supply_trbx(
            client,
            api_token="token",
            supply_id="WB-SUP-1",
            trbx_ids=[created[0]],
        )
        remaining = await fetch_marketplace_supply_trbx_list(
            client,
            api_token="token",
            supply_id="WB-SUP-1",
        )

    assert remaining == [created[1]]
