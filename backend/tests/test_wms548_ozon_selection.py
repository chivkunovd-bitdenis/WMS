"""WMS-548 D3: Ozon snapshot in /seller-catalog and its add-to-fulfillment leg.

Covers what D2's WB tests already prove generically (pagination, isolation,
role/permission checks) only lightly, and focuses on what is Ozon-specific:
the snapshot never turns into a product by itself (R12), an explicit add
does turn it into one (or links it to an existing product, never a
duplicate), and the "same physical item, two marketplaces" auto-link works
in both directions (R13). Ozon's own matching mechanics (barcode, offer_id,
the WB→Ozon transfer formula) are exercised in test_ozon_product_import.py;
here they are only used as fixtures, not re-verified.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard


def _wb_card(nm_id: int, vendor: str, title: str, barcode: str) -> dict[str, Any]:
    return {
        "nmID": nm_id,
        "vendorCode": vendor,
        "title": title,
        "subjectName": "Категория",
        "sizes": [{"techSize": "one", "chrtID": nm_id * 10, "skus": [barcode]}],
    }


def _ozon_card(
    product_id: str,
    offer_id: str,
    sku: str,
    name: str,
    *,
    barcodes: list[str] | None = None,
) -> dict[str, Any]:
    card: dict[str, Any] = {"id": product_id, "offer_id": offer_id, "sku": sku, "name": name}
    if barcodes:
        card["barcodes"] = barcodes
    return card


async def _register_with_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[str, str, dict[str, str], dict[str, str]]:
    """Returns (tenant_id, seller_id, seller_owner_auth_headers, admin_auth_headers)."""
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Ozon548 {suffix}",
            "slug": f"ozon548-{suffix}",
            "admin_email": f"ozon548-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = (await async_client.get("/auth/me", headers=admin_headers)).json()
    tenant_id = me["tenant_id"]

    seller_res = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": f"Seller {suffix}"}
    )
    assert seller_res.status_code == 201, seller_res.text
    seller_id = seller_res.json()["id"]

    seller_email = f"ozon548-sl-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": seller_email, "password": "password123"},
    )
    assert acc.status_code == 201, acc.text
    login = await async_client.post(
        "/auth/login", json={"email": seller_email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return tenant_id, seller_id, seller_headers, admin_headers


async def _seed_ozon_card(tenant_id: str, seller_id: str, card: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        session.add(
            SellerOzonImportedCard(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant_id),
                seller_id=uuid.UUID(seller_id),
                ozon_product_id=str(card["id"]),
                sku=str(card.get("sku")) if card.get("sku") is not None else None,
                offer_id=card.get("offer_id"),
                name=card.get("name"),
                raw_json=card,
            )
        )
        await session.commit()


async def _seed_wb_card(tenant_id: str, seller_id: str, card: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        session.add(
            SellerWildberriesImportedCard(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant_id),
                seller_id=uuid.UUID(seller_id),
                nm_id=card["nmID"],
                vendor_code=card["vendorCode"],
                title=card["title"],
                raw_json=card,
            )
        )
        await session.commit()


async def _ozon_link_for(tenant_id: str, seller_id: str, ozon_product_id: str) -> Any:
    async with SessionLocal() as session:
        return (
            await session.execute(
                select(ProductMarketplaceLink).where(
                    ProductMarketplaceLink.tenant_id == uuid.UUID(tenant_id),
                    ProductMarketplaceLink.seller_id == uuid.UUID(seller_id),
                    ProductMarketplaceLink.marketplace == "ozon",
                    ProductMarketplaceLink.external_product_id == ozon_product_id,
                    ProductMarketplaceLink.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()


async def _product_count(tenant_id: str, seller_id: str) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count()).where(
                    Product.tenant_id == uuid.UUID(tenant_id),
                    Product.seller_id == uuid.UUID(seller_id),
                )
            )
            or 0
        )


@pytest.mark.asyncio
async def test_ozon_snapshot_is_visible_but_not_on_fulfillment_until_added(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    card_a = _ozon_card("9500001", f"OZ-A-{suffix}", "5500001", "Товар А")
    card_b = _ozon_card("9500002", f"OZ-B-{suffix}", "5500002", "Товар Б")
    await _seed_ozon_card(tenant_id, seller_id, card_a)
    await _seed_ozon_card(tenant_id, seller_id, card_b)

    page = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"marketplace": "ozon", "on_fulfillment": "no"},
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 2
    by_id = {item["ozon_product_id"]: item for item in body["items"]}
    assert by_id["9500001"]["on_fulfillment"] is False
    assert by_id["9500001"]["marketplace"] == "ozon"
    assert by_id["9500001"]["vendor_code"] == f"OZ-A-{suffix}"
    assert by_id["9500001"]["name"] == "Товар А"
    assert by_id["9500001"]["key"] == "ozon:9500001"
    assert by_id["9500001"]["category"] is None  # А6: Ozon carries no category

    assert await _product_count(tenant_id, seller_id) == 0  # nothing created by the snapshot


@pytest.mark.asyncio
async def test_add_to_fulfillment_creates_a_product_and_repeat_is_idempotent(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    card = _ozon_card("9500010", f"OZ-{suffix}", "5500010", "Новый товар")
    await _seed_ozon_card(tenant_id, seller_id, card)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9500010"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skipped"] == []
    assert body["added"] == [
        {
            "marketplace": "ozon",
            "id": "9500010",
            "vendor_code": f"OZ-{suffix}",
            "products_added": 1,
        }
    ]
    assert await _product_count(tenant_id, seller_id) == 1

    # Repeat: same card, already on FF — re-links, does not duplicate.
    second = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9500010"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["added"][0]["products_added"] == 0  # matched, not re-created
    assert await _product_count(tenant_id, seller_id) == 1

    # The card must no longer show as "not on fulfillment".
    page = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"marketplace": "ozon", "on_fulfillment": "no"},
    )
    assert page.json()["total"] == 0


@pytest.mark.asyncio
async def test_add_to_fulfillment_concurrent_requests_do_not_duplicate(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    card = _ozon_card("9500020", f"OZ-C-{suffix}", "5500020", "Одновременно")
    await _seed_ozon_card(tenant_id, seller_id, card)

    async def _add() -> Any:
        return await async_client.post(
            "/seller-catalog/add-to-fulfillment",
            headers=seller_headers,
            json={"wb_nm_ids": [], "ozon_product_ids": ["9500020"]},
        )

    results = await asyncio.gather(_add(), _add())
    for res in results:
        assert res.status_code == 200, res.text
    assert await _product_count(tenant_id, seller_id) == 1


@pytest.mark.asyncio
async def test_add_to_fulfillment_ozon_isolation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, _seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    _, other_seller_id, _, _ = await _register_with_seller(async_client, suffix + "-b")

    foreign_card = _ozon_card("9500030", f"OZ-D-{suffix}", "5500030", "Чужой")
    await _seed_ozon_card(tenant_id, other_seller_id, foreign_card)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9500030"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["added"] == []
    assert res.json()["skipped"] == [
        {"marketplace": "ozon", "id": "9500030", "vendor_code": None, "reason": "not_found"}
    ]
    assert await _product_count(tenant_id, other_seller_id) == 0


@pytest.mark.asyncio
async def test_r13_adding_ozon_card_links_to_existing_wb_product_instead_of_duplicating(
    async_client: AsyncClient,
) -> None:
    """A twin already on FF (added from WB) must be linked, not duplicated."""
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    wb_card = _wb_card(8_400_001, f"TWIN-A-{suffix}", "Твин А", "7000000000001")
    await _seed_wb_card(tenant_id, seller_id, wb_card)
    add_wb = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_400_001], "ozon_product_ids": []},
    )
    assert add_wb.status_code == 200, add_wb.text
    assert add_wb.json()["added"][0]["products_added"] == 1
    assert await _product_count(tenant_id, seller_id) == 1

    ozon_twin = _ozon_card(
        "9400001", "OZTWIN-A", "5400001", "Твин А (Ozon)", barcodes=["7000000000001"]
    )
    await _seed_ozon_card(tenant_id, seller_id, ozon_twin)

    add_ozon = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9400001"]},
    )
    assert add_ozon.status_code == 200, add_ozon.text
    assert add_ozon.json()["skipped"] == []
    assert add_ozon.json()["added"][0]["products_added"] == 0  # linked, not created

    assert await _product_count(tenant_id, seller_id) == 1  # still one physical item
    link = await _ozon_link_for(tenant_id, seller_id, "9400001")
    assert link is not None


@pytest.mark.asyncio
async def test_r13_adding_wb_card_auto_links_a_preexisting_ozon_twin(
    async_client: AsyncClient,
) -> None:
    """The reverse direction: the Ozon twin was already sitting in the snapshot,
    unlinked, before the WB card got added — it must be linked automatically,
    not left as a separate "not on fulfillment" row.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    ozon_twin = _ozon_card(
        "9400002", "OZTWIN-B", "5400002", "Твин Б (Ozon)", barcodes=["7000000000002"]
    )
    await _seed_ozon_card(tenant_id, seller_id, ozon_twin)
    wb_card = _wb_card(8_400_002, f"TWIN-B-{suffix}", "Твин Б", "7000000000002")
    await _seed_wb_card(tenant_id, seller_id, wb_card)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_400_002], "ozon_product_ids": []},
    )
    assert res.status_code == 200, res.text
    assert res.json()["added"][0]["products_added"] == 1

    assert await _product_count(tenant_id, seller_id) == 1  # not two separate products
    link = await _ozon_link_for(tenant_id, seller_id, "9400002")
    assert link is not None

    page = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"marketplace": "ozon", "on_fulfillment": "no"},
    )
    assert page.json()["total"] == 0  # the twin no longer sits unmatched
