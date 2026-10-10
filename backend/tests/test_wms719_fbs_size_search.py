"""WMS-719 C4: visible column replacement must retain SKU search and data."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock


async def _snapshot(product_id, order_id):
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        order = await session.get(FbsOrder, order_id)
        assert product and order
        balances = (
            await session.scalars(
                select(InventoryBalance).where(InventoryBalance.product_id == product_id)
            )
        ).all()
        movements = (
            await session.scalars(
                select(InventoryMovement.id).where(InventoryMovement.product_id == product_id)
            )
        ).all()
        return (
            product.sku_code,
            order.product_id,
            order.status,
            order.reserve_status,
            sorted(
                (str(b.id), b.quantity, b.quantity_unpacked, b.quantity_packed) for b in balances
            ),
            sorted(map(str, movements)),
        )


@pytest.mark.asyncio
async def test_c4_sku_search_preserves_identity_size_inventory_and_reserve(
    async_client: AsyncClient,
):
    headers, seller, _, product_id, _, ids = await _setup_ff_admin_with_stock(async_client)
    before = await _snapshot(product_id, ids[0])
    sku = before[0]
    for _ in range(2):
        response = await async_client.get(
            "/operations/fbs-orders/worklist",
            headers=headers,
            params={"status_group": "new", "seller_id": str(seller), "search": sku},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 1
        assert [item["id"] for item in body["items"]] == [str(ids[0])]
        assert body["items"][0]["product"]["sku"] == sku
        assert body["items"][0]["product"]["size"] == "L"
    assert await _snapshot(product_id, ids[0]) == before
