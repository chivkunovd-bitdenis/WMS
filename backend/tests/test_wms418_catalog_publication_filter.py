from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from tests.test_products_ozon_catalog import _register_admin


async def test_publication_filter_combines_flags_scope_search_category_and_pagination(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "wms418")
    other_headers = await _register_admin(async_client, "wms418-other")
    sellers = []
    for auth, name in [(headers, "Первый"), (headers, "Второй"), (other_headers, "Чужой")]:
        response = await async_client.post("/sellers", headers=auth, json={"name": name})
        assert response.status_code == 201, response.text
        sellers.append(uuid.UUID(response.json()["id"]))

    ids = []
    async with SessionLocal() as session:
        seller_rows = [await session.get(Seller, seller_id) for seller_id in sellers]
        assert all(seller_rows)
        # No balances or publishing warehouses: enabled switches must still be findable.
        for i, (wb, ozon, seller_index, category) in enumerate([
            (True, False, 0, "Одежда"),
            (False, True, 0, "Одежда"),
            (True, True, 0, "Обувь"),
            (False, False, 0, "Одежда"),
            (True, None, 1, "Одежда"),
            (False, None, 1, "Обувь"),
            (True, True, 2, "Одежда"),
        ]):
            seller = seller_rows[seller_index]
            assert seller is not None
            product = Product(
                tenant_id=seller.tenant_id, seller_id=seller.id,
                name=f"Товар {i}", sku_code=f"WMS418-{i}", wb_nm_id=41800 + i,
                fbs_stock_sync_enabled=wb, fbs_ozon_stock_sync_enabled=ozon,
            )
            session.add(product)
            await session.flush()
            ids.append(str(product.id))
            session.add(SellerWildberriesImportedCard(
                tenant_id=seller.tenant_id, seller_id=seller.id, nm_id=41800 + i,
                raw_json={"subjectName": category},
            ))
            if i in (1, 2, 3, 4, 6):
                session.add(ProductMarketplaceLink(
                    tenant_id=seller.tenant_id, seller_id=seller.id, product_id=product.id,
                    marketplace="ozon", external_sku=f"OZ418-{i}", is_active=True,
                ))
        await session.commit()

    async def get_page(**params):
        response = await async_client.get(
            "/products/ff-catalog-page", headers=headers, params=params,
        )
        assert response.status_code == 200, response.text
        return response.json()

    for mode, indexes in {
        "wb": [0, 2, 4], "ozon": [1, 2, 4], "both": [2, 4],
        "any": [0, 1, 2, 4], "none": [3, 5],
    }.items():
        page = await get_page(stock_publication=mode)
        assert [row["id"] for row in page["items"]] == [ids[i] for i in indexes]
        assert page["total"] == len(indexes)
        assert page["scope_total"] == 6

    page = await get_page(stock_publication="ozon", limit=1, offset=1)
    assert [row["id"] for row in page["items"]] == [ids[2]]
    assert page["total"] == 3
    combined = await get_page(
        stock_publication="ozon", seller_id=str(sellers[0]), marketplace="ozon",
        category="Одежда", search="OZ418-1",
    )
    assert [row["id"] for row in combined["items"]] == [ids[1]]
    assert combined["total"] == 1
    assert combined["scope_total"] == 3
    assert (await get_page(stock_publication="wb", search="OZ418-1"))["total"] == 0
    assert (await get_page(stock_publication="any", seller_id=str(sellers[2])))["total"] == 0

    # An ordinary refresh must remove a product after its existing switch was disabled.
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(ids[1]))
        assert product is not None
        product.fbs_ozon_stock_sync_enabled = False
        await session.commit()
    assert (await get_page(stock_publication="ozon", search="OZ418-1"))["total"] == 0
    assert (await get_page(stock_publication="none", search="OZ418-1"))["total"] == 1
    assert (await get_page())["total"] == 6


async def test_publication_filter_rejects_unknown_value(async_client: AsyncClient) -> None:
    headers = await _register_admin(async_client, "wms418-invalid")
    response = await async_client.get(
        "/products/ff-catalog-page", headers=headers, params={"stock_publication": "unknown"},
    )
    assert response.status_code == 422
