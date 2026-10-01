"""WMS-616 seller-facing read-only FBS projection."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event

from app.core.roles import FULFILLMENT_SELLER
from app.db.session import SessionLocal, engine
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.user import User
from app.services.tokens import create_access_token


async def _register_with_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str], dict[str, str]]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Seller FBS {suffix}",
            "slug": f"seller-fbs-{suffix}",
            "admin_email": f"seller-fbs-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    admin_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    admin_me = (await async_client.get("/auth/me", headers=admin_headers)).json()
    tenant_id = uuid.UUID(admin_me["tenant_id"])

    created = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": f"Seller {suffix}"}
    )
    assert created.status_code == 201, created.text
    seller_id = uuid.UUID(created.json()["id"])
    email = f"seller-fbs-owner-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": str(seller_id), "email": email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    logged_in = await async_client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert logged_in.status_code == 200, logged_in.text
    seller_headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
    seller_me = (await async_client.get("/auth/me", headers=seller_headers)).json()
    return tenant_id, seller_id, uuid.UUID(seller_me["id"]), seller_headers, admin_headers


def _order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str,
    external_order_id: str,
    wb_order_id: int,
    status: str,
    received_at: datetime,
    wb_status: str | None = None,
    supplier_status: str | None = None,
) -> FbsOrder:
    return FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        marketplace=marketplace,
        external_order_id=external_order_id,
        wb_order_id=wb_order_id,
        status=status,
        wb_status=wb_status,
        supplier_status=supplier_status,
        created_at_wb=received_at,
        deadline_at=received_at + timedelta(days=1),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    )


@pytest.mark.asyncio
async def test_seller_fbs_lists_all_groups_quantities_filters_and_stable_pages(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    tenant_id, seller_id, _, headers, _ = await _register_with_seller(async_client, suffix)
    now = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
    rows = [
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="wb",
            external_order_id="WB-NEW",
            wb_order_id=616_001,
            status=FBS_ORDER_STATUS_NEW,
            received_at=now - timedelta(minutes=30),
            wb_status="waiting",
            supplier_status="new",
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="ozon",
            external_order_id="OZ-IN-WORK",
            wb_order_id=-616_002,
            status=FBS_ORDER_STATUS_ASSEMBLING,
            received_at=now - timedelta(hours=1),
            wb_status="done",  # local warehouse work has D3 priority
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="ozon",
            external_order_id="OZ-HANDED",
            wb_order_id=-616_003,
            status=FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
            received_at=now - timedelta(hours=2),
            wb_status="delivering",
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="wb",
            external_order_id="WB-ACCEPTED",
            wb_order_id=616_004,
            status=FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
            received_at=now - timedelta(hours=3),
            wb_status="sorted",
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="ozon",
            external_order_id="OZ-UNKNOWN",
            wb_order_id=-616_005,
            status=FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
            received_at=now - timedelta(hours=4),
            wb_status="provider_added_a_new_code",
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="ozon",
            external_order_id="OZ-DONE",
            wb_order_id=-616_006,
            status=FBS_ORDER_STATUS_DONE,
            received_at=now - timedelta(hours=5),
        ),
        _order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="wb",
            external_order_id="WB-CANCELLED",
            wb_order_id=616_007,
            status=FBS_ORDER_STATUS_CANCELLED,
            received_at=now - timedelta(hours=6),
        ),
    ]
    async with SessionLocal() as session:
        session.add_all(rows)
        await session.flush()
        session.add_all(
            [
                FbsOrderProduct(
                    order_id=rows[1].id, ozon_sku=1, quantity=2, position_index=0
                ),
                FbsOrderProduct(
                    order_id=rows[1].id, ozon_sku=2, quantity=1, position_index=1
                ),
                FbsOrderProduct(
                    order_id=rows[2].id, ozon_sku=3, quantity=3, position_index=0
                ),
                FbsOrderProduct(
                    order_id=rows[2].id, ozon_sku=4, quantity=0, position_index=1
                ),
            ]
        )
        await session.commit()

    response = await async_client.get("/seller-fbs/orders", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 7
    assert [item["external_order_id"] for item in body["items"]] == [
        "WB-NEW",
        "OZ-IN-WORK",
        "OZ-HANDED",
        "WB-ACCEPTED",
        "OZ-UNKNOWN",
        "OZ-DONE",
        "WB-CANCELLED",
    ]
    by_external_id = {item["external_order_id"]: item for item in body["items"]}
    assert by_external_id["WB-NEW"]["status_group"] == "new"
    assert by_external_id["WB-NEW"]["items_quantity"] == 1
    assert by_external_id["OZ-IN-WORK"]["status_group"] == "in_work"
    assert by_external_id["OZ-IN-WORK"]["items_quantity"] == 3
    assert by_external_id["OZ-HANDED"]["status_group"] == "handed"
    assert by_external_id["OZ-HANDED"]["items_quantity"] is None
    assert by_external_id["WB-ACCEPTED"]["status_group"] == "accepted"
    assert by_external_id["OZ-UNKNOWN"]["status_group"] == "external_processing"
    assert by_external_id["OZ-DONE"]["status_group"] == "done"
    assert by_external_id["OZ-DONE"]["items_quantity"] is None
    assert by_external_id["WB-CANCELLED"]["status_group"] == "cancelled"
    assert datetime.fromisoformat(body["server_now"]).tzinfo is not None

    filtered = await async_client.get(
        "/seller-fbs/orders",
        headers=headers,
        params={"marketplace": "ozon", "status": "handed", "limit": 1, "offset": 0},
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert [item["external_order_id"] for item in filtered.json()["items"]] == ["OZ-HANDED"]

    first_page = await async_client.get(
        "/seller-fbs/orders", headers=headers, params={"limit": 2, "offset": 0}
    )
    second_page = await async_client.get(
        "/seller-fbs/orders", headers=headers, params={"limit": 2, "offset": 2}
    )
    first_ids = {item["id"] for item in first_page.json()["items"]}
    second_ids = {item["id"] for item in second_page.json()["items"]}
    assert not first_ids & second_ids
    assert len(first_ids) == len(second_ids) == 2


@pytest.mark.asyncio
async def test_seller_fbs_is_tenant_seller_scoped_and_requires_documents(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    tenant_id, seller_a, owner_user_id, owner_headers, admin_headers = (
        await _register_with_seller(async_client, suffix)
    )
    other = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Other seller"}
    )
    assert other.status_code == 201, other.text
    seller_b = uuid.UUID(other.json()["id"])
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        own = _order(
            tenant_id=tenant_id,
            seller_id=seller_a,
            marketplace="wb",
            external_order_id="OWN-ORDER",
            wb_order_id=616_101,
            status=FBS_ORDER_STATUS_NEW,
            received_at=now,
        )
        foreign = _order(
            tenant_id=tenant_id,
            seller_id=seller_b,
            marketplace="wb",
            external_order_id="FOREIGN-ORDER",
            wb_order_id=616_102,
            status=FBS_ORDER_STATUS_NEW,
            received_at=now,
        )
        session.add_all([own, foreign])
        staff = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller_a,
            email=f"seller-fbs-staff-{suffix}@example.com",
            password_hash="x",
            must_set_password=False,
            role=FULFILLMENT_SELLER,
        )
        session.add(staff)
        session.add(
            SellerStaffPermissions(
                user_id=staff.id,
                can_documents=False,
                can_products=True,
                can_honest_sign=True,
                can_settings=False,
                can_staff=False,
            )
        )
        await session.commit()
        staff_token = create_access_token(
            user_id=staff.id,
            tenant_id=tenant_id,
            role=FULFILLMENT_SELLER,
            seller_id=seller_a,
        )

    own_response = await async_client.get(
        "/seller-fbs/orders",
        headers=owner_headers,
        params={"seller_id": str(seller_b)},
    )
    assert own_response.status_code == 200, own_response.text
    assert [item["external_order_id"] for item in own_response.json()["items"]] == ["OWN-ORDER"]

    forged = create_access_token(
        user_id=owner_user_id,
        tenant_id=tenant_id,
        role=FULFILLMENT_SELLER,
        seller_id=seller_b,
    )
    forged_response = await async_client.get(
        "/seller-fbs/orders", headers={"Authorization": f"Bearer {forged}"}
    )
    assert forged_response.status_code == 200, forged_response.text
    assert [item["external_order_id"] for item in forged_response.json()["items"]] == [
        "OWN-ORDER"
    ]

    denied = await async_client.get(
        "/seller-fbs/orders", headers={"Authorization": f"Bearer {staff_token}"}
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "forbidden"
    assert (await async_client.get("/seller-fbs/orders", headers=admin_headers)).status_code == 403


@pytest.mark.asyncio
async def test_seller_fbs_batches_ozon_quantities_without_n_plus_one(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    tenant_id, seller_id, _, headers, _ = await _register_with_seller(async_client, suffix)
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        orders = [
            _order(
                tenant_id=tenant_id,
                seller_id=seller_id,
                marketplace="ozon",
                external_order_id=f"OZ-BATCH-{index}",
                wb_order_id=-(617_000 + index),
                status=FBS_ORDER_STATUS_NEW,
                received_at=now - timedelta(minutes=index),
            )
            for index in range(20)
        ]
        session.add_all(orders)
        await session.flush()
        session.add_all(
            [
                FbsOrderProduct(
                    order_id=order.id,
                    ozon_sku=index,
                    quantity=2,
                    position_index=0,
                )
                for index, order in enumerate(orders)
            ]
        )
        await session.commit()

    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement.lower())

    event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        response = await async_client.get(
            "/seller-fbs/orders", headers=headers, params={"limit": 20}
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 20
    assert {item["items_quantity"] for item in response.json()["items"]} == {2}
    product_queries = [sql for sql in statements if "fbs_order_products" in sql]
    assert len(product_queries) == 1
