"""WMS-710 C9: признак «лист подбора в порядке вкладки» отдаётся в /auth/me.

Признак включён ровно для «Империи ФФ» и выключен для всех остальных
арендаторов, включая «ИП Львова В.В.» (R7, R13). Механизм как у
numbered_inbound_box_labels: поле ответа текущего пользователя, без миграций.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.api import auth as auth_api
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.services.passwords import hash_password

IMPERIYA_TENANT_ID = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")
IP_LVOVA_TENANT_ID = uuid.UUID("5fbf633c-3ea9-4c29-b5f5-f549b122bcae")
PASSWORD = "wms710-password123"
FLAG = "fbs_pick_list_tab_order"


async def _seed_fulfillment_admin(tenant_id: uuid.UUID, slug: str, email: str) -> None:
    async with SessionLocal() as session:
        session.add(Tenant(id=tenant_id, name=slug, slug=slug))
        await session.flush()
        session.add(User(
            tenant_id=tenant_id,
            role="fulfillment_admin",
            email=email,
            full_name="WMS-710 админ",
            password_hash=hash_password(PASSWORD),
            must_set_password=False,
        ))
        await session.commit()


async def _profile(client: AsyncClient, email: str) -> dict[str, Any]:
    login = await client.post("/auth/login", json={
        "email": email, "password": PASSWORD, "portal": "fulfillment",
    })
    assert login.status_code == 200, login.text
    me = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {login.json()['access_token']}"
    })
    assert me.status_code == 200, me.text
    profile: dict[str, Any] = me.json()
    return profile


@pytest.mark.asyncio
async def test_fbs_pick_list_tab_order_flag_is_on_only_for_imperiya(
    async_client: AsyncClient,
) -> None:
    await _seed_fulfillment_admin(
        IMPERIYA_TENANT_ID, "imperiya-ff-wms710", "imperiya710@example.com",
    )
    await _seed_fulfillment_admin(
        IP_LVOVA_TENANT_ID, "ip-lvova-wms710", "lvova710@example.com",
    )
    register = await async_client.post("/auth/register", json={
        "organization_name": "Другой арендатор WMS-710",
        "slug": "other-tenant-wms710",
        "admin_email": "other710@example.com",
        "password": PASSWORD,
    })
    assert register.status_code == 200, register.text

    imperiya = await _profile(async_client, "imperiya710@example.com")
    assert imperiya.get(FLAG) is True, imperiya
    lvova = await _profile(async_client, "lvova710@example.com")
    assert lvova.get(FLAG) is False, lvova
    other = await _profile(async_client, "other710@example.com")
    assert other.get(FLAG) is False, other


@pytest.mark.asyncio
async def test_fbs_pick_list_tab_order_flag_is_independent_of_numbered_labels(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_fulfillment_admin(
        IMPERIYA_TENANT_ID, "imperiya-ff-wms710-ind", "imperiya710ind@example.com",
    )
    await _seed_fulfillment_admin(
        IP_LVOVA_TENANT_ID, "ip-lvova-wms710-ind", "lvova710ind@example.com",
    )

    # Снятие одного признака не задевает другой (R7): номерной признак выключен
    # для всех, а признак подбора для «Империи» остаётся включённым.
    monkeypatch.setattr(auth_api, "uses_numbered_inbound_box_labels", lambda _tenant_id: False)
    imperiya = await _profile(async_client, "imperiya710ind@example.com")
    assert imperiya["numbered_inbound_box_labels"] is False
    assert imperiya.get(FLAG) is True, imperiya

    # Обратно: номерной признак включён для всех, признак подбора не расширяется.
    monkeypatch.setattr(auth_api, "uses_numbered_inbound_box_labels", lambda _tenant_id: True)
    lvova = await _profile(async_client, "lvova710ind@example.com")
    assert lvova["numbered_inbound_box_labels"] is True
    assert lvova.get(FLAG) is False, lvova
