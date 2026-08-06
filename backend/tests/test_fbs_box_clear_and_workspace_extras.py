"""Point backend additions for the new FBS operator UI:

- box clear (unassign all orders from a physical box, without closing/reopening)
- packaging_instructions surfaced on the workspace product object
- marking_pool: Честный знак (Chestny Znak / "honest sign") deficit for the supply

Style follows tests/test_fbs_packing_box.py.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    MARKING_KIND_SGTIN,
    META_STATUS_PENDING,
    PACK_STATUS_PACKED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
from app.models.marking_code import STATUS_AVAILABLE, STATUS_PRINTED, MarkingCode
from app.models.product import Product
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _packed_supply(
    async_client: AsyncClient,
    *,
    order_specs: list[tuple[int, timedelta]] | None = None,
) -> tuple[dict[str, str], uuid.UUID, list[uuid.UUID], uuid.UUID, uuid.UUID]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"box-clear-{suffix[-8:]}",
        barcode=f"2300{suffix[-9:]}",
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=order_specs or [(1, timedelta(hours=3)), (2, timedelta(hours=4))],
        barcode=f"2300{suffix[-9:]}",
    )
    async with SessionLocal() as session:
        result = await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
        for order in result.scalars().all():
            order.pack_status = PACK_STATUS_PACKED
        await session.commit()
    return headers, supply_id, order_ids, product_id, tenant_id


@pytest.mark.asyncio
async def test_clear_box_returns_orders_to_unassigned(async_client: AsyncClient) -> None:
    headers, supply_id, order_ids, _product_id, _tenant_id = await _packed_supply(async_client)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "clear-boxes-create-1"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0]), str(order_ids[1])]},
    )
    assert assigned.status_code == 200, assigned.text
    assert set(assigned.json()["boxes"][0]["assigned_order_ids"]) == {
        str(order_ids[0]),
        str(order_ids[1]),
    }

    cleared = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/clear",
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    boxes = cleared.json()["boxes"]
    assert len(boxes) == 1
    assert boxes[0]["assigned_order_ids"] == []

    # The box itself is not deleted or closed; it's just empty and reusable.
    reassigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["boxes"][0]["assigned_order_ids"] == [str(order_ids[0])]


@pytest.mark.asyncio
async def test_clear_box_on_empty_box_is_idempotent(async_client: AsyncClient) -> None:
    headers, supply_id, _order_ids, _product_id, _tenant_id = await _packed_supply(async_client)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "clear-boxes-empty-1"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]

    first_clear = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/clear",
        headers=headers,
    )
    assert first_clear.status_code == 200, first_clear.text
    assert first_clear.json()["boxes"][0]["assigned_order_ids"] == []

    second_clear = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/clear",
        headers=headers,
    )
    assert second_clear.status_code == 200, second_clear.text
    assert second_clear.json()["boxes"][0]["assigned_order_ids"] == []


@pytest.mark.asyncio
async def test_clear_box_after_supply_delivered_is_rejected(async_client: AsyncClient) -> None:
    headers, supply_id, order_ids, _product_id, tenant_id = await _packed_supply(async_client)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "clear-boxes-delivered-1"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
        await session.commit()

    rejected = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/clear",
        headers=headers,
    )
    assert rejected.status_code == 409, rejected.text
    detail = rejected.json()["detail"]
    assert detail["code"] == "supply_already_delivered"
    assert detail["retryable"] is False
    assert detail["message"] == (
        "Поставка уже передана в WB, изменение коробов запрещено."
    )


@pytest.mark.asyncio
async def test_workspace_exposes_packaging_instructions(async_client: AsyncClient) -> None:
    headers, supply_id, _order_ids, product_id, _tenant_id = await _packed_supply(async_client)

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.packaging_instructions = "Заворачивать в пупырку, скотч крест-накрест."
        await session.commit()

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    orders = workspace.json()["orders"]
    assert len(orders) == 2
    for order in orders:
        product_out = order["product"]
        assert product_out["packaging_instructions"] == (
            "Заворачивать в пупырку, скотч крест-накрест."
        )
        assert product_out["has_packaging_instructions"] is True


@pytest.mark.asyncio
async def test_workspace_exposes_packaging_instructions_absent(async_client: AsyncClient) -> None:
    headers, supply_id, _order_ids, _product_id, _tenant_id = await _packed_supply(async_client)

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    for order in workspace.json()["orders"]:
        product_out = order["product"]
        assert product_out["packaging_instructions"] is None
        assert product_out["has_packaging_instructions"] is False


@pytest.mark.asyncio
async def test_workspace_marking_pool_reports_shortage(async_client: AsyncClient) -> None:
    # order_specs deadlines: order 0 is due earliest, so it gets priority for
    # the single available Chestny Znak code; order 1 becomes the shortfall.
    headers, supply_id, order_ids, product_id, tenant_id = await _packed_supply(
        async_client,
        order_specs=[(1, timedelta(hours=3)), (2, timedelta(hours=5))],
    )

    async with SessionLocal() as session:
        result = await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
        seller_id: uuid.UUID | None = None
        for order in result.scalars().all():
            order.required_meta_json = ["sgtin"]
            seller_id = order.seller_id
        assert seller_id is not None
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                cis_code=f"010000000000012321{uuid.uuid4().hex}",
                gtin="00000000000001",
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    marking_pool = workspace.json()["marking_pool"]
    assert marking_pool["required"] == 2
    assert marking_pool["available"] == 1
    assert marking_pool["shortage"] == 1
    assert marking_pool["orders_without_code"] == [str(order_ids[1])]


@pytest.mark.asyncio
async def test_workspace_marking_pool_empty_when_nothing_needs_marking(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _order_ids, _product_id, _tenant_id = await _packed_supply(async_client)

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    marking_pool = workspace.json()["marking_pool"]
    assert marking_pool == {
        "required": 0,
        "available": 0,
        "shortage": 0,
        "orders_without_code": [],
    }


@pytest.mark.asyncio
async def test_order_print_tape_assigns_codes_to_requested_orders(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, order_ids, product_id, tenant_id = await _packed_supply(
        async_client,
        order_specs=[(1, timedelta(hours=3)), (2, timedelta(hours=4))],
    )

    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work",
        headers=headers,
    )
    assert started.status_code == 200, started.text

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.requires_honest_sign = True
        result = await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
        seller_id: uuid.UUID | None = None
        for order in result.scalars().all():
            order.required_meta_json = [MARKING_KIND_SGTIN]
            seller_id = order.seller_id
        assert seller_id is not None
        for idx in range(2):
            session.add(
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=product_id,
                    cis_code=f"010000000000012321{idx:02d}{uuid.uuid4().hex}",
                    gtin="00000000000001",
                    status=STATUS_AVAILABLE,
                )
            )
        await session.commit()

    printed = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_id) for order_id in order_ids],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
            "allow_partial": False,
            "include_order_qr": False,
            "reprint": False,
        },
    )
    assert printed.status_code == 200, printed.text
    body = printed.json()
    assert body["shortage"] == 0
    assert body["requested"] == 2
    assert body["ready"] == 2
    assert [row["order_id"] for row in body["orders"]] == [str(order_id) for order_id in order_ids]
    assert all(row["requires_honest_sign"] is True for row in body["orders"])
    assert all(len(row["printed_codes"]) == 1 for row in body["orders"])

    async with SessionLocal() as session:
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(
                        FbsOrderMarking.order_id.in_(order_ids),
                        FbsOrderMarking.kind == MARKING_KIND_SGTIN,
                    )
                )
            ).scalars()
        )
        assert len(markings) == 2
        assert {marking.order_id for marking in markings} == set(order_ids)
        assert all(marking.meta_status == META_STATUS_PENDING for marking in markings)
        assert all(marking.marking_code_id is not None for marking in markings)
        codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(
                        MarkingCode.id.in_([marking.marking_code_id for marking in markings])
                    )
                )
            ).scalars()
        )
        assert len(codes) == 2
        assert all(code.status == STATUS_PRINTED for code in codes)
