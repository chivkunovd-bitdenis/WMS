from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_DELIVERY, FbsOrder
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_shipment_warehouse_sc import (
    _create_supply,
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


# TC-NEW-FBS-SHIPPVZ-001 — create trbx count=2; warehouse_sc supply → 400
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
    assert bad.json()["detail"] == "wrong_delivery_type"


# TC-NEW-FBS-SHIPPVZ-002 — add 2 orders OK; weight>5kg → 400
@pytest.mark.asyncio
async def test_fbs_pvz_bind_orders_ok_and_overweight(
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
        supply_name="PVZ bind orders",
    )

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert create.status_code == 201, create.text
    trbx_id = create.json()["trbxes"][0]["id"]

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
    assert bind.status_code == 200, bind.text
    assert bind.json()["weight_g"] == 4000

    async with SessionLocal() as session:
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert str(order.trbx_id) == trbx_id

    overweight = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0]), str(order_ids[1])],
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 200,
            "weight_g": 5001,
        },
    )
    assert overweight.status_code == 400
    assert overweight.json()["detail"] == "trbx_overweight"


# TC-NEW-FBS-SHIPPVZ-003 — dims 61cm -> 400; 60x40x40 cm OK
@pytest.mark.asyncio
async def test_fbs_pvz_bind_orders_oversized_and_max_dims_ok(
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
        wb_order_ids=[962001, 962002],
        supply_name="PVZ dims",
    )

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert create.status_code == 201, create.text
    trbx_id = create.json()["trbxes"][0]["id"]

    oversized = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0]), str(order_ids[1])],
            "length_mm": 610,
            "width_mm": 400,
            "height_mm": 400,
            "weight_g": 5000,
        },
    )
    assert oversized.status_code == 400
    assert oversized.json()["detail"] == "trbx_oversized"

    ok = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0]), str(order_ids[1])],
            "length_mm": 600,
            "width_mm": 400,
            "height_mm": 400,
            "weight_g": 5000,
        },
    )
    assert ok.status_code == 200, ok.text


# TC-NEW-FBS-SHIPPVZ-004 — stickers cached; WB error surfaced
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

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 2},
    )
    assert create.status_code == 201, create.text

    first = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/stickers",
        headers=headers,
        params={"type": "png"},
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["trbxes"]) == 2
    for trbx in first.json()["trbxes"]:
        assert trbx["sticker_file"] is not None
        cached_path = Path(settings.wms_data_dir) / trbx["sticker_file"]
        assert cached_path.is_file()

    fetch_calls = 0
    import app.services.fbs_shipment_pvz_service as pvz_mod

    original_fetch = pvz_mod.fetch_marketplace_trbx_stickers

    async def wrapped_fetch(*args: object, **kwargs: object) -> list[dict[str, object]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return await original_fetch(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pvz_mod, "fetch_marketplace_trbx_stickers", wrapped_fetch)

    second = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/stickers",
        headers=headers,
        params={"type": "png"},
    )
    assert second.status_code == 200, second.text
    assert fetch_calls == 0

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

    monkeypatch.setattr(pvz_mod, "fetch_marketplace_trbx_stickers", fail_fetch)

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
        trbx_row.sticker_file = None
        await session.commit()

    fail_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply2['id']}/trbx/stickers",
        headers=headers,
        params={"type": "png"},
    )
    assert fail_resp.status_code == 502
    assert fail_resp.json()["detail"] == "wb_upstream_error_502"


@pytest.mark.asyncio
async def test_fbs_pvz_deliver_requires_trbx_and_ok_with_trbx(
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

    missing = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert missing.status_code == 400
    assert missing.json()["detail"] == "trbx_required"

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert create.status_code == 201, create.text
    trbx_id = create.json()["trbxes"][0]["id"]

    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0]), str(order_ids[1])],
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 200,
            "weight_g": 2000,
        },
    )
    assert bind.status_code == 200, bind.text

    deliver = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY


@pytest.mark.asyncio
async def test_fbs_pvz_bind_orders_min_two(
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
        wb_order_ids=[965001, 965002],
        supply_name="PVZ min orders",
    )

    create = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert create.status_code == 201, create.text
    trbx_id = create.json()["trbxes"][0]["id"]

    one_order = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/trbx/{trbx_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 200,
            "weight_g": 2000,
        },
    )
    assert one_order.status_code == 400
    assert one_order.json()["detail"] == "trbx_min_orders"
