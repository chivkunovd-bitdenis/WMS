"""Сведения о продавце по API площадки — источник для кнопок «Заполнить из WB /
из Ozon» в окне реквизитов селлера (WMS-547).

Что реально приходит от площадок (проверено по официальной документации,
раздел 2.3 требований WMS-547): только ИНН и наименование. WB —
``GET /api/v1/seller-info`` (common-api, любой токен, у базового — лимит раз в
сутки); Ozon — ``POST /v1/seller/info`` через общую границу провайдера
(``build_ozon_provider``). КПП ни у кого нет — он подставляется через уже
существующую подстановку DaData по полученному ИНН (``dadata_party_service``),
банковские поля не приходят ниоткуда и здесь не заполняются никогда.

Два уровня специально разделены:

* ``fetch_wb_requisites`` / ``fetch_ozon_requisites`` — разбор ответа площадки.
  Отсутствующий, ``null`` или пустой ИНН, а также ИНН с неверным контрольным
  числом — это не сбой запроса, а просто «в этом ответе взять нечего»:
  функция возвращает ``None`` без исключения (failure-cases B03). Настоящий
  сбой обращения к площадке (ключ отклонён, лимit частоты, площадка не
  ответила, кабинет Ozon заблокирован) — это исключение
  ``SellerRequisitesLookupError``.
* ``lookup_requisites`` — тот же разбор плюс наложение DaData, тоже возвращает
  ``None`` без исключения, если площадка не дала usable ИНН. Этим слоем
  пользуется как кнопка (оборачивает ``None`` в ошибку ``inn_missing`` через
  ``lookup_requisites_for_button``), так и будущее автозаполнение при
  подключении ключа (WMS-547 D2): там отсутствие данных — не ошибка, а
  «просто нечего сохранять».

Значения токенов никогда не попадают в исключения и в текст логов — только
код ошибки и код HTTP-ответа площадки.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.services.billing_configuration_service import BillingConfigurationError, validate_inn
from app.services.dadata_party_service import DadataError, lookup_party_by_inn
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
    SellerNotFound,
)
from app.services.marketplace_provider import MarketplaceProviderError
from app.services.ozon_provider_factory import build_ozon_provider
from app.services.wildberries_credentials_service import (
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)

logger = logging.getLogger(__name__)

WB_SELLER_INFO_PATH = "/api/v1/seller-info"
OZON_SELLER_INFO_PATH = "/v1/seller/info"
WB_REQUEST_TIMEOUT_SECONDS = 15.0

# Стенд PSP-2 без живых ключей: valid-по-контрольному-числу тестовый ИНН ИП
# (12 цифр) — тот же формат, что в примере официальной документации WB
# («ИП Кружинин В. Р.»).
_MOCK_WB_SELLER_INFO: dict[str, Any] = {
    "name": "ИП E2E Тестов Т. Т.",
    "tin": "500100732259",
    "sid": "00000000-0000-0000-0000-000000000000",
    "tradeMark": "E2E-MOCK-BRAND",
}


class SellerRequisitesLookupError(Exception):
    """Код ошибки для фронта; значений ключей и сырых ответов площадки не несёт.

    Коды: ``key_not_connected``, ``marketplace_rejected_key``,
    ``marketplace_rate_limited``, ``marketplace_unavailable``,
    ``ozon_account_blocked``, ``inn_missing``.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MarketplaceRequisites:
    inn: str
    legal_name: str | None
    kpp: str | None


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _valid_inn_or_none(raw: object) -> str | None:
    candidate = _clean_str(raw)
    if candidate is None:
        return None
    try:
        return validate_inn(candidate)
    except BillingConfigurationError:
        return None


async def _first_wb_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str | None:
    """Любой сохранённый токен селлера: метод сведений о продавце принимает
    токен любой категории (документация WB, раздел 2.3 требований)."""
    tokens = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if tokens is None:
        return None
    content_token, supplies_token = tokens
    if content_token:
        return content_token
    if supplies_token:
        return supplies_token
    return await get_decrypted_marketplace_token(session, tenant_id, seller_id)


async def _call_wb_seller_info(token: str) -> dict[str, Any]:
    if settings.e2e_mock_wb_seller_info:
        return dict(_MOCK_WB_SELLER_INFO)
    base = settings.wildberries_common_api_base.rstrip("/")
    url = f"{base}{WB_SELLER_INFO_PATH}"
    headers = {"Authorization": token}
    try:
        async with httpx.AsyncClient(timeout=WB_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        logger.warning("wb seller-info: transport error (%s)", type(exc).__name__)
        raise SellerRequisitesLookupError("marketplace_unavailable") from exc
    if response.status_code == 429:
        raise SellerRequisitesLookupError("marketplace_rate_limited")
    if response.status_code in (401, 403):
        raise SellerRequisitesLookupError("marketplace_rejected_key")
    if response.status_code >= 400:
        logger.warning("wb seller-info: upstream status %s", response.status_code)
        raise SellerRequisitesLookupError("marketplace_unavailable")
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("wb seller-info: non-json response")
        raise SellerRequisitesLookupError("marketplace_unavailable") from exc
    return payload if isinstance(payload, dict) else {}


async def fetch_wb_requisites(token: str) -> MarketplaceRequisites | None:
    """``None`` — WB ответил, но без usable ИНН (нет/``null``/пусто/неверная
    контрольная сумма). Исключение — только настоящий сбой обращения к WB."""
    raw = await _call_wb_seller_info(token)
    inn = _valid_inn_or_none(raw.get("tin"))
    if inn is None:
        return None
    return MarketplaceRequisites(inn=inn, legal_name=_clean_str(raw.get("name")), kpp=None)


async def _call_ozon_seller_info(*, client_id: str, api_key: str) -> dict[str, Any]:
    provider = build_ozon_provider()
    try:
        raw = await provider.call(
            client_id=client_id,
            api_key=api_key,
            path=OZON_SELLER_INFO_PATH,
            payload={},
        )
    except MarketplaceProviderError as exc:
        if exc.is_account_blocked:
            raise SellerRequisitesLookupError("ozon_account_blocked") from exc
        if exc.status_code == 429:
            raise SellerRequisitesLookupError("marketplace_rate_limited") from exc
        if exc.status_code in (401, 403):
            raise SellerRequisitesLookupError("marketplace_rejected_key") from exc
        logger.warning(
            "ozon seller-info: upstream error code=%s status=%s", exc.code, exc.status_code
        )
        raise SellerRequisitesLookupError("marketplace_unavailable") from exc
    return raw if isinstance(raw, dict) else {}


async def fetch_ozon_requisites(*, client_id: str, api_key: str) -> MarketplaceRequisites | None:
    """``None`` — Ozon ответил, но без usable ИНН (нет ``company``/ИНН, или ИНН
    с неверной контрольной суммой). Исключение — только настоящий сбой
    обращения к Ozon (в т.ч. заблокированный кабинет)."""
    raw = await _call_ozon_seller_info(client_id=client_id, api_key=api_key)
    company_raw = raw.get("company")
    company = company_raw if isinstance(company_raw, dict) else {}
    inn = _valid_inn_or_none(company.get("inn"))
    if inn is None:
        return None
    legal_name = _clean_str(company.get("legal_name")) or _clean_str(company.get("name"))
    return MarketplaceRequisites(inn=inn, legal_name=legal_name, kpp=None)


async def overlay_dadata(requisites: MarketplaceRequisites) -> MarketplaceRequisites:
    """Наложить DaData на уже полученный от площадки ИНН — тот же источник и
    тот же вид, что даёт существующая кнопка «Заполнить по ИНН». Отказ или
    отсутствие настройки DaData — не ошибка этого пути: остаётся то, что дала
    площадка (R11 требований WMS-547)."""
    try:
        party = await lookup_party_by_inn(requisites.inn)
    except DadataError:
        return requisites
    legal_name = _clean_str(party.get("legal_name")) or requisites.legal_name
    kpp = _clean_str(party.get("kpp"))
    return MarketplaceRequisites(inn=requisites.inn, legal_name=legal_name, kpp=kpp)


async def lookup_requisites(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str,
) -> MarketplaceRequisites | None:
    """Общая точка для кнопки (WMS-547 D1) и автозаполнения при подключении
    ключа (WMS-547 D2). Вызывающий отвечает за то, что seller_id принадлежит
    tenant_id (иначе не отличить «нет ключа» от «чужой селлер»).

    Возвращает ``None``, если площадка ответила, но без usable ИНН — это не
    ошибка, продолжать нечем. Поднимает ``SellerRequisitesLookupError`` для
    ``key_not_connected`` и настоящих сбоев обращения к площадке.
    """
    if marketplace == "wb":
        token = await _first_wb_token(session, tenant_id, seller_id)
        if not token:
            raise SellerRequisitesLookupError("key_not_connected")
        requisites = await fetch_wb_requisites(token)
    elif marketplace == "ozon":
        try:
            client_id, api_key = await MarketplaceAccountService(session).stored_credentials(
                tenant_id, seller_id
            )
        except (SellerNotFound, MarketplaceAccountError):
            raise SellerRequisitesLookupError("key_not_connected") from None
        requisites = await fetch_ozon_requisites(client_id=client_id, api_key=api_key)
    else:
        raise ValueError(f"unknown marketplace: {marketplace!r}")

    if requisites is None:
        return None
    return await overlay_dadata(requisites)


async def lookup_requisites_for_button(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str,
) -> MarketplaceRequisites:
    """Для эндпоинта кнопки: отсутствие usable ИНН — тоже ошибка ``inn_missing``,
    её нужно показать человеку (в отличие от тихого автозаполнения D2)."""
    requisites = await lookup_requisites(
        session, tenant_id=tenant_id, seller_id=seller_id, marketplace=marketplace
    )
    if requisites is None:
        raise SellerRequisitesLookupError("inn_missing")
    return requisites
