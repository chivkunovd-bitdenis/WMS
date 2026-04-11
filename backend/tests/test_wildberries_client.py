from __future__ import annotations

import httpx
import pytest

from app.core.settings import settings
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_cards_list,
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


@pytest.mark.asyncio
async def test_fetch_cards_list_e2e_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_cards", True)
    async with httpx.AsyncClient() as client:
        data = await fetch_cards_list(client, api_token="ignored")
    assert data["cards"][0]["nmID"] == 424242
