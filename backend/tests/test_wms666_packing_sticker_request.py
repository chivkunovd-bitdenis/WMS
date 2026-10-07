"""WMS-666: the packing request reaches WB and persists usable stickers."""

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
