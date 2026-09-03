"""Ozon FBS mutations validated by official Seller API 2.1 models and readbacks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.schemas.ozon_fbs_api import (
    OzonCarriageCarriageGetRequest,
    OzonCarriageCarriageGetResponse,
    OzonFbsv4FbsPostingShipV4Request,
    OzonFbsv4FbsPostingShipV4Response,
    OzonPostingBooleanResponse,
    OzonPostingv3GetFbsPostingRequest,
    OzonV1CarriageApproveRequest,
    OzonV1CarriageApproveResponse,
    OzonV1CarriageCreateRequest,
    OzonV1CarriageCreateResponse,
    OzonV1GetRestrictionsRequest,
    OzonV1GetRestrictionsResponse,
    OzonV1SetPostingsRequest,
    OzonV1SetPostingsResponse,
    OzonV2FbsPostingProductCountryListRequest,
    OzonV2FbsPostingProductCountryListResponse,
    OzonV2FbsPostingProductCountrySetRequest,
    OzonV2FbsPostingProductCountrySetResponse,
    OzonV2MovePostingToAwaitingDeliveryRequest,
    OzonV2PostingFBSGetBarcodeRequest,
    OzonV2PostingFBSGetBarcodeResponse,
    OzonV2PostingFBSGetBarcodeTextResponse,
    OzonV2PostingFBSGetDigitalActRequest,
    OzonV2PostingFBSGetDigitalActResponse,
    OzonV3GetFbsPostingResponseV3,
    OzonV5FbsPostingProductExemplarStatusV5Request,
    OzonV5FbsPostingProductExemplarStatusV5Response,
    OzonV5FbsPostingProductExemplarValidateV5Request,
    OzonV5FbsPostingProductExemplarValidateV5RequestProduct,
    OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplar,
    OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplarMark,
    OzonV5FbsPostingProductExemplarValidateV5Response,
    OzonV6FbsPostingProductExemplarCreateOrGetV6Request,
    OzonV6FbsPostingProductExemplarCreateOrGetV6Response,
    OzonV6FbsPostingProductExemplarSetV6Request,
)
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError
from app.services.ozon_fbs_errors import decode_file as _decode_file
from app.services.ozon_marking_position_service import (
    OzonMarkingPositionError,
    choose_exemplar_id,
    marking_position_sku,
)

TResponse = TypeVar("TResponse", bound=BaseModel)
__all__ = ["OzonFbsProcessError", "handoff_supply", "read_marking_status", "submit_marking"]

# Лист отгрузки по перевозке. Старый путь `/v2/posting/fbs/digital/act/get-pdf`
# Ozon отключил — живой вызов отвечает «obsolete method cannot be used».
SHIPPING_LIST_PATH = "/v2/posting/fbs/act/get-pdf"

# Этикетки отправлений передача больше не забирает, и это не потеря, а починка.
#
# Забирала она их так: создавала задание `/v2/posting/fbs/package-label/create`,
# опрашивала `/v1/posting/fbs/package-label/get` три раза с паузами 0,05 + 0,1 +
# 0,2 секунды и, не дождавшись, роняла всю передачу ошибкой `ozon_label_not_ready`.
# А спецификация того же метода советует прямо противоположное: «Рекомендуем
# запрашивать этикетки через 45—60 секунд после сборки заказа». То есть на живом
# кабинете передача почти всегда падала бы на этикетках — уже после того, как
# отправления собраны и перевозка подтверждена, то есть откатить нечего.
#
# Вдобавок полученный PDF никто не использовал: `label_bytes` возвращался наверх
# и там выбрасывался. Ездили за документом, роняли из-за него операцию и
# выкидывали результат.
#
# Теперь этикетка живёт там, где ей место, — в конвейере печатных активов
# (`fbs_print_asset_service`), по одной на заказ, по кнопке оператора и уже
# после передачи, когда отправление в статусе `awaiting_deliver` и этикетка у
# Ozon вообще существует.


@dataclass(frozen=True)
class OzonHandoffResult:
    carriage_id: int | None
    used_fallback: bool
    barcode_bytes: bytes | None
    barcode_text: str | None
    shipping_list_bytes: bytes | None


@dataclass(frozen=True)
class OzonMarkingResult:
    accepted: bool
    pending: bool
    reason: str | None
    details: dict[str, object]


def _payload(request: BaseModel) -> dict[str, object]:
    return request.model_dump(by_alias=True, exclude_none=True)


async def _call(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    path: str,
    request: BaseModel,
    response_type: type[TResponse],
    read: bool,
) -> TResponse:
    attempts = 3 if read else 1
    for attempt in range(attempts):
        try:
            raw = await provider.call(
                client_id=client_id,
                api_key=api_key,
                path=path,
                payload=_payload(request),
            )
            if raw is None:
                raise OzonFbsProcessError("ozon_empty_response", "Ozon вернул пустой ответ.")
            return response_type.model_validate(raw)
        except MarketplaceProviderError as exc:
            retryable = read and (
                exc.status_code == 429
                or (exc.status_code is not None and exc.status_code >= 500)
                or exc.code == "transport_error"
            )
            if not retryable or attempt + 1 == attempts:
                raise
            await asyncio.sleep(0.05 * (2**attempt))
        except ValidationError as exc:
            raise OzonFbsProcessError(
                "ozon_invalid_response", "Ozon вернул ответ неизвестного формата."
            ) from exc
    raise AssertionError("unreachable")


async def _ozon_product_id(
    session: AsyncSession,
    order: FbsOrder,
    marking: FbsOrderMarking | None = None,
) -> int:
    if marking is not None:
        try:
            position_sku = await marking_position_sku(session, order, marking)
        except OzonMarkingPositionError as error:
            raise OzonFbsProcessError(error.code, error.message) from error
        if position_sku is not None:
            return position_sku
    details = order.meta_details_json or {}
    direct = details.get("ozon_product_id")
    if direct is not None and str(direct).isdigit():
        return int(str(direct))
    if order.product_id is not None:
        link = await session.scalar(
            select(ProductMarketplaceLink).where(
                ProductMarketplaceLink.tenant_id == order.tenant_id,
                ProductMarketplaceLink.seller_id == order.seller_id,
                ProductMarketplaceLink.product_id == order.product_id,
                ProductMarketplaceLink.marketplace == "ozon",
                ProductMarketplaceLink.is_active.is_(True),
            )
        )
        if link is not None and link.external_sku and link.external_sku.isdigit():
            return int(link.external_sku)
    if order.wb_nm_id is not None:
        return int(order.wb_nm_id)
    raise OzonFbsProcessError(
        "ozon_product_id_missing",
        "У товара нет числового Ozon SKU — сборка отправления невозможна.",
    )


async def _ship_products(session: AsyncSession, order: FbsOrder) -> list[dict[str, int]]:
    positions = list(
        (
            await session.execute(
                select(FbsOrderProduct)
                .where(FbsOrderProduct.order_id == order.id)
                .order_by(FbsOrderProduct.position_index)
            )
        )
        .scalars()
        .all()
    )
    if not positions:
        return [{"product_id": await _ozon_product_id(session, order), "quantity": 1}]

    products: list[dict[str, int]] = []
    for position in positions:
        if position.ozon_sku is None:
            raise OzonFbsProcessError(
                "ozon_product_id_missing",
                "В составе отправления нет числового Ozon SKU — сборка невозможна.",
            )
        if position.quantity <= 0:
            raise OzonFbsProcessError(
                "ozon_product_quantity_invalid",
                "В составе отправления Ozon указано некорректное количество товара.",
            )
        products.append({"product_id": position.ozon_sku, "quantity": position.quantity})
    return products


# Наши виды маркировки в терминах Ozon. Остальные Ozon в экземплярах не хранит.
_MARK_TYPES: dict[str, str] = {"sgtin": "mandatory_mark", "uin": "jw_uin", "imei": "imei"}


async def _full_exemplar_products(
    session: AsyncSession,
    order: FbsOrder,
    *,
    current_marking: FbsOrderMarking,
    current_product_id: int,
    current_exemplar_id: int,
    current_mark_type: str,
) -> list[dict[str, object]]:
    """Собрать полный набор экземпляров отправления, а не один последний код.

    Спецификация метода `/v6/fbs/posting/product/exemplar/set` требует прямо:
    «Всегда передавайте полный набор данных по экземплярам и продуктам».
    Мы же слали ровно один только что отсканированный код, поэтому на
    отправлении из трёх единиц у Ozon оставался бы только последний из них, а
    два предыдущих терялись при каждой следующей отправке.
    """
    positions = {
        position.id: position
        for position in (
            await session.execute(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        )
        .scalars()
        .all()
    }
    markings = list(
        (
            await session.execute(
                select(FbsOrderMarking)
                .where(FbsOrderMarking.order_id == order.id)
                .order_by(FbsOrderMarking.created_at)
            )
        )
        .scalars()
        .all()
    )
    # ключ — (product_id Ozon, exemplar_id); значение — коды этого экземпляра
    grouped: dict[tuple[int, int], list[dict[str, str]]] = {}

    def _add(product_id: int, exemplar_id: int, value: str, mark_type: str) -> None:
        marks = grouped.setdefault((product_id, exemplar_id), [])
        if not any(mark["mark"] == value and mark["mark_type"] == mark_type for mark in marks):
            marks.append({"mark": value, "mark_type": mark_type})

    for row in markings:
        if row.id == current_marking.id:
            continue
        if row.meta_status in {"rejected", "replacement_required"}:
            continue
        mark_type = _MARK_TYPES.get(row.kind)
        if mark_type is None:
            continue
        details = row.meta_details_json if isinstance(row.meta_details_json, dict) else {}
        exemplar_id = details.get("exemplar_id")
        if not isinstance(exemplar_id, int):
            continue
        position = positions.get(row.order_product_id) if row.order_product_id else None
        sku = position.ozon_sku if position is not None else None
        if sku is None:
            # Экземпляр без позиции нельзя отнести к товару; молча приписать его
            # к чужому product_id — хуже, чем не отправить.
            continue
        _add(int(sku), exemplar_id, row.value, mark_type)

    _add(current_product_id, current_exemplar_id, current_marking.value, current_mark_type)

    products: dict[int, list[dict[str, object]]] = {}
    for (product_id, exemplar_id), marks in grouped.items():
        products.setdefault(product_id, []).append(
            {"exemplar_id": exemplar_id, "marks": marks}
        )
    return [
        {
            "product_id": product_id,
            "exemplars": sorted(exemplars, key=lambda item: int(str(item["exemplar_id"]))),
        }
        for product_id, exemplars in sorted(products.items())
    ]


async def submit_marking(
    session: AsyncSession,
    *,
    order: FbsOrder,
    marking: FbsOrderMarking,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> OzonMarkingResult:
    """Validate, set and read back one Ozon exemplar without retrying mutations."""
    posting_number = order.external_order_id or ""
    if not posting_number:
        raise OzonFbsProcessError("ozon_posting_number_missing", "Нет номера отправления Ozon.")
    product_id = await _ozon_product_id(session, order, marking)
    mark_type = _MARK_TYPES.get(marking.kind)
    if mark_type is None:
        return OzonMarkingResult(False, False, "unsupported_mark_type", {})

    exemplars = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v6/fbs/posting/product/exemplar/create-or-get",
        request=OzonV6FbsPostingProductExemplarCreateOrGetV6Request(posting_number=posting_number),
        response_type=OzonV6FbsPostingProductExemplarCreateOrGetV6Response,
        read=False,
    )
    # `products` — необязательное поле ответа. Пустой ответ (в том числе от
    # локального фейка) давал здесь `None`, итерация по нему бросала TypeError,
    # который никто не ловил до самой ручки, и оператор получал 500 вместо
    # понятной ошибки. Пустой список — это «Ozon не вернул экземпляров».
    posting_products = exemplars.products or []
    product = next((item for item in posting_products if item.product_id == product_id), None)
    ids = (
        [item.exemplar_id for item in (product.exemplars or []) if item.exemplar_id]
        if product
        else []
    )
    exemplar_id = await choose_exemplar_id(session, marking, ids)
    if exemplar_id is None:
        raise OzonFbsProcessError("ozon_exemplar_missing", "Ozon не вернул экземпляр товара.")

    mark = OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplarMark(
        mark=marking.value,
        mark_type=mark_type,
    )
    validation = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v5/fbs/posting/product/exemplar/validate",
        request=OzonV5FbsPostingProductExemplarValidateV5Request(
            posting_number=posting_number,
            products=[
                OzonV5FbsPostingProductExemplarValidateV5RequestProduct(
                    product_id=product_id,
                    exemplars=[
                        OzonV5FbsPostingProductExemplarValidateV5RequestProductExemplar.model_validate(
                            {"marks": [_payload(mark)]}
                        )
                    ],
                )
            ],
        ),
        response_type=OzonV5FbsPostingProductExemplarValidateV5Response,
        read=False,
    )
    validated = next(
        (item for item in (validation.products or []) if item.product_id == product_id), None
    )
    if validated is None or not validated.valid:
        errors: list[str] = []
        if validated is not None:
            if validated.error:
                errors.append(validated.error)
            for item in validated.exemplars or []:
                errors.extend(item.errors or [])
                for checked_mark in item.marks or []:
                    errors.extend(checked_mark.errors or [])
        reason = "; ".join(dict.fromkeys(errors)) or "ozon_mark_rejected"
        return OzonMarkingResult(
            False,
            False,
            reason,
            {"exemplar_id": exemplar_id, "validation_errors": list(dict.fromkeys(errors))},
        )

    set_request = OzonV6FbsPostingProductExemplarSetV6Request.model_validate(
        {
            "posting_number": posting_number,
            "products": await _full_exemplar_products(
                session,
                order,
                current_marking=marking,
                current_product_id=product_id,
                current_exemplar_id=exemplar_id,
                current_mark_type=mark_type,
            ),
        }
    )
    await provider.call(
        client_id=client_id,
        api_key=api_key,
        path="/v6/fbs/posting/product/exemplar/set",
        payload=_payload(set_request),
    )
    status = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v5/fbs/posting/product/exemplar/status",
        request=OzonV5FbsPostingProductExemplarStatusV5Request(posting_number=posting_number),
        response_type=OzonV5FbsPostingProductExemplarStatusV5Response,
        read=True,
    )
    details = {"status": status.status, "exemplar_id": exemplar_id}
    if status.status == "ship_available":
        return OzonMarkingResult(True, False, None, details)
    if status.status == "validation_in_process":
        return OzonMarkingResult(False, True, None, details)
    if status.status in {"ship_not_available", "update_not_available"}:
        return OzonMarkingResult(False, False, status.status, details)
    raise OzonFbsProcessError(
        "ozon_exemplar_unknown_status",
        f"Ozon вернул неизвестный статус маркировки: {status.status or 'пусто'}.",
    )


async def read_marking_status(
    *,
    posting_number: str,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> OzonMarkingResult:
    status = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v5/fbs/posting/product/exemplar/status",
        request=OzonV5FbsPostingProductExemplarStatusV5Request(posting_number=posting_number),
        response_type=OzonV5FbsPostingProductExemplarStatusV5Response,
        read=True,
    )
    if status.status == "ship_available":
        return OzonMarkingResult(True, False, None, {"status": status.status})
    if status.status == "validation_in_process":
        return OzonMarkingResult(False, True, None, {"status": status.status})
    if status.status in {"ship_not_available", "update_not_available"}:
        return OzonMarkingResult(False, False, status.status, {"status": status.status})
    raise OzonFbsProcessError(
        "ozon_exemplar_unknown_status",
        f"Ozon вернул неизвестный статус маркировки: {status.status or 'пусто'}.",
    )


async def _posting_readback(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_number: str,
) -> OzonV3GetFbsPostingResponseV3:
    return await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v3/posting/fbs/get",
        request=OzonPostingv3GetFbsPostingRequest.model_validate(
            {"posting_number": posting_number, "with": {"related_postings": True}}
        ),
        response_type=OzonV3GetFbsPostingResponseV3,
        read=True,
    )


def _apply_posting_readback(order: FbsOrder, response: OzonV3GetFbsPostingResponseV3) -> None:
    result = response.result
    if result is None:
        raise OzonFbsProcessError("ozon_empty_posting", "Ozon не вернул отправление.")
    order.wb_status = result.status or order.wb_status
    order.supplier_status = result.substatus or order.supplier_status
    details = dict(order.meta_details_json or {})
    details["ozon_posting_readback"] = {
        "status": result.status,
        "substatus": result.substatus,
        "message": (
            "Сборка Ozon не прошла; исправьте отправление и повторите."
            if result.substatus == "ship_failed"
            else None
        ),
    }
    related = result.related_postings
    if related is not None and related.related_posting_numbers:
        details["ozon_related_posting_numbers"] = list(related.related_posting_numbers)
    order.meta_details_json = details
    if result.substatus == "ship_failed":
        raise OzonFbsProcessError(
            "ozon_ship_failed",
            "Сборка Ozon не прошла; заказ не передан.",
            status_code=409,
        )
    if result.status not in {"awaiting_deliver", "delivering"}:
        raise OzonFbsProcessError(
            "ozon_ship_unconfirmed",
            f"Ozon не подтвердил сборку: {result.status or 'неизвестный статус'}.",
            status_code=409,
        )


def _required_country_skus(response: OzonV3GetFbsPostingResponseV3) -> set[str]:
    result = response.result
    requirements = result.requirements if result is not None else None
    if requirements is None:
        return set()
    return {
        *[str(value) for value in (requirements.products_requiring_country or [])],
        *[str(value) for value in (requirements.products_requiring_change_country or [])],
    }


async def _posting_weight_grams(session: AsyncSession, order: FbsOrder) -> float | None:
    """Вес отправления по позициям: у Ozon вес лежит в товаре отправления."""
    positions = list(
        (
            await session.execute(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    if not positions:
        return None
    total = 0.0
    seen = False
    for position in positions:
        data = position.provider_data_json if isinstance(position.provider_data_json, dict) else {}
        weight = data.get("weight")
        if isinstance(weight, (int, float)) and not isinstance(weight, bool):
            total += float(weight) * max(int(position.quantity or 0), 1)
            seen = True
    return total if seen else None


def _restriction_violations(
    response: OzonV1GetRestrictionsResponse,
    *,
    weight_grams: float | None,
    price_rub: float | None,
) -> list[str]:
    """Сравнить отправление с лимитами пункта приёма, а не считать лимиты нарушением.

    Метод `/v1/posting/fbs/restrictions` называется «Получить ограничения пункта
    приёма» и возвращает их всегда: у настоящего пункта в примере спецификации
    стоят 40 000 г и 500 на 500 на 500 см. Раньше код считал нарушением сам факт
    наличия любого лимита и валил передачу в 409 — на живом пункте приёма
    отгрузка не прошла бы никогда.

    Габариты отправления Ozon не сообщает, поэтому по ним сравнивать нечего:
    проверяем то, что действительно знаем, — вес и стоимость.
    """
    result = response.result
    if result is None:
        return []
    violations: list[str] = []
    max_weight = getattr(result, "max_posting_weight", None)
    min_weight = getattr(result, "min_posting_weight", None)
    if weight_grams is not None:
        if isinstance(max_weight, (int, float)) and max_weight > 0 and weight_grams > max_weight:
            violations.append(f"вес {weight_grams:g} г больше допустимых {max_weight:g} г")
        if isinstance(min_weight, (int, float)) and weight_grams < min_weight:
            violations.append(f"вес {weight_grams:g} г меньше допустимых {min_weight:g} г")
    max_price = getattr(result, "max_posting_price", None)
    min_price = getattr(result, "min_posting_price", None)
    if price_rub is not None:
        if isinstance(max_price, (int, float)) and max_price > 0 and price_rub > max_price:
            violations.append(f"стоимость {price_rub:g} ₽ больше допустимых {max_price:g} ₽")
        if isinstance(min_price, (int, float)) and price_rub < min_price:
            violations.append(f"стоимость {price_rub:g} ₽ меньше допустимых {min_price:g} ₽")
    return violations


async def _set_required_countries(
    session: AsyncSession,
    order: FbsOrder,
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_number: str,
    posting: OzonV3GetFbsPostingResponseV3,
) -> None:
    required_skus = _required_country_skus(posting)
    if not required_skus:
        return
    positions = list(
        (
            await session.execute(
                select(FbsOrderProduct)
                .where(FbsOrderProduct.order_id == order.id)
                .options(selectinload(FbsOrderProduct.product))
            )
        )
        .scalars()
        .all()
    )
    positions_by_sku = {
        str(position.ozon_sku): position for position in positions if position.ozon_sku is not None
    }
    countries = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/product/country/list",
        request=OzonV2FbsPostingProductCountryListRequest(name_search=""),
        response_type=OzonV2FbsPostingProductCountryListResponse,
        read=True,
    )
    allowed_iso_codes = {
        country.country_iso_code.upper()
        for country in (countries.result or [])
        if country.country_iso_code
    }
    for sku in sorted(required_skus):
        position = positions_by_sku.get(sku)
        country_iso_code = (
            position.product.country_of_origin_iso_code.upper()
            if position is not None
            and position.product is not None
            and position.product.country_of_origin_iso_code
            else None
        )
        if position is None or position.ozon_sku is None or country_iso_code is None:
            raise OzonFbsProcessError(
                "ozon_country_required",
                f"Для Ozon SKU {sku} укажите страну изготовления в каталоге.",
                status_code=409,
            )
        if country_iso_code not in allowed_iso_codes:
            raise OzonFbsProcessError(
                "ozon_country_invalid",
                f"Страна {country_iso_code} недоступна для Ozon SKU {sku}.",
                status_code=409,
            )
        await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v2/posting/fbs/product/country/set",
            request=OzonV2FbsPostingProductCountrySetRequest(
                posting_number=posting_number,
                product_id=int(position.ozon_sku),
                country_iso_code=country_iso_code,
            ),
            response_type=OzonV2FbsPostingProductCountrySetResponse,
            read=False,
        )
    verified = await _posting_readback(
        provider,
        client_id=client_id,
        api_key=api_key,
        posting_number=posting_number,
    )
    remaining = _required_country_skus(verified)
    if remaining:
        raise OzonFbsProcessError(
            "ozon_country_unconfirmed",
            "Ozon не подтвердил страну изготовления; отправление не собрано.",
            status_code=409,
        )


async def handoff_supply(
    session: AsyncSession,
    *,
    supply: FbsSupply,
    orders: list[FbsOrder],
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> OzonHandoffResult:
    posting_numbers: list[str] = []
    for order in orders:
        posting_number = order.external_order_id or ""
        if not posting_number:
            raise OzonFbsProcessError("ozon_posting_number_missing", "Нет номера отправления Ozon.")
        posting = await _posting_readback(
            provider,
            client_id=client_id,
            api_key=api_key,
            posting_number=posting_number,
        )
        restrictions = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/posting/fbs/restrictions",
            request=OzonV1GetRestrictionsRequest(posting_number=posting_number),
            response_type=OzonV1GetRestrictionsResponse,
            read=True,
        )
        if restrictions.result is None:
            raise OzonFbsProcessError(
                "ozon_restrictions_missing",
                "Ozon не вернул ограничения отправления; сборка остановлена.",
                status_code=409,
            )
        violations = _restriction_violations(
            restrictions,
            weight_grams=await _posting_weight_grams(session, order),
            price_rub=(order.price / 100) if order.price is not None else None,
        )
        if violations:
            raise OzonFbsProcessError(
                "ozon_posting_restricted",
                "Отправление Ozon не проходит ограничения пункта приёма ("
                + ", ".join(violations)
                + "); проверьте состав в кабинете Ozon до сборки.",
                status_code=409,
            )
        await _set_required_countries(
            session,
            order,
            provider,
            client_id=client_id,
            api_key=api_key,
            posting_number=posting_number,
            posting=posting,
        )
        products = await _ship_products(session, order)
        await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v4/posting/fbs/ship",
            request=OzonFbsv4FbsPostingShipV4Request.model_validate(
                {
                    "posting_number": posting_number,
                    "packages": [{"products": products}],
                    "with": {"additional_data": True},
                }
            ),
            response_type=OzonFbsv4FbsPostingShipV4Response,
            read=False,
        )
        readback = await _posting_readback(
            provider,
            client_id=client_id,
            api_key=api_key,
            posting_number=posting_number,
        )
        _apply_posting_readback(order, readback)
        posting_numbers.append(posting_number)
        related = readback.result.related_postings if readback.result is not None else None
        if related is not None:
            posting_numbers.extend(related.related_posting_numbers or [])
    posting_numbers = list(dict.fromkeys(posting_numbers))

    details = orders[0].meta_details_json or {}
    delivery_method = details.get("ozon_delivery_method_id")
    create_values: dict[str, object] = {"departure_date": datetime.now(UTC).isoformat()}
    if str(delivery_method).isdigit():
        create_values["delivery_method_id"] = int(str(delivery_method))
    create_request = OzonV1CarriageCreateRequest.model_validate(create_values)
    try:
        carriage = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/carriage/create",
            request=create_request,
            response_type=OzonV1CarriageCreateResponse,
            read=False,
        )
    except MarketplaceProviderError as exc:
        if exc.status_code not in {404, 409}:
            raise
        await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v2/posting/fbs/awaiting-delivery",
            request=OzonV2MovePostingToAwaitingDeliveryRequest(posting_number=posting_numbers),
            response_type=OzonPostingBooleanResponse,
            read=False,
        )
        for order in orders:
            response = await _posting_readback(
                provider,
                client_id=client_id,
                api_key=api_key,
                posting_number=order.external_order_id or "",
            )
            _apply_posting_readback(order, response)
        return OzonHandoffResult(None, True, None, None, None)

    if not carriage.carriage_id:
        raise OzonFbsProcessError("ozon_carriage_missing", "Ozon не создал отгрузку.")
    carriage_id = carriage.carriage_id
    get_request = OzonCarriageCarriageGetRequest(carriage_id=carriage_id)
    await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/carriage/get",
        request=get_request,
        response_type=OzonCarriageCarriageGetResponse,
        read=True,
    )
    set_result = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/carriage/set-postings",
        request=OzonV1SetPostingsRequest(
            carriage_id=carriage_id,
            posting_numbers=posting_numbers,
        ),
        response_type=OzonV1SetPostingsResponse,
        read=False,
    )
    if any(not row.result for row in set_result.result):
        raise OzonFbsProcessError(
            "ozon_carriage_postings_failed", "Ozon не добавил все отправления в отгрузку."
        )
    await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/carriage/get",
        request=get_request,
        response_type=OzonCarriageCarriageGetResponse,
        read=True,
    )
    await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/carriage/approve",
        request=OzonV1CarriageApproveRequest.model_validate({"carriage_id": carriage_id}),
        response_type=OzonV1CarriageApproveResponse,
        read=False,
    )
    confirmed = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/carriage/get",
        request=get_request,
        response_type=OzonCarriageCarriageGetResponse,
        read=True,
    )
    if confirmed.status not in {"sended", "received", "closed"}:
        raise OzonFbsProcessError("ozon_carriage_unconfirmed", "Ozon не подтвердил отгрузку.")
    barcode = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/act/get-barcode",
        request=OzonV2PostingFBSGetBarcodeRequest(id=carriage_id),
        response_type=OzonV2PostingFBSGetBarcodeResponse,
        read=True,
    )
    barcode_text = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/act/get-barcode/text",
        request=OzonV2PostingFBSGetBarcodeRequest(id=carriage_id),
        response_type=OzonV2PostingFBSGetBarcodeTextResponse,
        read=True,
    )
    # Лист отгрузки берём живым методом. `/v2/posting/fbs/digital/act/get-pdf`
    # Ozon уже отключил: 03.09.2026 живой вызов отвечает
    # `400 {"code":9,"message":"obsolete method cannot be used"}`, срок
    # отключения в спецификации был назначен на 22 марта 2026 года. Замена
    # `/v2/posting/fbs/act/get-pdf` жива и принимает то же тело: с номером
    # несуществующей перевозки отвечает `404 CARRIAGE_NOT_FOUND`.
    act = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path=SHIPPING_LIST_PATH,
        request=OzonV2PostingFBSGetDigitalActRequest(
            id=carriage_id,
            doc_type="act_of_acceptance",
        ),
        response_type=OzonV2PostingFBSGetDigitalActResponse,
        read=True,
    )
    return OzonHandoffResult(
        carriage_id=carriage_id,
        used_fallback=False,
        barcode_bytes=_decode_file(barcode.file_content),
        barcode_text=barcode_text.result,
        shipping_list_bytes=_decode_file(act.file_content),
    )
