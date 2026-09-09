"""WMS-325: append-only audit for staff permission mutations.

The source card names `update_staff_permissions` (and calls out that the
existing DocumentEvent middleware tracks only inbound/FBS/MP documents; the
permission service commits without an event). This audit is now written on
each covered mutation into the SAME `document_event` table — no new parallel
journal. Test the four permission-touching mutations we own here:

- ``patch_staff_permissions`` (fulfillment_staff, staff-accounts permissions PATCH)
- ``patch_seller_staff_permissions`` (fulfillment_seller, seller-staff PATCH)
- ``post_staff_account`` (create FF staff, defaults all-False)
- ``post_seller_staff_account`` (create seller staff with initial permission set)
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document_event import (
    DOCUMENT_TYPE_STAFF_USER,
    EVENT_PERMISSIONS_CHANGED,
    EVENT_STAFF_USER_CREATED,
    SOURCE_USER,
    DocumentEvent,
)
from app.services.tokens import decode_access_token


async def _register_admin(
    async_client: AsyncClient, suffix: str
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"PermAudit {suffix}",
            "slug": f"perm-audit-{suffix}",
            "admin_email": f"perm-audit-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    payload = decode_access_token(token)
    return (
        {"Authorization": f"Bearer {token}"},
        uuid.UUID(str(payload["tenant_id"])),
        uuid.UUID(str(payload["sub"])),
    )


async def _fetch_events_for_target(
    tenant_id: uuid.UUID, target_user_id: uuid.UUID
) -> list[DocumentEvent]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(DocumentEvent)
            .where(
                DocumentEvent.tenant_id == tenant_id,
                DocumentEvent.document_type == DOCUMENT_TYPE_STAFF_USER,
                DocumentEvent.document_id == target_user_id,
            )
            .order_by(DocumentEvent.occurred_at.asc(), DocumentEvent.created_at.asc())
        )
        return list(rows.all())


@pytest.mark.asyncio
async def test_ff_staff_permissions_patch_writes_audit_with_before_after_and_actor(
    async_client: AsyncClient,
) -> None:
    """PATCH /auth/staff-accounts/{id}/permissions writes acting_user + before/after."""
    suffix = str(int(time.time() * 1000))
    ah, tenant_id, admin_id = await _register_admin(async_client, suffix)

    created = await async_client.post(
        "/auth/staff-accounts",
        headers=ah,
        json={"email": f"staff-{suffix}@example.com"},
    )
    assert created.status_code == 201, created.text
    target_id = uuid.UUID(created.json()["id"])

    # Creation itself must produce a staff_user_created event with defaults (all False).
    create_events = await _fetch_events_for_target(tenant_id, target_id)
    assert len(create_events) == 1, [
        (e.event_type, e.payload_json) for e in create_events
    ]
    first = create_events[0]
    assert first.event_type == EVENT_STAFF_USER_CREATED
    assert first.actor_user_id == admin_id
    assert first.source == SOURCE_USER
    assert first.payload_json["target_user_id"] == str(target_id)
    assert first.payload_json["acting_user_id"] == str(admin_id)
    assert first.payload_json["role"] == "fulfillment_staff"
    assert first.payload_json["before"] is None
    assert first.payload_json["after"]["reception"] is False
    assert first.payload_json["after"]["mp_shipments"] is False

    # Grant reception and mp_shipments.
    patch = await async_client.patch(
        f"/auth/staff-accounts/{target_id}/permissions",
        headers=ah,
        json={
            "settings": False,
            "mp_shipments": True,
            "reception": True,
            "cells": False,
            "inventory": False,
            "packaging": False,
            "shift_lead": False,
        },
    )
    assert patch.status_code == 200, patch.text

    events = await _fetch_events_for_target(tenant_id, target_id)
    assert len(events) == 2, [
        (e.event_type, e.payload_json) for e in events
    ]
    perm_event = events[1]
    assert perm_event.event_type == EVENT_PERMISSIONS_CHANGED
    assert perm_event.actor_user_id == admin_id
    assert perm_event.source == SOURCE_USER
    payload = perm_event.payload_json
    assert payload["role"] == "fulfillment_staff"
    assert payload["target_user_id"] == str(target_id)
    assert payload["acting_user_id"] == str(admin_id)
    assert payload["before"]["reception"] is False
    assert payload["before"]["mp_shipments"] is False
    assert payload["after"]["reception"] is True
    assert payload["after"]["mp_shipments"] is True
    assert perm_event.occurred_at is not None


@pytest.mark.asyncio
async def test_ff_staff_permissions_patch_without_change_writes_no_extra_event(
    async_client: AsyncClient,
) -> None:
    """No effective change (same set) — no duplicate audit row is appended."""
    suffix = str(int(time.time() * 1000) + 1)
    ah, tenant_id, _admin_id = await _register_admin(async_client, suffix)

    created = await async_client.post(
        "/auth/staff-accounts",
        headers=ah,
        json={"email": f"staff-noop-{suffix}@example.com"},
    )
    assert created.status_code == 201, created.text
    target_id = uuid.UUID(created.json()["id"])

    noop = await async_client.patch(
        f"/auth/staff-accounts/{target_id}/permissions",
        headers=ah,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": False,
            "shift_lead": False,
        },
    )
    assert noop.status_code == 200, noop.text

    events = await _fetch_events_for_target(tenant_id, target_id)
    # Only the creation event; noop PATCH must not append a second row.
    assert [e.event_type for e in events] == [EVENT_STAFF_USER_CREATED]


@pytest.mark.asyncio
async def test_seller_staff_permission_mutations_write_audit_rows(
    async_client: AsyncClient,
) -> None:
    """Seller-side create + patch both hit the same document_event journal."""
    suffix = str(int(time.time() * 1000) + 2)
    ah, tenant_id, _admin_id = await _register_admin(async_client, suffix)

    # Create seller and an owner-role user via admin.
    from app.core.roles import FULFILLMENT_SELLER
    from app.models.seller_staff_permissions import SellerStaffPermissions
    from app.models.user import User

    # Use the admin to create a seller with an owner account.
    resp = await async_client.post(
        "/sellers/with-account",
        headers=ah,
        json={
            "name": f"Seller {suffix}",
            "email": f"owner-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code in (200, 201), resp.text

    owner_login = await async_client.post(
        "/auth/login",
        json={"email": f"owner-{suffix}@example.com", "password": "password123"},
    )
    assert owner_login.status_code == 200, owner_login.text
    owner_token = str(owner_login.json()["access_token"])
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    owner_id = uuid.UUID(str(decode_access_token(owner_token)["sub"]))

    # Owner grants staff-management to itself so it can invite staff.
    async with SessionLocal() as session:
        # Owner has no permissions row (is_owner) — grant staff via inserting row.
        stmt = select(User).where(User.email == f"owner-{suffix}@example.com")
        user = (await session.execute(stmt)).scalar_one()
        assert user.role == FULFILLMENT_SELLER
        row = await session.get(SellerStaffPermissions, user.id)
        if row is None:
            row = SellerStaffPermissions(
                user_id=user.id,
                can_documents=True,
                can_products=True,
                can_honest_sign=True,
                can_settings=True,
                can_staff=True,
            )
            session.add(row)
        else:
            row.can_staff = True
            row.can_documents = True
            row.can_products = True
            row.can_honest_sign = True
            row.can_settings = True
        await session.commit()

    # Owner creates staff.
    created = await async_client.post(
        "/auth/seller-staff-accounts",
        headers=owner_headers,
        json={
            "email": f"seller-staff-{suffix}@example.com",
            "permissions": {
                "documents": True,
                "products": False,
                "honest_sign": False,
                "settings": False,
                "staff": False,
            },
        },
    )
    assert created.status_code == 201, created.text
    target_id = uuid.UUID(created.json()["id"])

    events = await _fetch_events_for_target(tenant_id, target_id)
    assert len(events) == 1, [
        (e.event_type, e.payload_json) for e in events
    ]
    creation = events[0]
    assert creation.event_type == EVENT_STAFF_USER_CREATED
    assert creation.actor_user_id == owner_id
    assert creation.payload_json["role"] == "fulfillment_seller"
    assert creation.payload_json["after"]["documents"] is True
    assert creation.payload_json["after"]["products"] is False

    # Owner patches permissions.
    patch = await async_client.patch(
        f"/auth/seller-staff-accounts/{target_id}/permissions",
        headers=owner_headers,
        json={
            "documents": True,
            "products": True,
            "honest_sign": True,
            "settings": False,
            "staff": False,
        },
    )
    assert patch.status_code == 200, patch.text

    events = await _fetch_events_for_target(tenant_id, target_id)
    assert len(events) == 2, [
        (e.event_type, e.payload_json) for e in events
    ]
    change = events[1]
    assert change.event_type == EVENT_PERMISSIONS_CHANGED
    assert change.actor_user_id == owner_id
    assert change.payload_json["role"] == "fulfillment_seller"
    assert change.payload_json["target_user_id"] == str(target_id)
    assert change.payload_json["acting_user_id"] == str(owner_id)
    assert change.payload_json["before"]["products"] is False
    assert change.payload_json["after"]["products"] is True
    assert change.payload_json["after"]["honest_sign"] is True


@pytest.mark.asyncio
async def test_staff_history_is_available_over_http_and_keeps_rate_changes(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers, _tenant_id, admin_id = await _register_admin(async_client, suffix)
    created = await async_client.post(
        "/auth/staff-accounts", headers=headers,
        json={"email": f"rate-{suffix}@example.com"},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    for _ in range(2):
        response = await async_client.patch(
            f"/auth/staff-accounts/{staff_id}/packaging-rate", headers=headers,
            json={"rate_rub": "12.34"},
        )
        assert response.status_code == 200, response.text
    response = await async_client.get(
        "/operations/document-events", headers=headers,
        params={"document_type": "staff_user", "document_id": staff_id},
    )
    assert response.status_code == 200, response.text
    rates = [row for row in response.json() if row["event_type"] == "staff_rate_changed"]
    assert len(rates) == 1
    assert rates[0]["actor"]["id"] == str(admin_id)
    assert rates[0]["payload"]["before"] == {"packaging_rate_kopecks": 0}
    assert rates[0]["payload"]["after"] == {"packaging_rate_kopecks": 1234}
    other, _, _ = await _register_admin(async_client, suffix + "other")
    forbidden = await async_client.get(
        "/operations/document-events", headers=other,
        params={"document_type": "staff_user", "document_id": staff_id},
    )
    assert forbidden.status_code == 200, forbidden.text
    assert forbidden.json() == []
