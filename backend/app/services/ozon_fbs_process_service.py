"""Ozon-specific mutations behind the existing WMS FBS operator flow.

Every request/response is validated by models generated from the official
Seller API 2.1 snapshot. Mutations are issued once and followed by a readback.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_supply import FbsSupply
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.schemas.ozon_fbs_api import (
    OzonCarriageCarriageGetRequest,
    OzonCarriageCarriageGetResponse,
    OzonFbsv4FbsPostingShipV4Request,
    OzonFbsv4FbsPostingShipV4Response,
    OzonPostingBooleanResponse,
    OzonPostingPostingFBSPackageLabelRequest,
    OzonPostingPostingFBSPackageLabelResponse,
    OzonPostingv3GetFbsPostingRequest,
    OzonV1CarriageApproveRequest,
    OzonV1CarriageApproveResponse,
    OzonV1CarriageCreateRequest,
    OzonV1CarriageCreateResponse,
    OzonV1CreateLabelBatchRequest,
    OzonV1GetLabelBatchRequest,
    OzonV1GetLabelBatchResponse,
    OzonV1SetPostingsRequest,
    OzonV1SetPostingsResponse,
    OzonV2CreateLabelBatchResponse,
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

TResponse = TypeVar("TResponse", bound=BaseModel)


class OzonFbsProcessError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True)
class OzonHandoffResult:
    carriage_id: int | None
    used_fallback: bool
    barcode_bytes: bytes | None
    barcode_text: str | None
    shipping_list_bytes: bytes | None
    label_bytes: bytes | None


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


def _decode_file(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise OzonFbsProcessError(
            "ozon_invalid_file", "Ozon вернул повреждённый печатный файл."
        ) from exc


async def _ozon_product_id(session: AsyncSession, order: FbsOrder) -> int:
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
    product_id = await _ozon_product_id(session, order)
    mark_type = {"sgtin": "mandatory_mark", "uin": "jw_uin", "imei": "imei"}.get(marking.kind)
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
    product = next((item for item in exemplars.products if item.product_id == product_id), None)
    exemplar = product.exemplars[0] if product is not None and product.exemplars else None
    if exemplar is None or not exemplar.exemplar_id:
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
    validated = next((item for item in validation.products if item.product_id == product_id), None)
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
            {"validation_errors": list(dict.fromkeys(errors))},
        )

    set_request = OzonV6FbsPostingProductExemplarSetV6Request.model_validate(
        {
            "posting_number": posting_number,
            "products": [
                {
                    "product_id": product_id,
                    "exemplars": [
                        {
                            "exemplar_id": exemplar.exemplar_id,
                            "marks": [{"mark": marking.value, "mark_type": mark_type}],
                        }
                    ],
                }
            ],
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


async def _labels(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    posting_numbers: list[str],
) -> bytes | None:
    created = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/package-label/create",
        request=OzonV1CreateLabelBatchRequest(posting_number=posting_numbers),
        response_type=OzonV2CreateLabelBatchResponse,
        read=False,
    )
    tasks = created.result.tasks if created.result is not None else []
    if not tasks or not tasks[0].task_id:
        raise OzonFbsProcessError("ozon_label_task_missing", "Ozon не создал этикетки.")
    label_state: OzonV1GetLabelBatchResponse | None = None
    for attempt in range(3):
        label_state = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/posting/fbs/package-label/get",
            request=OzonV1GetLabelBatchRequest(task_id=tasks[0].task_id),
            response_type=OzonV1GetLabelBatchResponse,
            read=True,
        )
        state = label_state.result.status if label_state.result is not None else None
        if state == "completed":
            break
        if state == "error":
            raise OzonFbsProcessError("ozon_label_failed", "Ozon не сформировал этикетки.")
        if state not in {"pending", "in_progress"}:
            raise OzonFbsProcessError(
                "ozon_label_unknown_status", "Неизвестный статус этикеток Ozon."
            )
        await asyncio.sleep(0.05 * (2**attempt))
    else:
        raise OzonFbsProcessError("ozon_label_not_ready", "Этикетки Ozon ещё не готовы.")
    file_response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/package-label",
        request=OzonPostingPostingFBSPackageLabelRequest(posting_number=posting_numbers),
        response_type=OzonPostingPostingFBSPackageLabelResponse,
        read=True,
    )
    return _decode_file(file_response.file_content)


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
        product_id = await _ozon_product_id(session, order)
        await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v4/posting/fbs/ship",
            request=OzonFbsv4FbsPostingShipV4Request.model_validate(
                {
                    "posting_number": posting_number,
                    "packages": [{"products": [{"product_id": product_id, "quantity": 1}]}],
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
    label_bytes = await _labels(
        provider,
        client_id=client_id,
        api_key=api_key,
        posting_numbers=posting_numbers,
    )

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
        return OzonHandoffResult(None, True, None, None, None, label_bytes)

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
    act = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v2/posting/fbs/digital/act/get-pdf",
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
        label_bytes=label_bytes,
    )
