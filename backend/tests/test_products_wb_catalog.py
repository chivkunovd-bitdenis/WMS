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


@pytest.mark.asyncio
async def test_ff_catalog_shows_only_products_with_warehouse_movements(
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
                    "nmID": 919191,
                    "vendorCode": "ADM-WB-VC",
                    "subjectName": "Брюки",
                    "sizes": [{"skus": ["4600000000011"]}],
                    "photos": [{"big": "https://img.example/admin-wb.jpg"}],
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
            "organization_name": "Admin Cat Co",
            "slug": f"adm-cat-{suffix}",
            "admin_email": f"adm-cat-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller_a = (await async_client.post("/sellers", headers=ah, json={"name": "Seller A"})).json()
    seller_b = (await async_client.post("/sellers", headers=ah, json={"name": "Seller B"})).json()
    sid_a = seller_a["id"]
    sid_b = seller_b["id"]

    await async_client.patch(
        f"/integrations/wildberries/sellers/{sid_a}/tokens",
        headers=ah,
        json={"content_api_token": "token-a"},
    )
    start = await async_client.post(
        "/operations/background-jobs",
        headers=ah,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": sid_a},
    )
    jid = start.json()["id"]
    for _ in range(40):
        await asyncio.sleep(0.12)
        jr = await async_client.get(f"/operations/background-jobs/{jid}", headers=ah)
        if jr.json()["status"] == "done":
            break

    product_a = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Admin Alpha",
            "sku_code": f"ADM-A-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid_a,
        },
    )
    product_b_private_only = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Admin Private Only",
            "sku_code": f"ADM-B-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid_b,
        },
    )
    product_c = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Admin Moved B",
            "sku_code": f"ADM-C-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid_b,
        },
    )
    pid_a = product_a.json()["id"]
    pid_b_private_only = product_b_private_only.json()["id"]
    pid_c = product_c.json()["id"]
    link = await async_client.post(
        f"/integrations/wildberries/sellers/{sid_a}/link-product",
        headers=ah,
        json={"product_id": pid_a, "nm_id": 919191},
    )
    assert link.status_code == 200

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "WH", "code": f"wh-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "A-01"}
    )
    loc_id = loc.json()["id"]

    async def post_inbound_actual(product_id: str, actual_qty: int) -> None:
        req = await async_client.post(
            "/operations/inbound-intake-requests",
            headers=ah,
            json={"warehouse_id": wid},
        )
        rid = req.json()["id"]
        line_res = await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/lines",
            headers=ah,
            json={"product_id": product_id, "expected_qty": 10},
        )
        line_id = line_res.json()["id"]
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/submit", headers=ah
        )
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/primary-accept", headers=ah
        )
        await async_client.patch(
            f"/operations/inbound-intake-requests/{rid}/lines/{line_id}",
            headers=ah,
            json={"storage_location_id": loc_id},
        )
        await async_client.patch(
            f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
            headers=ah,
            json={"actual_qty": actual_qty},
        )
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/verify", headers=ah
        )
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/post", headers=ah
        )

    await post_inbound_actual(pid_a, 7)
    await post_inbound_actual(pid_c, 3)

    all_rows_res = await async_client.get("/products/ff-catalog", headers=ah)
    assert all_rows_res.status_code == 200, all_rows_res.text
    all_rows = all_rows_res.json()
    row_ids = {r["id"] for r in all_rows}
    assert pid_a in row_ids
    assert pid_c in row_ids
    assert pid_b_private_only not in row_ids
    row_a = next(r for r in all_rows if r["id"] == pid_a)
    assert row_a["seller_id"] == sid_a
    assert row_a["seller_name"] == "Seller A"
    assert row_a["wb_subject_name"] == "Брюки"
    assert row_a["wb_primary_image_url"] == "https://img.example/admin-wb.jpg"
    assert row_a["wb_barcodes"] == ["4600000000011"]
    assert row_a["wb_primary_barcode"] == "4600000000011"
    assert row_a["wb_vendor_code"] == "ADM-WB-VC"

    filtered_res = await async_client.get(
        f"/products/ff-catalog?seller_id={sid_b}",
        headers=ah,
    )
    assert filtered_res.status_code == 200
    filtered_rows = filtered_res.json()
    assert {r["id"] for r in filtered_rows} == {pid_c}
    assert filtered_rows[0]["seller_name"] == "Seller B"


@pytest.mark.asyncio
async def test_ff_catalog_forbidden_for_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Adm Cat RBAC",
            "slug": f"adm-cat-rbac-{suffix}",
            "admin_email": f"adm-cat-rbac-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=ah, json={"name": "Seller"})
    sid = seller.json()["id"]
    email = f"adm-cat-seller-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={"seller_id": sid, "email": email, "password": "password123"},
    )
    assert acc.status_code in (200, 201)
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await async_client.get("/products/ff-catalog", headers=sh)
    assert r.status_code == 403
