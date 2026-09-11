from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import (
    fulfill_inbound_via_box_scans,
    post_primary_accept,
    set_planned_boxes,
)
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_reservation import InventoryReservation
from app.services.sorting_location_service import get_or_create_sorting_location


@pytest.mark.asyncio
async def test_second_outbound_line_blocks_when_reserved_exceeds_on_hand(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Res Co",
            "slug": f"res-{suffix}",
            "admin_email": f"res-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A1"}
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    rid = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 10,
            "storage_location_id": lid,
        },
    )
    base_in = "/operations/inbound-intake-requests"
    await set_planned_boxes(async_client, base_in, rid, h)
    submit = await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    assert submit.status_code == 200, submit.text
    await post_primary_accept(async_client, base_in, rid, h)
    inb = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}", headers=h
    )
    inb.json()["lines"][0]["id"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 10)
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    assert (
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/post", headers=h
        )
    ).status_code == 200

    base = "/operations/outbound-shipment-requests"
    o1 = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    id1 = o1.json()["id"]
    assert (
        await async_client.post(
            f"{base}/{id1}/lines",
            headers=h,
            json={"product_id": pid, "quantity": 6, "storage_location_id": lid},
        )
    ).status_code == 201

    o2 = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    id2 = o2.json()["id"]
    bad = await async_client.post(
        f"{base}/{id2}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 6, "storage_location_id": lid},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "insufficient_available"


@pytest.mark.asyncio
async def test_stock_transfer_blocked_by_outbound_reservation(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Tr Co",
            "slug": f"tr-{suffix}",
            "admin_email": f"tr-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-tr-{suffix}"}
    )
    wid = wh.json()["id"]
    la = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "FROM"}
    )
    lb = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "TO"}
    )
    aid = la.json()["id"]
    bid = lb.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-tr-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    rid = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 10,
            "storage_location_id": aid,
        },
    )
    base_in = "/operations/inbound-intake-requests"
    await set_planned_boxes(async_client, base_in, rid, h)
    submit = await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    assert submit.status_code == 200, submit.text
    await post_primary_accept(async_client, base_in, rid, h)
    inb = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}", headers=h
    )
    inb.json()["lines"][0]["id"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 10)
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 8, "storage_location_id": aid},
    )
    await async_client.post(f"{base}/{oid}/submit", headers=h)

    tr = await async_client.post(
        "/operations/stock-transfers",
        headers=h,
        json={
            "from_storage_location_id": aid,
            "to_storage_location_id": bid,
            "product_id": pid,
            "quantity": 3,
        },
    )
    assert tr.status_code == 422
    assert tr.json()["detail"] == "insufficient_stock"


@pytest.mark.asyncio
async def test_inventory_balances_include_reserved_and_available(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Bal Co",
            "slug": f"bal-{suffix}",
            "admin_email": f"bal-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-bal-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "L1"}
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-bal-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    rid = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 10,
            "storage_location_id": lid,
        },
    )
    base_in = "/operations/inbound-intake-requests"
    await set_planned_boxes(async_client, base_in, rid, h)
    submit = await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    assert submit.status_code == 200, submit.text
    await post_primary_accept(async_client, base_in, rid, h)
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 10)
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 7, "storage_location_id": lid},
    )

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal.status_code == 200
    row = bal.json()[0]
    assert row["quantity"] == 10
    assert row["reserved"] == 7
    assert row["available"] == 3



@pytest.mark.asyncio
async def test_outbound_reserves_stock_lying_in_sorting_zone(
    async_client: AsyncClient,
) -> None:
    """Товар в зоне сортировки обязан резервироваться под отгрузку.

    Два живых сценария владельца. Первый: у арендатора выключено адресное
    хранение — ячеек нет вообще, весь товар всегда лежит в сортировке, и без
    этого резерв не встал бы ни разу. Второй: приехала палета, она уже
    упакована, у продавца горят сроки, и её надо отгрузить сразу, не гоняя через
    раскладку. Раньше строка отгрузки без указанной ячейки считала доступным
    только хранение и отвечала «недостаточно остатка» на товар, который
    физически стоит на складе.
    """
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Sorting Co",
            "slug": f"sort-{suffix}",
            "admin_email": f"sort-{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "W", "code": f"w-{suffix}"}
    )
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Приехало упакованным",
            "sku_code": f"SORT-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    product_id = uuid.UUID(product.json()["id"])

    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=sorting.id,
                product_id=product_id,
                quantity=5,
                quantity_unpacked=5,
                quantity_packed=0,
            )
        )
        await session.commit()

    created = await async_client.post(
        "/operations/outbound-shipment-requests",
        headers=headers,
        json={"warehouse_id": str(warehouse_id)},
    )
    assert created.status_code == 201, created.text

    line = await async_client.post(
        f"/operations/outbound-shipment-requests/{created.json()['id']}/lines",
        headers=headers,
        # Ячейку не указываем: товар лежит в сортировке, ячеек может не быть вовсе.
        json={"product_id": str(product_id), "quantity": 3},
    )
    assert line.status_code == 201, line.text

    async with SessionLocal() as session:
        reserved = await session.scalar(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.product_id == product_id,
            )
        )
    assert reserved == 3
