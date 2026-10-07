"""WMS-666: the packing request reaches WB and persists usable stickers."""

import asyncio
import base64
import json
import uuid
from typing import Any

import httpx
import pytest

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.seller import Seller
from app.services.fbs_print_asset_storage import PNG_MAGIC
from tests.test_fbs_supply_assembly import (
    _create_order,
    _create_supply,
    _register_ff_admin,
    _setup_seller_with_token,
)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/k9sAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_packing_request_calls_wb_and_returns_saved_sticker_content(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    seller, warehouse = await _setup_seller_with_token(async_client, headers, suffix)
    supply = await _create_supply(async_client, headers, seller, warehouse)
    async with SessionLocal() as session:
        seller_row = await session.get(Seller, uuid.UUID(seller))
        assert seller_row is not None
        tenant = seller_row.tenant_id
    order_id = await _create_order(
        tenant, uuid.UUID(seller), uuid.UUID(warehouse), order_id=666777001
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.supply_id = uuid.UUID(str(supply["id"]))
        order.status = "in_supply"
        assert order.sticker_code is None
        await session.commit()

    # Only WB HTTP is mocked: real API, service, WB client, DB and binary endpoint.
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", False)
    original_send = httpx.AsyncClient.send
    wb_requests: list[dict[str, object]] = []

    async def send(
        client: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        if request.url.path == "/api/v3/orders/stickers":
            assert request.method == "POST"
            wb_requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                request=request,
                json={
                    "stickers": [
                        {
                            "orderId": 666777001,
                            "partA": "5877994",
                            "partB": "0283",
                            "barcode": "*fixture666",
                            "file": base64.b64encode(PNG).decode(),
                        }
                    ]
                },
            )
        assert isinstance(client._transport, httpx.ASGITransport), (
            f"Unexpected external request: {request.url.path}"
        )
        return await original_send(client, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_id)], "retry_missing": True},
    )
    assert batch.status_code == 200, batch.text
    assert wb_requests == [{"orders": [666777001]}]
    result = batch.json()
    assert (result["requested"], result["ready"], result["missing"], result["failed"]) == (
        1,
        1,
        0,
        0,
    )
    assert result["order_errors"] == []
    assert len(result["assets"]) == 1
    content = await async_client.get(result["assets"][0]["download_url"], headers=headers)
    assert content.status_code == 200
    assert content.content == PNG
    assert content.content.startswith(PNG_MAGIC)
    refreshed = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/workspace", headers=headers
    )
    assert refreshed.status_code == 200, refreshed.text
    sticker = next(
        row["sticker"] for row in refreshed.json()["orders"] if row["id"] == str(order_id)
    )
    assert sticker["code"] == "5877994 0283"
    assert sticker["asset_url"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_fails", [False, True, "timeout", "db_cancel"])
async def test_creation_prefetches_stickers_and_preserves_supply_on_provider_failure(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    provider_fails: bool | str,
) -> None:
    from app.services.wildberries_client import WildberriesClientError
    from tests.test_fbs_supply_from_orders import (
        _create_product,
        _create_ready_order,
    )
    from tests.test_fbs_supply_from_orders import (
        _register_ff_admin as register,
    )
    from tests.test_fbs_supply_from_orders import (
        _setup_seller_with_token as setup,
    )

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await register(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant = uuid.UUID(me.json()["tenant_id"])
    seller, warehouse, location = await setup(async_client, headers, suffix)
    product = await _create_product(async_client, headers, seller, sku=f"sticker-{suffix}")
    order_id = await _create_ready_order(
        tenant,
        uuid.UUID(seller),
        uuid.UUID(warehouse),
        uuid.UUID(location),
        product,
        order_id=666777002,
    )
    calls = []

    async def stickers(client, *, api_token, order_ids, **kwargs):
        calls.append(order_ids)
        if provider_fails == "timeout":
            await asyncio.sleep(1)
        if provider_fails:
            raise WildberriesClientError("transport_error")
        return [
            {
                "orderId": oid,
                "partA": "5877994",
                "partB": "0283",
                "barcode": "*fixture666",
                "file": base64.b64encode(PNG).decode(),
            }
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_print_asset_service.fetch_marketplace_order_stickers", stickers
    )
    if provider_fails in ("timeout", "db_cancel"):
        monkeypatch.setattr(
            "app.services.fbs_supply_service.CREATE_STICKER_PREFETCH_TIMEOUT_SECONDS", 0.1
        )
    if provider_fails == "db_cancel":
        async def interrupted_prefetch(session, *args, **kwargs):
            connection = await session.connection()
            await connection.invalidate()
            await asyncio.sleep(1)

        monkeypatch.setattr(
            "app.services.fbs_supply_service._request_order_stickers_for_picking",
            interrupted_prefetch,
        )
    body = {
        "name": "Immediate stickers",
        "order_ids": [str(order_id)],
        "planned_delivery_type": "warehouse_sc",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = await async_client.post(
        "/operations/fbs-supplies/from-orders", headers=headers, json=body
    )
    assert response.status_code == 201, response.text
    assert calls == ([] if provider_fails == "db_cancel" else [[666777002]])
    result = response.json()
    assert result["supply"]["status"] == "draft"
    assert result["supply"]["packaging_task_id"] is None
    assert result["orders"][0]["sticker"]["code"] == (None if provider_fails else "5877994 0283")
    readback = await async_client.get(
        f"/operations/fbs-supplies/{result['supply']['id']}/workspace", headers=headers
    )
    assert readback.status_code == 200
    assert len(readback.json()["orders"]) == 1
    if not provider_fails:
        content = await async_client.get(
            result["orders"][0]["sticker"]["asset_url"], headers=headers
        )
        assert content.status_code == 200 and content.content == PNG
        repeat = await async_client.post(
            "/operations/fbs-supplies/from-orders", headers=headers, json=body
        )
        assert repeat.status_code == 201, repeat.text
        assert repeat.json()["supply"]["id"] == result["supply"]["id"]
        assert calls == [[666777002]]
