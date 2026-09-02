"""Подстановка реквизитов организации по ИНН через DaData.

Зачем: реквизиты плательщика вбиваются руками, а ошибка в ИНН или КПП всплывает
только когда счёт уже уехал. DaData отдаёт наименование, КПП, ОГРН, адрес и
руководителя по одному ИНН — метод входит в бесплатный тариф (10 000 запросов в
сутки), нужен только ключ.

Чего он не отдаёт и отдать не может: **расчётный счёт**. Его нет в открытых
данных ни у кого, поэтому счёт и банк заполняются руками (банк можно подтянуть
отдельным справочником по БИК — это следующий шаг, не этот).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.settings import settings
from app.services.billing_configuration_service import BillingConfigurationError, validate_inn

logger = logging.getLogger(__name__)

DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
REQUEST_TIMEOUT_SECONDS = 8.0


class DadataError(ValueError):
    """Код ошибки, понятный экрану: not_configured, not_found, unavailable."""


def _dict(value: object) -> dict[str, Any]:
    """Ответ DaData — чужой JSON: любой уровень может оказаться не словарём."""
    return value if isinstance(value, dict) else {}


def _first_party(payload: dict[str, Any]) -> dict[str, Any] | None:
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        return None
    first = suggestions[0]
    return first if isinstance(first, dict) else None


async def lookup_party_by_inn(inn: str) -> dict[str, Any]:
    """Вернуть реквизиты организации или ИП по ИНН."""
    token = settings.dadata_token
    if not token:
        raise DadataError("dadata_not_configured")
    try:
        normalized = validate_inn(inn)
    except BillingConfigurationError as exc:
        raise DadataError("inn_invalid") from exc

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                DADATA_URL,
                json={"query": normalized},
                headers={
                    "Authorization": f"Token {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("dadata request failed: %s", exc)
        raise DadataError("dadata_unavailable") from exc

    if response.status_code == 403:
        # Так DaData отвечает и на чужой ключ, и на исчерпанный дневной лимит.
        raise DadataError("dadata_rejected")
    if response.status_code >= 400:
        logger.warning("dadata answered %s", response.status_code)
        raise DadataError("dadata_unavailable")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("dadata answered non-json")
        raise DadataError("dadata_unavailable") from exc

    party = _first_party(payload)
    if party is None:
        raise DadataError("party_not_found")

    data = _dict(party.get("data"))
    name = _dict(data.get("name"))
    address = _dict(data.get("address"))
    management = _dict(data.get("management"))
    state = _dict(data.get("state"))
    return {
        "legal_name": name.get("short_with_opf") or name.get("full_with_opf") or party.get("value"),
        "inn": data.get("inn") or normalized,
        "kpp": data.get("kpp"),
        "ogrn": data.get("ogrn"),
        "address": address.get("unrestricted_value") or address.get("value"),
        "manager": management.get("name"),
        "state": state.get("status"),
    }
