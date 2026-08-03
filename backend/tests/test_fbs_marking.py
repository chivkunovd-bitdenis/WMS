from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_PACKED,
    FbsOrderMarking,
)
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import (
    WildberriesClientError,
    reset_mock_marketplace_order_meta,
)


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS marking {suffix}",
            "slug": f"fbs-marking-{suffix}",
            "admin_email": f"fbs-marking-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _setup_seller_with_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[str, str, uuid.UUID]:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    reg = await async_client.get("/auth/me", headers=headers)
    assert reg.status_code == 200
    tenant_id = uuid.UUID(reg.json()["tenant_id"])
    return seller_id, warehouse.json()["id"], tenant_id


def _wb_order_row(
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID
) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": "ART-001",
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
        "warehouseId": wb_warehouse_id,
    }


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    status: str | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=order_id),
        )
        if status is not None:
            order.status = status
        await session.commit()
        return order.id


@pytest.fixture
def enable_wb_marketplace_marking_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)
    reset_mock_marketplace_order_meta()


# TC-NEW-FBS-MARK-001 — PUT sgtin → DB+WB, check_status=new; negatives
@pytest.mark.asyncio
async def test_fbs_marking_put_sgtin_ok_and_validation(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=910001,
        status=FBS_ORDER_STATUS_PACKED,
    )

    put = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-SGTIN-001"},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["kind"] == "sgtin"
    assert body["value"] == "01CIS-SGTIN-001"
    assert body["check_status"] == CHECK_STATUS_NEW
    assert body["marking_code_id"] is None

    bad_kind = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/unknown",
        headers=headers,
        json={"value": "x"},
    )
    assert bad_kind.status_code == 400
    assert bad_kind.json()["detail"] == "invalid_kind"

    empty = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "   "},
    )
    assert empty.status_code == 400
    assert empty.json()["detail"] == "empty_value"

    frozen_order = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=910002,
        status=FBS_ORDER_STATUS_IN_DELIVERY,
    )
    frozen = await async_client.put(
        f"/operations/fbs-orders/{frozen_order}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-FROZEN"},
    )
    assert frozen.status_code == 409
    assert frozen.json()["detail"] == "order_marking_frozen"


# TC-NEW-FBS-MARK-002 — sync updates check_status from GET meta
@pytest.mark.asyncio
async def test_fbs_marking_sync_updates_check_status(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=920001,
        status=FBS_ORDER_STATUS_PACKED,
    )
    cis = "01CIS-SYNC-001"
    put = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": cis},
    )
    assert put.status_code == 200, put.text

    async def fake_meta(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> dict[str, Any]:
        assert order_id == 920001
        return {
            "sgtins": [{"value": cis, "checkStatus": "checking"}],
        }

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_order_meta",
        fake_meta,
    )

    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text
    rows = sync.json()
    assert len(rows) == 1
    assert rows[0]["check_status"] == CHECK_STATUS_CHECKING


# TC-NEW-FBS-MARK-003 — MarkingCode cis lookup links marking_code_id
@pytest.mark.asyncio
async def test_fbs_marking_links_existing_marking_code(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    cis = "01CIS-LINK-001"
    async with SessionLocal() as session:
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=uuid.UUID(seller_id),
                cis_code=cis,
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=930001,
        status=FBS_ORDER_STATUS_PACKED,
    )
    put = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": cis},
    )
    assert put.status_code == 200, put.text
    assert put.json()["marking_code_id"] is not None

    missing = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-NOT-IN-POOL"},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["marking_code_id"] is None


# TC-NEW-FBS-MARK-004 — GET list all kinds; empty → []
@pytest.mark.asyncio
async def test_fbs_marking_get_list_all_kinds(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=940001,
        status=FBS_ORDER_STATUS_PACKED,
    )

    empty = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    for kind, value in (
        ("sgtin", "01CIS-A"),
        ("sgtin", "01CIS-B"),
        ("imei", "356938035643809"),
    ):
        resp = await async_client.put(
            f"/operations/fbs-orders/{order_id}/markings/{kind}",
            headers=headers,
            json={"value": value},
        )
        assert resp.status_code == 200, resp.text

    listed = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 3
    kinds = {row["kind"] for row in rows}
    assert kinds == {"sgtin", "imei"}
    values = {row["value"] for row in rows}
    assert values == {"01CIS-A", "01CIS-B", "356938035643809"}


@pytest.mark.asyncio
async def test_fbs_marking_wb_upstream_error_502(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=950001,
        status=FBS_ORDER_STATUS_PACKED,
    )

    async def fail_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        fail_put,
    )

    resp = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-FAIL"},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "wb_upstream_error_502"

    async with SessionLocal() as session:
        result = await session.execute(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        assert result.scalars().all() == []
