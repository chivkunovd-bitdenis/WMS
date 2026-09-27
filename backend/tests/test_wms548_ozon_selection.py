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


@pytest.mark.asyncio
async def test_f2_ozon_cards_sharing_an_offer_id_do_not_steal_each_others_link(
    async_client: AsyncClient,
) -> None:
    """WMS-548 review-astra-1 F2 (blocker).

    ``_link_matches`` used to treat "any of offer_id/sku/id matches" as
    "this is the same card, safe to refresh in place". A live Ozon cabinet
    can carry two genuinely different listings sharing the same offer_id
    (the schema does not forbid it). Adding the first card created its link
    correctly; adding the second one then found *that* link via the shared
    offer_id and silently moved it onto the second card's own
    external_product_id — the first card's claim vanished from the
    fulfillment catalog with no error at all (reviewer's exact reproduction:
    "В БД остаётся одна привязка (external_product_id=802,
    external_sku=1801, ...)" — a hybrid identity belonging to neither card).

    Both cards computing the same sku_code from that shared offer_id
    (``card_product_sku_code`` — untouched, out of F2's scope) means the
    second card genuinely cannot become a *second* product here; the fixed,
    honest outcome is that it is reported ``not_added`` instead of silently
    stealing the first card's link. What F2 actually guards is the first
    card: it must come out of this completely untouched, not go missing.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    card_first = _ozon_card("9600801", "SAME-OFFER", "5600801", "Карточка 801")
    card_second = _ozon_card("9600802", "SAME-OFFER", "5600802", "Карточка 802")
    await _seed_ozon_card(tenant_id, seller_id, card_first)
    await _seed_ozon_card(tenant_id, seller_id, card_second)

    add_first = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9600801"]},
    )
    assert add_first.status_code == 200, add_first.text
    assert add_first.json()["added"][0]["products_added"] == 1
    link_before = await _ozon_link_for(tenant_id, seller_id, "9600801")
    assert link_before is not None
    product_id_before = link_before.product_id

    add_second = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9600802"]},
    )
    assert add_second.status_code == 200, add_second.text
    # The second card is honestly rejected (sku collision on the shared
    # offer_id) — it must never silently take over the first card's link.
    assert add_second.json()["added"] == []
    assert add_second.json()["skipped"] == [
        {
            "marketplace": "ozon",
            "id": "9600802",
            "vendor_code": "SAME-OFFER",
            "reason": "not_added",
        }
    ]

    # The first card's claim is completely intact: same product, same
    # external_product_id — nothing about it changed underneath it.
    assert await _product_count(tenant_id, seller_id) == 1
    link_after = await _ozon_link_for(tenant_id, seller_id, "9600801")
    assert link_after is not None
    assert link_after.product_id == product_id_before
    assert link_after.external_product_id == "9600801"
    assert link_after.external_sku == "5600801"

    page = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"marketplace": "ozon", "on_fulfillment": "no"},
    )
    # "9600801" (successfully linked) did not reappear as unmatched; the
    # rejected "9600802" is still there, still pickable by the seller later.
    not_on_ff_ids = {item["ozon_product_id"] for item in page.json()["items"]}
    assert not_on_ff_ids == {"9600802"}


@pytest.mark.asyncio
async def test_f3_one_failing_ozon_card_does_not_crash_the_rest_of_the_batch(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WMS-548 review-astra-1 F3 (существенное), ветка Ozon.

    The shared match context's indexed links are ORM objects too: after one
    card's processing fails and rolls back, those cached links are expired
    the same way the WB snapshot rows were. The next card's lookup used to
    read the stale context and crash the whole request instead of just
    skipping the one bad card — the context must be rebuilt after a rollback.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    failing_card = _ozon_card("9650001", "FAIL-OFFER", "5650001", "Падает")
    ok_card = _ozon_card("9650002", "OK-OFFER", "5650002", "Работает")
    await _seed_ozon_card(tenant_id, seller_id, failing_card)
    await _seed_ozon_card(tenant_id, seller_id, ok_card)

    import app.services.seller_fulfillment_catalog_service as catalog_svc
    from app.services.ozon_product_import_service import (
        process_one_ozon_card as original_process,
    )

    async def flaky_process(
        session: Any, tenant_id_arg: Any, seller_id_arg: Any, raw: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if raw.get("id") == "9650001":
            raise RuntimeError("WMS-548 F3 simulated Ozon failure")
        return await original_process(session, tenant_id_arg, seller_id_arg, raw, *args, **kwargs)

    monkeypatch.setattr(catalog_svc, "process_one_ozon_card", flaky_process)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9650001", "9650002"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert {s["id"]: s["reason"] for s in body["skipped"]} == {"9650001": "internal_error"}
    assert {a["id"] for a in body["added"]} == {"9650002"}


@pytest.mark.asyncio
async def test_f5_wb_twin_backfill_reads_only_matching_ozon_candidates(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WMS-548 review-astra-1 F5 (существенное).

    Adding one WB card used to read every not-yet-linked Ozon snapshot card
    of the seller (full raw_json, all of them) looking for a twin. A seller
    with many Ozon cards paid for scanning all of them on every single WB
    card added, however unrelated. The backfill must look only at Ozon
    cards whose own offer_id/sku/barcode could actually match the
    just-added WB product.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    for i in range(200):
        await _seed_ozon_card(
            tenant_id,
            seller_id,
            _ozon_card(f"97{i:06d}", f"UNRELATED-{suffix}-{i}", f"58{i:06d}", f"Товар {i}"),
        )
    twin = _ozon_card("9700999", "OZTWIN-F5", "5700999", "Твин", barcodes=["4800000000999"])
    await _seed_ozon_card(tenant_id, seller_id, twin)

    wb_card = _wb_card(8_800_001, f"TWIN-F5-{suffix}", "Твин WB", "4800000000999")
    await _seed_wb_card(tenant_id, seller_id, wb_card)

    import app.services.seller_fulfillment_catalog_service as catalog_svc
    from app.services.ozon_product_import_service import (
        process_one_ozon_card as original_process,
    )

    seen_ids: list[str] = []

    async def counting_process(
        session: Any, tenant_id_arg: Any, seller_id_arg: Any, raw: Any, *args: Any, **kwargs: Any
    ) -> Any:
        seen_ids.append(raw.get("id"))
        return await original_process(
            session, tenant_id_arg, seller_id_arg, raw, *args, **kwargs
        )

    monkeypatch.setattr(catalog_svc, "process_one_ozon_card", counting_process)

    res = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [8_800_001], "ozon_product_ids": []},
    )
    assert res.status_code == 200, res.text

    # Only the one real candidate was ever looked at — not all 201 cards.
    assert seen_ids == ["9700999"]

    link = await _ozon_link_for(tenant_id, seller_id, "9700999")
    assert link is not None


@pytest.mark.asyncio
async def test_f6_added_ozon_product_is_still_findable_by_its_own_barcode(
    async_client: AsyncClient,
) -> None:
    """WMS-548 review-astra-1 F6 (существенное).

    Before selection, the snapshot's raw_json carries the card's barcode and
    search finds it there. After the card becomes a product, search switched
    to the product/link fields — external_sku and external_offer_id — but
    never checked external_barcodes, so the very same product stopped being
    findable by its own barcode right after being added.
    """
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id, seller_headers, _ = await _register_with_seller(async_client, suffix)

    card = _ozon_card(
        "9600900", "SEARCH-OFFER", "5600900", "Поиск", barcodes=["SPECIAL-BAR-900"]
    )
    await _seed_ozon_card(tenant_id, seller_id, card)

    before = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"search": "SPECIAL-BAR-900"},
    )
    assert before.status_code == 200, before.text
    assert before.json()["total"] == 1
    assert before.json()["items"][0]["on_fulfillment"] is False

    add = await async_client.post(
        "/seller-catalog/add-to-fulfillment",
        headers=seller_headers,
        json={"wb_nm_ids": [], "ozon_product_ids": ["9600900"]},
    )
    assert add.status_code == 200, add.text

    after = await async_client.get(
        "/seller-catalog/page",
        headers=seller_headers,
        params={"search": "SPECIAL-BAR-900"},
    )
    assert after.status_code == 200, after.text
    assert after.json()["total"] == 1
    assert after.json()["items"][0]["on_fulfillment"] is True
