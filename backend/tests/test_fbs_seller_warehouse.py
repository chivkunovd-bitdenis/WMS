from __future__ import annotations

import time
from typing import Any, cast

import pytest
from httpx import AsyncClient

from app.core.settings import settings


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS WH {suffix}",
            "slug": f"fbs-wh-{suffix}",
            "admin_email": f"fbs-wh-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _create_seller(async_client: AsyncClient, headers: dict[str, str], suffix: str) -> str:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    return cast(str, seller.json()["id"])


async def _patch_marketplace_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    token: str = "wb-marketplace-token",
) -> None:
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": token},
    )
    assert tok.status_code == 200, tok.text
    assert tok.json()["has_marketplace_token"] is True


@pytest.fixture
def enable_wb_marketplace_warehouses_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_warehouses", True)


# TC-NEW-FBS-WHTOKEN-001 — warehouses OK + no token → 403
@pytest.mark.asyncio
async def test_fbs_seller_warehouses_ok_and_missing_token_403(
    async_client: AsyncClient,
    enable_wb_marketplace_warehouses_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)

    no_token = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouses",
        headers=headers,
    )
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "missing_marketplace_token"

    await _patch_marketplace_token(async_client, headers, seller_id)

    ok = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouses",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert len(body) >= 1
    wh = body[0]
    assert wh["id"] == 501001
    assert wh["name"] == "E2E Seller Warehouse"
    assert wh["officeId"] == 601001
    assert wh["address"] == "E2E Seller WH Address"


# TC-NEW-FBS-WHTOKEN-002 — offices OK
@pytest.mark.asyncio
async def test_fbs_seller_offices_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_warehouses_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    await _patch_marketplace_token(async_client, headers, seller_id)

    ok = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/offices",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert len(body) >= 1
    office = body[0]
    assert office["officeId"] == 601001
    assert office["name"] == "E2E Seller Office"
    assert office["city"] == "Moscow"


# TC-NEW-FBS-WHTOKEN-003 — supplies-only (no marketplace) → 403 on warehouses
@pytest.mark.asyncio
async def test_fbs_seller_warehouses_supplies_only_403(
    async_client: AsyncClient,
    enable_wb_marketplace_warehouses_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)

    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"supplies_api_token": "wb-supplies-only"},
    )
    assert tok.status_code == 200, tok.text
    assert tok.json()["has_supplies_token"] is True
    assert tok.json()["has_marketplace_token"] is False

    r = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouses",
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_marketplace_token"


# TC-NEW-FBS-WHTOKEN-004 — cross-tenant isolation → 404
@pytest.mark.asyncio
async def test_fbs_seller_warehouses_cross_tenant_404(
    async_client: AsyncClient,
    enable_wb_marketplace_warehouses_mock: None,
) -> None:
    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_a = await _create_seller(async_client, headers_a, suffix_a)
    await _patch_marketplace_token(async_client, headers_a, seller_a)

    headers_b, _suffix_b = await _register_ff_admin(async_client)

    cross = await async_client.get(
        f"/operations/fbs-sellers/{seller_a}/warehouses",
        headers=headers_b,
    )
    assert cross.status_code == 404
    assert cross.json()["detail"] == "seller_not_found"


@pytest.mark.asyncio
async def test_fbs_seller_warehouses_wb_upstream_error_502(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.wildberries_client import WildberriesClientError

    async def fake_warehouses(
        client: object, *, api_token: str, marketplace_api_base: str | None = None
    ) -> list[dict[str, Any]]:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_seller_warehouse_service.fetch_marketplace_seller_warehouses",
        fake_warehouses,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    await _patch_marketplace_token(async_client, headers, seller_id)

    r = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouses",
        headers=headers,
    )
    assert r.status_code == 502
    assert r.json()["detail"] == "wb_upstream_error_502"
