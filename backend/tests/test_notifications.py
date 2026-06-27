from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.notification import SEVERITY_INFO
from app.services import notification_service as notify_svc
from app.services.notification_service import NotificationRecipient


async def _register_admin(async_client: AsyncClient) -> tuple[str, dict[str, str], str]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Notify Co {suffix}",
            "slug": f"notify-{suffix}",
            "admin_email": f"notify-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return suffix, headers, str(me.json()["id"])


async def _create_seller(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> tuple[dict[str, str], str]:
    email = f"notify-seller-{suffix}@example.com"
    created = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Notify Seller", "email": email, "password": "password123"},
    )
    assert created.status_code == 201, created.text
    seller_id = str(created.json()["seller_id"])

    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, seller_id


async def _seed_notification(
    tenant_id: uuid.UUID,
    recipient: NotificationRecipient,
    *,
    title: str,
) -> uuid.UUID:
    async with SessionLocal() as session:
        row = await notify_svc.notify(
            session,
            tenant_id,
            recipient,
            type="test_event",
            severity=SEVERITY_INFO,
            title=title,
            body="body",
            link="/test",
        )
        await session.commit()
        return row.id


@pytest.mark.asyncio
async def test_notifications_user_scope_isolated(async_client: AsyncClient) -> None:
    _, admin_headers, admin_user_id = await _register_admin(async_client)

    me = await async_client.get("/auth/me", headers=admin_headers)
    tenant_id = uuid.UUID(str(me.json()["tenant_id"]))

    other_user_id = str(uuid.uuid4())
    await _seed_notification(
        tenant_id,
        NotificationRecipient("user", other_user_id),
        title="foreign",
    )
    own_id = await _seed_notification(
        tenant_id,
        NotificationRecipient("user", admin_user_id),
        title="mine",
    )

    listed = await async_client.get("/operations/notifications", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(own_id)
    assert body["items"][0]["title"] == "mine"


@pytest.mark.asyncio
async def test_notifications_seller_scope_isolated(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id = await _create_seller(async_client, admin_headers, suffix)

    me = await async_client.get("/auth/me", headers=admin_headers)
    tenant_id = uuid.UUID(str(me.json()["tenant_id"]))

    await _seed_notification(
        tenant_id,
        NotificationRecipient("seller", seller_id),
        title="for seller",
    )
    await _seed_notification(
        tenant_id,
        NotificationRecipient("seller", str(uuid.uuid4())),
        title="other seller",
    )

    listed = await async_client.get("/operations/notifications", headers=seller_headers)
    assert listed.status_code == 200
    assert listed.json()["unread_count"] == 1
    assert listed.json()["items"][0]["title"] == "for seller"


@pytest.mark.asyncio
async def test_notifications_ff_portal_visible_to_admin_not_seller(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, _ = await _create_seller(async_client, admin_headers, suffix)

    me = await async_client.get("/auth/me", headers=admin_headers)
    tenant_id = uuid.UUID(str(me.json()["tenant_id"]))

    async with SessionLocal() as session:
        await notify_svc.notify_ff_portal(
            session,
            tenant_id,
            type="inbound_created",
            severity=SEVERITY_INFO,
            title="Новая приёмка",
            body="Селлер создал приёмку",
            link="/inbound/1",
        )
        await session.commit()

    admin_list = await async_client.get("/operations/notifications", headers=admin_headers)
    assert admin_list.status_code == 200
    assert admin_list.json()["unread_count"] == 1
    assert admin_list.json()["items"][0]["title"] == "Новая приёмка"

    seller_list = await async_client.get("/operations/notifications", headers=seller_headers)
    assert seller_list.status_code == 200
    assert seller_list.json()["unread_count"] == 0
    assert seller_list.json()["items"] == []


@pytest.mark.asyncio
async def test_notifications_mark_read_and_read_all(async_client: AsyncClient) -> None:
    _, admin_headers, admin_user_id = await _register_admin(async_client)

    me = await async_client.get("/auth/me", headers=admin_headers)
    tenant_id = uuid.UUID(str(me.json()["tenant_id"]))

    n1 = await _seed_notification(
        tenant_id,
        NotificationRecipient("user", admin_user_id),
        title="one",
    )
    await _seed_notification(
        tenant_id,
        NotificationRecipient("user", admin_user_id),
        title="two",
    )

    unread = await async_client.get(
        "/operations/notifications",
        headers=admin_headers,
        params={"unread": "true"},
    )
    assert unread.status_code == 200
    assert len(unread.json()["items"]) == 2

    marked = await async_client.post(
        f"/operations/notifications/{n1}/read",
        headers=admin_headers,
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    still_unread = await async_client.get(
        "/operations/notifications",
        headers=admin_headers,
        params={"unread": "true"},
    )
    assert len(still_unread.json()["items"]) == 1

    read_all = await async_client.post(
        "/operations/notifications/read-all",
        headers=admin_headers,
    )
    assert read_all.status_code == 200
    assert read_all.json()["marked"] == 1

    none_left = await async_client.get(
        "/operations/notifications",
        headers=admin_headers,
        params={"unread": "true"},
    )
    assert none_left.json()["items"] == []
    assert none_left.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_notifications_mark_read_foreign_returns_404(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id = await _create_seller(async_client, admin_headers, suffix)

    me = await async_client.get("/auth/me", headers=admin_headers)
    tenant_id = uuid.UUID(str(me.json()["tenant_id"]))

    notification_id = await _seed_notification(
        tenant_id,
        NotificationRecipient("seller", seller_id),
        title="seller only",
    )

    forbidden = await async_client.post(
        f"/operations/notifications/{notification_id}/read",
        headers=admin_headers,
    )
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"] == "notification_not_found"

    _ = seller_headers
