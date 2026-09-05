"""Ozon FBS mutations validated by official Seller API 2.1 models and readbacks."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
    OzonPostingBooleanResponse,
    OzonPostingCancelFbsPostingRequest,
    OzonPostingCancelReasonRequest,
    OzonPostingCancelReasonResponse,
    OzonPostingv3GetFbsPostingRequest,
    OzonV1CarriageApproveRequest,
    OzonV1CarriageApproveResponse,
    OzonV1CarriageCreateRequest,
    OzonV1CarriageCreateResponse,
    OzonV1GetRestrictionsRequest,
    OzonV1GetRestrictionsResponse,
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
__all__ = [
    "CANCEL_REASON_OTHER",
    "CANCEL_REASON_OUT_OF_STOCK",
    "OzonFbsProcessError",
    "OzonHandoffProgress",
    "cancel_posting",
    "handoff_supply",
    "read_marking_status",
    "submit_marking",
]

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
# Этикетки получает конвейер печатных активов после сборки кнопкой QR.
# Один PDF заказа содержит этикетки всех отправлений, полученных из его коробов.


@dataclass(frozen=True)
class OzonHandoffResult:
    carriage_id: int | None
    used_fallback: bool
    barcode_bytes: bytes | None
    barcode_text: str | None
    shipping_list_bytes: bytes | None


@dataclass
class OzonHandoffProgress:
    """Что в кабинете Ozon уже сделано и повторять этого нельзя.

    Передача поставки — не одна операция, а цепочка необратимых: каждое
    отправление собирается своим `/v4/posting/fbs/ship`, потом создаётся и
    подтверждается перевозка. Если цепочка обрывается посередине, сделанное в
    кабинете назад не отыграть, а локальная транзакция откатывается целиком —
    и повтор отправляет уже собранное отправление второй раз.

    Поэтому после каждого необратимого шага вызывающий код получает этот
    снимок и обязан сохранить его так, чтобы он пережил падение (у нас — в
    журнале операции, с коммитом). На повторе тот же снимок приходит обратно, и
    передача продолжается с места обрыва, а не начинается заново.

    Хранится он в JSON, поэтому здесь только простые типы: списки строк, число
    и флаги.
    """

    shipped_postings: list[str] = field(default_factory=list)
    posting_numbers: list[str] = field(default_factory=list)
    carriage_id: int | None = None
    carriage_create_started: bool = False
    carriage_postings_set: bool = False
    carriage_approved: bool = False
    used_fallback: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "shipped_postings": list(self.shipped_postings),
            "posting_numbers": list(self.posting_numbers),
            "carriage_id": self.carriage_id,
            "carriage_create_started": self.carriage_create_started,
            "carriage_postings_set": self.carriage_postings_set,
            "carriage_approved": self.carriage_approved,
            "used_fallback": self.used_fallback,
        }

    @classmethod
    def from_json(cls, raw: object) -> OzonHandoffProgress:
        """Разобрать снимок из журнала; мусор трактуется как «ничего не сделано».

        Пустой снимок безопаснее битого: он заставит передачу пройти путь
        заново, а повторный `/ship` по уже собранному отправлению Ozon отклонит
        сам. Молча поверить в непонятную структуру и пропустить сборку — хуже.
        """
        if not isinstance(raw, dict):
            return cls()
        carriage_id = raw.get("carriage_id")
        return cls(
            shipped_postings=[value for value in _str_list(raw.get("shipped_postings")) if value],
            posting_numbers=[value for value in _str_list(raw.get("posting_numbers")) if value],
            carriage_id=(
                int(carriage_id)
                if isinstance(carriage_id, int) and not isinstance(carriage_id, bool)
                else None
            ),
            carriage_create_started=raw.get("carriage_create_started") is True,
            carriage_postings_set=raw.get("carriage_postings_set") is True,
            carriage_approved=raw.get("carriage_approved") is True,
            used_fallback=raw.get("used_fallback") is True,
        )

    def absorb(self, other: OzonHandoffProgress) -> None:
        """Вобрать в себя чужой снимок: сделанное в кабинете не отменяется.

        Складывать снимки приходится потому, что попыток передачи у одной
        поставки может быть несколько, и «взять последнюю» — ненадёжно:
        различить две попытки одной секунды нечем. А складывать безопасно:
        каждое поле снимка описывает необратимо сделанное, поэтому объединение
        по всем попыткам и есть полное «что уже нельзя повторять».
        """
        for posting in other.shipped_postings:
            if posting not in self.shipped_postings:
                self.shipped_postings.append(posting)
        for posting in other.posting_numbers:
            if posting not in self.posting_numbers:
                self.posting_numbers.append(posting)
        if other.carriage_id is not None:
            self.carriage_id = other.carriage_id
        self.carriage_create_started = self.carriage_create_started or other.carriage_create_started
        self.carriage_postings_set = self.carriage_postings_set or other.carriage_postings_set
        self.carriage_approved = self.carriage_approved or other.carriage_approved
        self.used_fallback = self.used_fallback or other.used_fallback


def _str_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [value for value in raw if isinstance(value, str)]


# Как вызывающий код сохраняет снимок. Возвращать ничего не нужно: единственная
# обязанность — сделать сохранение долговечным до возврата управления сюда.
OzonHandoffCheckpoint = Callable[["OzonHandoffProgress"], Awaitable[None]]


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
        products.setdefault(product_id, []).append({"exemplar_id": exemplar_id, "marks": marks})
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


# Отмена отправления. Метод и его форма взяты из официальной спецификации Ozon
# (`PostingAPI_CancelFbsPosting`), а не выведены по аналогии: в нашей копии
# спецификации FBS его не было, поэтому оба пути добавлены в неё дословно и
# модели пересобраны генератором.
CANCEL_PATH = "/v2/posting/fbs/cancel"
CANCEL_REASON_PATH = "/v1/posting/fbs/cancel-reason"

# «Товар закончился на складе продавца». Ровно та причина, по которой отменяет
# фулфилмент: он не может собрать отправление, потому что товара нет. Официальный
# FAQ Ozon по FBS говорит то же самое — «Отменяйте заказ, только если товара нет
# в наличии». Причину не угадываем вслепую: перед отменой спрашиваем у Ozon
# список причин для этого отправления и сверяемся с ним.
CANCEL_REASON_OUT_OF_STOCK = 352
# Причина «другое (вина продавца)»; спецификация требует при ней текст.
CANCEL_REASON_OTHER = 402
# Отменять от лица продавца имеет право только продавцовская причина: у Ozon
# рядом лежат причины покупателя (`type_id == "buyer"`), и подставить их нельзя.
CANCEL_INITIATOR_SELLER = "seller"


async def _seller_cancel_reasons(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_number: str,
) -> set[int]:
    """Причины отмены, которые Ozon разрешает этому отправлению прямо сейчас.

    Список зависит от состояния отправления: четыре причины из семи английская
    версия спецификации помечает как доступные только в статусах доставки. Плюс
    у метода отмены есть собственная частая ошибка `HAS_INCORRECT_CANCEL_REASON`
    — «Указан неправильный идентификатор отмены заказа». Проще спросить, чем
    получить отказ уже на мутации.
    """
    response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path=CANCEL_REASON_PATH,
        request=OzonPostingCancelReasonRequest(related_posting_numbers=[posting_number]),
        response_type=OzonPostingCancelReasonResponse,
        read=True,
    )
    allowed: set[int] = set()
    for row in response.result or []:
        if row.posting_number and row.posting_number != posting_number:
            continue
        for reason in row.reasons or []:
            if reason.id and reason.type_id == CANCEL_INITIATOR_SELLER:
                allowed.add(int(reason.id))
    return allowed


async def cancel_posting(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_number: str,
    reason_id: int = CANCEL_REASON_OUT_OF_STOCK,
    reason_message: str | None = None,
) -> None:
    """Отменить отправление Ozon и убедиться, что он это подтвердил.

    Обратного хода у операции нет: «Статус отправления изменится на Отменено —
    после этого восстановить заказ не получится» (База знаний Ozon). Поэтому
    сначала спрашиваем разрешённые причины и отказываемся, если нашей среди них
    нет, и только потом отменяем.
    """
    if not posting_number:
        raise OzonFbsProcessError("ozon_posting_number_missing", "Нет номера отправления Ozon.")
    if reason_id == CANCEL_REASON_OTHER and not (reason_message or "").strip():
        # Требование спецификации, которое её же `required` не ловит: «Если
        # значение параметра `cancel_reason_id` — 402, заполните поле
        # `cancel_reason_message`».
        raise OzonFbsProcessError(
            "ozon_cancel_reason_message_required",
            "Для причины «другое» Ozon требует пояснение.",
            status_code=409,
        )

    allowed = await _seller_cancel_reasons(
        provider,
        client_id=client_id,
        api_key=api_key,
        posting_number=posting_number,
    )
    if allowed and reason_id not in allowed:
        raise OzonFbsProcessError(
            "ozon_cancel_reason_unavailable",
            "Ozon не разрешает эту причину отмены для отправления.",
            status_code=409,
        )
    if not allowed:
        # Пустой список — это не «можно любую»: это «Ozon не назвал ни одной
        # причины, доступной продавцу», то есть отменять нельзя. Отправить
        # мутацию наугад дороже, чем остановиться.
        raise OzonFbsProcessError(
            "ozon_cancel_not_available",
            "Ozon не предлагает ни одной причины отмены — отправление отменить нельзя.",
            status_code=409,
        )

    values: dict[str, object] = {
        "posting_number": posting_number,
        "cancel_reason_id": reason_id,
    }
    if reason_message and reason_message.strip():
        values["cancel_reason_message"] = reason_message.strip()
    confirmed = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path=CANCEL_PATH,
        request=OzonPostingCancelFbsPostingRequest.model_validate(values),
        response_type=OzonPostingBooleanResponse,
        read=False,
    )
    if confirmed.result is not True:
        raise OzonFbsProcessError(
            "ozon_cancel_unconfirmed",
            "Ozon не подтвердил отмену отправления.",
            status_code=502,
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


def _apply_posting_readback(
    order: FbsOrder,
    response: OzonV3GetFbsPostingResponseV3,
    *,
    require_shipped: bool = True,
) -> None:
    """Перенести карточку отправления на заказ и, если нужно, проверить сборку.

    `require_shipped=False` — для повтора по отправлению, которое собрано в
    прошлой попытке. Там гейт «статус должен быть `awaiting_deliver` или
    `delivering`» вреден: за время между попытками отправление могло уйти
    дальше по жизненному циклу (перевозку подтвердили, курьер забрал), и тогда
    проверка сборки заблокировала бы получение уже готовых документов. Провал
    самой сборки (`ship_failed`) останавливает передачу в обоих случаях — это
    не «ушло дальше», а «не уехало вовсе».
    """
    result = response.result
    if result is None:
        if not require_shipped:
            return
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
    if not require_shipped:
        return
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
        (await session.execute(select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)))
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


async def prepare_order_assembly(
    session: AsyncSession,
    order: FbsOrder,
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting: OzonV3GetFbsPostingResponseV3,
) -> None:
    """Проверить обязательные требования Ozon перед кнопкой сборки."""
    posting_number = order.external_order_id or ""
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


async def handoff_supply(
    session: AsyncSession,
    *,
    supply: FbsSupply,
    orders: list[FbsOrder],
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
    progress: OzonHandoffProgress | None = None,
    checkpoint: OzonHandoffCheckpoint | None = None,
) -> OzonHandoffResult:
    """Передать поставку Ozon, отмечая каждый необратимый шаг.

    `progress` — то, что уже сделано в кабинете по этой поставке в прошлых
    попытках; `checkpoint` — способ сохранить снимок так, чтобы он пережил
    падение процесса. Оба необязательны только ради тестов и прямых вызовов:
    боевой путь (`fbs_shipment_service._deliver_ozon_supply`) передаёт оба, и
    без них повтор после обрыва отправил бы уже собранное отправление заново.
    """
    # Imported at the operation boundary: assembly itself uses the API helpers above.
    from app.services.ozon_box_assembly_service import order_packages

    state = progress if progress is not None else OzonHandoffProgress()

    async def _save() -> None:
        if checkpoint is not None:
            await checkpoint(state)

    # Validate every order before any external call. A partial /ship response must
    # never turn into a whole-order write-off through the handoff button.
    confirmed_numbers: list[list[str]] = []
    for order in orders:
        posting_number = order.external_order_id or ""
        assembly = (order.meta_details_json or {}).get("ozon_assembly")
        numbers = _str_list(assembly.get("posting_numbers")) if isinstance(assembly, dict) else []
        if not numbers and posting_number not in state.shipped_postings:
            raise OzonFbsProcessError(
                "ozon_order_not_assembled",
                "Сначала нажмите QR на коробе заказа: Ozon должен подтвердить сборку.",
                status_code=409,
            )
        if isinstance(assembly, dict):
            packages = await order_packages(session, order)
            if (
                len(numbers) != len(packages)
                or len(set(numbers)) != len(numbers)
                or any(not number for number in numbers)
            ):
                raise OzonFbsProcessError(
                    "ozon_assembly_unconfirmed",
                    "Ozon не подтвердил все упаковки заказа. Повторите QR для проверки сборки.",
                    status_code=409,
                )
        confirmed_numbers.append(numbers or [posting_number])
    for order, numbers in zip(orders, confirmed_numbers, strict=True):
        posting_number = order.external_order_id or ""
        for number in numbers:
            _apply_posting_readback(
                order,
                await _posting_readback(
                    provider,
                    client_id=client_id,
                    api_key=api_key,
                    posting_number=number,
                ),
                require_shipped=False,
            )
        if posting_number not in state.shipped_postings:
            state.shipped_postings.append(posting_number)
        for number in numbers:
            if number not in state.posting_numbers:
                state.posting_numbers.append(number)
    await _save()
    posting_numbers = list(dict.fromkeys(state.posting_numbers))

    if state.used_fallback:
        # Перевозки у этого продавца нет, и отправления уже переведены в
        # ожидание отгрузки прошлой попыткой. Повторять мутацию незачем.
        for order in orders:
            _apply_posting_readback(
                order,
                await _posting_readback(
                    provider,
                    client_id=client_id,
                    api_key=api_key,
                    posting_number=order.external_order_id or "",
                ),
                require_shipped=False,
            )
        return OzonHandoffResult(None, True, None, None, None)

    if state.carriage_id is not None:
        return await _finish_carriage_handoff(
            provider,
            client_id=client_id,
            api_key=api_key,
            posting_numbers=posting_numbers,
            state=state,
            save=_save,
        )

    if state.carriage_create_started:
        raise OzonFbsProcessError(
            "ozon_carriage_unconfirmed",
            "Запрос создания отгрузки отправлен, но Ozon не вернул её номер. "
            "Проверьте результат в кабинете Ozon: повторный запрос не отправлен.",
            status_code=409,
        )
    details = orders[0].meta_details_json or {}
    delivery_method = details.get("ozon_delivery_method_id")
    create_values: dict[str, object] = {"departure_date": datetime.now(UTC).isoformat()}
    if str(delivery_method).isdigit():
        create_values["delivery_method_id"] = int(str(delivery_method))
    create_request = OzonV1CarriageCreateRequest.model_validate(create_values)
    state.carriage_create_started = True
    await _save()
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
            if exc.status_code in {400, 401, 403, 422, 429}:
                state.carriage_create_started = False
                await _save()
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
        state.used_fallback = True
        await _save()
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
    state.carriage_id = carriage.carriage_id
    await _save()
    return await _finish_carriage_handoff(
        provider,
        client_id=client_id,
        api_key=api_key,
        posting_numbers=posting_numbers,
        state=state,
        save=_save,
    )


async def _finish_carriage_handoff(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_numbers: list[str],
    state: OzonHandoffProgress,
    save: Callable[[], Awaitable[None]],
) -> OzonHandoffResult:
    """Довести созданную перевозку до подтверждения и забрать её документы.

    Вынесено отдельно ровно ради повтора: сюда же попадает попытка, которая в
    прошлый раз оборвалась после `/v1/carriage/approve` — например на штрихкоде
    акта. Состав перевозки и её подтверждение — мутации, и каждая отмечается в
    снимке, чтобы повтор их не задваивал.
    """
    carriage_id = state.carriage_id
    if carriage_id is None:
        raise OzonFbsProcessError("ozon_carriage_missing", "Ozon не создал отгрузку.")
    get_request = OzonCarriageCarriageGetRequest(carriage_id=carriage_id)
    if not state.carriage_approved:
        current = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/carriage/get",
            request=get_request,
            response_type=OzonCarriageCarriageGetResponse,
            read=True,
        )
        # Approve may have succeeded immediately before the worker died.
        # The external fact takes precedence over the last local checkpoint.
        if current.status not in {"sended", "received", "closed"}:
            await _call(
                provider,
                client_id=client_id,
                api_key=api_key,
                path="/v1/carriage/approve",
                request=OzonV1CarriageApproveRequest.model_validate({"carriage_id": carriage_id}),
                response_type=OzonV1CarriageApproveResponse,
                read=False,
            )
        state.carriage_approved = True
        await save()
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
