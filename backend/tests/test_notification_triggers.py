from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.notification import Notification


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Trig Co {suffix}",
            "slug": f"trig-{suffix}",
            "admin_email": f"trig-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    me = await async_client.get("/auth/me", headers=headers)
    return headers, str(me.json()["tenant_id"])


async def _create_seller_with_login(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> dict[str, str]:
    email = f"trig-seller-{suffix}@example.com"
    created = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Trig Seller", "email": email, "password": "password123"},
    )
    assert created.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_inbound_create_notifies_ff(async_client: AsyncClient) -> None:
    admin_headers, tenant_id = await _register_admin(async_client)
    suffix = str(int(time.time() * 1000))
    seller_headers = await _create_seller_with_login(async_client, admin_headers, suffix)

    wh = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "WH", "code": f"wh-{suffix}"},
    )
    assert wh.status_code in (200, 201)
    warehouse_id = wh.json()["id"]

    created = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=seller_headers,
        json={"warehouse_id": warehouse_id},
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        note = (
            await session.execute(
                select(Notification).where(
                    Notification.tenant_id == uuid.UUID(tenant_id),
                    Notification.type == "inbound_created",
                )
            )
        ).scalar_one()
        assert note.title == "Новая приёмка"
        assert note.link == "/app/ff/reception"


@pytest.mark.asyncio
async def test_marketplace_unload_create_notifies_ff(async_client: AsyncClient) -> None:
    admin_headers, tenant_id = await _register_admin(async_client)
    suffix = str(int(time.time() * 1000))

    wh = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "WH2", "code": f"wh2-{suffix}"},
    )
    warehouse_id = wh.json()["id"]
    seller = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": "Unload Seller", "email": f"ul-{suffix}@example.com"},
    )
    seller_id = seller.json()["id"]

    created = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=admin_headers,
        json={"warehouse_id": warehouse_id, "seller_id": seller_id},
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        note = (
            await session.execute(
                select(Notification).where(
                    Notification.tenant_id == uuid.UUID(tenant_id),
                    Notification.type == "marketplace_unload_created",
                )
            )
        ).scalar_one()
        assert note.link == "/app/ff/mp-shipments"
