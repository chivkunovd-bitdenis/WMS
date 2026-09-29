from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.roles import FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    MAPPING_STATUS_MAPPED,
    PACK_STATUS_PACKED,
    PACK_STATUS_PENDING,
    PICK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FbsSupply,
)
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.user import User

BASE = "/operations/fbs-assembly-tasks"


async def _register(
    async_client: AsyncClient,
    label: str,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = f"{label}-{time.time_ns()}"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": suffix,
            "slug": suffix.lower(),
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {label}"},
    )
    assert seller.status_code in {200, 201}, seller.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"Warehouse {label}", "code": f"wh-{uuid.uuid4().hex[:10]}"},
    )
    assert warehouse.status_code in {200, 201}, warehouse.text
    return (
        headers,
        uuid.UUID(me.json()["tenant_id"]),
        uuid.UUID(me.json()["id"]),
        uuid.UUID(seller.json()["id"]),
        uuid.UUID(warehouse.json()["id"]),
    )


async def _seed_supply(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    name: str,
    status: str = FBS_SUPPLY_STATUS_ASSEMBLING,
    marketplace: str = "wb",
    order_states: list[tuple[str, str]] | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace=marketplace,
            name=name,
            status=status,
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        now = datetime.now(tz=UTC)
        for index, (pick_status, pack_status) in enumerate(order_states or []):
            session.add(
                FbsOrder(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    supply_id=supply.id,
                    marketplace=marketplace,
                    wb_order_id=int(time.time_ns()) + index,
                    status=FBS_ORDER_STATUS_ASSEMBLING,
                    supplier_status="confirm",
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                    mapping_status=MAPPING_STATUS_MAPPED,
                    reserve_status=RESERVE_STATUS_RESERVED,
                    pick_status=pick_status,
                    pack_status=pack_status,
                )
            )
        await session.commit()
        return supply.id


async def _create_task(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_ids: list[uuid.UUID],
    key: str,
):
    return await async_client.post(
        BASE,
        headers=headers,
        json={"supply_ids": [str(value) for value in supply_ids], "idempotency_key": key},
    )


@pytest.mark.asyncio
async def test_create_detail_and_idempotent_replay(async_client: AsyncClient) -> None:
    headers, tenant_id, user_id, seller_id, warehouse_id = await _register(
        async_client, "create"
    )
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="WB supply",
        order_states=[
            (PICK_STATUS_PICKED, PACK_STATUS_PACKED),
            (PICK_STATUS_PICKED, PACK_STATUS_PENDING),
            (PICK_STATUS_PENDING, PACK_STATUS_PENDING),
        ],
    )
    ozon_supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="Ozon supply",
        marketplace="ozon",
    )

    created = await _create_task(
        async_client,
        headers,
        [supply_id, ozon_supply_id],
        "wms588-create",
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["number"] == "№000001"
    assert body["created_by"]["id"] == str(user_id)
    by_id = {row["id"]: row for row in body["supplies"]}
    assert by_id[str(supply_id)] == {
        "id": str(supply_id),
        "marketplace": "wb",
        "name": "WB supply",
        "seller": {"id": str(seller_id), "name": "Seller create"},
        "status": FBS_SUPPLY_STATUS_ASSEMBLING,
        "orders_count": 3,
        "picked_count": 2,
        "packed_count": 1,
    }
    assert by_id[str(ozon_supply_id)]["marketplace"] == "ozon"

    detail = await async_client.get(f"{BASE}/{body['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json() == body

    replay = await _create_task(
        async_client,
        headers,
        [ozon_supply_id, supply_id],
        "wms588-create",
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == body["id"]
    async with SessionLocal() as session:
        assert await session.scalar(
            select(func.count()).select_from(FbsAssemblyTask)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(FbsAssemblyTaskSupply)
        ) == 2


@pytest.mark.asyncio
async def test_supply_cannot_be_added_to_two_tasks(async_client: AsyncClient) -> None:
    headers, tenant_id, _user_id, seller_id, warehouse_id = await _register(
        async_client, "double"
    )
    supply_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="Only once",
    )
    first = await _create_task(async_client, headers, [supply_id], "wms588-first")
    assert first.status_code == 201, first.text

    second = await _create_task(async_client, headers, [supply_id], "wms588-second")
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "supply_already_in_assembly_task"


@pytest.mark.asyncio
async def test_list_contains_task_while_any_supply_is_active(async_client: AsyncClient) -> None:
    headers, tenant_id, _user_id, seller_id, warehouse_id = await _register(
        async_client, "active"
    )
    active_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="Still active",
    )
    done_in_mixed_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="Already handed off",
        status=FBS_SUPPLY_STATUS_DONE,
    )
    done_only_id = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        name="Done only",
        status=FBS_SUPPLY_STATUS_DONE,
    )
    mixed = await _create_task(
        async_client,
        headers,
        [active_id, done_in_mixed_id],
        "wms588-mixed",
    )
    done = await _create_task(async_client, headers, [done_only_id], "wms588-done")
    assert mixed.status_code == done.status_code == 201

    listed = await async_client.get(BASE, headers=headers, params={"marketplace": "wb"})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [mixed.json()["id"]]
    assert {row["id"] for row in listed.json()["items"][0]["supplies"]} == {
        str(active_id),
        str(done_in_mixed_id),
    }

    async with SessionLocal() as session:
        active = await session.get(FbsSupply, active_id)
        assert active is not None
        active.status = FBS_SUPPLY_STATUS_DONE
        await session.commit()
    empty = await async_client.get(BASE, headers=headers)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"items": []}


@pytest.mark.asyncio
async def test_tenant_boundary_for_create_list_and_detail(async_client: AsyncClient) -> None:
    headers_a, _tenant_a, _user_a, _seller_a, _warehouse_a = await _register(
        async_client, "tenant-a"
    )
    headers_b, tenant_b, _user_b, seller_b, warehouse_b = await _register(
        async_client, "tenant-b"
    )
    supply_b = await _seed_supply(
        tenant_id=tenant_b,
        seller_id=seller_b,
        warehouse_id=warehouse_b,
        name="Tenant B",
    )

    foreign_create = await _create_task(
        async_client,
        headers_a,
        [supply_b],
        "wms588-foreign",
    )
    assert foreign_create.status_code == 409, foreign_create.text
    assert foreign_create.json()["detail"]["code"] == "supply_scope_conflict"

    own_create = await _create_task(async_client, headers_b, [supply_b], "wms588-own")
    assert own_create.status_code == 201, own_create.text
    foreign_detail = await async_client.get(
        f"{BASE}/{own_create.json()['id']}", headers=headers_a
    )
    assert foreign_detail.status_code == 404, foreign_detail.text
    foreign_list = await async_client.get(BASE, headers=headers_a)
    assert foreign_list.status_code == 200, foreign_list.text
    assert foreign_list.json() == {"items": []}


@pytest.mark.asyncio
async def test_effective_seller_scope_matches_supply_worklist(async_client: AsyncClient) -> None:
    headers, tenant_id, user_id, seller_a, warehouse_id = await _register(
        async_client, "seller-scope"
    )
    seller_b_response = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Seller B"},
    )
    assert seller_b_response.status_code in {200, 201}, seller_b_response.text
    seller_b = uuid.UUID(seller_b_response.json()["id"])
    supply_a = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_a,
        warehouse_id=warehouse_id,
        name="Seller A supply",
    )
    supply_b = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_b,
        warehouse_id=warehouse_id,
        name="Seller B supply",
    )
    task_a = await _create_task(async_client, headers, [supply_a], "wms588-seller-a")
    task_b = await _create_task(async_client, headers, [supply_b], "wms588-seller-b")
    assert task_a.status_code == task_b.status_code == 201

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = FULFILLMENT_STAFF
        user.seller_id = seller_a
        session.add(FfStaffPermissions(user_id=user.id, can_packaging=True))
        await session.commit()

    listed = await async_client.get(BASE, headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [task_a.json()["id"]]
    hidden = await async_client.get(f"{BASE}/{task_b.json()['id']}", headers=headers)
    assert hidden.status_code == 404, hidden.text
    forbidden_create = await _create_task(
        async_client,
        headers,
        [supply_b],
        "wms588-scoped-foreign",
    )
    assert forbidden_create.status_code == 409, forbidden_create.text
    assert forbidden_create.json()["detail"]["code"] == "supply_scope_conflict"
