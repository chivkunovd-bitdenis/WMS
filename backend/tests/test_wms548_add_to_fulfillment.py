"""WMS-548 D2: POST /seller-catalog/add-to-fulfillment.

Turns selected WB card snapshots into WMS products. Covers: partial success
(unaddable cards are skipped with a reason, the rest still get added), repeat
and concurrent-request idempotency (no duplicate products), the 500-id
request cap, isolation (a foreign/unknown nmID never leaks or creates
anything) and role/permission enforcement.
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
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard


def _wb_card(
    nm_id: int, vendor: str, title: str, barcodes: list[str], *, with_sizes: bool = True
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "nmID": nm_id,
        "vendorCode": vendor,
        "title": title,
        "subjectName": "Категория",
    }
    if with_sizes:
        card["sizes"] = [
            {"techSize": f"S{i}", "chrtID": nm_id * 10 + i, "skus": [barcode]}
            for i, barcode in enumerate(barcodes)
        ]
    return card


async def _register_with_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[str, str, dict[str, str], dict[str, str]]:
    """Returns (tenant_id, seller_id, seller_owner_auth_headers, admin_auth_headers)."""
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Add548 {suffix}",
            "slug": f"add548-{suffix}",
            "admin_email": f"add548-adm-{suffix}@example.com",
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

    seller_email = f"add548-sl-{suffix}@example.com"
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


async def _product_count(tenant_id: str, seller_id: str, nm_id: int) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count()).where(
                    Product.tenant_id == uuid.UUID(tenant_id),
                    Product.seller_id == uuid.UUID(seller_id),
                    Product.wb_nm_id == nm_id,
                )
            )
            or 0
        )


async def _product_identity(tenant_id: str, seller_id: str, nm_id: int) -> dict[str, Any]:
    """The fields a conflicting card must never be allowed to overwrite (А12)."""
    async with SessionLocal() as session:
        product = (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == uuid.UUID(tenant_id),
                    Product.seller_id == uuid.UUID(seller_id),
                    Product.wb_nm_id == nm_id,
                )
            )
        ).scalar_one()
        return {
            "wb_nm_id": product.wb_nm_id,
            "wb_barcode": product.wb_barcode,
            "name": product.name,
        }


@pytest.mark.asyncio
async def test_add_to_fulfillment_creates_products_only_for_requested_cards(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)
    _, other_seller_id, _, _ = await _register_with_seller(async_client, suffix + "-b")

    single = _wb_card(8_000_001, f"SINGLE-{suffix}", "Один размер", ["4000000000001"])
    multi = _wb_card(
        8_000_002, f"MULTI-{suffix}", "Два размера", ["4000000000002", "4000000000003"]
    )
    untouched = _wb_card(8_000_003, f"UNTOUCHED-{suffix}", "Не трогаем", ["4000000000004"])

    await _seed_snapshot_card(tenant_id, seller_id, single)
    await _seed_snapshot_card(tenant_id, seller_id, multi)
    await _seed_snapshot_card(tenant_id, other_seller_id, untouched)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_000_001, 8_000_002], "ozon_product_ids": []},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skipped"] == []
    added_by_id = {a["id"]: a for a in body["added"]}
    assert added_by_id["8000001"]["products_added"] == 1
    assert added_by_id["8000001"]["vendor_code"] == f"SINGLE-{suffix}"
    assert added_by_id["8000001"]["marketplace"] == "wildberries"
    assert added_by_id["8000002"]["products_added"] == 2

    assert await _product_count(tenant_id, seller_id, 8_000_001) == 1
    assert await _product_count(tenant_id, seller_id, 8_000_002) == 2
    # The other seller's untouched card was never even looked at.
    assert await _product_count(tenant_id, other_seller_id, 8_000_003) == 0

    page = await async_client.get(
        "/seller-catalog/page", headers=seller_headers, params={"on_fulfillment": "yes"}
    )
    assert page.json()["total"] == 3  # 1 + 2 sizes


@pytest.mark.asyncio
async def test_add_to_fulfillment_repeat_and_concurrent_requests_do_not_duplicate(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    card = _wb_card(
        8_100_001, f"REPEAT-{suffix}", "Повтор", ["4100000000001", "4100000000002"]
    )
    await _seed_snapshot_card(tenant_id, seller_id, card)

    first = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_100_001], "ozon_product_ids": []},
    )
    assert first.status_code == 200, first.text
    assert first.json()["added"][0]["products_added"] == 2
    assert await _product_count(tenant_id, seller_id, 8_100_001) == 2

    # Repeating the same request re-upserts but must not create a second set.
    second = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_100_001], "ozon_product_ids": []},
    )
    assert second.status_code == 200, second.text
    assert await _product_count(tenant_id, seller_id, 8_100_001) == 2

    # A brand-new card added from two "tabs" at once must also end up as one set.
    concurrent_card = _wb_card(
        8_100_002, f"CONCURRENT-{suffix}", "Одновременно", ["4100000000003"]
    )
    await _seed_snapshot_card(tenant_id, seller_id, concurrent_card)

    async def _add() -> Any:
        return await async_client.post(
            "/seller-catalog/add-to-fulfillment",
            headers=seller_headers,
            json={"wb_nm_ids": [8_100_002], "ozon_product_ids": []},
        )

    results = await asyncio.gather(_add(), _add())
    for res in results:
        assert res.status_code == 200, res.text
    assert await _product_count(tenant_id, seller_id, 8_100_002) == 1


@pytest.mark.asyncio
async def test_add_to_fulfillment_skips_unaddable_cards_with_reasons(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    # 1) No size/barcode data at all.
    no_sizes = _wb_card(8_200_001, f"NOSIZE-{suffix}", "Без размеров", [], with_sizes=False)
    await _seed_snapshot_card(tenant_id, seller_id, no_sizes)

    # 2) Vendor-code conflict: nm 8_200_010 is already a product under vendor
    # "SAME-<suffix>"; a never-added card sharing that exact vendor code (and
    # therefore the same single-variant sku_code) must not silently steal it.
    existing_card = _wb_card(
        8_200_010, f"SAME-{suffix}", "Уже на ФФ", ["4200000000010"]
    )
    await _seed_snapshot_card(tenant_id, seller_id, existing_card)
    add_existing = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_200_010], "ozon_product_ids": []},
    )
    assert add_existing.status_code == 200, add_existing.text
    assert add_existing.json()["added"][0]["products_added"] == 1
    identity_before = await _product_identity(tenant_id, seller_id, 8_200_010)

    conflicting_card = _wb_card(
        8_200_011, f"SAME-{suffix}", "Конфликт артикула", ["4200000000011"]
    )
    await _seed_snapshot_card(tenant_id, seller_id, conflicting_card)

    # 3) A perfectly addable card in the same request.
    good_card = _wb_card(8_200_020, f"GOOD-{suffix}", "Нормальная карточка", ["4200000000020"])
    await _seed_snapshot_card(tenant_id, seller_id, good_card)

    # 4) An id that does not belong to this seller at all (nor exists anywhere).
    unknown_nm_id = 8_200_099

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={
            "wb_nm_ids": [8_200_001, 8_200_011, 8_200_020, unknown_nm_id],
            "ozon_product_ids": [],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    added_ids = {a["id"] for a in body["added"]}
    assert added_ids == {"8200020"}

    skipped_by_id = {s["id"]: s for s in body["skipped"]}
    assert skipped_by_id["8200001"]["reason"] == "no_size_variants"
    assert skipped_by_id["8200011"]["reason"] == "vendor_code_conflict"
    assert skipped_by_id[str(unknown_nm_id)]["reason"] == "not_found"

    assert await _product_count(tenant_id, seller_id, 8_200_001) == 0
    assert await _product_count(tenant_id, seller_id, 8_200_011) == 0
    assert await _product_count(tenant_id, seller_id, 8_200_020) == 1
    # The vendor-code owner (already on FF before the request) is unaffected —
    # not just in count, but in identity: the rejected card must not have
    # overwritten its nmID, barcode or name (А12, решение 27.09).
    assert await _product_count(tenant_id, seller_id, 8_200_010) == 1
    assert await _product_identity(tenant_id, seller_id, 8_200_010) == identity_before


@pytest.mark.asyncio
async def test_add_to_fulfillment_barcode_conflict_leaves_other_card_untouched(
    async_client: AsyncClient,
) -> None:
    """А12: a card sharing another already-on-FF card's barcode (different
    vendor code) must be skipped, not silently steal that product's identity.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    shared_barcode = f"5{suffix}"[:13].ljust(13, "0")
    owner_card = _wb_card(8_300_010, f"OWNER-{suffix}", "Владелец ШК", [shared_barcode])
    await _seed_snapshot_card(tenant_id, seller_id, owner_card)
    add_owner = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_300_010], "ozon_product_ids": []},
    )
    assert add_owner.status_code == 200, add_owner.text
    assert add_owner.json()["added"][0]["products_added"] == 1
    identity_before = await _product_identity(tenant_id, seller_id, 8_300_010)

    # Different nmID, different vendor code, but the exact same barcode.
    colliding_card = _wb_card(
        8_300_011, f"OTHER-VENDOR-{suffix}", "Чужой ШК", [shared_barcode]
    )
    await _seed_snapshot_card(tenant_id, seller_id, colliding_card)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_300_011], "ozon_product_ids": []},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["added"] == []
    assert body["skipped"] == [
        {
            "marketplace": "wildberries",
            "id": "8300011",
            "vendor_code": f"OTHER-VENDOR-{suffix}",
            "reason": "vendor_code_conflict",
        }
    ]
    assert await _product_count(tenant_id, seller_id, 8_300_011) == 0
    assert await _product_count(tenant_id, seller_id, 8_300_010) == 1
    assert await _product_identity(tenant_id, seller_id, 8_300_010) == identity_before


@pytest.mark.asyncio
async def test_add_to_fulfillment_adopts_a_manual_product_without_nm_id(
    async_client: AsyncClient,
) -> None:
    """А12: the conflict guard only protects products that already belong to a
    different WB card (``wb_nm_id`` set). A manually created product (no
    nmID yet — the same physical item) is adopted exactly like today's import.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, admin_headers = await _register_with_seller(
        async_client, suffix
    )

    barcode = f"6{suffix}"[:13].ljust(13, "0")
    # Manual product creation (Excel/ФФ-created, no nmID) is a fulfillment-only
    # action — done here with the admin token, exactly as an operator would.
    manual = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Ручной товар ФФ",
            "sku_code": f"MANUAL-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
            "wb_barcode": barcode,
        },
    )
    assert manual.status_code == 200, manual.text

    card = _wb_card(8_300_020, f"CARD-{suffix}", "WB-карточка того же товара", [barcode])
    await _seed_snapshot_card(tenant_id, seller_id, card)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_300_020], "ozon_product_ids": []},
    )
    assert res.status_code == 200, res.text
    assert res.json()["skipped"] == []
    assert res.json()["added"][0]["products_added"] == 1

    async with SessionLocal() as session:
        products = (
            (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == uuid.UUID(tenant_id),
                        Product.seller_id == uuid.UUID(seller_id),
                        Product.wb_barcode == barcode,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(products) == 1  # adopted in place, no duplicate row
    assert products[0].wb_nm_id == 8_300_020
    assert products[0].name == "WB-карточка того же товара"


@pytest.mark.asyncio
async def test_add_to_fulfillment_rejects_over_500_ids(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    _tenant_id, _seller_id, seller_headers, _ = await _register_with_seller(
        async_client, suffix
    )

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": list(range(1, 502)), "ozon_product_ids": []},
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "too_many_ids"


@pytest.mark.asyncio
async def test_add_to_fulfillment_requires_seller_role_with_products_permission(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    _tenant_id, _seller_id, _seller_headers, admin_headers = await _register_with_seller(
        async_client, suffix
    )

    admin_res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=admin_headers,
        json={"wb_nm_ids": [1], "ozon_product_ids": []},
    )
    assert admin_res.status_code == 403
    assert admin_res.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_add_to_fulfillment_accepts_ozon_ids_field_and_reports_unknown_ones(
    async_client: AsyncClient,
) -> None:
    """The contract field is accepted even with no matching Ozon cards (WMS-548
    D3 implements real Ozon selection — see test_wms548_ozon_selection.py for
    that; this only guards that the request shape itself never breaks).
    """
    suffix = str(int(time.time() * 1000))
    _tenant_id, _seller_id, seller_headers, _ = await _register_with_seller(
        async_client, suffix
    )

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["123", "456"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["added"] == []
    reasons = {s["id"]: s["reason"] for s in body["skipped"]}
    assert reasons == {"123": "not_found", "456": "not_found"}
