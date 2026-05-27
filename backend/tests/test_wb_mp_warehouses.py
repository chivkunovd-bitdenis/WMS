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
