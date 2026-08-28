from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.warehouse import Warehouse


@pytest.mark.asyncio
async def test_scan_resolve_route_returns_match_and_structured_failures(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Scan route {suffix}",
            "slug": f"scan-route-{suffix}",
            "admin_email": f"scan-route-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    warehouse = Warehouse(
        tenant_id=tenant_id,
        name="Склад API",
        code="api-warehouse",
        barcode="API-WAREHOUSE-BARCODE",
    )
    async with SessionLocal() as session:
        session.add(warehouse)
        await session.commit()

    resolved = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "API-WAREHOUSE-BARCODE", "warehouse_id": str(warehouse.id)},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json() == {
        "type": "warehouse",
        "id": str(warehouse.id),
        "name": "Склад API",
        "warehouse_id": str(warehouse.id),
    }

    unknown = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "UNKNOWN-API-CODE"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == {
        "code": "scan_not_found",
        "message": "Объект с таким кодом не найден.",
        "matches": [],
    }

    unauthenticated = await async_client.get(
        "/operations/scan/resolve",
        params={"code": "API-WAREHOUSE-BARCODE"},
    )
    assert unauthenticated.status_code == 401
