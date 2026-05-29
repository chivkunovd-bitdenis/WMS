"""WB marketplace warehouses cache (supplies API, content token fallback)."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wb_mp_warehouses_lazy_sync_from_seller_content_token(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB WH Content",
            "slug": f"wbwhc-{suffix}",
            "admin_email": f"wbwhc-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sel = await async_client.post("/sellers", headers=ah, json={"name": "Seller Content"})
    assert sel.status_code == 201, sel.text
    sid = sel.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "wb-content-only-token"},
    )
    assert tok.status_code == 200, tok.text
    whs = await async_client.get("/operations/wb-mp-warehouses", headers=ah)
    assert whs.status_code == 200, whs.text
    rows = whs.json()
    assert len(rows) >= 1
    assert rows[0]["wb_warehouse_id"] == 900001


@pytest.mark.asyncio
async def test_wb_mp_warehouses_tries_content_after_supplies_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import wildberries_client as wb_client
    from app.services.wildberries_client import WildberriesClientError

    calls: list[str] = []

    async def fake_fetch(
        _client: object,
        *,
        api_token: str,
        supplies_api_base: str | None = None,
    ) -> list[dict[str, object]]:
        del supplies_api_base
        calls.append(api_token)
        if api_token == "bad-supplies":
            raise WildberriesClientError("upstream_error", status_code=401)
        return [
            {
                "ID": 900002,
                "name": "WB склад content",
                "address": "addr",
                "workTime": "24/7",
                "isActive": True,
                "isTransitActive": False,
            }
        ]

    monkeypatch.setattr(wb_client, "fetch_mp_warehouses_list", fake_fetch)
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB WH Fallback",
            "slug": f"wbwhf-{suffix}",
            "admin_email": f"wbwhf-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sel = await async_client.post("/sellers", headers=ah, json={"name": "Seller FB"})
    assert sel.status_code == 201, sel.text
    sid = sel.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={
            "content_api_token": "good-content",
            "supplies_api_token": "bad-supplies",
        },
    )
    assert tok.status_code == 200, tok.text
    whs = await async_client.get("/operations/wb-mp-warehouses", headers=ah)
    assert whs.status_code == 200, whs.text
    rows = whs.json()
    assert len(rows) == 1
    assert rows[0]["wb_warehouse_id"] == 900002
    assert calls == ["good-content"]


@pytest.mark.asyncio
async def test_wb_mp_warehouses_tries_supplies_when_content_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import wildberries_client as wb_client
    from app.services.wildberries_client import WildberriesClientError

    calls: list[str] = []

    async def fake_fetch(
        _client: object,
        *,
        api_token: str,
        supplies_api_base: str | None = None,
    ) -> list[dict[str, object]]:
        del supplies_api_base
        calls.append(api_token)
        if api_token == "bad-content":
            raise WildberriesClientError("upstream_error", status_code=403)
        return [
            {
                "ID": 900003,
                "name": "WB склад supplies",
                "address": "addr",
                "workTime": "24/7",
                "isActive": True,
                "isTransitActive": False,
            }
        ]

    monkeypatch.setattr(wb_client, "fetch_mp_warehouses_list", fake_fetch)
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB WH Sup",
            "slug": f"wbwhs-{suffix}",
            "admin_email": f"wbwhs-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sel = await async_client.post("/sellers", headers=ah, json={"name": "Seller S"})
    sid = sel.json()["id"]
    await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={
            "content_api_token": "bad-content",
            "supplies_api_token": "good-supplies",
        },
    )
    whs = await async_client.get("/operations/wb-mp-warehouses", headers=ah)
    assert whs.status_code == 200
    assert whs.json()[0]["wb_warehouse_id"] == 900003
    assert calls == ["bad-content", "good-supplies"]
