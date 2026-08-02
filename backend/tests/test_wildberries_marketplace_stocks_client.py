from __future__ import annotations

import httpx
import pytest

from app.services.wildberries_client import (
    MarketplaceStockAmount,
    WildberriesClientError,
    fetch_marketplace_stocks,
    put_marketplace_stocks,
    split_marketplace_stocks_batches,
)


def _stock(chrt_id: int, amount: int = 0) -> MarketplaceStockAmount:
    return MarketplaceStockAmount(chrt_id=chrt_id, amount=amount)


# TC-NEW-FBS-STOCK-001 — exact WB PUT/POST contract
@pytest.mark.asyncio
async def test_put_marketplace_stocks_exact_contract_and_204_empty() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content.decode()
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        await put_marketplace_stocks(
            client,
            api_token="wb-secret-token",
            warehouse_id=501001,
            stocks=[_stock(111, 7), _stock(222, 3)],
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v3/stocks/501001"
    assert captured["authorization"] == "wb-secret-token"
    assert captured["content_type"] == "application/json"
    assert (
        captured["body"]
        == '{"stocks":[{"chrtId":111,"amount":7},{"chrtId":222,"amount":3}]}'
    )


@pytest.mark.asyncio
async def test_fetch_marketplace_stocks_exact_contract_and_parse() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"stocks": [{"chrtId": 111, "amount": 7}, {"chrtId": 222, "amount": 3}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        rows = await fetch_marketplace_stocks(
            client,
            api_token="wb-secret-token",
            warehouse_id=501001,
            chrt_ids=[111, 222],
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v3/stocks/501001"
    assert captured["authorization"] == "wb-secret-token"
    assert captured["content_type"] == "application/json"
    assert captured["body"] == '{"chrtIds":[111,222]}'
    assert rows == [_stock(111, 7), _stock(222, 3)]


# TC-NEW-FBS-STOCK-002 — batching boundary
def test_split_marketplace_stocks_batches_1001_items() -> None:
    items = [_stock(chrt_id, chrt_id % 50) for chrt_id in range(1, 1002)]
    batches = split_marketplace_stocks_batches(items)
    assert len(batches) == 2
    assert len(batches[0]) == 1000
    assert len(batches[1]) == 1
    assert batches[0][0].chrt_id == 1
    assert batches[0][-1].chrt_id == 1000
    assert batches[1][0].chrt_id == 1001
    merged_ids = [item.chrt_id for batch in batches for item in batch]
    assert merged_ids == list(range(1, 1002))
    assert len(merged_ids) == len(set(merged_ids))


@pytest.mark.asyncio
async def test_put_marketplace_stocks_rejects_1001_items_before_network() -> None:
    items = [_stock(chrt_id) for chrt_id in range(1, 1002)]

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called for invalid batch")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await put_marketplace_stocks(
                client,
                api_token="wb-token",
                warehouse_id=1,
                stocks=items,
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "invalid_request"


# TC-NEW-FBS-STOCK-009 — PUT + readback happy path
@pytest.mark.asyncio
async def test_put_then_readback_returns_matching_amounts() -> None:
    calls: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.content))
        if request.method == "PUT":
            return httpx.Response(204)
        return httpx.Response(200, json={"stocks": [{"chrtId": 333, "amount": 7}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        await put_marketplace_stocks(
            client,
            api_token="wb-token",
            warehouse_id=77,
            stocks=[_stock(333, 7)],
            marketplace_api_base="https://wb-mock.test",
        )
        rows = await fetch_marketplace_stocks(
            client,
            api_token="wb-token",
            warehouse_id=77,
            chrt_ids=[333],
            marketplace_api_base="https://wb-mock.test",
        )

    assert calls[0][0] == "PUT"
    assert calls[1][0] == "POST"
    assert rows == [_stock(333, 7)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_json", "label"),
    [
        ({"stocks": [{"chrtId": 1, "amount": 1}, {"chrtId": 1, "amount": 2}]}, "duplicate"),
        ({"stocks": [{"chrtId": "1", "amount": 1}]}, "string_id"),
        ({"stocks": [{"chrtId": 1, "amount": "2"}]}, "string_amount"),
        ({"stocks": [{"chrtId": 0, "amount": 1}]}, "zero_id"),
        ({"stocks": [{"chrtId": 1, "amount": -1}]}, "negative_amount"),
        ({"items": []}, "missing_stocks_key"),
        ({"stocks": "bad"}, "stocks_not_list"),
    ],
)
async def test_fetch_marketplace_stocks_malformed_readback_fails(
    response_json: object,
    label: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await fetch_marketplace_stocks(
                client,
                api_token="wb-token",
                warehouse_id=1,
                chrt_ids=[1],
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "invalid_response", label


# TC-NEW-FBS-STOCK-012 — upstream/transport errors without leaking secrets
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 409, 429])
async def test_put_marketplace_stocks_upstream_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"detail": "wb-secret-token must not appear"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await put_marketplace_stocks(
                client,
                api_token="wb-secret-token",
                warehouse_id=1,
                stocks=[_stock(1, 1)],
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "upstream_error"
    assert excinfo.value.status_code == status_code
    assert "wb-secret-token" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_marketplace_stocks_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await fetch_marketplace_stocks(
                client,
                api_token="wb-secret-token",
                warehouse_id=1,
                chrt_ids=[1],
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "transport_error"
    assert "wb-secret-token" not in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stocks", "chrt_ids", "expected_code"),
    [
        ([], None, "invalid_request"),
        (None, [], "invalid_request"),
        ([_stock(1, -1)], None, "invalid_request"),
        ([_stock(0, 1)], None, "invalid_request"),
        ([_stock(1, 1), _stock(1, 2)], None, "invalid_request"),
        (None, [1, 1], "invalid_request"),
        (None, [0], "invalid_request"),
    ],
)
async def test_marketplace_stocks_validation_before_network(
    stocks: list[MarketplaceStockAmount] | None,
    chrt_ids: list[int] | None,
    expected_code: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called for invalid input")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            if stocks is not None:
                await put_marketplace_stocks(
                    client,
                    api_token="wb-token",
                    warehouse_id=1,
                    stocks=stocks,
                    marketplace_api_base="https://wb-mock.test",
                )
            else:
                await fetch_marketplace_stocks(
                    client,
                    api_token="wb-token",
                    warehouse_id=1,
                    chrt_ids=chrt_ids or [],
                    marketplace_api_base="https://wb-mock.test",
                )
    assert excinfo.value.code == expected_code
