from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_DELIVERY, FbsOrder
from app.models.fbs_print_asset import PRINT_ASSET_KIND_CARGO_PLACE_QR, FbsPrintAsset
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services.fbs_print_asset_storage import PNG_MAGIC
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_shipment_warehouse_sc import (
    _create_and_fill_physical_box,
    _create_supply,
    _deliver_with_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


async def _prepare_pvz_supply(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    tenant_id: uuid.UUID,
    *,
    wb_order_ids: list[int],
    supply_name: str,
) -> tuple[dict[str, Any], list[uuid.UUID]]:
    return await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=wb_order_ids,
        supply_name=supply_name,
        delivery_type="pvz",
    )


def _default_boxes(count: int) -> list[dict[str, object]]:
    return [
        {
            "client_id": f"box-{idx + 1}",
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 200,
            "weight_g": 2000,
            "measurements_confirmed": False,
        }
        for idx in range(count)
    ]


async def _create_cargo_places(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
    *,
    count: int,
    idempotency_key: str | None = None,
    boxes: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    payload = {
        "count": count,
        "boxes": boxes if boxes is not None else _default_boxes(count),
        "idempotency_key": idempotency_key or str(uuid.uuid4()),
    }
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/cargo-places",
        headers=headers,
        json=payload,
    )
    return response


async def _delete_cargo_places(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
    *,
    wb_trbx_ids: list[str],
    idempotency_key: str | None = None,
) -> Response:
    return await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/cargo-places",
        headers=headers,
        json={
            "wb_trbx_ids": wb_trbx_ids,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        },
    )


# TC-17 — count creates WB trbx; each has printable QR; no order→trbx mapping
@pytest.mark.asyncio
async def test_tc17_pvz_cargo_places_create_qr_and_deliver_without_bind(
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
        wb_order_ids=[970001, 970002, 970003],
        supply_name="PVZ cargo places TC-17",
    )

    idem_key = str(uuid.uuid4())
    create = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert len(body["cargo_places"]) == 2
    for place in body["cargo_places"]:
        assert place["wb_trbx_id"].startswith("MOCK-TRBX-")
        assert place["qr_asset"] is not None
        assert place["qr_asset"]["status"] == "ready"
        assert place["qr_asset"]["preview_url"] is not None

    listed = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["cargo_places"]) == 2

    retry = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert retry.status_code == 201, retry.text
    assert len(retry.json()["cargo_places"]) == 2

    async with SessionLocal() as session:
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert order.trbx_id is None

    asset_id = body["cargo_places"][0]["qr_asset"]["id"]
    content = await async_client.get(
        f"/operations/fbs-print-assets/{asset_id}/content",
        headers=headers,
    )
    assert content.status_code == 200, content.text
    assert content.content.startswith(PNG_MAGIC)

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text
    deliver_body = deliver.json()
    assert deliver_body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    for order in deliver_body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY


# TC-NEW-FBS-PVZ-001 — WB creates cargo places, transport loses response; retry reconciles only
@pytest.mark.asyncio
async def test_pvz_cargo_places_transport_after_wb_side_effect_reconciles_without_recreate(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[970101, 970102],
        supply_name="PVZ timeout reconcile",
    )

    import app.services.fbs_shipment_pvz_service as pvz_mod

    create_calls = 0
    real_create = pvz_mod.create_marketplace_supply_trbx

    async def create_then_lose_response(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        amount: int,
        marketplace_api_base: str | None = None,
    ) -> list[str]:
        nonlocal create_calls
        create_calls += 1
        _ = await real_create(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            amount=amount,
            marketplace_api_base=marketplace_api_base,
        )
        raise WildberriesClientError("transport_error")

    monkeypatch.setattr(pvz_mod, "create_marketplace_supply_trbx", create_then_lose_response)

    idem_key = str(uuid.uuid4())
    first = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert first.status_code == 504, first.text
    assert first.json()["detail"] == {
        "code": "wb_timeout",
        "message": "WB не подтвердил создание грузомест — повторите операцию.",
        "context": {"operation_state": "pending_confirmation"},
        "retryable": True,
    }
    assert create_calls == 1

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION

    retry = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert retry.status_code == 201, retry.text
    assert len(retry.json()["cargo_places"]) == 2
    assert create_calls == 1

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED


# TC-NEW-FBS-PVZ-002 — unresolved cargo reconcile remains retryable 504 and never repeats create
@pytest.mark.asyncio
async def test_pvz_cargo_places_unresolved_reconcile_returns_structured_504(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[970201, 970202],
        supply_name="PVZ unresolved reconcile",
    )

    import app.services.fbs_shipment_pvz_service as pvz_mod

    create_calls = 0

    async def timeout_without_response(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        amount: int,
        marketplace_api_base: str | None = None,
    ) -> list[str]:
        nonlocal create_calls
        create_calls += 1
        raise WildberriesClientError("transport_error")

    monkeypatch.setattr(pvz_mod, "create_marketplace_supply_trbx", timeout_without_response)

    idem_key = str(uuid.uuid4())
    first = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert first.status_code == 504, first.text

    retry = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=2,
        idempotency_key=idem_key,
    )
    assert retry.status_code == 504, retry.text
    assert retry.json()["detail"] == {
        "code": "wb_pending_confirmation",
        "message": "WB пока не подтвердил создание грузомест; выполняется сверка.",
        "context": {"operation_state": "pending_confirmation"},
        "retryable": True,
    }
    assert create_calls == 1

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION


# TC-18 — explicit dimension blockers; missing dims require audited confirmation
@pytest.mark.asyncio
async def test_tc18_pvz_cargo_places_dimension_blockers(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[971001, 971002],
        supply_name="PVZ dims TC-18",
    )

    preflight_oversized = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places/preflight",
        headers=headers,
        json={
            "count": 1,
            "boxes": [
                {
                    "client_id": "big-box",
                    "length_mm": 610,
                    "width_mm": 400,
                    "height_mm": 400,
                    "weight_g": 4000,
                    "measurements_confirmed": False,
                }
            ],
        },
    )
    assert preflight_oversized.status_code == 200, preflight_oversized.text
    oversized_body = preflight_oversized.json()
    assert oversized_body["compatible"] is False
    oversized_codes = {issue["code"] for issue in oversized_body["issues"]}
    assert "trbx_oversized" in oversized_codes

    preflight_overweight = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places/preflight",
        headers=headers,
        json={
            "count": 1,
            "boxes": [
                {
                    "client_id": "heavy-box",
                    "length_mm": 400,
                    "width_mm": 300,
                    "height_mm": 200,
                    "weight_g": 5001,
                    "measurements_confirmed": False,
                }
            ],
        },
    )
    assert preflight_overweight.status_code == 200
    assert any(
        issue["code"] == "trbx_overweight"
        for issue in preflight_overweight.json()["issues"]
    )

    preflight_sum = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places/preflight",
        headers=headers,
        json={
            "count": 1,
            "boxes": [
                {
                    "client_id": "long-sum-box",
                    "length_mm": 600,
                    "width_mm": 500,
                    "height_mm": 400,
                    "weight_g": 4000,
                    "measurements_confirmed": False,
                }
            ],
        },
    )
    assert preflight_sum.status_code == 200
    assert any(
        issue["code"] == "trbx_sides_sum_exceeded"
        for issue in preflight_sum.json()["issues"]
    )

    import app.services.fbs_shipment_pvz_service as pvz_mod

    monkeypatch.setattr(pvz_mod, "MAX_SUPPLY_TRBX_VOLUME_MM3", 100_000_000)

    preflight_volume = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places/preflight",
        headers=headers,
        json={
            "count": 2,
            "boxes": [
                {
                    "client_id": "vol-1",
                    "length_mm": 600,
                    "width_mm": 400,
                    "height_mm": 400,
                    "weight_g": 4000,
                    "measurements_confirmed": False,
                },
                {
                    "client_id": "vol-2",
                    "length_mm": 600,
                    "width_mm": 400,
                    "height_mm": 400,
                    "weight_g": 4000,
                    "measurements_confirmed": False,
                },
            ],
        },
    )
    assert preflight_volume.status_code == 200
    assert any(
        issue["code"] == "trbx_volume_exceeded"
        for issue in preflight_volume.json()["issues"]
    )

    preflight_missing = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places/preflight",
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
        },
    )
    assert preflight_missing.status_code == 200
    assert any(
        issue["code"] == "measurements_confirmation_required"
        for issue in preflight_missing.json()["issues"]
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
    assert create_missing.status_code == 400
    assert create_missing.json()["detail"]["code"] == "cargo_places_preflight_failed"

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
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create_confirmed.status_code == 201, create_confirmed.text
    place = create_confirmed.json()["cargo_places"][0]
    assert place["length_mm"] is None
    assert place["qr_asset"] is not None


@pytest.mark.asyncio
async def test_fbs_pvz_create_trbx_ok_and_wrong_delivery_type(
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
        wb_order_ids=[960001, 960002, 960003],
        supply_name="PVZ trbx create",
    )

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 2},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert len(body["trbxes"]) == 2
    for trbx in body["trbxes"]:
        assert trbx["wb_trbx_id"].startswith("MOCK-TRBX-")

    sc_supply = await _create_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        name="SC supply",
        delivery_type="warehouse_sc",
    )
    bad = await async_client.post(
        f"/operations/fbs-supplies/{sc_supply['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "wrong_delivery_type"


@pytest.mark.asyncio
async def test_fbs_pvz_bind_orders_deprecated_410(
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
        wb_order_ids=[961001, 961002],
        supply_name="PVZ bind deprecated",
    )

    create = await _create_cargo_places(async_client, headers, supply["id"], count=1)
    assert create.status_code == 201, create.text
    trbx_id = create.json()["cargo_places"][0]["id"]

    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0]), str(order_ids[1])],
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 200,
            "weight_g": 4000,
        },
    )
    assert bind.status_code == 410
    assert bind.json()["detail"]["code"] == "deprecated_use_cargo_places"


@pytest.mark.asyncio
async def test_fbs_pvz_trbx_stickers_cached_and_wb_error(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[963001, 963002],
        supply_name="PVZ stickers",
    )

    create = await _create_cargo_places(async_client, headers, supply["id"], count=2)
    assert create.status_code == 201, create.text
    places = create.json()["cargo_places"]
    assert len(places) == 2
    for place in places:
        assert place["qr_asset"] is not None
        asset_id = place["qr_asset"]["id"]
        content = await async_client.get(
            f"/operations/fbs-print-assets/{asset_id}/content",
            headers=headers,
        )
        assert content.status_code == 200
        assert content.content.startswith(PNG_MAGIC)

    fetch_calls = 0
    import app.services.fbs_print_asset_service as print_mod

    original_fetch = print_mod.fetch_marketplace_trbx_stickers

    async def wrapped_fetch(*args: object, **kwargs: object) -> list[dict[str, object]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return await original_fetch(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(print_mod, "fetch_marketplace_trbx_stickers", wrapped_fetch)

    second = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/cargo-places",
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert fetch_calls == 0

    supply2, _ = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[963003],
        supply_name="PVZ stickers fail",
    )
    create2 = await async_client.post(
        f"/operations/fbs-supplies/{supply2['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert create2.status_code == 201, create2.text
    trbx_id = create2.json()["trbxes"][0]["id"]
    async with SessionLocal() as session:
        trbx_row = await session.get(FbsTrbx, uuid.UUID(trbx_id))
        assert trbx_row is not None
        trbx_row.qr_asset_id = None
        assets = await session.execute(
            select(FbsPrintAsset).where(
                FbsPrintAsset.fbs_trbx_id == trbx_row.id,
                FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
            )
        )
        for asset in assets.scalars().all():
            await session.delete(asset)
        await session.commit()

    async def fail_fetch(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        trbx_ids: list[str],
        type: str = "png",
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, object]]:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(print_mod, "fetch_marketplace_trbx_stickers", fail_fetch)

    fail_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply2['id']}/trbx/stickers",
        headers=headers,
        params={"type": "png"},
    )
    assert fail_resp.status_code == 502
    assert fail_resp.json()["detail"]["code"] == "wb_upstream_error_502"


@pytest.mark.asyncio
async def test_fbs_pvz_deliver_requires_physical_boxes(
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
        wb_order_ids=[964001, 964002],
        supply_name="PVZ deliver",
    )

    missing = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "physical_boxes_required"

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY


# TC-NEW-FBS-PVZ-DELETE-001 — delete selected cargo places while supply is assembling
@pytest.mark.asyncio
async def test_pvz_delete_cargo_places_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[971001, 971002],
        supply_name="PVZ delete cargo",
    )

    create = await _create_cargo_places(async_client, headers, supply["id"], count=2)
    assert create.status_code == 201, create.text
    places = create.json()["cargo_places"]
    assert len(places) == 2
    delete_target = places[0]["wb_trbx_id"]
    keep_target = places[1]["wb_trbx_id"]
    idem_key = str(uuid.uuid4())

    import app.services.fbs_shipment_pvz_service as pvz_mod

    delete_calls = 0
    real_delete = pvz_mod.delete_marketplace_supply_trbx

    async def counted_delete(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        trbx_ids: list[str],
        marketplace_api_base: str | None = None,
    ) -> None:
        nonlocal delete_calls
        delete_calls += 1
        await real_delete(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            trbx_ids=trbx_ids,
            marketplace_api_base=marketplace_api_base,
        )

    monkeypatch.setattr(pvz_mod, "delete_marketplace_supply_trbx", counted_delete)

    deleted = await _delete_cargo_places(
        async_client,
        headers,
        supply["id"],
        wb_trbx_ids=[delete_target],
        idempotency_key=idem_key,
    )
    assert deleted.status_code == 200, deleted.text
    remaining = deleted.json()["cargo_places"]
    assert len(remaining) == 1
    assert remaining[0]["wb_trbx_id"] == keep_target
    assert delete_calls == 1

    retry = await _delete_cargo_places(
        async_client,
        headers,
        supply["id"],
        wb_trbx_ids=[delete_target],
        idempotency_key=idem_key,
    )
    assert retry.status_code == 200, retry.text
    assert [row["wb_trbx_id"] for row in retry.json()["cargo_places"]] == [keep_target]
    assert delete_calls == 1

    async with SessionLocal() as session:
        trbx_rows = (
            await session.execute(
                select(FbsTrbx).where(FbsTrbx.supply_id == uuid.UUID(supply["id"]))
            )
        ).scalars().all()
        assert len(trbx_rows) == 1
        assert trbx_rows[0].wb_trbx_id == keep_target
        assets = (
            await session.execute(
                select(FbsPrintAsset).where(
                    FbsPrintAsset.fbs_trbx_id == trbx_rows[0].id,
                    FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
                )
            )
        ).scalars().all()
        assert len(assets) == 1


# TC-NEW-FBS-PVZ-DELETE-002 — lost DELETE response reconciles without double delete
@pytest.mark.asyncio
async def test_pvz_delete_cargo_places_transport_reconciles_without_double_delete(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        wb_order_ids=[971101, 971102],
        supply_name="PVZ delete reconcile",
    )

    create = await _create_cargo_places(async_client, headers, supply["id"], count=2)
    assert create.status_code == 201, create.text
    places = create.json()["cargo_places"]
    delete_target = places[0]["wb_trbx_id"]
    keep_target = places[1]["wb_trbx_id"]
    idem_key = str(uuid.uuid4())

    import app.services.fbs_shipment_pvz_service as pvz_mod

    delete_calls: list[list[str]] = []
    real_delete = pvz_mod.delete_marketplace_supply_trbx

    async def delete_then_lose_response(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        trbx_ids: list[str],
        marketplace_api_base: str | None = None,
    ) -> None:
        delete_calls.append(list(trbx_ids))
        await real_delete(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            trbx_ids=trbx_ids,
            marketplace_api_base=marketplace_api_base,
        )
        raise WildberriesClientError("transport_error")

    monkeypatch.setattr(pvz_mod, "delete_marketplace_supply_trbx", delete_then_lose_response)

    first = await _delete_cargo_places(
        async_client,
        headers,
        supply["id"],
        wb_trbx_ids=[delete_target],
        idempotency_key=idem_key,
    )
    assert first.status_code == 504, first.text
    assert first.json()["detail"]["code"] == "wb_timeout"
    assert delete_calls == [[delete_target]]

    async with SessionLocal() as session:
        trbx_rows = (
            await session.execute(
                select(FbsTrbx).where(FbsTrbx.supply_id == uuid.UUID(supply["id"]))
            )
        ).scalars().all()
        assert len(trbx_rows) == 2
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION

    retry = await _delete_cargo_places(
        async_client,
        headers,
        supply["id"],
        wb_trbx_ids=[delete_target],
        idempotency_key=idem_key,
    )
    assert retry.status_code == 200, retry.text
    remaining = retry.json()["cargo_places"]
    assert len(remaining) == 1
    assert remaining[0]["wb_trbx_id"] == keep_target
    assert delete_calls == [[delete_target]]

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED


# TC-NEW-FBS-PVZ-DELETE-003 — guards: unknown id, wrong route, post-deliver block
@pytest.mark.asyncio
async def test_pvz_delete_cargo_places_guards(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    pvz_supply, order_ids = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[971201],
        supply_name="PVZ delete guards",
    )
    create = await _create_cargo_places(async_client, headers, pvz_supply["id"], count=1)
    assert create.status_code == 201, create.text
    wb_id = create.json()["cargo_places"][0]["wb_trbx_id"]

    missing = await _delete_cargo_places(
        async_client,
        headers,
        pvz_supply["id"],
        wb_trbx_ids=["MOCK-TRBX-MISSING"],
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "cargo_place_not_found"

    wh_supply, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[971202],
        supply_name="WH delete blocked",
        delivery_type="warehouse_sc",
    )
    wh_delete = await _delete_cargo_places(
        async_client,
        headers,
        wh_supply["id"],
        wb_trbx_ids=[wb_id],
    )
    assert wh_delete.status_code == 400
    assert wh_delete.json()["detail"]["code"] == "wrong_delivery_type"

    await _create_and_fill_physical_box(async_client, headers, pvz_supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, pvz_supply["id"])
    assert deliver.status_code == 200, deliver.text

    blocked = await _delete_cargo_places(
        async_client,
        headers,
        pvz_supply["id"],
        wb_trbx_ids=[wb_id],
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "supply_bad_status"
