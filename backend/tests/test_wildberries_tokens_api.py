from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.services.tokens import decode_access_token
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller


@pytest.mark.asyncio
async def test_wb_tokens_get_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{uuid.uuid4()}/tokens",
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wb_tokens_forbidden_for_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co",
            "slug": f"wbt-{suffix}",
            "admin_email": f"wbt-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    sid = s.json()["id"]
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"wbt-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"wbt-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await async_client.get(f"/integrations/wildberries/sellers/{sid}/tokens", headers=sh)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wb_tokens_patch_get_roundtrip_and_clear(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co2",
            "slug": f"wbt2-{suffix}",
            "admin_email": f"wbt2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {token}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S2"})
    sid = uuid.UUID(s.json()["id"])

    g0 = await async_client.get(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
    )
    assert g0.status_code == 200
    assert g0.json()["has_content_token"] is False
    assert g0.json()["has_supplies_token"] is False

    p1 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "  secret-content  ", "supplies_api_token": "supp-1"},
    )
    assert p1.status_code == 200
    b1 = p1.json()
    assert b1["has_content_token"] is True
    assert b1["has_supplies_token"] is True

    async with SessionLocal() as session:
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, sid)
    assert pair is not None
    c, sup = pair
    assert c == "secret-content"
    assert sup == "supp-1"

    g1 = await async_client.get(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
    )
    assert "secret" not in g1.text

    p2 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": None},
    )
    assert p2.status_code == 200
    assert p2.json()["has_content_token"] is False
    assert p2.json()["has_supplies_token"] is True


@pytest.mark.asyncio
async def test_wb_tokens_patch_validation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co3",
            "slug": f"wbt3-{suffix}",
            "admin_email": f"wbt3-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S3"})
    sid = s.json()["id"]

    r = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={},
    )
    assert r.status_code == 422

    r2 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "   "},
    )
    assert r2.status_code == 422
    assert r2.json()["detail"] == "token_empty"

    r3 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "ok", "extra": 1},
    )
    assert r3.status_code == 422


@pytest.mark.asyncio
async def test_wb_tokens_seller_not_found(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co4",
            "slug": f"wbt4-{suffix}",
            "admin_email": f"wbt4-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    missing = uuid.UUID("00000000-0000-4000-8000-000000000099")
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{missing}/tokens",
        headers=ah,
    )
    assert r.status_code == 404
