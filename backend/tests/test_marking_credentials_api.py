from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.services.seller_marking_credentials_service import get_decrypted_credentials_for_seller
from app.services.tokens import decode_access_token


@pytest.mark.asyncio
async def test_marking_credentials_get_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get("/operations/marking-codes/self/credentials")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_marking_credentials_forbidden_for_ff_on_self(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "CZ Cred Co",
            "slug": f"czc-{suffix}",
            "admin_email": f"czc-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    r = await async_client.get("/operations/marking-codes/self/credentials", headers=ah)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_marking_credentials_patch_get_roundtrip_and_no_secrets_in_response(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "CZ Cred Co2",
            "slug": f"czc2-{suffix}",
            "admin_email": f"czc2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(admin_token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {admin_token}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "CZ Seller"})
    sid = uuid.UUID(s.json()["id"])
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": str(sid),
            "email": f"czc-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"czc-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    g0 = await async_client.get("/operations/marking-codes/self/credentials", headers=sh)
    assert g0.status_code == 200
    body0 = g0.json()
    assert body0["has_cz_token"] is False
    assert body0["signing_method"] == "manual"
    assert body0["edo_route"] == "edo_light_roaming_diadoc"

    p1 = await async_client.patch(
        "/operations/marking-codes/self/credentials",
        headers=sh,
        json={
            "cz_token": "  cz-secret-token  ",
            "suz_oms_token": "suz-1",
            "mp_api_key": "mp-key-1",
            "marketplace": "wildberries",
            "mchd_id": "MCHD-123",
            "mchd_valid_until": "2027-12-31",
            "signing_method": "ff_kep_mchd",
            "edo_route": "diadoc_direct",
            "auto_introduce": True,
            "auto_emit_limit": 5000,
        },
    )
    assert p1.status_code == 200
    b1 = p1.json()
    assert b1["has_cz_token"] is True
    assert b1["has_suz_oms_token"] is True
    assert b1["has_mp_api_key"] is True
    assert b1["marketplace"] == "wildberries"
    assert b1["mchd_id"] == "MCHD-123"
    assert b1["signing_method"] == "ff_kep_mchd"
    assert b1["auto_introduce"] is True
    assert b1["auto_emit_limit"] == 5000
    assert "cz-secret" not in p1.text
    assert "mp-key" not in p1.text

    async with SessionLocal() as session:
        secrets = await get_decrypted_credentials_for_seller(session, tenant_id, sid)
    assert secrets is not None
    assert secrets.cz_token == "cz-secret-token"
    assert secrets.suz_oms_token == "suz-1"
    assert secrets.mp_api_key == "mp-key-1"

    admin_get = await async_client.get(
        f"/operations/marking-codes/sellers/{sid}/credentials",
        headers=ah,
    )
    assert admin_get.status_code == 200
    assert "cz-secret" not in admin_get.text

    p2 = await async_client.patch(
        "/operations/marking-codes/self/credentials",
        headers=sh,
        json={"cz_token": None},
    )
    assert p2.status_code == 200
    assert p2.json()["has_cz_token"] is False
    assert p2.json()["has_suz_oms_token"] is True


@pytest.mark.asyncio
async def test_marking_credentials_patch_validation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "CZ Cred Co3",
            "slug": f"czc3-{suffix}",
            "admin_email": f"czc3-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "CZ Seller3"})
    sid = s.json()["id"]
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"czc3-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"czc3-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await async_client.patch(
        "/operations/marking-codes/self/credentials",
        headers=sh,
        json={},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "empty_patch"

    r2 = await async_client.patch(
        "/operations/marking-codes/self/credentials",
        headers=sh,
        json={"cz_token": "   "},
    )
    assert r2.status_code == 422
    assert r2.json()["detail"] == "token_empty"

    r3 = await async_client.patch(
        "/operations/marking-codes/self/credentials",
        headers=sh,
        json={"signing_method": "unknown"},
    )
    assert r3.status_code == 422
    assert r3.json()["detail"] == "invalid_signing_method"
