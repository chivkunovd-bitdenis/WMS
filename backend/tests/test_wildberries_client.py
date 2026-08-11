from __future__ import annotations

import httpx
import pytest

from app.core.settings import settings
from app.services.wildberries_client import (
    WildberriesClientError,
    build_marketplace_order_meta_put_body,
    fetch_cards_list,
    fetch_marketplace_orders_page,
    fetch_supplies_list,
    put_marketplace_order_meta,
)


@pytest.mark.asyncio
async def test_fetch_cards_list_uses_post_and_returns_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/content/v2/get/cards/list"
        assert request.headers.get("authorization") == "wb-token"
        return httpx.Response(200, json={"cards": [], "cursor": {"updatedAt": "x"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        data = await fetch_cards_list(
            client,
            api_token="wb-token",
            content_api_base="https://wb-mock.test",
            limit=50,
        )
    assert data["cards"] == []


@pytest.mark.asyncio
async def test_fetch_cards_list_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"title": "unauthorized"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await fetch_cards_list(
                client,
                api_token="bad",
                content_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "upstream_error"
    assert excinfo.value.status_code == 401


@pytest.mark.parametrize("body", ["", "<html>not json</html>"])
@pytest.mark.asyncio
async def test_fetch_cards_list_invalid_json(body: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await fetch_cards_list(
                client,
                api_token="wb-token",
                content_api_base="https://wb-mock.test",
            )

    assert excinfo.value.code == "invalid_json"
    assert excinfo.value.status_code is None


@pytest.mark.asyncio
async def test_fetch_supplies_list_e2e_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_supplies", True)
    async with httpx.AsyncClient() as client:
        rows = await fetch_supplies_list(client, api_token="x")
    assert rows[0]["supplyID"] == 888001


@pytest.mark.asyncio
async def test_fetch_cards_list_e2e_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_cards", True)
    async with httpx.AsyncClient() as client:
        data = await fetch_cards_list(client, api_token="ignored")
    assert data["cards"][0]["nmID"] == 424242


@pytest.mark.asyncio
async def test_fetch_marketplace_orders_page_first_request_sends_next_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_orders", False)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = request.url.query.decode()
        return httpx.Response(200, json={"orders": [], "next": None})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        rows, next_token = await fetch_marketplace_orders_page(
            client,
            api_token="wb-token",
            marketplace_api_base="https://wb-mock.test",
            limit=100,
            next_token=None,
        )

    assert rows == []
    assert next_token is None
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v3/orders"
    assert captured["query"] == "limit=100&next=0"


def test_build_marketplace_order_meta_put_body_official_shapes() -> None:
    assert build_marketplace_order_meta_put_body("sgtin", "0101") == {"sgtins": ["0101"]}
    assert build_marketplace_order_meta_put_body("uin", "uin-1") == {"uin": "uin-1"}
    assert build_marketplace_order_meta_put_body("imei", "123") == {"imei": "123"}
    assert build_marketplace_order_meta_put_body("gtin", "0460") == {"gtin": "0460"}
    with pytest.raises(WildberriesClientError) as excinfo:
        build_marketplace_order_meta_put_body("unknown", "x")
    assert excinfo.value.code == "invalid_meta_kind"


@pytest.mark.asyncio
async def test_put_marketplace_order_meta_uses_kind_specific_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", False)
    calls: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content.decode()))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        await put_marketplace_order_meta(
            client,
            api_token="wb-token",
            order_id=1001,
            kind="sgtin",
            value="0101",
            marketplace_api_base="https://wb-mock.test",
        )
        await put_marketplace_order_meta(
            client,
            api_token="wb-token",
            order_id=1002,
            kind="uin",
            value="uin-1",
            marketplace_api_base="https://wb-mock.test",
        )

    assert calls == [
        ("PUT", "/api/v3/orders/1001/meta/sgtin", '{"sgtins":["0101"]}'),
        ("PUT", "/api/v3/orders/1002/meta/uin", '{"uin":"uin-1"}'),
    ]
