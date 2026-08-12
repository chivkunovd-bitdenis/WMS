from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadRequest


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = uuid.uuid4().hex[:10]
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Seller Staff Co",
            "slug": f"seller-staff-{suffix}",
            "admin_email": f"seller-staff-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}, suffix


async def _seller_login_headers(
    async_client: AsyncClient,
    email: str,
    password: str = "password123",
) -> dict[str, str]:
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_seller_owner_creates_staff_user_and_updates_permissions(
    async_client: AsyncClient,
) -> None:
    ah, suffix = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=ah,
        json={"name": "Seller Staff Brand"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    owner_email = f"seller-owner-{suffix}@example.com"
    owner = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": seller_id,
            "email": owner_email,
            "password": "password123",
        },
    )
    assert owner.status_code == 201, owner.text
    owner_headers = await _seller_login_headers(async_client, owner_email)

    me_owner = await async_client.get("/auth/me", headers=owner_headers)
    assert me_owner.status_code == 200
    assert me_owner.json()["seller_permissions"] == {
        "documents": True,
        "products": True,
        "honest_sign": True,
        "settings": True,
        "staff": True,
    }

    initial_staff = await async_client.get(
        "/auth/seller-staff-accounts",
        headers=owner_headers,
    )
    assert initial_staff.status_code == 200, initial_staff.text
    owner_row = initial_staff.json()[0]
    assert owner_row["email"] == owner_email
    assert owner_row["is_owner"] is True

    staff_email = f"seller-staff-user-{suffix}@example.com"
    created = await async_client.post(
        "/auth/seller-staff-accounts",
        headers=owner_headers,
        json={
            "email": staff_email,
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
    staff_id = created.json()["id"]
    assert created.json()["must_set_password"] is True
    assert created.json()["is_owner"] is False
    assert created.json()["permissions"]["documents"] is True
    assert created.json()["permissions"]["products"] is False

    setup = await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    assert setup.status_code == 200, setup.text
    staff_headers = await _seller_login_headers(async_client, staff_email)
    me_staff = await async_client.get("/auth/me", headers=staff_headers)
    assert me_staff.status_code == 200
    assert me_staff.json()["seller_permissions"]["documents"] is True
    assert me_staff.json()["seller_permissions"]["staff"] is False

    staff_list_forbidden = await async_client.get(
        "/auth/seller-staff-accounts",
        headers=staff_headers,
    )
    assert staff_list_forbidden.status_code == 403

    patched = await async_client.patch(
        f"/auth/seller-staff-accounts/{staff_id}/permissions",
        headers=owner_headers,
        json={
            "documents": True,
            "products": True,
            "honest_sign": False,
            "settings": True,
            "staff": True,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["permissions"]["staff"] is True
    assert patched.json()["permissions"]["settings"] is True

    staff_list_allowed = await async_client.get(
        "/auth/seller-staff-accounts",
        headers=staff_headers,
    )
    assert staff_list_allowed.status_code == 200, staff_list_allowed.text

    owner_patch = await async_client.patch(
        f"/auth/seller-staff-accounts/{owner_row['id']}/permissions",
        headers=owner_headers,
        json={
            "documents": False,
            "products": False,
            "honest_sign": False,
            "settings": False,
            "staff": False,
        },
    )
    assert owner_patch.status_code == 409
    assert owner_patch.json()["detail"] == "owner_protected"


@pytest.mark.asyncio
async def test_seller_delete_only_draft_documents(async_client: AsyncClient) -> None:
    ah, suffix = await _register_admin(async_client)
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code in (200, 201), wh.text
    warehouse_id = wh.json()["id"]
    seller = await async_client.post(
        "/sellers",
        headers=ah,
        json={"name": "Delete Drafts Seller"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]
    seller_email = f"delete-drafts-seller-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": seller_id,
            "email": seller_email,
            "password": "password123",
        },
    )
    assert account.status_code == 201, account.text
    sh = await _seller_login_headers(async_client, seller_email)

    inbound_draft = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={"warehouse_id": warehouse_id},
    )
    assert inbound_draft.status_code == 201, inbound_draft.text
    inbound_id = inbound_draft.json()["id"]
    inbound_deleted = await async_client.delete(
        f"/operations/inbound-intake-requests/{inbound_id}",
        headers=sh,
    )
    assert inbound_deleted.status_code == 204, inbound_deleted.text
    inbound_gone = await async_client.get(
        f"/operations/inbound-intake-requests/{inbound_id}",
        headers=sh,
    )
    assert inbound_gone.status_code == 404

    inbound_submitted = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={"warehouse_id": warehouse_id},
    )
    assert inbound_submitted.status_code == 201, inbound_submitted.text
    inbound_submitted_id = inbound_submitted.json()["id"]
    async with SessionLocal() as session:
        inbound_req = await session.get(
            InboundIntakeRequest,
            uuid.UUID(inbound_submitted_id),
        )
        assert inbound_req is not None
        inbound_req.status = "submitted"
        await session.commit()
    inbound_blocked = await async_client.delete(
        f"/operations/inbound-intake-requests/{inbound_submitted_id}",
        headers=sh,
    )
    assert inbound_blocked.status_code == 409
    assert inbound_blocked.json()["detail"] == "not_draft"

    mp_draft = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=sh,
        json={"warehouse_id": warehouse_id},
    )
    assert mp_draft.status_code == 201, mp_draft.text
    mp_id = mp_draft.json()["id"]
    mp_deleted = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mp_id}",
        headers=sh,
    )
    assert mp_deleted.status_code == 204, mp_deleted.text
    mp_gone = await async_client.get(
        f"/operations/marketplace-unload-requests/{mp_id}",
        headers=sh,
    )
    assert mp_gone.status_code == 404

    mp_submitted = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=sh,
        json={"warehouse_id": warehouse_id},
    )
    assert mp_submitted.status_code == 201, mp_submitted.text
    mp_submitted_id = mp_submitted.json()["id"]
    async with SessionLocal() as session:
        mp_req = await session.get(
            MarketplaceUnloadRequest,
            uuid.UUID(mp_submitted_id),
        )
        assert mp_req is not None
        mp_req.status = "submitted"
        await session.commit()
    mp_blocked = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mp_submitted_id}",
        headers=sh,
    )
    assert mp_blocked.status_code == 409
    assert mp_blocked.json()["detail"] == "not_draft"
