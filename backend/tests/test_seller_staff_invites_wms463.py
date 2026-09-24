from __future__ import annotations

import asyncio
import re
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.user import User
from app.services import auth_service
from app.services.passwords import hash_password

PERMISSIONS = dict(documents=True, products=False, honest_sign=False, settings=False, staff=False)


async def owner(client: AsyncClient, slug: str, admin: dict | None = None) -> dict[str, str]:
    if admin is None:
        registered = await client.post(
            "/auth/register",
            json={
                "organization_name": slug,
                "slug": slug,
                "admin_email": f"admin-{slug}@example.com",
                "password": "password123",
            },
        )
        assert registered.status_code == 200, registered.text
        admin = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await client.post("/sellers", headers=admin, json={"name": slug})
    assert seller.status_code == 201, seller.text
    account = await client.post(
        "/auth/seller-accounts",
        headers=admin,
        json={
            "seller_id": seller.json()["id"],
            "email": f"owner-{slug}@example.com",
            "password": "password123",
        },
    )
    assert account.status_code == 201, account.text
    login = await client.post(
        "/auth/login",
        json={
            "email": f"owner-{slug}@example.com",
            "password": "password123",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def mail(monkeypatch):
    messages = []

    async def capture(**kwargs):
        messages.append(kwargs)
        return True

    monkeypatch.setattr(auth_service, "send_email", capture)
    return messages


def link_token(message: dict) -> str:
    link = re.search(r"https?://\S+", message["body"]).group()
    assert urlparse(link).path == "/seller/set-password"
    return parse_qs(urlparse(link).query)["token"][0]


async def create(client, headers, email="employee@example.com"):
    return await client.post(
        "/auth/seller-staff-accounts",
        headers=headers,
        json={
            "email": email,
            "full_name": "Иван Петров",
            "job_title": "Менеджер",
            "permissions": PERMISSIONS,
        },
    )


@pytest.mark.asyncio
async def test_email_invitation_resend_activation_and_permissions(async_client, mail):
    headers = await owner(async_client, "invite463")
    created = await create(async_client, headers, "Employee@Example.com")
    assert created.status_code == 201, created.text
    staff = created.json()
    assert staff["must_set_password"] and staff["email"] == "employee@example.com"
    assert len(mail) == 1 and mail[0]["to"] == "employee@example.com"
    initial_token = link_token(mail[0])
    login = await async_client.post(
        "/auth/login",
        json={
            "email": staff["email"],
            "password": "password123",
        },
    )
    assert login.status_code == 401
    async with SessionLocal() as session:
        initial = await session.get(User, uuid.UUID(staff["id"]))
        original_hash = initial.password_hash
    for _ in range(2):
        repeated = await async_client.post(
            f"/auth/seller-staff-accounts/{staff['id']}/invite", headers=headers
        )
        assert repeated.status_code == 204
    assert len(mail) == 3
    async with SessionLocal() as session:
        unchanged = await session.get(User, uuid.UUID(staff["id"]))
        assert unchanged.password_hash == original_hash
    activated = await async_client.post(
        "/auth/set-password",
        json={
            "token": initial_token,
            "password": "self-password-463",
        },
    )
    assert activated.status_code == 200, activated.text
    employee = {"Authorization": f"Bearer {activated.json()['access_token']}"}
    me = (await async_client.get("/auth/me", headers=employee)).json()
    assert me["id"] == staff["id"] and me["seller_id"] == staff["seller_id"]
    assert me["seller_permissions"] == PERMISSIONS
    for path in ["/products", "/auth/seller-staff-accounts"]:
        assert (await async_client.get(path, headers=employee)).status_code == 403
    assert (
        await async_client.get("/operations/inbound-intake-requests", headers=employee)
    ).status_code == 200
    for message in mail:
        used = await async_client.post(
            "/auth/set-password",
            json={
                "token": link_token(message),
                "password": "another-password",
            },
        )
        assert used.status_code == 409
    resend = await async_client.post(
        f"/auth/seller-staff-accounts/{staff['id']}/invite", headers=headers
    )
    assert resend.status_code == 409 and resend.json()["detail"] == "account_already_active"
    assert len(mail) == 3
    login = await async_client.post(
        "/auth/login",
        json={
            "email": staff["email"],
            "password": "self-password-463",
        },
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_creation_validation_duplicate_and_concurrency(async_client, mail):
    headers = await owner(async_client, "duplicate463")
    for bad in [None, "", "not-an-email"]:
        response = await async_client.post(
            "/auth/seller-staff-accounts", headers=headers, json={"full_name": "Иван", "email": bad}
        )
        assert response.status_code == 422
    with_password = await async_client.post(
        "/auth/seller-staff-accounts",
        headers=headers,
        json={
            "full_name": "Иван",
            "email": "valid@example.com",
            "password": "known-password",
        },
    )
    assert with_password.status_code == 422 and not mail
    results = await asyncio.gather(create(async_client, headers), create(async_client, headers))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert len(mail) == 1
    retry = await create(async_client, headers, "EMPLOYEE@EXAMPLE.COM")
    assert retry.status_code == 409 and retry.json()["detail"] == "email_taken"
    other = await owner(async_client, "other463")
    retry_other = await create(async_client, other)
    assert retry_other.status_code == 409 and len(mail) == 1
    rows = (await async_client.get("/auth/seller-staff-accounts", headers=headers)).json()
    assert len([r for r in rows if not r["is_owner"]]) == 1


@pytest.mark.asyncio
async def test_mail_failure_preserves_account_and_resend_recovers(async_client, monkeypatch, mail):
    headers = await owner(async_client, "mail463")
    capture = auth_service.send_email

    async def unavailable(**kwargs):
        return False

    monkeypatch.setattr(auth_service, "send_email", unavailable)
    created = await create(async_client, headers)
    assert created.status_code == 201 and created.json()["must_set_password"]
    assert not mail
    monkeypatch.setattr(auth_service, "send_email", capture)
    staff_id = created.json()["id"]
    resent = await async_client.post(
        f"/auth/seller-staff-accounts/{staff_id}/invite", headers=headers
    )
    assert resent.status_code == 204 and len(mail) == 1
    accepted = await async_client.post(
        "/auth/set-password",
        json={
            "token": link_token(mail[0]),
            "password": "self-password-463",
        },
    )
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_legacy_email_transition_and_foreign_isolation(async_client, mail):
    headers = await owner(async_client, "legacy463")
    foreign = await owner(async_client, "foreign463")
    admin_login = await async_client.post(
        "/auth/login",
        json={
            "email": "admin-legacy463@example.com",
            "password": "password123",
        },
    )
    same_tenant = await owner(
        async_client,
        "same-tenant463",
        {
            "Authorization": f"Bearer {admin_login.json()['access_token']}",
        },
    )
    owner_me = (await async_client.get("/auth/me", headers=headers)).json()
    async with SessionLocal() as session:
        manager = await session.get(User, uuid.UUID(owner_me["id"]))
        legacy = User(
            tenant_id=manager.tenant_id,
            seller_id=manager.seller_id,
            role="fulfillment_seller",
            full_name="Старый Сотрудник",
            password_hash=hash_password("legacy-password"),
            must_set_password=False,
        )
        session.add(legacy)
        await session.flush()
        session.add(
            SellerStaffPermissions(
                user_id=legacy.id,
                can_documents=True,
                can_products=False,
                can_honest_sign=False,
                can_settings=False,
                can_staff=False,
            )
        )
        await session.commit()
        staff_id = str(legacy.id)
    login_body = {"full_name": "Старый Сотрудник", "password": "legacy-password"}
    assert (await async_client.post("/auth/login-by-name", json=login_body)).status_code == 200
    profile_url = f"/auth/seller-staff-accounts/{staff_id}/profile"
    invite_url = f"/auth/seller-staff-accounts/{staff_id}/invite"
    profile = {"full_name": "Старый Сотрудник", "email": "legacy463@example.com"}
    assert (await async_client.patch(profile_url, headers=foreign, json=profile)).status_code == 404
    assert (await async_client.post(invite_url, headers=foreign)).status_code == 404
    assert (
        await async_client.patch(profile_url, headers=same_tenant, json=profile)
    ).status_code == 404
    assert (await async_client.post(invite_url, headers=same_tenant)).status_code == 404
    assert (
        await async_client.patch(
            f"/auth/seller-staff-accounts/{staff_id}/permissions",
            headers=same_tenant,
            json=PERMISSIONS,
        )
    ).status_code == 404
    for outsider in [foreign, same_tenant]:
        listed = (await async_client.get("/auth/seller-staff-accounts", headers=outsider)).json()
        assert all(row["id"] != staff_id for row in listed)
    assert not mail
    collision = await async_client.patch(
        profile_url,
        headers=headers,
        json={
            **profile,
            "email": "owner-legacy463@example.com",
        },
    )
    assert collision.status_code == 409 and not mail
    assert (await async_client.post("/auth/login-by-name", json=login_body)).status_code == 200
    updated = await async_client.patch(profile_url, headers=headers, json=profile)
    assert updated.status_code == 200 and updated.json()["id"] == staff_id
    assert updated.json()["must_set_password"] and updated.json()["permissions"] == PERMISSIONS
    assert (await async_client.post("/auth/login-by-name", json=login_body)).status_code == 401
    assert (
        await async_client.post(
            "/auth/login",
            json={
                "email": profile["email"],
                "password": "legacy-password",
            },
        )
    ).status_code == 401
    assert (
        await async_client.patch(
            profile_url,
            headers=headers,
            json={
                **profile,
                "email": "changed@example.com",
            },
        )
    ).status_code == 409
    accepted = await async_client.post(
        "/auth/set-password",
        json={
            "token": link_token(mail[0]),
            "password": "self-password-463",
        },
    )
    assert accepted.status_code == 200
    employee = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    assert (await async_client.post(invite_url, headers=employee)).status_code == 403
    assert (
        await async_client.post(
            "/auth/login-by-name",
            json={
                **login_body,
                "password": "self-password-463",
            },
        )
    ).status_code == 200
    assert (
        await async_client.post(
            "/auth/login",
            json={
                "email": profile["email"],
                "password": "self-password-463",
            },
        )
    ).status_code == 200
    async with SessionLocal() as session:
        matches = (await session.scalars(select(User).where(User.email == profile["email"]))).all()
        assert len(matches) == 1 and str(matches[0].id) == staff_id
