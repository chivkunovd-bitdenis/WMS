"""Contract/regression: stable FBS error envelope on operator-facing endpoints."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.user import User
from tests.test_fbs_shipment_pvz import (
    _prepare_pvz_supply,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


def assert_fbs_error_envelope(
    resp: Response,
    *,
    code: str,
    status_code: int | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    if status_code is not None:
        assert resp.status_code == status_code, resp.text
    body = resp.json()
    detail = body["detail"]
    assert isinstance(detail, dict), body
    assert set(detail.keys()) >= {"code", "message", "context", "retryable"}
    assert detail["code"] == code
    assert isinstance(detail["message"], str) and detail["message"]
    assert isinstance(detail["context"], dict)
    assert isinstance(detail["retryable"], bool)
    if retryable is not None:
        assert detail["retryable"] is retryable
    # Nested {"detail": {"detail": ...}} must never appear.
    assert "detail" not in detail
    return detail


@pytest.mark.asyncio
async def test_print_asset_404_uses_flat_error_envelope(
    async_client: AsyncClient,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    missing = await async_client.get(
        f"/operations/fbs-print-assets/{uuid.uuid4()}/content",
        headers=headers,
    )
    assert_fbs_error_envelope(
        missing,
        code="asset_not_found",
        status_code=404,
        retryable=False,
    )


@pytest.mark.asyncio
async def test_cargo_places_preflight_failed_envelope(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, _ = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[981001],
        supply_name="PVZ envelope",
    )
    create_missing = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places",
        headers=headers,
        json={
            "count": 1,
            "boxes": [
                {
                    "client_id": "unknown-box",
                    "length_mm": None,
                    "width_mm": None,
                    "height_mm": None,
                    "weight_g": None,
                    "measurements_confirmed": False,
                }
            ],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert_fbs_error_envelope(
        create_missing,
        code="cargo_places_preflight_failed",
        status_code=400,
        retryable=False,
    )


@pytest.mark.asyncio
async def test_pvz_missing_dims_confirmation_persists_actor_timestamp_source(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, _ = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[981101],
        supply_name="PVZ audit confirm",
    )
    idem_key = str(uuid.uuid4())
    create_confirmed = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places",
        headers=headers,
        json={
            "count": 1,
            "boxes": [
                {
                    "client_id": "unknown-box",
                    "length_mm": None,
                    "width_mm": None,
                    "height_mm": None,
                    "weight_g": None,
                    "measurements_confirmed": True,
                }
            ],
            "idempotency_key": idem_key,
        },
    )
    assert create_confirmed.status_code == 201, create_confirmed.text
    # Success JSON unchanged (no audit fields on FbsCargoPlace).
    place = create_confirmed.json()["cargo_places"][0]
    assert set(place.keys()) >= {
        "id",
        "wb_trbx_id",
        "length_mm",
        "width_mm",
        "height_mm",
        "weight_g",
        "qr_asset",
        "applied_at",
    }
    assert "measurements_confirmation_audit" not in place

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        summary = operation.request_summary_json or {}
        audit = summary.get("measurements_confirmation_audit")
        assert isinstance(audit, dict)
        assert audit["source"] == "operator_manual_missing_dims"
        assert audit["confirmed_client_ids"] == ["unknown-box"]
        assert isinstance(audit["confirmed_at"], str) and audit["confirmed_at"]
        actor = uuid.UUID(audit["actor_user_id"])
        user = await session.get(User, actor)
        assert user is not None
        assert user.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_deprecated_trbx_bind_returns_envelope(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[981201],
        supply_name="PVZ deprecated bind",
    )
    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{uuid.uuid4()}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "weight_g": 500,
        },
    )
    assert_fbs_error_envelope(
        bind,
        code="deprecated_use_cargo_places",
        status_code=410,
        retryable=False,
    )


def test_legacy_sticker_endpoints_marked_deprecated_in_openapi() -> None:
    from app.main import create_app

    schema = create_app().openapi()
    stickers = schema["paths"]["/operations/fbs-supplies/{supply_id}/stickers"]["post"]
    trbx_stickers = schema["paths"]["/operations/fbs-supplies/{supply_id}/trbx/stickers"][
        "post"
    ]
    barcode = schema["paths"]["/operations/fbs-supplies/{supply_id}/barcode"]["get"]
    assert stickers.get("deprecated") is True
    assert trbx_stickers.get("deprecated") is True
    assert barcode.get("deprecated") is True
