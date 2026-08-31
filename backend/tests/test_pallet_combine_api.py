from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeRequest
from app.models.pallet import Pallet
from app.models.warehouse import Warehouse


async def _register_admin(client: AsyncClient) -> tuple[dict[str, str], uuid.UUID]:
    suffix = uuid.uuid4().hex[:12]
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Pallet combine {suffix}",
            "slug": f"pallet-combine-{suffix}",
            "admin_email": f"pallet-combine-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return headers, uuid.UUID(me.json()["tenant_id"])


async def _create_reception_staff(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:12]
    email = f"pallet-receiver-{suffix}@example.com"
    created = await client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": email},
    )
    assert created.status_code == 201, created.text
    permissions = await client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": True,
            "cells": False,
            "inventory": False,
            "packaging": False,
            "shift_lead": False,
        },
    )
    assert permissions.status_code == 200, permissions.text
    password = await client.post(
        "/auth/set-initial-password",
        json={"email": email, "password": "password123"},
    )
    assert password.status_code == 200, password.text
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_combine_inbound_boxes_creates_one_pallet_and_returns_it_in_document(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id = await _register_admin(async_client)
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад сборки палеты",
            code=f"pallet-{suffix}",
            barcode=f"WH-PALLET-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add(request)
        await session.flush()
        boxes = [
            InboundIntakeBox(
                tenant_id=tenant_id,
                request_id=request.id,
                box_number=number,
                internal_barcode=f"BOX-PALLET-{suffix}-{number}",
            )
            for number in (1, 2)
        ]
        session.add_all(boxes)
        await session.commit()
        warehouse_id = warehouse.id
        request_id = request.id
        box_ids = [box.id for box in boxes]

    combined = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=headers,
        json={
            "pallet_id": None,
            "inbound_request_id": str(request_id),
            "inbound_box_ids": [str(box_id) for box_id in box_ids],
            "cargo_place_ids": [],
            "warehouse_box_ids": [],
        },
    )
    assert combined.status_code == 200, combined.text
    pallet = combined.json()
    assert pallet["code"].startswith("П-")

    listed = await async_client.get(
        f"/warehouses/{warehouse_id}/pallets?inbound_request_id={request_id}",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [pallet["id"]]

    detail = await async_client.get(
        f"/operations/inbound-intake-requests/{request_id}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert {box["pallet_id"] for box in detail.json()["boxes"]} == {pallet["id"]}
    assert {box["pallet_code"] for box in detail.json()["boxes"]} == {pallet["code"]}


@pytest.mark.asyncio
async def test_reception_only_staff_can_list_and_combine_inbound_pallets(
    async_client: AsyncClient,
) -> None:
    admin_headers, tenant_id = await _register_admin(async_client)
    reception_headers = await _create_reception_staff(async_client, admin_headers)
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад сотрудника приёмки",
            code=f"receiver-pallet-{suffix}",
            barcode=f"WH-RECEIVER-PALLET-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add(request)
        await session.flush()
        box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=request.id,
            box_number=1,
            internal_barcode=f"BOX-RECEIVER-PALLET-{suffix}",
        )
        session.add(box)
        await session.commit()
        warehouse_id = warehouse.id
        request_id = request.id
        box_id = box.id

    listed = await async_client.get(
        f"/warehouses/{warehouse_id}/pallets?inbound_request_id={request_id}",
        headers=reception_headers,
    )
    assert listed.status_code == 200, listed.text

    combined = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=reception_headers,
        json={
            "inbound_request_id": str(request_id),
            "inbound_box_ids": [str(box_id)],
        },
    )
    assert combined.status_code == 200, combined.text


@pytest.mark.asyncio
async def test_empty_new_pallet_combine_rolls_back_created_pallet(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id = await _register_admin(async_client)
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад пустой палеты",
            code=f"empty-pallet-{suffix}",
            barcode=f"WH-EMPTY-PALLET-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add(request)
        await session.commit()
        warehouse_id = warehouse.id
        request_id = request.id

    blocked = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=headers,
        json={
            "pallet_id": None,
            "inbound_request_id": str(request_id),
            "inbound_box_ids": [],
            "cargo_place_ids": [],
            "warehouse_box_ids": [],
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["detail"] == "containers_required"
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(Pallet.id)).where(Pallet.tenant_id == tenant_id)
        )
        assert count == 0


@pytest.mark.asyncio
async def test_combine_rejects_box_from_another_receipt_on_same_warehouse(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id = await _register_admin(async_client)
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад двух приёмок",
            code=f"two-receipts-{suffix}",
            barcode=f"WH-TWO-RECEIPTS-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        first = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        second = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add_all([first, second])
        await session.flush()
        foreign_box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=second.id,
            box_number=1,
            internal_barcode=f"BOX-OTHER-RECEIPT-{suffix}",
        )
        session.add(foreign_box)
        await session.commit()
        warehouse_id = warehouse.id
        first_id = first.id
        foreign_box_id = foreign_box.id

    blocked = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=headers,
        json={
            "pallet_id": None,
            "inbound_request_id": str(first_id),
            "inbound_box_ids": [str(foreign_box_id)],
        },
    )
    assert blocked.status_code == 404, blocked.text
    assert blocked.json()["detail"] == "box_not_found"
    async with SessionLocal() as session:
        stored_box = await session.get(InboundIntakeBox, foreign_box_id)
        assert stored_box is not None and stored_box.pallet_id is None
        assert await session.scalar(
            select(func.count(Pallet.id)).where(Pallet.tenant_id == tenant_id)
        ) == 0


@pytest.mark.asyncio
async def test_combine_rejects_completed_receipt(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id = await _register_admin(async_client)
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад завершённой приёмки",
            code=f"closed-receipt-{suffix}",
            barcode=f"WH-CLOSED-RECEIPT-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="sorting",
        )
        session.add(request)
        await session.flush()
        box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=request.id,
            box_number=1,
            internal_barcode=f"BOX-CLOSED-RECEIPT-{suffix}",
        )
        session.add(box)
        await session.commit()
        warehouse_id = warehouse.id
        request_id = request.id
        box_id = box.id

    blocked = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=headers,
        json={
            "pallet_id": None,
            "inbound_request_id": str(request_id),
            "inbound_box_ids": [str(box_id)],
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == "inbound_request_not_receiving"
    async with SessionLocal() as session:
        stored_box = await session.get(InboundIntakeBox, box_id)
        assert stored_box is not None and stored_box.pallet_id is None
        assert await session.scalar(
            select(func.count(Pallet.id)).where(Pallet.tenant_id == tenant_id)
        ) == 0
