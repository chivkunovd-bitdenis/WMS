"""Боевой транспорт Ozon: то, чего до него не существовало вовсе.

До этого модуля во всём бэкенде был ровно один настоящий HTTP-запрос к Ozon —
проверка ключей через `/v1/seller/info`. Все десять мест, где создаётся
провайдер, сидели на фейке, а настроек Ozon в системе не было ни одной.

Формы запросов и кодов ответов здесь не выдуманы: `/v2/warehouse/list`,
`/v4/posting/fbs/unfulfilled/list`, `/v4/product/info/attributes`,
`/v2/posting/fbs/act/get-pdf` и `/v1/warehouse/list` проверены живым кабинетом
03.09.2026 читающими вызовами.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from app.core.settings import settings
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
)
from app.services.ozon_marketplace_transport import (
    PACKAGE_LABEL_PATH,
    PRODUCTS_STOCKS_PATH,
    UNFULFILLED_LIST_PATH,
    HttpxOzonMarketplaceTransport,
)
from app.services.ozon_provider_factory import build_ozon_transport


def _transport(handler: Any) -> HttpxOzonMarketplaceTransport:
    return HttpxOzonMarketplaceTransport(
        base_url="https://api-seller.ozon.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_json_call_sends_credentials_and_returns_parsed_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["client_id"] = request.headers.get("Client-Id")
        seen["api_key"] = request.headers.get("Api-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"warehouses": [{"warehouse_id": 1020005028840530}]})

    result = await _transport(handler).call(
        client_id="5641753",
        api_key="secret",
        path="/v2/warehouse/list",
        payload={},
    )

    assert seen["url"] == "https://api-seller.ozon.test/v2/warehouse/list"
    assert seen["client_id"] == "5641753"
    assert seen["api_key"] == "secret"
    assert seen["body"] == {}
    assert result == {"warehouses": [{"warehouse_id": 1020005028840530}]}


async def test_obsolete_method_becomes_a_typed_provider_error() -> None:
    """`/v1/warehouse/list` живьём отвечает 400 «obsolete method cannot be used»."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 9, "message": "obsolete method cannot be used"})

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).call(
            client_id="c",
            api_key="k",
            path="/v1/warehouse/list",
            payload={},
        )
    assert caught.value.status_code == 400
    assert caught.value.payload["message"] == "obsolete method cannot be used"
    assert caught.value.is_account_blocked is False


async def test_account_blocked_stays_recognisable_through_the_live_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"code": 7, "message": "client is blocked"})

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).call(client_id="c", api_key="k", path="/x", payload={})
    assert caught.value.is_account_blocked is True


async def test_rate_limit_carries_retry_after_for_the_shared_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": 8}, headers={"Retry-After": "12"})

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).call(client_id="c", api_key="k", path="/x", payload={})
    assert caught.value.payload["retry_after_seconds"] == 12.0


async def test_network_failure_is_the_retryable_transport_error_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).call(client_id="c", api_key="k", path="/x", payload={})
    assert caught.value.code == "transport_error"
    assert caught.value.status_code is None


async def test_binary_answer_is_normalised_into_the_same_file_envelope() -> None:
    """Спека Ozon сама себе противоречит: бинарный тип и JSON-пример разом.

    Транспорт принимает оба варианта и отдаёт наверх один, поэтому разбор в
    `ozon_fbs_process_service` не зависит от того, кто из двух прав.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4 fake",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="act.pdf"',
            },
        )

    result = await _transport(handler).call(
        client_id="c",
        api_key="k",
        path="/v2/posting/fbs/act/get-pdf",
        payload={"id": 1},
    )
    assert isinstance(result, dict)
    assert base64.b64decode(str(result["file_content"])) == b"%PDF-1.4 fake"
    assert result["content_type"] == "application/pdf"
    assert result["file_name"] == "act.pdf"


async def test_unfulfilled_orders_are_walked_page_by_page_with_barcodes_asked_for() -> None:
    """Штрихкоды и цену Ozon кладёт в ответ только по явной просьбе в `with`."""
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == UNFULFILLED_LIST_PATH
        body = json.loads(request.content)
        bodies.append(body)
        if not body.get("cursor"):
            return httpx.Response(
                200,
                json={
                    "postings": [{"posting_number": "0195832-0021-1"}],
                    "cursor": "next-page",
                    "has_next": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "postings": [{"posting_number": "0195832-0021-2"}],
                "cursor": "",
                "has_next": False,
            },
        )

    rows = await _transport(handler).fetch_orders(client_id="c", api_key="k")

    assert [row["posting_number"] for row in rows] == ["0195832-0021-1", "0195832-0021-2"]
    assert bodies[0]["with"] == {"barcodes": True, "financial_data": True}
    assert "cutoff_from" in bodies[0]["filter"] and "cutoff_to" in bodies[0]["filter"]
    assert bodies[1]["cursor"] == "next-page"


async def test_statuses_are_read_back_per_posting_and_a_vanished_one_is_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        posting_number = json.loads(request.content)["posting_number"]
        if posting_number == "gone":
            return httpx.Response(404, json={"code": 5, "message": "Unknown posting number"})
        return httpx.Response(
            200,
            json={"result": {"posting_number": posting_number, "status": "delivering"}},
        )

    rows = await _transport(handler).fetch_statuses(
        client_id="c",
        api_key="k",
        order_ids=["0195832-0021-1", "gone"],
    )
    assert rows == [{"posting_number": "0195832-0021-1", "status": "delivering"}]


async def test_supply_qr_is_the_carriage_barcode_and_comes_back_as_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/posting/fbs/act/get-barcode"
        assert json.loads(request.content) == {"id": 12345}
        return httpx.Response(200, content=b"\x89PNG fake", headers={"Content-Type": "image/png"})

    png = await _transport(handler).fetch_supply_qr(client_id="c", api_key="k", supply_id="12345")
    assert png == b"\x89PNG fake"


async def test_supply_qr_refuses_a_placeholder_supply_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no request expected for a PENDING placeholder")

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).fetch_supply_qr(
            client_id="c",
            api_key="k",
            supply_id="PENDING-4f2a",
        )
    assert caught.value.code == "ozon_carriage_id_invalid"


async def test_stocks_go_out_signed_by_product_id_without_the_removed_quant_size() -> None:
    """Ровно один идентификатор в позиции — это требование самой спецификации.

    «Если запрос содержит оба параметра — `offer_id` и `product_id`, изменения
    применятся к товару с `offer_id`. Для избежания неоднозначности используйте
    только один из параметров». Плюс `quant_size` Ozon удалил из запроса
    26.06.2025, хотя в `required` схемы он до сих пор висит.
    """
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == PRODUCTS_STOCKS_PATH
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "offer_id": "OZ1",
                        "product_id": 6204279711,
                        "warehouse_id": 1020005028840530,
                        "updated": True,
                        "errors": [],
                    }
                ]
            },
        )

    await _transport(handler).publish_stocks(
        client_id="c",
        api_key="k",
        stocks=[
            {
                "offer_id": "OZ1",
                "product_id": 6204279711,
                "stock": 7,
                "warehouse_id": 1020005028840530,
            }
        ],
    )

    assert bodies == [
        {"stocks": [{"warehouse_id": 1020005028840530, "stock": 7, "product_id": 6204279711}]}
    ]


async def test_stocks_fall_back_to_the_seller_article_when_there_is_no_product_id() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"result": [{"offer_id": "OZ1", "updated": True}]})

    await _transport(handler).publish_stocks(
        client_id="c",
        api_key="k",
        stocks=[{"offer_id": " OZ1 ", "stock": 0, "warehouse_id": "1020005028840530"}],
    )

    assert bodies[0]["stocks"] == [
        {"warehouse_id": 1020005028840530, "stock": 0, "offer_id": "OZ1"}
    ]


async def test_stocks_are_split_into_batches_of_the_hundred_ozon_allows() -> None:
    """Живой кабинет сам назвал границу: «between 1 and 100 items, inclusive»."""
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sizes.append(len(body["stocks"]))
        rows = [{"product_id": item["product_id"], "updated": True} for item in body["stocks"]]
        return httpx.Response(200, json={"result": rows})

    await _transport(handler).publish_stocks(
        client_id="c",
        api_key="k",
        stocks=[{"product_id": index + 1, "stock": 1, "warehouse_id": 42} for index in range(250)],
    )

    assert sizes == [100, 100, 50]


async def test_a_rejected_stock_row_is_an_error_and_carries_ozons_own_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": [
                    {"product_id": 1, "warehouse_id": 42, "updated": True, "errors": []},
                    {
                        "product_id": 2,
                        "warehouse_id": 42,
                        "updated": False,
                        "errors": [
                            {
                                "code": "PRODUCT_IS_ARCHIVED",
                                "message": "Товар в архиве.",
                            }
                        ],
                    },
                ]
            },
        )

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).publish_stocks(
            client_id="c",
            api_key="k",
            stocks=[
                {"product_id": 1, "stock": 1, "warehouse_id": 42},
                {"product_id": 2, "stock": 1, "warehouse_id": 42},
            ],
        )
    assert caught.value.code == "ozon_stock_rejected"
    failed = caught.value.payload["failed"]
    assert isinstance(failed, list)
    assert failed[0]["product_id"] == 2
    assert failed[0]["codes"] == ["PRODUCT_IS_ARCHIVED"]


async def test_an_answer_without_result_rows_is_not_treated_as_a_confirmation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).publish_stocks(
            client_id="c",
            api_key="k",
            stocks=[{"product_id": 1, "stock": 1, "warehouse_id": 42}],
        )
    assert caught.value.code == "ozon_stock_unconfirmed"


async def test_a_stock_without_warehouse_or_identifier_never_reaches_the_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("an invalid stock row must not be sent")

    for row, reason in (
        ({"product_id": 1, "stock": 1}, "warehouse_id"),
        ({"product_id": 1, "warehouse_id": 42}, "stock"),
        ({"stock": 1, "warehouse_id": 42}, "identifier"),
    ):
        with pytest.raises(MarketplaceProviderError) as caught:
            await _transport(handler).publish_stocks(client_id="c", api_key="k", stocks=[row])
        assert caught.value.code == "ozon_stock_item_invalid"
        assert caught.value.payload["reason"] == reason


async def test_publishing_an_empty_list_makes_no_request_at_all() -> None:
    """Ozon отвечает на пустой список 400; спрашивать его об этом незачем."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("an empty publish must not reach the network")

    await _transport(handler).publish_stocks(client_id="c", api_key="k", stocks=[])


def test_factory_keeps_the_local_fake_until_the_setting_is_switched_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ozon_live_api_enabled", False)
    assert isinstance(build_ozon_transport(), FakeMarketplaceTransport)
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    assert isinstance(build_ozon_transport(), HttpxOzonMarketplaceTransport)


def test_factory_keeps_the_blocked_operation_semantics_of_the_local_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ozon_live_api_enabled", False)
    transport = build_ozon_transport(blocked_operation="fetch_orders")
    assert isinstance(transport, FakeMarketplaceTransport)
    assert transport.errors["fetch_orders"].is_account_blocked is True


async def test_labels_are_asked_one_posting_at_a_time() -> None:
    """Спека того же метода: ошибка одного отправления рушит весь пакет.

    «Если хотя бы для одного отправления возникнет ошибка, этикетки не будут
    подготовлены для всех отправлений в запросе» — поэтому двадцать номеров в
    одном запросе нам не подходят, спрашиваем по одному.
    """
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == PACKAGE_LABEL_PATH
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=b"%PDF-1.7 label",
            headers={"Content-Type": "application/pdf"},
        )

    rows = await _transport(handler).fetch_order_labels(
        client_id="c",
        api_key="k",
        posting_numbers=["0195832-0021-1", "0195832-0021-2"],
    )

    assert bodies == [
        {"posting_number": ["0195832-0021-1"]},
        {"posting_number": ["0195832-0021-2"]},
    ]
    assert [row["posting_number"] for row in rows] == ["0195832-0021-1", "0195832-0021-2"]
    assert base64.b64decode(str(rows[0]["file"])) == b"%PDF-1.7 label"
    assert rows[0]["content_type"] == "application/pdf"


async def test_one_unready_posting_does_not_take_the_others_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        posting_number = json.loads(request.content)["posting_number"][0]
        if posting_number.endswith("-1"):
            return httpx.Response(
                400,
                json={"code": 3, "message": "The next postings aren't ready"},
            )
        return httpx.Response(
            200,
            content=b"%PDF-1.7 label",
            headers={"Content-Type": "application/pdf"},
        )

    rows = await _transport(handler).fetch_order_labels(
        client_id="c",
        api_key="k",
        posting_numbers=["0195832-0021-1", "0195832-0021-2"],
    )

    assert rows[0]["error_code"] == "ozon_label_400"
    assert rows[0]["error_message"] == "The next postings aren't ready"
    assert "file" not in rows[0]
    assert base64.b64decode(str(rows[1]["file"])) == b"%PDF-1.7 label"


async def test_a_blocked_account_stops_the_whole_label_run() -> None:
    """Заблокированный кабинет — не свойство одного отправления."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["posting_number"][0])
        return httpx.Response(403, json={"code": 7, "message": "client is blocked"})

    with pytest.raises(MarketplaceProviderError) as caught:
        await _transport(handler).fetch_order_labels(
            client_id="c",
            api_key="k",
            posting_numbers=["a", "b"],
        )
    assert caught.value.is_account_blocked is True
    assert seen == ["a"]
