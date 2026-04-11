from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.services.background_job_service import JOB_TYPE_WILDBERRIES_CARDS_SYNC


@pytest.mark.asyncio
async def test_link_product_to_wb_card(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_cards(
        client: object,
        *,
        api_token: str,
        content_api_base: str | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        return {
            "cards": [{"nmID": 555001, "vendorCode": "VC-LINK"}],
            "cursor": {},
        }

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_cards_list",
        fake_cards,
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Link Co",
            "slug": f"wbl-{suffix}",
            "admin_email": f"wbl-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "SellerL"})
    sid = s.json()["id"]
    await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=h,
        json={"content_api_token": "t"},
    )
    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": sid},
    )
    jid = start.json()["id"]
    for _ in range(40):
        await asyncio.sleep(0.12)
        jr = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        if jr.json()["status"] == "done":
            break
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"SKU-L-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200
    pid = pr.json()["id"]
    link = await async_client.post(
        f"/integrations/wildberries/sellers/{sid}/link-product",
        headers=h,
        json={"product_id": pid, "nm_id": 555001},
    )
    assert link.status_code == 200
    assert link.json()["wb_nm_id"] == 555001
    assert link.json()["wb_vendor_code"] == "VC-LINK"
    plist = await async_client.get("/products", headers=h)
    row = next(x for x in plist.json() if x["id"] == pid)
    assert row["wb_nm_id"] == 555001


@pytest.mark.asyncio
async def test_link_product_wb_card_not_found(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Link Co2",
            "slug": f"wbl2-{suffix}",
            "admin_email": f"wbl2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "S"})
    sid = s.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"SKU-X-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    r = await async_client.post(
        f"/integrations/wildberries/sellers/{sid}/link-product",
        headers=h,
        json={"product_id": pid, "nm_id": 999999999},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "wb_card_not_found"
