"""WMS-727 keeps the real box assignment transaction independent of the new draft button."""

import asyncio

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBoxItem
from tests.fbs_supply_card_fixture import boxes, seed, snapshot


async def assignment(client, headers, supply, box, ids, marketplace):
    body = (
        {"order_ids": ids} if marketplace == "wb" else {"order_ids": [], "order_product_ids": ids}
    )
    return await client.post(
        f"/operations/fbs-supplies/{supply}/boxes/{box}/orders", headers=headers, json=body
    )


async def data(client, marketplace):
    headers, tenant, supply, orders = await seed(client, marketplace)
    box_ids = await boxes(tenant, supply)
    async with SessionLocal() as session:
        positions = []
        if marketplace == "ozon":
            order = await session.get(FbsOrder, orders[0])
            session.add(
                FbsOrderProduct(
                    order_id=order.id,
                    product_id=order.product_id,
                    quantity=2,
                    position_index=1,
                    name="Second position",
                )
            )
            await session.commit()
            positions = list(
                (
                    await session.scalars(
                        select(FbsOrderProduct)
                        .where(FbsOrderProduct.order_id == order.id)
                        .order_by(FbsOrderProduct.position_index)
                    )
                ).all()
            )
    ids = [str(i) for i in orders] if marketplace == "wb" else [str(p.id) for p in positions]
    return headers, supply, box_ids, ids


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c2_c4_assignment_preserves_order_quantity_stock_reserve_codes_and_packing(
    async_client, marketplace
):
    headers, supply, box_ids, ids = await data(async_client, marketplace)
    before = await snapshot(exclude=("fbs_packing_box_items", "audit_logs"))
    response = await assignment(async_client, headers, supply, box_ids[0], ids[:1], marketplace)
    assert response.status_code == 200, response.text
    assert await snapshot(exclude=("fbs_packing_box_items", "audit_logs")) == before
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply}/workspace", headers=headers
    )
    assert response.status_code == 200, response.text
    target = next(b for b in response.json()["boxes"] if b["id"] == str(box_ids[0]))
    assert (
        target["assigned_order_ids" if marketplace == "wb" else "assigned_order_product_ids"]
        == ids[:1]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c7_repeated_same_box_assignment_has_one_membership(async_client, marketplace):
    headers, supply, box_ids, ids = await data(async_client, marketplace)
    for _ in range(2):
        response = await assignment(async_client, headers, supply, box_ids[0], ids[:1], marketplace)
        assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        items = list((await session.scalars(select(FbsPackingBoxItem))).all())
        assert len(items) == 1 and items[0].box_id == box_ids[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c7_conflicting_batch_is_atomic(async_client, marketplace):
    headers, supply, box_ids, ids = await data(async_client, marketplace)
    response = await assignment(async_client, headers, supply, box_ids[0], ids[:1], marketplace)
    assert response.status_code == 200, response.text
    response = await assignment(async_client, headers, supply, box_ids[1], ids, marketplace)
    assert response.status_code == 409, response.text
    async with SessionLocal() as session:
        items = list((await session.scalars(select(FbsPackingBoxItem))).all())
        assert len(items) == 1 and items[0].box_id == box_ids[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c7_simultaneous_boxes_have_one_winner_without_partial_items(
    async_client, marketplace
):
    headers, supply, box_ids, ids = await data(async_client, marketplace)
    responses = await asyncio.gather(
        *(assignment(async_client, headers, supply, b, ids[:1], marketplace) for b in box_ids),
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) for r in responses), [str(r) for r in responses]
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    async with SessionLocal() as session:
        items = list((await session.scalars(select(FbsPackingBoxItem))).all())
        assert len(items) == 1 and items[0].box_id in box_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c8_readback_after_lost_reply_then_repeat_does_not_duplicate(
    async_client, marketplace
):
    headers, supply, box_ids, ids = await data(async_client, marketplace)
    # Discard the first HTTP body after commit, then recover by an independent read.
    committed = await assignment(async_client, headers, supply, box_ids[0], ids[:1], marketplace)
    assert committed.status_code == 200, committed.text
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply}/workspace", headers=headers
    )
    target = next(b for b in response.json()["boxes"] if b["id"] == str(box_ids[0]))
    assert (
        target["assigned_order_ids" if marketplace == "wb" else "assigned_order_product_ids"]
        == ids[:1]
    )
    repeated = await assignment(async_client, headers, supply, box_ids[0], ids[:1], marketplace)
    assert repeated.status_code == 200, repeated.text
    async with SessionLocal() as session:
        assert len(list((await session.scalars(select(FbsPackingBoxItem))).all())) == 1
