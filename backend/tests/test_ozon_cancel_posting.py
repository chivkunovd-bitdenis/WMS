"""Отмена отправления Ozon: метод, форма и то, чего делать нельзя.

До 03.09.2026 отмены для Ozon не было вовсе — запрос уходил PATCH-ом в чужой
вайлдберрисовский кабинет с отрицательным хешем вместо номера заказа, а после
защиты просто отказывал. Метода не было и в нашей копии спецификации FBS: там
только сборка, перевозка и акты.

Путь `/v2/posting/fbs/cancel` (`PostingAPI_CancelFbsPosting`) взят из
официальной спецификации Ozon и добавлен в нашу копию дословно, вместе с
`/v1/posting/fbs/cancel-reason`. Живой кабинет 03.09.2026 подтвердил, что метод
причин существует и понимает наше тело: на несуществующее отправление он
отвечает `404 POSTING_NOT_FOUND`, а не `400` про форму запроса.

Сам вызов отмены — необратимая мутация в боевом кабинете живого продавца, и он
здесь не выполняется: проверяется то, что мы отправляем и как разбираем ответ.
"""

from __future__ import annotations

import pytest

from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from app.services.ozon_fbs_process_service import (
    CANCEL_PATH,
    CANCEL_REASON_PATH,
    OzonFbsProcessError,
    cancel_posting,
)

POSTING = "12345-0001-1"


def _reasons(*ids_and_types: tuple[int, str]) -> dict[str, object]:
    return {
        "result": [
            {
                "posting_number": POSTING,
                "reasons": [
                    {"id": reason_id, "title": "причина", "type_id": type_id}
                    for reason_id, type_id in ids_and_types
                ],
            }
        ]
    }


def _provider(transport: FakeMarketplaceTransport) -> OzonMarketplaceProvider:
    return OzonMarketplaceProvider(transport=transport)


async def test_cancel_asks_for_reasons_then_cancels_with_the_out_of_stock_one() -> None:
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            CANCEL_REASON_PATH: _reasons((352, "seller"), (402, "seller")),
            CANCEL_PATH: {"result": True},
        }
    )

    await cancel_posting(_provider(transport), client_id="c", api_key="k", posting_number=POSTING)

    assert [path for path, _ in transport.endpoint_calls] == [CANCEL_REASON_PATH, CANCEL_PATH]
    assert transport.endpoint_calls[0][1] == {"related_posting_numbers": [POSTING]}
    # Ни `cancel_reason_message`, ни каких-либо лишних полей: причина 352 их не требует.
    assert transport.endpoint_calls[1][1] == {
        "posting_number": POSTING,
        "cancel_reason_id": 352,
    }


async def test_a_buyer_reason_is_not_a_permission_for_the_seller_to_cancel() -> None:
    """У Ozon рядом лежат причины покупателя; подставлять их продавцу нельзя."""
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            CANCEL_REASON_PATH: _reasons((352, "buyer")),
            CANCEL_PATH: {"result": True},
        }
    )

    with pytest.raises(OzonFbsProcessError) as caught:
        await cancel_posting(
            _provider(transport),
            client_id="c",
            api_key="k",
            posting_number=POSTING,
        )
    assert caught.value.code == "ozon_cancel_not_available"
    assert [path for path, _ in transport.endpoint_calls] == [CANCEL_REASON_PATH]


async def test_a_reason_ozon_does_not_offer_is_refused_before_the_mutation() -> None:
    """Частая ошибка метода — `HAS_INCORRECT_CANCEL_REASON`. Проще спросить заранее."""
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            CANCEL_REASON_PATH: _reasons((400, "seller")),
            CANCEL_PATH: {"result": True},
        }
    )

    with pytest.raises(OzonFbsProcessError) as caught:
        await cancel_posting(
            _provider(transport),
            client_id="c",
            api_key="k",
            posting_number=POSTING,
            reason_id=352,
        )
    assert caught.value.code == "ozon_cancel_reason_unavailable"
    assert [path for path, _ in transport.endpoint_calls] == [CANCEL_REASON_PATH]


async def test_reason_other_without_a_message_never_leaves_the_process() -> None:
    """«Если значение параметра `cancel_reason_id` — 402, заполните поле
    `cancel_reason_message`» — правило спецификации, которого нет в её `required`.
    """
    transport = FakeMarketplaceTransport(endpoint_responses={CANCEL_PATH: {"result": True}})

    with pytest.raises(OzonFbsProcessError) as caught:
        await cancel_posting(
            _provider(transport),
            client_id="c",
            api_key="k",
            posting_number=POSTING,
            reason_id=402,
        )
    assert caught.value.code == "ozon_cancel_reason_message_required"
    assert transport.endpoint_calls == []


async def test_reason_other_with_a_message_carries_it_to_ozon() -> None:
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            CANCEL_REASON_PATH: _reasons((402, "seller")),
            CANCEL_PATH: {"result": True},
        }
    )

    await cancel_posting(
        _provider(transport),
        client_id="c",
        api_key="k",
        posting_number=POSTING,
        reason_id=402,
        reason_message="  товар повреждён при упаковке  ",
    )

    assert transport.endpoint_calls[1][1] == {
        "posting_number": POSTING,
        "cancel_reason_id": 402,
        "cancel_reason_message": "товар повреждён при упаковке",
    }


async def test_an_answer_without_result_true_is_not_a_cancellation() -> None:
    """Документированный признак успеха ровно один — `result: true`."""
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            CANCEL_REASON_PATH: _reasons((352, "seller")),
            CANCEL_PATH: {},
        }
    )

    with pytest.raises(OzonFbsProcessError) as caught:
        await cancel_posting(
            _provider(transport),
            client_id="c",
            api_key="k",
            posting_number=POSTING,
        )
    assert caught.value.code == "ozon_cancel_unconfirmed"


async def test_an_empty_posting_number_never_reaches_ozon() -> None:
    transport = FakeMarketplaceTransport()

    with pytest.raises(OzonFbsProcessError) as caught:
        await cancel_posting(_provider(transport), client_id="c", api_key="k", posting_number="")
    assert caught.value.code == "ozon_posting_number_missing"
    assert transport.endpoint_calls == []


async def test_a_blocked_cabinet_surfaces_as_itself_and_stops_the_mutation() -> None:
    transport = FakeMarketplaceTransport(
        errors={CANCEL_REASON_PATH: MarketplaceProviderError("ozon", 403, {"code": 7})},
        endpoint_responses={CANCEL_PATH: {"result": True}},
    )

    with pytest.raises(MarketplaceProviderError) as caught:
        await cancel_posting(
            _provider(transport),
            client_id="c",
            api_key="k",
            posting_number=POSTING,
        )
    assert caught.value.is_account_blocked is True
    assert [path for path, _ in transport.endpoint_calls] == [CANCEL_REASON_PATH]
