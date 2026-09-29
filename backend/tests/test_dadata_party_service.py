"""lookup_party_by_inn на подставном HTTP-транспорте DaData.

Независимое ревью WMS-547 (F2) нашло, что клиент падает AttributeError, если
DaData отвечает 200 с валидным JSON, но не объектом (``null``, массив, строка):
``payload.get(...)`` вызывается на значении без метода ``.get``. Раньше это
не проверялось — существующие тесты подставляли только словарь-ответ.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.settings import settings
from app.services import dadata_party_service as svc

VALID_INN = "500100732259"

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(handler: Any) -> Any:
    def factory(**_kwargs: object) -> httpx.AsyncClient:
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    return factory


def _json_handler(status_code: int, body: object) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(status_code, json=body)

    return handler


@pytest.fixture(autouse=True)
def _dadata_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dadata_token", "test-dadata-token")


@pytest.mark.asyncio
async def test_lookup_party_by_inn_returns_fields_on_valid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "suggestions": [
            {
                "value": "ООО РОМАШКА",
                "data": {
                    "inn": VALID_INN,
                    "kpp": "770701001",
                    "name": {"short_with_opf": "ООО «Ромашка»"},
                    "address": {"unrestricted_value": "г. Москва"},
                    "management": {"name": "Иванов И. И."},
                    "state": {"status": "ACTIVE"},
                },
            }
        ]
    }
    monkeypatch.setattr(svc.httpx, "AsyncClient", _client_factory(_json_handler(200, body)))
    result = await svc.lookup_party_by_inn(VALID_INN)
    assert result["legal_name"] == "ООО «Ромашка»"
    assert result["kpp"] == "770701001"
    assert result["inn"] == VALID_INN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [None, [], "unexpected"],
    ids=["null", "empty-list", "string"],
)
async def test_lookup_party_by_inn_normalizes_non_object_response_to_dadata_error(
    monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    monkeypatch.setattr(svc.httpx, "AsyncClient", _client_factory(_json_handler(200, body)))
    with pytest.raises(svc.DadataError) as exc_info:
        await svc.lookup_party_by_inn(VALID_INN)
    # Не "party_not_found": это сбой ответа, а не законный «организация не
    # найдена» — иначе пользователь получит неверный совет проверить ИНН.
    assert str(exc_info.value) == "dadata_unavailable"


@pytest.mark.asyncio
async def test_lookup_party_by_inn_empty_suggestions_is_still_party_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc.httpx, "AsyncClient", _client_factory(_json_handler(200, {"suggestions": []}))
    )
    with pytest.raises(svc.DadataError) as exc_info:
        await svc.lookup_party_by_inn(VALID_INN)
    assert str(exc_info.value) == "party_not_found"
