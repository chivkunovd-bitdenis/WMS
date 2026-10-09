"""Existing Ozon marking facts must reach the selection UI; unknown is not plain."""

import pytest

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.product import Product
from tests.fbs_supply_card_fixture import seed


@pytest.mark.asyncio
async def test_c3_workspace_projects_known_empty_versus_unknown_requirements(async_client):
    headers, _tenant, supply, ids = await seed(async_client, "ozon")
    async with SessionLocal() as session:
        for index, oid in enumerate(ids):
            order = await session.get(FbsOrder, oid)
            order.required_meta_json = []
            order.meta_details_json = {"ozon_requirements": {}} if index == 0 else {}
        await session.commit()
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply}/workspace", headers=headers
    )
    assert response.status_code == 200, response.text
    orders = {o["id"]: o for o in response.json()["orders"]}
    assert orders[str(ids[0])]["metadata"].get("requirements_known") is True
    assert orders[str(ids[1])]["metadata"].get("requirements_known") is False


@pytest.mark.asyncio
async def test_c3_workspace_projects_marked_second_position(async_client):
    headers, tenant, supply, ids = await seed(async_client, "ozon", count=1)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, ids[0])
        first = await session.get(Product, order.product_id)
        first.requires_honest_sign = False
        marked = Product(
            tenant_id=tenant,
            seller_id=order.seller_id,
            name="Маркируемая вторая позиция",
            sku_code="marked-second",
            requires_honest_sign=True,
        )
        session.add(marked)
        await session.flush()
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=marked.id,
                quantity=2,
                position_index=1,
                name=marked.name,
            )
        )
        order.meta_details_json = {"ozon_requirements": {}}
        order.required_meta_json = []
        await session.commit()
        product_id = marked.id
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply}/workspace", headers=headers
    )
    assert response.status_code == 200, response.text
    positions = response.json()["orders"][0]["positions"]
    assert len(positions) == 2
    second = next(p for p in positions if p["product_id"] == str(product_id))
    assert second.get("requires_honest_sign") is True
