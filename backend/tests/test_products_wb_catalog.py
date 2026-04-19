from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.services.background_job_service import JOB_TYPE_WILDBERRIES_CARDS_SYNC


@pytest.mark.asyncio
async def test_seller_wb_catalog_enriched_from_imported_card(
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
            "cards": [
                {
                    "nmID": 777888,
                    "vendorCode": "VC-ENRICH",
                    "subjectName": "Футболки",
                    "sizes": [{"skus": ["2000000111223"]}],
                    "photos": [{"big": "https://img.example/wb1.jpg"}],
                }
            ],
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
            "organization_name": "Cat Co",
            "slug": f"cat-{suffix}",
            "admin_email": f"cat-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    sid = s.json()["id"]
    await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "t"},
    )
    start = await async_client.post(
        "/operations/background-jobs",
        headers=ah,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": sid},
    )
    jid = start.json()["id"]
    for _ in range(40):
        await asyncio.sleep(0.12)
        jr = await async_client.get(f"/operations/background-jobs/{jid}", headers=ah)
        if jr.json()["status"] == "done":
            break
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Tee",
            "sku_code": f"SKU-CAT-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    link = await async_client.post(
        f"/integrations/wildberries/sellers/{sid}/link-product",
        headers=ah,
        json={"product_id": pid, "nm_id": 777888},
    )
    assert link.status_code == 200

    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={"seller_id": sid, "email": f"cat-sl-{suffix}@example.com", "password": "password123"},
    )
    assert acc.status_code in (200, 201)
    login = await async_client.post(
        "/auth/login",
        json={"email": f"cat-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    cat = await async_client.get("/products/wb-catalog", headers=sh)
    assert cat.status_code == 200, cat.text
    rows = cat.json()
    row = next(r for r in rows if r["id"] == pid)
    assert row["wb_subject_name"] == "Футболки"
    assert row["wb_primary_image_url"] == "https://img.example/wb1.jpg"
    assert row["wb_barcodes"] == ["2000000111223"]
    assert row["wb_primary_barcode"] == "2000000111223"
    assert row["wb_vendor_code"] == "VC-ENRICH"


@pytest.mark.asyncio
async def test_wb_catalog_forbidden_for_admin(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Adm",
            "slug": f"adm-{suffix}",
            "admin_email": f"adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    r = await async_client.get("/products/wb-catalog", headers=ah)
    assert r.status_code == 403
