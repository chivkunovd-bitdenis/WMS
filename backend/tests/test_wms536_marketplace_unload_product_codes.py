from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from test_marketplace_unload_and_discrepancy_acts import (  # type: ignore[import-not-found]
    E2E_BARCODE,
)
from test_marketplace_unload_tsd_scan_contract import (  # type: ignore[import-not-found]
    BASE,
    _confirmed_unload_with_open_box,
    _register_headers,
)

from app.db.session import SessionLocal
from app.models.marketplace_unload import (
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadPickAllocation,
)
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller

WB_ADDITIONAL = "4601234567886"
OZON_BARCODE = "OZN-987654"
CYRILLIC_SKU = "ФА_МОД8-4а/083/42"
DUPLICATE_CODE = "DUP-536"
KIZ_WITH_GS = "010460123456789321SERIAL536\x1d91ABCD\x1d92SIGNATURE536"


async def _post_product_scan(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    endpoint: str,
    request_id: str,
    box_id: str,
    location_id: str,
    barcode: str,
    product_id: str | None = None,
) -> Response:
    path = (
        f"{BASE}/{request_id}/pick/scan"
        if endpoint == "pick"
        else f"{BASE}/{request_id}/boxes/{box_id}/scan"
    )
    body: dict[str, object] = {
        "barcode": barcode,
        "storage_location_id": location_id,
    }
    if product_id is not None:
        body["product_id"] = product_id
    return await async_client.post(path, headers=headers, json=body)


async def _product_scope(product_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        assert product.seller_id is not None
        return product.tenant_id, product.seller_id


async def _mutation_counts(request_id: str, box_id: str) -> tuple[int, int]:
    async with SessionLocal() as session:
        picked = int(
            await session.scalar(
                select(func.count())
                .select_from(MarketplaceUnloadPickAllocation)
                .where(
                    MarketplaceUnloadPickAllocation.request_id
                    == uuid.UUID(request_id)
                )
            )
            or 0
        )
        boxed = int(
            await session.scalar(
                select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0)).where(
                    MarketplaceUnloadBoxLine.box_id == uuid.UUID(box_id)
                )
            )
            or 0
        )
        return picked, boxed


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["pick", "box"])
async def test_marketplace_unload_uses_default_product_aliases_without_tsd_hint(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    headers = await _register_headers(async_client, f"wms536-alias-{endpoint}")
    request_id, box_id, product_id, location_id, _ = (
        await _confirmed_unload_with_open_box(
            async_client,
            headers,
            monkeypatch,
            address_storage_enabled=True,
            plan_qty=8,
        )
    )
    tenant_id, seller_id = await _product_scope(product_id)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.sku_code = "AbC-42"
        session.add_all(
            [
                ProductBarcode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=product.id,
                    barcode=WB_ADDITIONAL,
                    source="wb",
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=product.id,
                    marketplace="ozon",
                    external_sku="identity-536",
                    external_offer_id="offer-536",
                    external_barcodes=[OZON_BARCODE],
                ),
            ]
        )
        await session.commit()

    for expected_quantity, code in enumerate(
        (E2E_BARCODE, WB_ADDITIONAL, OZON_BARCODE, "aBc-42"),
        start=1,
    ):
        response = await _post_product_scan(
            async_client,
            headers,
            endpoint=endpoint,
            request_id=request_id,
            box_id=box_id,
            location_id=location_id,
            barcode=code,
        )
        assert response.status_code == 200, response.text
        assert response.json()["kind"] == "product"
        assert response.json()["product_id"] == product_id
        quantity_field = "picked_qty" if endpoint == "pick" else "quantity"
        assert response.json()[quantity_field] == expected_quantity

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.sku_code = CYRILLIC_SKU
        await session.commit()

    cyrillic = await _post_product_scan(
        async_client,
        headers,
        endpoint=endpoint,
        request_id=request_id,
        box_id=box_id,
        location_id=location_id,
        barcode=CYRILLIC_SKU,
    )
    assert cyrillic.status_code == 200, cyrillic.text
    assert cyrillic.json()["kind"] == "product"
    assert cyrillic.json()["product_id"] == product_id

    for code in ("identity-536", KIZ_WITH_GS):
        rejected = await _post_product_scan(
            async_client,
            headers,
            endpoint=endpoint,
            request_id=request_id,
            box_id=box_id,
            location_id=location_id,
            barcode=code,
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"] == "barcode_unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["pick", "box"])
async def test_marketplace_unload_api_returns_409_for_product_code_ambiguity(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    headers = await _register_headers(async_client, f"wms536-ambiguous-{endpoint}")
    request_id, box_id, product_id, location_id, _ = (
        await _confirmed_unload_with_open_box(
            async_client,
            headers,
            monkeypatch,
            address_storage_enabled=True,
            plan_qty=3,
        )
    )
    tenant_id, seller_id = await _product_scope(product_id)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.sku_code = DUPLICATE_CODE
        collision = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="WMS-536 collision",
            sku_code="WMS-536-Q",
        )
        session.add(collision)
        await session.flush()
        session.add(
            ProductMarketplaceLink(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=collision.id,
                marketplace="ozon",
                external_barcodes=[DUPLICATE_CODE],
            )
        )
        await session.commit()

    before = await _mutation_counts(request_id, box_id)
    response = await _post_product_scan(
        async_client,
        headers,
        endpoint=endpoint,
        request_id=request_id,
        box_id=box_id,
        location_id=location_id,
        barcode=DUPLICATE_CODE,
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "barcode_ambiguous"
    assert await _mutation_counts(request_id, box_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["pick", "box"])
async def test_marketplace_unload_rejects_wrong_hint_before_mutation(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    headers = await _register_headers(async_client, f"wms536-hint-{endpoint}")
    request_id, box_id, product_id, location_id, _ = (
        await _confirmed_unload_with_open_box(
            async_client,
            headers,
            monkeypatch,
            address_storage_enabled=True,
            plan_qty=3,
        )
    )
    tenant_id, seller_id = await _product_scope(product_id)
    async with SessionLocal() as session:
        wrong = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Wrong hint",
            sku_code="WRONG-HINT-536",
        )
        session.add(wrong)
        await session.commit()
        wrong_id = str(wrong.id)

    before = await _mutation_counts(request_id, box_id)
    response = await _post_product_scan(
        async_client,
        headers,
        endpoint=endpoint,
        request_id=request_id,
        box_id=box_id,
        location_id=location_id,
        barcode=E2E_BARCODE,
        product_id=wrong_id,
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "barcode_unknown"
    assert await _mutation_counts(request_id, box_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["pick", "box"])
async def test_marketplace_unload_seller_scope_and_location_priority_are_preserved(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    headers = await _register_headers(async_client, f"wms536-scope-{endpoint}")
    request_id, box_id, product_id, location_id, warehouse_id = (
        await _confirmed_unload_with_open_box(
            async_client,
            headers,
            monkeypatch,
            address_storage_enabled=True,
            plan_qty=3,
        )
    )
    tenant_id, _seller_id = await _product_scope(product_id)
    shared_code = "SHARED-SELLER-536"
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.sku_code = shared_code
        other_seller = Seller(tenant_id=tenant_id, name="Other seller WMS-536")
        session.add(other_seller)
        await session.flush()
        session.add(
            Product(
                tenant_id=tenant_id,
                seller_id=other_seller.id,
                name="Foreign seller product",
                sku_code=shared_code,
            )
        )
        await session.commit()

    scoped = await _post_product_scan(
        async_client,
        headers,
        endpoint=endpoint,
        request_id=request_id,
        box_id=box_id,
        location_id=location_id,
        barcode=shared_code,
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["kind"] == "product"
    assert scoped.json()["product_id"] == product_id

    locations = await async_client.get(
        f"/warehouses/{warehouse_id}/locations", headers=headers
    )
    location_barcode = next(
        row["barcode"] for row in locations.json() if row["id"] == location_id
    )
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.sku_code = location_barcode
        await session.commit()

    before = await _mutation_counts(request_id, box_id)
    object_scan = await _post_product_scan(
        async_client,
        headers,
        endpoint=endpoint,
        request_id=request_id,
        box_id=box_id,
        location_id=location_id,
        barcode=location_barcode,
    )
    assert object_scan.status_code == 200, object_scan.text
    assert object_scan.json()["kind"] == "location"
    assert await _mutation_counts(request_id, box_id) == before
