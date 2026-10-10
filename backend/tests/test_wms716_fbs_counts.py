"""WMS-716: real HTTP/SQLite count contract, before product implementation.

The read transport chosen for this test contract is GET fbs-orders/counts:
tabs contains new/active/delivery; sellers maps accessible seller UUIDs to the
current status_group count. These are derived counts, never a stored ledger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.services.tokens import create_access_token
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock

COUNTS = "/operations/fbs-orders/counts"


async def _read(client, headers, **params):
    response = await client.get(COUNTS, headers=headers, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["tabs"]) == {"new", "active", "delivery"}
    assert all(isinstance(value, int) and value >= 0 for value in body["tabs"].values())
    return body


async def _supply(session, orders, *, status="assembling", marketplace="wb", name="Count supply"):
    first = orders[0]
    supply = FbsSupply(
        tenant_id=first.tenant_id,
        seller_id=first.seller_id,
        warehouse_id=first.warehouse_id,
        marketplace=marketplace,
        wb_supply_id=f"WB-GI-{uuid.uuid4()}",
        name=name,
        status=status,
        delivery_type="warehouse_sc",
    )
    session.add(supply)
    await session.flush()
    for item in orders:
        item.supply_id = supply.id
        item.wb_supply_id = supply.wb_supply_id
        item.status = "in_delivery" if status == "in_delivery" else "assembling"
        item.marketplace = marketplace
    return supply


async def _stock_snapshot(product_id):
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product
        balances = (
            (
                await session.execute(
                    select(InventoryBalance).where(InventoryBalance.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        movements = (
            (
                await session.execute(
                    select(InventoryMovement).where(InventoryMovement.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        orders = (
            (await session.execute(select(FbsOrder).where(FbsOrder.tenant_id == product.tenant_id)))
            .scalars()
            .all()
        )
        return (
            sorted(
                (str(b.id), b.quantity, b.quantity_unpacked, b.quantity_packed) for b in balances
            ),
            sorted(str(m.id) for m in movements),
            sorted(
                (str(o.id), o.status, o.reserve_status, str(o.product_id), str(o.supply_id))
                for o in orders
            ),
        )


@pytest.mark.asyncio
async def test_c1_counts_orders_in_three_tabs_not_supply_rows(async_client: AsyncClient):
    headers, seller, _, _, _, ids = await _setup_ff_admin_with_stock(async_client, order_count=14)
    async with SessionLocal() as session:
        orders = [await session.get(FbsOrder, identifier) for identifier in ids]
        await _supply(session, orders[3:5])
        await _supply(session, orders[5:9])
        await _supply(session, orders[9:14], status="in_delivery")
        await session.commit()
    for group, current in (("new", 3), ("active", 6), ("delivery", 5)):
        for _ in range(2):
            body = await _read(async_client, headers, status_group=group)
            assert body["tabs"] == {"new": 3, "active": 6, "delivery": 5}
            assert body["sellers"][str(seller)] == current


@pytest.mark.asyncio
async def test_c2_full_volume_unique_ozon_positions_and_assembly_members(async_client: AsyncClient):
    # 501 new + 501 local supplies + 1 external order; the posting has 2
    # positions/12 units, but remains one order. The task links an existing supply.
    headers, seller, _, product, _, ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1003
    )
    async with SessionLocal() as session:
        orders = [await session.get(FbsOrder, identifier) for identifier in ids]
        linked = None
        for item in orders[501:1002]:
            supply = await _supply(session, [item])
            linked = linked or supply
        posting = orders[501]
        posting.marketplace = "ozon"
        linked.marketplace = "ozon"
        posting.external_order_id = "WMS716-MULTI-1"
        for index in range(2):
            session.add(
                FbsOrderProduct(
                    order_id=posting.id,
                    product_id=product,
                    position_index=index,
                    quantity=6,
                    ozon_sku=716000 + index,
                    name=f"Position {index}",
                )
            )
        external = orders[-1]
        external.status = "external_processing"
        external.wb_supply_id = "WB-GI-EXTERNAL-716"
        task = FbsAssemblyTask(
            tenant_id=external.tenant_id, number="716", idempotency_key="716-count-task"
        )
        session.add(task)
        await session.flush()
        session.add(FbsAssemblyTaskSupply(task_id=task.id, supply_id=linked.id))
        await session.commit()
    first = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"status_group": "new", "limit": 500},
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 500
    assert first.json()["next_cursor"]
    supplies = await async_client.get(
        "/operations/fbs-supplies/worklist",
        headers=headers,
        params={"status_group": "active", "limit": 500},
    )
    assert supplies.status_code == 200, supplies.text
    assert len(supplies.json()["items"]) == 500
    body = await _read(async_client, headers, status_group="active")
    assert body["tabs"] == {"new": 501, "active": 502, "delivery": 0}
    assert body["sellers"][str(seller)] == 502


@pytest.mark.asyncio
async def test_c3_filters_use_full_target_list_and_whole_matched_supply(async_client: AsyncClient):
    headers, seller, warehouse, _, _, ids = await _setup_ff_admin_with_stock(
        async_client, order_count=6
    )
    async with SessionLocal() as session:
        orders = [await session.get(FbsOrder, identifier) for identifier in ids]
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=orders[0].tenant_id,
            seller_id=seller,
            wms_warehouse_id=warehouse,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID + 1,
        )
        orders[1].wb_warehouse_id = DEFAULT_WB_WAREHOUSE_ID + 1
        orders[2].marketplace = "ozon"
        orders[2].external_order_id = "716-ozon-new"
        await _supply(session, orders[3:5], name="Find whole supply")
        await _supply(session, orders[5:], marketplace="ozon", status="in_delivery")
        await session.commit()
    cases = [
        ({"seller_id": str(seller)}, {"new": 3, "active": 2, "delivery": 1}),
        ({"marketplace": "wb"}, {"new": 2, "active": 2, "delivery": 0}),
        ({"marketplace": "ozon"}, {"new": 1, "active": 0, "delivery": 1}),
        (
            {"marketplace": "wb", "wb_warehouse_id": DEFAULT_WB_WAREHOUSE_ID},
            {"new": 1, "active": 2, "delivery": 0},
        ),
        # An inactive warehouse filter cannot narrow the supply context.
        (
            {"status_group": "active", "wb_warehouse_id": 999999},
            {"new": 3, "active": 2, "delivery": 1},
        ),
        # Search by one member includes every order of the matching supply.
        (
            {"status_group": "active", "search": "800003", "wb_warehouse_id": 999999},
            {"new": 0, "active": 2, "delivery": 0},
        ),
        ({"search": "Find whole supply"}, {"new": 0, "active": 2, "delivery": 0}),
        ({"search": "FBS product"}, {"new": 3, "active": 2, "delivery": 1}),
    ]
    for filters, expected in cases:
        body = await _read(async_client, headers, **{"status_group": "new", **filters})
        assert body["tabs"] == expected, filters


@pytest.mark.asyncio
async def test_c4_seller_counts_replace_selected_seller_and_include_zero(async_client: AsyncClient):
    headers, seller, warehouse, _, _, ids = await _setup_ff_admin_with_stock(
        async_client, order_count=4
    )
    second = await async_client.post("/sellers", headers=headers, json={"name": "Seller B 716"})
    zero = await async_client.post("/sellers", headers=headers, json={"name": "Seller zero 716"})
    assert second.status_code in (200, 201), second.text
    assert zero.status_code in (200, 201), zero.text
    second_id = uuid.UUID(second.json()["id"])
    second_product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Seller B product",
            "sku_code": f"B-716-{uuid.uuid4()}",
            "seller_id": str(second_id),
        },
    )
    assert second_product.status_code in (200, 201), second_product.text
    async with SessionLocal() as session:
        orders = [await session.get(FbsOrder, identifier) for identifier in ids]
        await seed_fbs_warehouse_binding(
            session, tenant_id=orders[0].tenant_id, seller_id=second_id, wms_warehouse_id=warehouse
        )
        orders[1].seller_id = second_id
        orders[2].seller_id = second_id
        orders[1].product_id = orders[2].product_id = uuid.UUID(second_product.json()["id"])
        orders[2].external_order_id = "716-B-ozon-active"
        await _supply(session, orders[2:3], marketplace="ozon")
        await _supply(session, orders[3:4], status="in_delivery")
        await session.commit()
    for group, expected in (
        ("new", (1, 1)),
        ("active", (0, 1)),
        ("delivery", (1, 0)),
        ("cancelled", (0, 0)),
    ):
        body = await _read(async_client, headers, status_group=group, seller_id=str(seller))
        assert body["tabs"] == {"new": 1, "active": 0, "delivery": 1}
        assert body["sellers"] == {
            str(seller): expected[0],
            str(second_id): expected[1],
            zero.json()["id"]: 0,
        }
    second_context = await _read(
        async_client, headers, status_group="active", seller_id=str(second_id)
    )
    assert second_context["tabs"] == {"new": 1, "active": 1, "delivery": 0}
    assert second_context["sellers"][str(seller)] == 0
    for marketplace, expected in (("wb", 0), ("ozon", 1)):
        filtered = await _read(
            async_client,
            headers,
            status_group="active",
            seller_id=str(seller),
            marketplace=marketplace,
        )
        assert filtered["sellers"][str(second_id)] == expected
        assert filtered["tabs"]["active"] == 0


@pytest.mark.asyncio
async def test_c5_tenant_and_employee_seller_scope_cannot_be_widened(async_client: AsyncClient):
    headers, seller, _, _, _, ids = await _setup_ff_admin_with_stock(async_client, order_count=2)
    foreign_headers, foreign_seller, *_ = await _setup_ff_admin_with_stock(
        async_client, order_count=9
    )
    async with SessionLocal() as session:
        item = await session.get(FbsOrder, ids[0])
        user = User(
            tenant_id=item.tenant_id,
            seller_id=seller,
            email=f"716-{uuid.uuid4()}@example.com",
            password_hash="unused",
            role="fulfillment_staff",
        )
        session.add(user)
        await session.flush()
        session.add(FfStaffPermissions(user_id=user.id, can_packaging=True))
        token = create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role, seller_id=seller
        )
        await session.commit()
    employee = {"Authorization": f"Bearer {token}"}
    # Validate employee setup on the existing read before the new count read.
    # This keeps a permissions/fixture failure distinct from the expected 404.
    for params in ({}, {"seller_id": str(foreign_seller)}):
        listed = await async_client.get(
            "/operations/fbs-orders/worklist",
            headers=employee,
            params={"status_group": "new", **params},
        )
        assert listed.status_code == 200, listed.text
        assert {row["id"] for row in listed.json()["items"]} == set(map(str, ids))
    body = await _read(async_client, foreign_headers, status_group="new")
    assert body["tabs"]["new"] == 9
    assert str(seller) not in body["sellers"]
    for params in ({}, {"seller_id": str(foreign_seller)}):
        body = await _read(async_client, employee, status_group="new", **params)
        assert body["tabs"] == {"new": 2, "active": 0, "delivery": 0}
        assert body["sellers"] == {str(seller): 2}
        listed = await async_client.get(
            "/operations/fbs-orders/worklist",
            headers=employee,
            params={"status_group": "new", **params},
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["items"]) == body["tabs"]["new"]
    forbidden = await async_client.get(
        COUNTS, headers=headers, params={"seller_id": str(foreign_seller)}
    )
    assert forbidden.status_code == 404
    assert str(foreign_seller) not in forbidden.text


@pytest.mark.asyncio
async def test_c7_recounts_changed_data_without_writes_to_orders_stock_or_reserve(
    async_client: AsyncClient,
):
    headers, _, _, product, _, ids = await _setup_ff_admin_with_stock(async_client, order_count=3)
    before = await _stock_snapshot(product)
    for _ in range(2):
        body = await _read(async_client, headers, status_group="new")
        assert body["tabs"]["new"] == 3
    assert await _stock_snapshot(product) == before
    async with SessionLocal() as session:
        item = await session.get(FbsOrder, ids[0])
        item.status = "cancelled"
        await session.commit()
    changed = await _stock_snapshot(product)
    body = await _read(async_client, headers, status_group="new")
    assert body["tabs"]["new"] == 2
    assert await _stock_snapshot(product) == changed


@pytest.mark.asyncio
async def test_c8_shipped_count_uses_derived_ozon_supply_membership(async_client: AsyncClient):
    headers, seller, _, _, _, ids = await _setup_ff_admin_with_stock(async_client, order_count=2)
    async with SessionLocal() as session:
        orders = [await session.get(FbsOrder, identifier) for identifier in ids]
        supply = await _supply(session, orders, status="done", marketplace="ozon")
        # WMS-721 derives the displayed stage from posting facts even when the
        # stored supply status is already done.
        supply.delivered_at = datetime.now(UTC)
        for order in orders:
            order.status = "done"
            order.wb_status = "awaiting_packaging"
            order.supplier_status = "new"
            order.meta_details_json = {}
        await session.commit()

    listed = await async_client.get(
        "/operations/fbs-supplies/worklist",
        headers=headers,
        params={"status_group": "shipped", "marketplace": "ozon"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()["items"]
    assert len(rows) == 1
    assert rows[0]["status"] == "shipped"

    response = await async_client.get(
        COUNTS,
        headers=headers,
        params={"status_group": "shipped", "marketplace": "ozon"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tabs"] == {"new": 0, "active": 0, "delivery": 0}
    assert body["sellers"][str(seller)] == rows[0]["orders_count"] == len(orders)
