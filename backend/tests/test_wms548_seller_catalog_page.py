"""WMS-548 D2: GET /seller-catalog/page and /seller-catalog/keys.

The seller must see the union of already-on-fulfillment products and
not-yet-selected WB card snapshots, paginated on the server (WMS-538 taught us
what loading a whole catalog into the browser does at 15000 cards), with
search, category and the new on_fulfillment filter all resolved in SQL.

Products that already exist (the "on fulfillment" side) are seeded through the
real ``upsert_products_from_wb_cards`` import path rather than hand-built ORM
rows, so the test data matches exactly what today's WB sync would have
produced before this feature shipped.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.roles import FULFILLMENT_SELLER
from app.db.session import SessionLocal
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.user import User
from app.services.tokens import create_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


def _wb_card(
    nm_id: int, vendor: str, title: str, category: str, barcodes: list[str]
) -> dict[str, Any]:
    return {
        "nmID": nm_id,
        "vendorCode": vendor,
        "title": title,
        "subjectName": category,
        "sizes": [
            {"techSize": f"S{i}", "chrtID": nm_id * 10 + i, "skus": [barcode]}
            for i, barcode in enumerate(barcodes)
        ],
        "photos": [{"big": f"https://img.example/{nm_id}.jpg"}],
    }


async def _register_with_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[str, str, dict[str, str], dict[str, str]]:
    """Returns (tenant_id, seller_id, seller_owner_auth_headers, admin_auth_headers)."""
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Cat548 {suffix}",
            "slug": f"cat548-{suffix}",
            "admin_email": f"cat548-adm-{suffix}@example.com",
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

    seller_email = f"cat548-sl-{suffix}@example.com"
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


async def _seed_snapshot_card(tenant_id: str, seller_id: str, card: dict[str, Any]) -> None:
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


async def _add_as_product(tenant_id: str, seller_id: str, card: dict[str, Any]) -> None:
    """Seed an "already on fulfillment" card via the real WB import path."""
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
        await upsert_products_from_wb_cards(
            session, uuid.UUID(tenant_id), uuid.UUID(seller_id), [card]
        )


@pytest.mark.asyncio
async def test_seller_catalog_page_unions_products_and_not_on_ff_cards(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    _, other_seller_id, _, _ = await _register_with_seller(async_client, suffix + "-b")

    card_dress = _wb_card(9_000_001, f"DRESS-{suffix}", "Платье А", "Платья", ["1000000000001"])
    card_skirt = _wb_card(
        9_000_002,
        f"SKIRT-{suffix}",
        "Юбка Б",
        "Юбки",
        ["2000000000001", "2000000000002", "2000000000003"],
    )
    foreign_card = _wb_card(9_000_003, f"OTHER-{suffix}", "Чужое", "Платья", ["3000000000001"])

    await _seed_snapshot_card(tenant_id, seller_id, card_dress)  # not on FF
    await _add_as_product(tenant_id, seller_id, card_skirt)  # already on FF (3 sizes)
    # Different seller entirely — must never show up for the first seller.
    async with SessionLocal() as session:
        session.add(
            SellerWildberriesImportedCard(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant_id),
                seller_id=uuid.UUID(other_seller_id),
                nm_id=foreign_card["nmID"],
                vendor_code=foreign_card["vendorCode"],
                title=foreign_card["title"],
                raw_json=foreign_card,
            )
        )
        await session.commit()

    # 1) Union: 1 not-on-ff card + 3 products (one per size of the skirt card).
    page = await async_client.get("/seller-catalog/page", headers=seller_headers)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 4
    assert body["scope_total"] == 4
    nm_ids_seen = {item.get("nm_id") or item.get("wb_nm_id") for item in body["items"]}
    assert 9_000_003 not in nm_ids_seen  # foreign seller's card never leaks
    on_ff_flags = {item["on_fulfillment"] for item in body["items"]}
    assert on_ff_flags == {True, False}
    assert all(item["marketplace"] == "wildberries" for item in body["items"])
    assert "Платья" in body["categories"]
    assert "Юбки" in body["categories"]

    # 2) on_fulfillment=yes -> only the 3 skirt-size products.
    only_ff = await async_client.get(
        "/seller-catalog/page", headers=seller_headers, params={"on_fulfillment": "yes"}
    )
    assert only_ff.status_code == 200
    assert only_ff.json()["total"] == 3
    assert all(item["on_fulfillment"] for item in only_ff.json()["items"])
    assert all(item["wb_nm_id"] == 9_000_002 for item in only_ff.json()["items"])

    # 3) on_fulfillment=no -> only the dress card, with the not-on-ff field shape.
    only_not_ff = await async_client.get(
        "/seller-catalog/page", headers=seller_headers, params={"on_fulfillment": "no"}
    )
    assert only_not_ff.status_code == 200
    not_ff_items = only_not_ff.json()["items"]
    assert len(not_ff_items) == 1
    row = not_ff_items[0]
    assert row["on_fulfillment"] is False
    assert row["nm_id"] == 9_000_001
    assert row["vendor_code"] == f"DRESS-{suffix}"
    assert row["name"] == "Платье А"
    assert row["photo_url"] == "https://img.example/9000001.jpg"
    assert row["barcodes"] == ["1000000000001"]
    assert row["category"] == "Платья"
    assert row["key"] == "wb:9000001"

    # 4) Category filter narrows to the matching card's rows.
    by_category = await async_client.get(
        "/seller-catalog/page", headers=seller_headers, params={"category": "Юбки"}
    )
    assert by_category.status_code == 200
    assert by_category.json()["total"] == 3

    # 5) Search by the not-on-ff card's own vendor code.
    by_vendor = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"search": f"DRESS-{suffix}"},
    )
    assert by_vendor.status_code == 200
    assert by_vendor.json()["total"] == 1
    assert by_vendor.json()["items"][0]["nm_id"] == 9_000_001

    # 6) Search by any barcode of a multi-size on-ff card finds all its rows —
    # same "the whole card matches" semantics as the existing FF catalog search.
    by_barcode = await async_client.get(
        "/seller-catalog/page", headers=seller_headers, params={"search": "2000000000002"}
    )
    assert by_barcode.status_code == 200
    assert by_barcode.json()["total"] == 3

    # 7) /seller-catalog/keys matches the unfiltered page total and lists every key.
    keys_res = await async_client.get("/seller-catalog/keys", headers=seller_headers)
    assert keys_res.status_code == 200
    keys = keys_res.json()
    assert len(keys) == 4
    assert "wb:9000001" in keys
    assert sum(1 for k in keys if k.startswith("product:")) == 3


@pytest.mark.asyncio
async def test_seller_catalog_page_pagination_has_no_gap_or_duplicate(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    total_cards = 23
    for i in range(total_cards):
        card = _wb_card(
            9_100_000 + i, f"PAG-{suffix}-{i:03d}", f"Товар {i}", "Категория", [f"9{i:012d}"]
        )
        await _seed_snapshot_card(tenant_id, seller_id, card)

    seen_keys: list[str] = []
    offset = 0
    limit = 7
    while True:
        page = await async_client.get(
            "/seller-catalog/page",
            headers=seller_headers,
            params={"limit": limit, "offset": offset},
        )
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == total_cards
        items = body["items"]
        if not items:
            break
        seen_keys.extend(item["key"] for item in items)
        offset += limit

    assert len(seen_keys) == total_cards
    assert len(set(seen_keys)) == total_cards  # no duplicates across page boundaries

    keys_res = await async_client.get("/seller-catalog/keys", headers=seller_headers)
    assert set(keys_res.json()) == set(seen_keys)


@pytest.mark.asyncio
async def test_seller_catalog_page_requires_seller_role_and_products_permission(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, _seller_headers, admin_headers = await _register_with_seller(
        async_client, suffix
    )

    # The fulfillment admin from the same registration must never reach this endpoint.
    admin_res = await async_client.get("/seller-catalog/page", headers=admin_headers)
    assert admin_res.status_code == 403
    assert admin_res.json()["detail"] == "forbidden"

    # A real staff user of this seller without the "Товары" permission -> 403.
    async with SessionLocal() as session:
        staff_user = User(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            seller_id=uuid.UUID(seller_id),
            email=f"cat548-staff-{suffix}@example.com",
            password_hash="x",
            must_set_password=False,
            role=FULFILLMENT_SELLER,
        )
        session.add(staff_user)
        session.add(
            SellerStaffPermissions(
                user_id=staff_user.id,
                can_documents=True,
                can_products=False,
                can_honest_sign=True,
                can_settings=False,
                can_staff=False,
            )
        )
        await session.commit()
        staff_token = create_access_token(
            user_id=staff_user.id,
            tenant_id=uuid.UUID(tenant_id),
            role=FULFILLMENT_SELLER,
            seller_id=uuid.UUID(seller_id),
        )

    staff_res = await async_client.get(
        "/seller-catalog/page", headers={"Authorization": f"Bearer {staff_token}"}
    )
    assert staff_res.status_code == 403
    assert staff_res.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_seller_catalog_page_ignores_forged_seller_id_without_shop_management(
    async_client: AsyncClient,
) -> None:
    """A plain seller user cannot widen its scope to another seller via a forged JWT."""
    suffix = str(int(time.time() * 1000))
    tenant_id, _seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    _, other_seller_id, _, _ = await _register_with_seller(async_client, suffix + "-b")

    secret_card = _wb_card(9_200_001, f"SECRET-{suffix}", "Секрет", "Кат", ["9200000000001"])
    await _seed_snapshot_card(tenant_id, other_seller_id, secret_card)

    me = (await async_client.get("/auth/me", headers=seller_headers)).json()
    forged = create_access_token(
        user_id=uuid.UUID(me["id"]),
        tenant_id=uuid.UUID(tenant_id),
        role=FULFILLMENT_SELLER,
        seller_id=uuid.UUID(other_seller_id),
    )
    res = await async_client.get(
        "/seller-catalog/page", headers={"Authorization": f"Bearer {forged}"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 0  # scoped to the caller's own (empty) shop, not the forged one
    nm_ids = {item.get("nm_id") for item in body["items"]}
    assert 9_200_001 not in nm_ids
