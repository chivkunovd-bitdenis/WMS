"""TC-S16-003, TC-S16-011, TC-S16-012: catalog package read model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select

from app.db.session import SessionLocal, engine
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.product import Product
from app.models.warehouse import Warehouse


async def _register_admin(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Package catalog {suffix}",
            "slug": f"package-catalog-{suffix}",
            "admin_email": f"package-catalog-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _tenant_id(async_client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    response = await async_client.get("/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["tenant_id"])


async def _create_staff(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
    label: str,
    permissions: dict[str, bool],
) -> dict[str, str]:
    email = f"package-catalog-{label}-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts", headers=admin_headers, json={"email": email}
    )
    assert created.status_code == 201, created.text
    updated = await async_client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": False,
            "shift_lead": False,
            **permissions,
        },
    )
    assert updated.status_code == 200, updated.text
    password_set = await async_client.post(
        "/auth/set-initial-password", json={"email": email, "password": "password123"}
    )
    assert password_set.status_code == 200, password_set.text
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _seed_packages(tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    now = datetime.now(UTC)
    warehouse_one = Warehouse(id=uuid.uuid4(), tenant_id=tenant_id, name="Основной", code="main")
    warehouse_two = Warehouse(id=uuid.uuid4(), tenant_id=tenant_id, name="Резерв", code="reserve")
    product = Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Товар в коробе",
        sku_code="PKG-CATALOG-SKU",
    )
    current_request = InboundIntakeRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        warehouse_id=warehouse_one.id,
        status="sorting",
        display_number="№000002",
        document_number="ПРИЕМ-26-08-23-2",
        created_at=now,
    )
    old_request = InboundIntakeRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        warehouse_id=warehouse_two.id,
        status="sorting",
        display_number="№000001",
        document_number="ПРИЕМ-26-08-23-1",
        created_at=now - timedelta(minutes=1),
    )
    done_request = InboundIntakeRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        warehouse_id=warehouse_one.id,
        status="done",
        display_number="№000003",
        document_number="ПРИЕМ-26-08-23-3",
        created_at=now - timedelta(minutes=2),
    )
    residual_box = InboundIntakeBox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=current_request.id,
        box_number=3,
        internal_barcode="INB-CURRENT-RESIDUAL",
        intake_opened_at=now - timedelta(minutes=5),
    )
    empty_box = InboundIntakeBox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=current_request.id,
        box_number=4,
        internal_barcode="INB-CURRENT-EMPTY",
    )
    distributed_box = InboundIntakeBox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=current_request.id,
        box_number=5,
        internal_barcode="INB-CURRENT-DISTRIBUTED",
        intake_closed_at=now - timedelta(minutes=1),
    )
    old_residual_box = InboundIntakeBox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=old_request.id,
        box_number=1,
        internal_barcode="INB-OLD-RESIDUAL",
    )
    done_box = InboundIntakeBox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=done_request.id,
        box_number=2,
        internal_barcode="INB-DONE-DISTRIBUTED",
        intake_opened_at=now - timedelta(minutes=10),
        intake_closed_at=now - timedelta(minutes=9),
    )
    current_cargo = InboundIntakeCargoPlace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=current_request.id,
        place_number=6,
        internal_barcode="ICG-CURRENT",
        created_at=now,
    )
    done_cargo = InboundIntakeCargoPlace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=done_request.id,
        place_number=1,
        internal_barcode="ICG-DONE",
        created_at=now - timedelta(minutes=2),
    )
    lines = [
        InboundIntakeBoxLine(
            id=uuid.uuid4(),
            product_id=product.id,
            box_id=residual_box.id,
            quantity=10,
            posted_qty=4,
        ),
        InboundIntakeBoxLine(
            id=uuid.uuid4(),
            product_id=product.id,
            box_id=distributed_box.id,
            quantity=2,
            posted_qty=2,
        ),
        InboundIntakeBoxLine(
            id=uuid.uuid4(),
            product_id=product.id,
            box_id=old_residual_box.id,
            quantity=3,
            posted_qty=1,
        ),
        InboundIntakeBoxLine(
            id=uuid.uuid4(), product_id=product.id, box_id=done_box.id, quantity=4, posted_qty=4
        ),
    ]
    async with SessionLocal() as session:
        session.add_all(
            [
                warehouse_one,
                warehouse_two,
                product,
                current_request,
                old_request,
                done_request,
                residual_box,
                empty_box,
                distributed_box,
                old_residual_box,
                done_box,
                current_cargo,
                done_cargo,
                *lines,
            ]
        )
        await session.commit()
    return {
        "product_id": product.id,
        "residual_box_id": residual_box.id,
        "distributed_box_id": distributed_box.id,
        "done_box_id": done_box.id,
        "current_request_id": current_request.id,
    }


async def _read_state(ids: dict[str, uuid.UUID]) -> tuple[object, ...]:
    async with SessionLocal() as session:
        boxes = (
            (
                await session.execute(
                    select(InboundIntakeBox)
                    .where(InboundIntakeBox.id.in_([ids["residual_box_id"], ids["done_box_id"]]))
                    .order_by(InboundIntakeBox.internal_barcode)
                )
            )
            .scalars()
            .all()
        )
        lines = (
            (
                await session.execute(
                    select(InboundIntakeBoxLine)
                    .where(InboundIntakeBoxLine.box_id == ids["residual_box_id"])
                    .order_by(InboundIntakeBoxLine.id)
                )
            )
            .scalars()
            .all()
        )
        request = await session.get(InboundIntakeRequest, ids["current_request_id"])
        assert request is not None
        return (
            tuple((box.intake_opened_at, box.intake_closed_at) for box in boxes),
            tuple((line.quantity, line.posted_qty) for line in lines),
            request.status,
        )


@pytest.mark.asyncio
async def test_catalog_list_and_lookup_are_tenant_scoped_read_only(
    async_client: AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    admin_headers = await _register_admin(async_client, suffix)
    tenant_id = await _tenant_id(async_client, admin_headers)
    ids = await _seed_packages(tenant_id)
    before = await _read_state(ids)

    listed = await async_client.get("/operations/inbound-packages", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["internal_barcode"] for row in rows] == [
        "INB-CURRENT-RESIDUAL",
        "INB-CURRENT-EMPTY",
        "ICG-CURRENT",
        "INB-OLD-RESIDUAL",
    ]
    residual = rows[0]
    assert residual["kind"] == "box"
    assert residual["fully_distributed"] is False
    assert residual["remaining_qty"] == 6
    assert residual["lines"] == [{"product_id": str(ids["product_id"]), "remaining_qty": 6}]
    assert residual["warehouse_name"] == "Основной"
    assert rows[1]["remaining_qty"] == 0
    assert rows[1]["fully_distributed"] is False
    assert rows[2]["kind"] == "cargo_place"
    assert rows[2]["composition_tracked"] is False
    assert rows[2]["fully_distributed"] is False
    assert rows[2]["remaining_qty"] is None
    assert rows[3]["warehouse_name"] == "Резерв"

    done_box = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=inb-done-distributed",
        headers=admin_headers,
    )
    assert done_box.status_code == 200, done_box.text
    assert done_box.json()["remaining_qty"] == 0
    assert done_box.json()["lines"] == []
    assert done_box.json()["intake_status"] == "done"
    assert done_box.json()["fully_distributed"] is True

    distributed_box = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=INB-CURRENT-DISTRIBUTED",
        headers=admin_headers,
    )
    assert distributed_box.status_code == 200, distributed_box.text
    assert distributed_box.json()["intake_status"] == "sorting"
    assert distributed_box.json()["remaining_qty"] == 0
    assert distributed_box.json()["lines"] == []
    assert distributed_box.json()["fully_distributed"] is True
    assert "INB-CURRENT-DISTRIBUTED" not in [row["internal_barcode"] for row in rows]

    done_cargo = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=ICG-DONE", headers=admin_headers
    )
    assert done_cargo.status_code == 200, done_cargo.text
    assert done_cargo.json()["kind"] == "cargo_place"
    assert done_cargo.json()["intake_status"] == "done"

    other_headers = await _register_admin(async_client, f"other-{suffix}")
    other_tenant_id = await _tenant_id(async_client, other_headers)
    async with SessionLocal() as session:
        other_warehouse = Warehouse(
            id=uuid.uuid4(), tenant_id=other_tenant_id, name="Other", code="other"
        )
        other_request = InboundIntakeRequest(
            id=uuid.uuid4(),
            tenant_id=other_tenant_id,
            warehouse_id=other_warehouse.id,
            status="receiving",
            display_number="№000001",
        )
        other_box = InboundIntakeBox(
            id=uuid.uuid4(),
            tenant_id=other_tenant_id,
            request_id=other_request.id,
            box_number=1,
            internal_barcode="INB-OTHER-TENANT",
        )
        session.add_all([other_warehouse, other_request, other_box])
        await session.commit()

    unknown = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=INB-UNKNOWN", headers=admin_headers
    )
    foreign = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=INB-OTHER-TENANT",
        headers=admin_headers,
    )
    assert unknown.status_code == foreign.status_code == 404
    assert unknown.json() == foreign.json() == {"detail": "package_not_found"}
    assert await _read_state(ids) == before


@pytest.mark.asyncio
async def test_catalog_list_loads_only_current_package_rows(
    async_client: AsyncClient,
) -> None:
    """TC-S16-003: list SQL excludes historical package rows before eager loading."""
    suffix = uuid.uuid4().hex[:12]
    admin_headers = await _register_admin(async_client, suffix)
    tenant_id = await _tenant_id(async_client, admin_headers)
    ids = await _seed_packages(tenant_id)
    statements: list[tuple[str, object]] = []

    def capture_sql(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if "inbound_intake_" in statement:
            statements.append((statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", capture_sql)
    try:
        response = await async_client.get("/operations/inbound-packages", headers=admin_headers)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_sql)

    assert response.status_code == 200, response.text
    assert [row["internal_barcode"] for row in response.json()] == [
        "INB-CURRENT-RESIDUAL",
        "INB-CURRENT-EMPTY",
        "ICG-CURRENT",
        "INB-OLD-RESIDUAL",
    ]

    box_statement = next(
        statement
        for statement, _parameters in statements
        if "FROM inbound_intake_boxes" in statement
    )
    assert "EXISTS" in box_statement
    assert (
        "inbound_intake_box_lines.quantity > inbound_intake_box_lines.posted_qty"
        in box_statement
    )

    cargo_statement = next(
        statement
        for statement, _parameters in statements
        if "FROM inbound_intake_cargo_places" in statement
    )
    assert "inbound_intake_requests.status != ?" in cargo_statement

    line_parameters = next(
        parameters
        for statement, parameters in statements
        if "FROM inbound_intake_box_lines" in statement
    )
    assert str(ids["distributed_box_id"]) not in str(line_parameters)
    assert str(ids["done_box_id"]) not in str(line_parameters)


@pytest.mark.asyncio
async def test_catalog_package_access_matches_catalog_read_permissions(
    async_client: AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    admin_headers = await _register_admin(async_client, suffix)
    tenant_id = await _tenant_id(async_client, admin_headers)
    await _seed_packages(tenant_id)

    cells_headers = await _create_staff(
        async_client, admin_headers, suffix, "cells", {"cells": True}
    )
    inventory_headers = await _create_staff(
        async_client, admin_headers, suffix, "inventory", {"inventory": True}
    )
    reception_headers = await _create_staff(
        async_client, admin_headers, suffix, "reception", {"reception": True}
    )

    for headers in (admin_headers, cells_headers, inventory_headers):
        listed = await async_client.get("/operations/inbound-packages", headers=headers)
        looked_up = await async_client.get(
            "/operations/inbound-packages/lookup?barcode=INB-CURRENT-RESIDUAL",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert looked_up.status_code == 200, looked_up.text

    denied_list = await async_client.get("/operations/inbound-packages", headers=reception_headers)
    denied_lookup = await async_client.get(
        "/operations/inbound-packages/lookup?barcode=INB-CURRENT-RESIDUAL",
        headers=reception_headers,
    )
    assert denied_list.status_code == denied_lookup.status_code == 403
