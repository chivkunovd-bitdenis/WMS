from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FbsSupply,
)
from app.models.packaging_task import STATUS_DONE, PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services.staff_packaging_billing_service import (
    aggregate_staff_billing,
    current_billing_month_msk,
)


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Billing FF",
            "slug": f"bill-{suffix}",
            "admin_email": f"adm-bill-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    return {"Authorization": f"Bearer {token}"}, suffix


async def _create_staff(
    async_client: AsyncClient,
    admin_h: dict[str, str],
    *,
    suffix: str,
    packaging: bool = True,
) -> tuple[str, dict[str, str]]:
    staff_email = f"packer-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_h,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=admin_h,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": packaging,
        },
    )
    assert patched.status_code == 200, patched.text
    await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    staff_h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return staff_id, staff_h


async def _inventory_at_location(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    warehouse_id: str,
    product_id: str,
    qty: int,
    location_code: str,
) -> str:
    loc = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=h,
        json={"code": location_code},
    )
    assert loc.status_code == 200, loc.text
    location_id = str(loc.json()["id"])
    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=h, json={"warehouse_id": warehouse_id})
    assert inbound.status_code == 201, inbound.text
    rid = inbound.json()["id"]
    line = await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=h,
        json={
            "product_id": product_id,
            "expected_qty": qty,
            "storage_location_id": location_id,
        },
    )
    assert line.status_code == 201, line.text
    await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    await post_primary_accept(async_client, base_in, rid, h)
    sku = line.json()["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, qty)
    verify = await async_client.post(f"{base_in}/{rid}/verify", headers=h)
    assert verify.status_code == 200, verify.text
    post = await async_client.post(f"{base_in}/{rid}/post", headers=h)
    assert post.status_code == 200, post.text
    return location_id


@pytest.mark.asyncio
async def test_staff_packaging_billing_counts_only_packed_in_task(
    async_client: AsyncClient,
) -> None:
    admin_h, suffix = await _register_admin(async_client)
    staff_id, staff_h = await _create_staff(async_client, admin_h, suffix=suffix)

    rate_patch = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/packaging-rate",
        headers=admin_h,
        json={"rate_rub": "10.00"},
    )
    assert rate_patch.status_code == 200, rate_patch.text
    assert rate_patch.json()["packaging_rate_rub"] == "10.00"

    wh = await async_client.post(
        "/warehouses",
        headers=admin_h,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=admin_h,
        json={
            "name": "Bill Product",
            "sku_code": f"bill-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert pr.status_code in (200, 201), pr.text
    product_id = pr.json()["id"]
    loc_id = await _inventory_at_location(
        async_client,
        admin_h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=20,
        location_code=f"BILL-{suffix[:4]}",
    )

    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=staff_h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 10}],
        },
    )
    assert create.status_code == 201, create.text
    task_id = create.json()["id"]
    line_id = create.json()["lines"][0]["id"]

    pack_partial = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=staff_h,
        json={"quantity": 4},
    )
    assert pack_partial.status_code == 200, pack_partial.text
    assert pack_partial.json()["packaging_task"]["status"] != STATUS_DONE

    listed_open = await async_client.get("/auth/staff-accounts", headers=admin_h)
    assert listed_open.status_code == 200, listed_open.text
    row_open = next(r for r in listed_open.json() if r["id"] == staff_id)
    assert row_open["packaging_rate_rub"] == "10.00"
    assert row_open["packaging_billing"]["units_packed"] == 0

    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=staff_h,
        json={"quantity": 6},
    )
    assert pack.status_code == 200, pack.text
    assert pack.json()["packaging_task"]["status"] == "in_progress"

    listed_before_complete = await async_client.get("/auth/staff-accounts", headers=admin_h)
    assert listed_before_complete.status_code == 200, listed_before_complete.text
    row_before_complete = next(r for r in listed_before_complete.json() if r["id"] == staff_id)
    assert row_before_complete["packaging_rate_rub"] == "10.00"
    assert row_before_complete["packaging_billing"]["units_packed"] == 0

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=staff_h,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == STATUS_DONE

    listed = await async_client.get("/auth/staff-accounts", headers=admin_h)
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == staff_id)
    assert row["packaging_rate_rub"] == "10.00"
    assert row["packaging_billing"]["units_packed"] == 10
    assert row["packaging_billing"]["earned_rub"] == "100.00"


@pytest.mark.asyncio
async def test_staff_without_packaging_permission_cannot_create_task(
    async_client: AsyncClient,
) -> None:
    admin_h, suffix = await _register_admin(async_client)
    _staff_id, staff_h = await _create_staff(
        async_client, admin_h, suffix=f"nopkg-{suffix}", packaging=False
    )

    listed = await async_client.get("/operations/packaging-tasks", headers=staff_h)
    assert listed.status_code == 403


@pytest.mark.asyncio
async def test_wb_billing_credits_each_fulfillment_actor(
    async_client: AsyncClient,
) -> None:
    admin_h, suffix = await _register_admin(async_client)
    first_id, _ = await _create_staff(
        async_client, admin_h, suffix=f"first-{suffix}"
    )
    second_id, _ = await _create_staff(
        async_client, admin_h, suffix=f"second-{suffix}"
    )
    for staff_id, rate in ((first_id, "10.00"), (second_id, "15.00")):
        response = await async_client.patch(
            f"/auth/staff-accounts/{staff_id}/packaging-rate",
            headers=admin_h,
            json={"rate_rub": rate},
        )
        assert response.status_code == 200, response.text

    me = await async_client.get("/auth/me", headers=admin_h)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant_id, name="WB billing seller")
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="WB billing warehouse",
            code=f"wb-billing-{suffix}",
        )
        session.add_all([seller, warehouse])
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="WB billing product",
            sku_code=f"WB-BILL-{suffix}",
        )
        location = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="BILL-01",
            barcode=f"WB-BILL-LOC-{suffix}",
        )
        task = PackagingTask(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status=STATUS_DONE,
            completed_by_user_id=uuid.UUID(first_id),
            completed_at=now,
            billing_units_packed=2,
            billing_rate_kopecks=1000,
            billing_earned_kopecks=2000,
        )
        session.add_all([product, location, task])
        await session.flush()
        line = PackagingTaskLine(
            task_id=task.id,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=2,
            qty_packed_in_task=2,
        )
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            marketplace="wb",
            wb_supply_id=f"WB-BILL-{suffix}",
            name="WB billing supply",
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            packaging_task_id=task.id,
        )
        session.add_all([line, supply])
        await session.flush()
        orders = [
            FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
                supply_id=supply.id,
                wb_order_id=990_000 + index,
                status=FBS_ORDER_STATUS_ASSEMBLING,
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
                created_at_wb=now,
                deadline_at=now + timedelta(days=1),
            )
            for index in (1, 2)
        ]
        session.add_all(orders)
        await session.flush()
        session.add_all(
            [
                FbsPackagingFulfillment(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    packaging_task_id=task.id,
                    packaging_task_line_id=line.id,
                    fulfilled_by_user_id=actor_id,
                    fulfilled_at=now,
                    pack_idempotency_key=f"wb-billing-{order.id}",
                )
                for order, actor_id in zip(
                    orders,
                    (uuid.UUID(first_id), uuid.UUID(second_id)),
                    strict=True,
                )
            ]
        )
        await session.commit()

        totals = await aggregate_staff_billing(
            session,
            tenant_id=tenant_id,
            staff_user_ids=[uuid.UUID(first_id), uuid.UUID(second_id)],
            billing_month=current_billing_month_msk(),
        )

    assert totals[uuid.UUID(first_id)].units_packed == 1
    assert totals[uuid.UUID(first_id)].earned_kopecks == 1000
    assert totals[uuid.UUID(second_id)].units_packed == 1
    assert totals[uuid.UUID(second_id)].earned_kopecks == 1500
