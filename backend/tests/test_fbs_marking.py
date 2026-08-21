from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    FbsOrderMarking,
)
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import reset_mock_marketplace_order_meta
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


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
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID, **extra: Any
) -> dict[str, Any]:
    row = {
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
    row.update(extra)
    return row


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    status: str | None = None,
    wb_row_extra: dict[str, Any] | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        row = _wb_order_row(order_id=order_id, **(wb_row_extra or {}))
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            row,
        )
        if status is not None:
            order.status = status
        await session.commit()
        return order.id


@pytest.fixture
def enable_wb_marketplace_marking_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)
    reset_mock_marketplace_order_meta()


# TC-NEW-FBS-MARK-002 — sync updates check_status from official batch meta
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
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=cis,
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [920001]
        return [
            MarketplaceOrderMetaRow(
                order_id=920001,
                meta={"sgtins": [{"value": cis, "checkStatus": "checking"}]},
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text
    rows = sync.json()
    assert len(rows) == 1
    assert rows[0]["check_status"] == CHECK_STATUS_CHECKING


# TC-NEW-FBS-MARK-005 — missing from WB does not erase local code binding
@pytest.mark.asyncio
async def test_fbs_marking_sync_preserves_binding_when_wb_code_is_absent(
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
        order_id=920002,
        status=FBS_ORDER_STATUS_PACKED,
    )
    local_code_id = uuid.uuid4()
    cis = "01CIS-LOCAL-BINDING"
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=cis,
                marking_code_id=local_code_id,
                check_status=CHECK_STATUS_CHECKING,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [920002]
        return [MarketplaceOrderMetaRow(order_id=920002, meta_details=(), meta={})]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )
    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync", headers=headers
    )
    assert sync.status_code == 200, sync.text

    async with SessionLocal() as session:
        marking = (
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            )
            .scalar_one()
        )
        assert marking.check_status == CHECK_STATUS_CHECKING
        assert marking.marking_code_id == local_code_id


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

    async with SessionLocal() as session:
        session.add_all(
            [
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind=kind,
                    value=value,
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
                for kind, value in (
                    ("sgtin", "01CIS-A"),
                    ("sgtin", "01CIS-B"),
                    ("imei", "356938035643809"),
                )
            ]
        )
        await session.commit()

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


# TC-14 — metadata gate: rejected blocks; allowed_without_check continues
@pytest.mark.asyncio
async def test_fbs_metadata_gate_rejected_blocks_allowed_without_check_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.fbs_marking_service import compute_delivery_allowed

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960201,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )

    meta = await async_client.get(
        f"/operations/fbs-orders/{order_id}/metadata",
        headers=headers,
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["required"] == ["sgtin"]
    assert meta.json()["delivery_allowed"] is False

    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.required_meta_json = ["sgtin"]
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-REJECTED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_REJECTED,
                reason="invalid_kiz",
            )
        )
        await session.commit()
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is False

    async with SessionLocal() as session:
        await session.execute(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        for row in (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
        ).scalars():
            await session.delete(row)
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-ALLOWED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ALLOWED_WITHOUT_CHECK,
            )
        )
        await session.commit()
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is True


def test_fbs_metadata_gate_pending_blocks_filled_allows() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import (
        compute_delivery_allowed,
        derive_meta_status,
    )

    order = SimpleNamespace(required_meta_json=["sgtin"])
    pending = SimpleNamespace(kind="sgtin", value="01CIS-PENDING", meta_status=META_STATUS_PENDING)
    assert compute_delivery_allowed(order, [pending]) is False
    assert (
        derive_meta_status(
            check_status=None,
            decision="filled",
            has_value=True,
        )
        == META_STATUS_ACCEPTED
    )
    filled = SimpleNamespace(kind="sgtin", value="01CIS-FILLED", meta_status=META_STATUS_ACCEPTED)
    assert compute_delivery_allowed(order, [filled]) is True


@pytest.mark.asyncio
async def test_fbs_intake_stores_required_optional_meta(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960301,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )
    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.required_meta_json == ["sgtin"]
        assert order.optional_meta_json == ["imei"]
