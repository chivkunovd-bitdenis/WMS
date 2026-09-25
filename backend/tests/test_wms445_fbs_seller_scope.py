"""WMS-445: the TSD orders and active-supplies lists share seller scope."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.user import User
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock


@pytest.mark.asyncio
async def test_tsd_worklists_hold_effective_seller_scope(async_client: AsyncClient) -> None:
    """C20: a scoped employee cannot reveal another seller through either list."""
    headers, seller_a, warehouse_id, product_id, _location_id, order_ids = (
        await _setup_ff_admin_with_stock(async_client)
    )
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    seller_b_response = await async_client.post(
        "/sellers", headers=headers, json={"name": "WMS-445 seller B"}
    )
    assert seller_b_response.status_code == 201, seller_b_response.text
    seller_b = uuid.UUID(seller_b_response.json()["id"])

    async with SessionLocal() as session:
        user = await session.get(User, uuid.UUID(me.json()["id"]))
        order_a = await session.get(FbsOrder, order_ids[0])
        assert user is not None and order_a is not None
        user.role = FULFILLMENT_STAFF
        user.seller_id = seller_a
        session.add(FfStaffPermissions(user_id=user.id, can_packaging=True))
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=order_a.tenant_id,
            seller_id=seller_b,
            wms_warehouse_id=warehouse_id,
        )
        order_b = FbsOrder(
            tenant_id=order_a.tenant_id,
            seller_id=seller_b,
            warehouse_id=warehouse_id,
            product_id=product_id,
            marketplace="wb",
            wb_order_id=945_002,
            wb_nm_id=900_100,
            wb_chrt_id=777_001,
            wb_barcode=order_a.wb_barcode,
            wb_article=order_a.wb_article,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
            status=FBS_ORDER_STATUS_NEW,
            supplier_status="new",
            created_at_wb=order_a.created_at_wb,
            deadline_at=order_a.deadline_at,
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
        )
        supply_a = FbsSupply(
            tenant_id=order_a.tenant_id,
            seller_id=seller_a,
            warehouse_id=warehouse_id,
            marketplace="wb",
            name="WMS-445 A",
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            delivery_type="warehouse_sc",
        )
        supply_b = FbsSupply(
            tenant_id=order_a.tenant_id,
            seller_id=seller_b,
            warehouse_id=warehouse_id,
            marketplace="wb",
            name="WMS-445 B",
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            delivery_type="warehouse_sc",
        )
        session.add_all([order_b, supply_a, supply_b])
        await session.commit()

    orders_params = {"marketplace": "wb", "status_group": "tsd_working"}
    supplies_params = {"marketplace": "wb", "status_group": "active"}
    for params in (orders_params, {**orders_params, "seller_id": str(seller_b)}):
        response = await async_client.get(
            "/operations/fbs-orders/worklist", headers=headers, params=params
        )
        assert response.status_code == 200, response.text
        actual_order_ids = {item["id"] for item in response.json()["items"]}
        assert actual_order_ids == {str(order_ids[0])}, (
            params,
            str(seller_a),
            str(seller_b),
            str(order_b.id),
            actual_order_ids,
        )
    for params in (supplies_params, {**supplies_params, "seller_id": str(seller_b)}):
        response = await async_client.get(
            "/operations/fbs-supplies/worklist", headers=headers, params=params
        )
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} == {str(supply_a.id)}

    # Removing the scope restores the existing all-sellers tenant worklist;
    # an explicit seller then narrows it rather than granting cross-tenant access.
    async with SessionLocal() as session:
        user = await session.get(User, uuid.UUID(me.json()["id"]))
        assert user is not None
        user.role = FULFILLMENT_ADMIN
        user.seller_id = None
        await session.commit()
    unscoped = await async_client.get(
        "/operations/fbs-orders/worklist", headers=headers, params=orders_params
    )
    assert unscoped.status_code == 200, unscoped.text
    assert {item["id"] for item in unscoped.json()["items"]} == {
        str(order_ids[0]),
        str(order_b.id),
    }
    narrowed = await async_client.get(
        "/operations/fbs-supplies/worklist",
        headers=headers,
        params={**supplies_params, "seller_id": str(seller_b)},
    )
    assert narrowed.status_code == 200, narrowed.text
    assert {item["id"] for item in narrowed.json()["items"]} == {str(supply_b.id)}
