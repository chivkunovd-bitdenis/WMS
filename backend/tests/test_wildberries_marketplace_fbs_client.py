"""Contract tests for typed WB Marketplace FBS client.

OpenAPI reference: dev.wildberries.ru/docs/openapi/orders-fbs (verified 2026-08-03).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import httpx
import pytest

from app.core.settings import settings
from app.services.wildberries_client import (
    add_orders_to_marketplace_supply,
    deliver_marketplace_supply,
    put_marketplace_order_meta,
    reset_mock_marketplace_order_meta,
)
from app.services.wildberries_errors import (
    MetaValidationFailItem,
    WildberriesBusinessError,
    WildberriesClientError,
    translate_wb_message,
    wb_operator_message,
)
from app.services.wildberries_fbs_client import (
    MAX_MARKETPLACE_FBS_BATCH,
    MAX_RETRY_AFTER_WAIT_SECONDS,
    WB_FBS_OPENAPI_VERIFIED_DATE,
    MarketplaceMetaDetail,
    add_orders_to_marketplace_supply_batch,
    delete_marketplace_order_meta,
    delete_marketplace_supply_trbx,
    fetch_marketplace_orders_meta_batch,
    fetch_marketplace_supply_details,
    fetch_marketplace_supply_order_ids,
    fetch_marketplace_supply_trbx_list,
    split_marketplace_order_id_batches,
)


def test_openapi_reference_date_is_set() -> None:
    assert WB_FBS_OPENAPI_VERIFIED_DATE == "2026-08-03"


@pytest.mark.parametrize(
    ("raw", "expected_fragment"),
    [
        ("Supply not found", "не нашёл эту поставку"),
        ("fix them to dispatch items", "ещё обрабатывает поставку"),
        ("MetaValidationFail: uinBadStatus", "отклонил данные маркировки"),
        ("mandatory mark is required", "требует обязательную маркировку"),
    ],
)
def test_known_wb_operator_messages_are_translated(
    raw: str, expected_fragment: str
) -> None:
    translated = translate_wb_message(raw)
    assert translated is not None
    assert expected_fragment in translated


def test_wb_response_body_uses_translation_instead_of_raw_english() -> None:
    exc = WildberriesClientError(
        "wb_http_error",
        status_code=502,
        response_body='{"message":"Supply not found"}',
    )
    message = wb_operator_message(exc)
    assert "не нашёл эту поставку" in message
    assert "Supply not found" not in message


def test_unknown_wb_response_body_is_not_shown_as_raw_english() -> None:
    exc = WildberriesClientError(
        "wb_http_error",
        status_code=502,
        response_body='{"message":"upstream exploded in an unknown way"}',
    )
    message = wb_operator_message(exc)
    assert message == "На стороне Wildberries сбой. Повторите операцию через несколько минут."
    assert "upstream exploded" not in message


# TC-NEW-FBS-CLIENT-001 — batch add orders exact contract + 204
@pytest.mark.asyncio
async def test_add_orders_to_supply_batch_exact_contract_and_204() -> None:
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
        await add_orders_to_marketplace_supply_batch(
            client,
            api_token="wb-secret-token",
            supply_id="WB-GI-123",
            order_ids=[1001, 1002],
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/marketplace/v3/supplies/WB-GI-123/orders"
    assert captured["authorization"] == "wb-secret-token"
    assert captured["content_type"] == "application/json"
    assert captured["body"] == '{"orders":[1001,1002]}'


@pytest.mark.asyncio
async def test_fetch_supply_order_ids_exact_contract_and_parse() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={"orderIds": [132334, 203984]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        order_ids = await fetch_marketplace_supply_order_ids(
            client,
            api_token="wb-secret-token",
            supply_id="WB-GI-123",
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/marketplace/v3/supplies/WB-GI-123/order-ids"
    assert order_ids == [132334, 203984]


@pytest.mark.asyncio
async def test_fetch_orders_meta_batch_exact_contract_and_parse() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "orders": [
                    {
                        "id": 123456,
                        "metaDetails": [
                            {
                                "key": "sgtin",
                                "value": "010460...",
                                "decision": "filled",
                                "reason": "confirmed by WB",
                            },
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        rows = await fetch_marketplace_orders_meta_batch(
            client,
            api_token="wb-secret-token",
            order_ids=[123456],
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/marketplace/v3/orders/meta"
    assert captured["body"] == '{"orders":[123456]}'
    assert len(rows) == 1
    assert rows[0].order_id == 123456
    assert rows[0].meta_details[0].key == "sgtin"
    assert rows[0].meta_details[0].value == "010460..."
    assert rows[0].meta_details[0].decision == "filled"
    assert rows[0].meta_details[0].reason == "confirmed by WB"


@pytest.mark.asyncio
async def test_fetch_orders_meta_batch_retries_429_once_after_retry_after() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3600"})
        return httpx.Response(200, json={"orders": [{"id": 123456, "metaDetails": []}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with patch("app.services.wildberries_fbs_client.asyncio.sleep") as sleep:
            rows = await fetch_marketplace_orders_meta_batch(
                client, api_token="wb-token", order_ids=[123456], marketplace_api_base="https://wb-mock.test"
            )

    assert calls == 2
    # WB на 429 умеет просить и час. Столько ждать внутри прохода нельзя: сверка
    # держит строки поставок под блокировкой, а следующий проход и так через
    # десять минут. Поэтому ожидание срезается потолком, а не берётся как есть.
    assert calls == 2
    sleep.assert_awaited_once_with(MAX_RETRY_AFTER_WAIT_SECONDS)
    assert rows[0].order_id == 123456


@pytest.mark.asyncio
async def test_fetch_orders_meta_batch_honors_retry_after_http_date() -> None:
    calls = 0
    retry_at = datetime.now(UTC) + timedelta(seconds=60)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
            )
        return httpx.Response(200, json={"orders": [{"id": 123456, "metaDetails": []}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with patch("app.services.wildberries_fbs_client.asyncio.sleep") as sleep:
            await fetch_marketplace_orders_meta_batch(
                client,
                api_token="wb-token",
                order_ids=[123456],
                marketplace_api_base="https://wb-mock.test",
            )

    assert calls == 2
    # Дата в Retry-After читается правильно, но ожидание всё равно срезается
    # потолком: шестьдесят секунд под блокировкой строк поставки того не стоят.
    delay = sleep.await_args.args[0]
    assert delay == MAX_RETRY_AFTER_WAIT_SECONDS


@pytest.mark.asyncio
async def test_fetch_orders_meta_batch_mock_returns_meta_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)
    reset_mock_marketplace_order_meta()
    transport = httpx.MockTransport(
        lambda request: pytest.fail("mock marking mode must not call the network")
    )

    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        await put_marketplace_order_meta(
            client,
            api_token="wb-token",
            order_id=123456,
            kind="sgtin",
            value="010460...",
            marketplace_api_base="https://wb-mock.test",
        )
        rows = await fetch_marketplace_orders_meta_batch(
            client,
            api_token="wb-token",
            order_ids=[123456],
            marketplace_api_base="https://wb-mock.test",
        )

    assert rows[0].meta is None
    assert rows[0].meta_details == (
        MarketplaceMetaDetail(
            key="sgtin",
            value="010460...",
            decision="pending",
            reason=None,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 500])
async def test_fetch_orders_meta_batch_does_not_retry_other_errors(status_code: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"orders": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError):
            await fetch_marketplace_orders_meta_batch(
                client, api_token="wb-token", order_ids=[123456], marketplace_api_base="https://wb-mock.test"
            )

    assert calls == 1


@pytest.mark.asyncio
async def test_fetch_orders_meta_batch_rejects_malformed_response_after_single_429_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, content=b"not-json")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with patch("app.services.wildberries_fbs_client.asyncio.sleep"):
            with pytest.raises(WildberriesClientError) as excinfo:
                await fetch_marketplace_orders_meta_batch(
                    client, api_token="wb-token", order_ids=[123456], marketplace_api_base="https://wb-mock.test"
                )

    assert calls == 2
    assert excinfo.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_delete_order_meta_exact_contract_and_204() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = request.url.query.decode()
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        await delete_marketplace_order_meta(
            client,
            api_token="wb-secret-token",
            order_id=5632423,
            key="sgtin",
            marketplace_api_base="https://wb-mock.test",
        )

    assert captured["method"] == "DELETE"
    assert captured["path"] == "/api/v3/orders/5632423/meta"
    assert captured["query"] == "key=sgtin"


@pytest.mark.asyncio
async def test_fetch_trbx_list_and_delete_trbx_contract() -> None:
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        if request.method == "GET":
            return httpx.Response(200, json={"trbxes": [{"id": "WB-TRBX-1"}]})
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        trbx_rows = await fetch_marketplace_supply_trbx_list(
            client,
            api_token="wb-token",
            supply_id="WB-GI-9",
            marketplace_api_base="https://wb-mock.test",
        )
        await delete_marketplace_supply_trbx(
            client,
            api_token="wb-token",
            supply_id="WB-GI-9",
            trbx_ids=["WB-TRBX-1"],
            marketplace_api_base="https://wb-mock.test",
        )

    assert calls[0][0] == "GET"
    assert calls[0][1] == "/api/v3/supplies/WB-GI-9/trbx"
    assert trbx_rows[0].trbx_id == "WB-TRBX-1"
    assert calls[1][0] == "DELETE"
    assert calls[1][1] == "/api/v3/supplies/WB-GI-9/trbx"
    assert calls[1][2] == b'{"trbxIds":["WB-TRBX-1"]}'


@pytest.mark.asyncio
async def test_fetch_supply_details_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "WB-GI-777",
                "name": "Test supply",
                "done": False,
                "orders": [1, 2],
                "trbxIds": ["WB-TRBX-9"],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        details = await fetch_marketplace_supply_details(
            client,
            api_token="wb-token",
            supply_id="WB-GI-777",
            marketplace_api_base="https://wb-mock.test",
        )

    assert details.supply_id == "WB-GI-777"
    assert details.name == "Test supply"
    assert details.done is False
    assert details.order_ids == (1, 2)
    assert details.trbx_ids == ("WB-TRBX-9",)


# TC-NEW-FBS-CLIENT-002 — chunk boundary 101 → 2 batches
def test_split_marketplace_order_id_batches_101_items() -> None:
    order_ids = list(range(1, 102))
    batches = split_marketplace_order_id_batches(order_ids)
    assert len(batches) == 2
    assert len(batches[0]) == MAX_MARKETPLACE_FBS_BATCH
    assert len(batches[1]) == 1
    assert batches[0][0] == 1
    assert batches[0][-1] == 100
    assert batches[1][0] == 101


@pytest.mark.asyncio
async def test_add_orders_rejects_101_items_before_network() -> None:
    order_ids = list(range(1, 102))

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called for invalid batch")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await add_orders_to_marketplace_supply(
                client,
                api_token="wb-token",
                supply_id="WB-GI-1",
                order_ids=order_ids,
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "invalid_request"


# TC-NEW-FBS-CLIENT-003 — deliver 409 MetaValidationFail parsed by order/key/decision
@pytest.mark.asyncio
async def test_deliver_supply_parses_meta_validation_fail_409() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "code": "MetaValidationFail",
                "message": "Marking validation failed",
                "orders": [
                    {
                        "id": 9001,
                        "metaDetails": [
                            {
                                "key": "sgtin",
                                "value": "bad-code",
                                "decision": "invalid",
                            }
                        ],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesBusinessError) as excinfo:
            await deliver_marketplace_supply(
                client,
                api_token="wb-token",
                supply_id="WB-GI-1",
                marketplace_api_base="https://wb-mock.test",
            )

    err = excinfo.value
    assert err.code == "meta_validation_fail"
    assert err.status_code == 409
    assert err.wb_code == "MetaValidationFail"
    assert len(err.meta_validation) == 1
    item = err.meta_validation[0]
    assert isinstance(item, MetaValidationFailItem)
    assert item.order_id == 9001
    assert item.key == "sgtin"
    assert item.value == "bad-code"
    assert item.decision == "invalid"
    assert "wb-token" not in str(err)


# TC-NEW-FBS-CLIENT-004 — transport error without leaking secrets
@pytest.mark.asyncio
async def test_deliver_supply_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await deliver_marketplace_supply(
                client,
                api_token="wb-secret-token",
                supply_id="WB-GI-1",
                marketplace_api_base="https://wb-mock.test",
            )
    assert excinfo.value.code == "transport_error"
    assert "wb-secret-token" not in str(excinfo.value)


# TC-NEW-FBS-CLIENT-005 — 429 upstream error, single request (no retry loop on 409/429)
@pytest.mark.asyncio
async def test_deliver_supply_429_single_request_no_retry() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            429,
            json={"detail": "wb-secret-token must not appear"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesClientError) as excinfo:
            await deliver_marketplace_supply(
                client,
                api_token="wb-secret-token",
                supply_id="WB-GI-1",
                marketplace_api_base="https://wb-mock.test",
            )

    assert call_count == 1
    assert excinfo.value.code == "upstream_error"
    assert excinfo.value.status_code == 429
    assert "wb-secret-token" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_deliver_supply_409_meta_fail_single_request_no_retry() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            409,
            json={
                "code": "MetaValidationFail",
                "metaDetails": [{"key": "uin", "value": None, "decision": "required"}],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://wb-mock.test") as client:
        with pytest.raises(WildberriesBusinessError) as excinfo:
            await deliver_marketplace_supply(
                client,
                api_token="wb-token",
                supply_id="WB-GI-1",
                marketplace_api_base="https://wb-mock.test",
            )

    assert call_count == 1
    assert excinfo.value.code == "meta_validation_fail"
    assert excinfo.value.meta_validation[0].key == "uin"
    assert excinfo.value.meta_validation[0].decision == "required"
