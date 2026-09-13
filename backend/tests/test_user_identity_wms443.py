from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.document_events import _event_out
from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.user import User


async def register(client: AsyncClient, slug: str = "identity-one") -> dict[str, str]:
    response = await client.post("/auth/register", json={
        "organization_name": slug, "slug": slug,
        "admin_email": f"{slug}@example.com", "password": "test-password-443",
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def by_name(client: AsyncClient, name: str, password: str = "test-password-443",
                  organization: str | None = None):
    response = await client.post("/auth/login-by-name", json={
        "full_name": name, "password": password, "organization": organization,
    })
    if response.status_code != 200:
        return response, None
    me = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {response.json()['access_token']}",
    })
    assert me.status_code == 200
    return response, me.json()


@pytest.mark.asyncio
async def test_cold_legacy_admin_fills_self_and_keeps_old_token_and_password(async_client):
    headers = await register(async_client)
    before = (await async_client.get("/auth/me", headers=headers)).json()
    assert before["full_name"] is None and before["display_name"] == "ФИО не указано"
    for name in (None, "  Анна   Ли  "):
        if name:
            saved = await async_client.patch("/auth/me", headers=headers, json={
                "full_name": name, "job_title": "  Старшая смены  ",
            })
            assert saved.status_code == 200
            assert saved.json()["full_name"] == "Анна Ли"
        legacy = await async_client.post("/auth/login", json={
            "email": "identity-one@example.com", "password": "test-password-443",
        })
        assert legacy.status_code == 200
        assert set(legacy.json()) == {"access_token", "token_type"}
        same = (await async_client.get("/auth/me", headers=headers)).json()
        assert same["id"] == before["id"] and same["role"] == before["role"]
        warehouses = await async_client.get("/warehouses", headers=headers)
        assert warehouses.status_code == 200
    response, named = await by_name(async_client, "\tАННА   ли\n")
    assert response.status_code == 200 and named["id"] == before["id"]
    assert named["job_title"] == "Старшая смены"
    assert named["organization_slug"] == "identity-one"


@pytest.mark.asyncio
async def test_homonyms_same_and_other_organization_never_select_first(async_client):
    admin = await register(async_client)
    other_admin = await register(async_client, "identity-two")
    ids = []
    for headers, password in [(admin, "test-password-443"), (admin, "different-443"),
                              (other_admin, "test-password-443")]:
        created = await async_client.post("/auth/staff-accounts", headers=headers, json={
            "full_name": "Маша", "job_title": "Упаковщик", "password": password,
        })
        assert created.status_code == 201
        assert created.json().get("email") is None
        ids.append(created.json()["id"])
    ambiguous, _ = await by_name(async_client, "Маша")
    assert ambiguous.status_code == 401 and ambiguous.json() == {"detail": "invalid_credentials"}
    for org, password, expected in [("identity-one", "test-password-443", ids[0]),
                                    ("identity-one", "different-443", ids[1]),
                                    ("identity-two", "test-password-443", ids[2])]:
        response, profile = await by_name(async_client, "МАША", password, org)
        assert response.status_code == 200 and profile["id"] == expected
    duplicate = await async_client.post("/auth/staff-accounts", headers=admin, json={
        "full_name": "Маша", "password": "test-password-443",
    })
    assert duplicate.status_code == 201
    ambiguous, _ = await by_name(async_client, "Маша", organization="identity-one")
    assert ambiguous.status_code == 401
    missing, _ = await by_name(async_client, "Нет Такого")
    wrong, _ = await by_name(async_client, "Маша", "wrong-password")
    assert ambiguous.json() == missing.json() == wrong.json()


@pytest.mark.asyncio
async def test_profile_permissions_scope_and_immutable_identity(async_client):
    admin = await register(async_client)
    foreign = await register(async_client, "identity-two")
    created = await async_client.post("/auth/staff-accounts", headers=admin, json={
        "full_name": "Али", "job_title": "Стажёр", "password": "test-password-443",
    })
    staff = created.json()
    response, profile = await by_name(async_client, "Али")
    worker = {"Authorization": f"Bearer {response.json()['access_token']}"}
    url = f"/auth/staff-accounts/{staff['id']}/profile"
    for headers, expected in [(foreign, 404), (worker, 403)]:
        denied = await async_client.patch(url, headers=headers, json={"full_name": "Подмена"})
        assert denied.status_code == expected
    forbidden = await async_client.patch("/auth/me", headers=worker, json={
        "full_name": "Али", "role": "fulfillment_admin", "id": str(uuid.uuid4()),
    })
    assert forbidden.status_code == 422
    updated = await async_client.patch(url, headers=admin, json={
        "full_name": "Али-Хасан", "job_title": "Администратор",
    })
    assert updated.status_code == 200
    assert updated.json()["id"] == staff["id"]
    assert updated.json()["permissions"] == staff["permissions"]
    assert updated.json()["packaging_rate_rub"] == staff["packaging_rate_rub"]
    profile2 = (await async_client.get("/auth/me", headers=worker)).json()
    assert profile2["role"] == profile["role"] == "fulfillment_staff"
    assert (await async_client.get("/auth/staff-accounts", headers=worker)).status_code == 403
    assert (await by_name(async_client, "Али-Хасан"))[1]["id"] == staff["id"]


@pytest.mark.asyncio
async def test_name_login_rate_limit_and_invalid_creation(async_client):
    admin = await register(async_client)
    for body in [{"email": "unnamed@example.com", "password": "test-password-443"},
                 {"full_name": "   ", "password": "test-password-443"},
                 {"full_name": "Иван"}, {"full_name": "Иван", "password": "short"}]:
        result = await async_client.post("/auth/staff-accounts", headers=admin, json=body)
        assert result.status_code == 422
    for _ in range(5):
        response, _ = await by_name(async_client, "Несуществующий")
        assert response.status_code == 401
    limited, _ = await by_name(async_client, "Другой")
    assert limited.status_code == 429


@pytest.mark.asyncio
async def test_historical_display_preserves_real_name_and_neutral_system(async_client):
    headers = await register(async_client)
    async with SessionLocal() as session:
        actor = await session.scalar(select(User).where(User.email == "identity-one@example.com"))
        assert actor is not None
        actor.full_name = "Елена Смирнова"
        await session.commit()
        common = dict(id=uuid.uuid4(), tenant_id=actor.tenant_id,
                      document_type="staff_user", document_id=actor.id,
                      event_type="updated", source="user", occurred_at=datetime.now(UTC),
                      actor_user_id=actor.id, actor=actor, product=None)
        for snapshot, expected in [(actor.email, actor.full_name),
                                   ("Елена Иванова", "Елена Иванова"),
                                   ("ФИО не указано", actor.full_name)]:
            payload = {"actor_name_snapshot": snapshot, "actor_user_id_snapshot": str(actor.id)}
            event = DocumentEvent(**common, payload_json=payload)
            out = _event_out(event)
            assert out.actor.name == expected
            assert out.actor.id == actor.id
            assert event.payload_json == payload  # Read must not rewrite stored history.
        actor.full_name = None
        event = DocumentEvent(**common, payload_json={"actor_name_snapshot": actor.email,
                                                     "actor_user_id_snapshot": str(actor.id)})
        assert _event_out(event).actor.name == "ФИО не указано"
        system = DocumentEvent(**{**common, "actor": None, "actor_user_id": None,
                                  "source": "system"}, payload_json={})
        assert _event_out(system).actor is None
    assert (await async_client.get("/auth/me", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_seller_named_staff_create_edit_and_other_seller_scope(async_client):
    admin = await register(async_client)
    owners = []
    for number in (1, 2):
        seller = await async_client.post(
            "/sellers", headers=admin, json={"name": f"Seller {number}"},
        )
        account = await async_client.post("/auth/seller-accounts", headers=admin, json={
            "seller_id": seller.json()["id"], "email": f"owner-{number}@example.com",
            "password": "test-password-443",
        })
        assert account.status_code == 201
        login = await async_client.post("/auth/login", json={
            "email": f"owner-{number}@example.com", "password": "test-password-443",
        })
        owners.append({"Authorization": f"Bearer {login.json()['access_token']}"})
    created = await async_client.post("/auth/seller-staff-accounts", headers=owners[0], json={
        "full_name": "Джон Ли", "job_title": "Менеджер", "password": "test-password-443",
    })
    assert created.status_code == 201 and created.json()["email"] is None
    staff = created.json()
    response, profile = await by_name(async_client, "джон   ЛИ")
    assert response.status_code == 200 and profile["id"] == staff["id"]
    assert profile["role"] == "fulfillment_seller"
    url = f"/auth/seller-staff-accounts/{staff['id']}/profile"
    foreign = await async_client.patch(url, headers=owners[1], json={"full_name": "Подмена"})
    assert foreign.status_code == 404
    saved = await async_client.patch(url, headers=owners[0], json={
        "full_name": "Джон Ли-Мин", "job_title": "Старший менеджер",
    })
    assert saved.status_code == 200
    assert saved.json()["seller_id"] == staff["seller_id"]
    assert saved.json()["permissions"] == staff["permissions"]
    named = (await by_name(async_client, "Джон Ли-Мин"))[1]
    assert named["id"] == staff["id"]
