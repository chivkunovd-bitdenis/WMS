"""Ozon return giveouts mapped into the existing inbound-return document."""

from __future__ import annotations

import asyncio
import base64
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.ozon_return import InboundOzonReturnGiveout, InboundOzonReturnItem
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.schemas.ozon_returns_api import (
    OzonGetReturnsListResponseReturnsItem,
    OzonGiveoutListResponseGiveoutDetails,
    OzonReturnsCompanyFbsInfoResponseDropOffPoints,
    OzonV1Empty,
    OzonV1GetReturnsListRequest,
    OzonV1GetReturnsListResponse,
    OzonV1GiveoutBarcodeResetResponse,
    OzonV1GiveoutGetBarcodeResponse,
    OzonV1GiveoutGetPDFResponse,
    OzonV1GiveoutGetPNGResponse,
    OzonV1GiveoutInfoRequest,
    OzonV1GiveoutInfoResponse,
    OzonV1GiveoutIsEnabledResponse,
    OzonV1GiveoutListRequest,
    OzonV1GiveoutListResponse,
    OzonV1ReturnsCompanyFbsInfoRequest,
    OzonV1ReturnsCompanyFbsInfoResponse,
)
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider

TResponse = TypeVar("TResponse", bound=BaseModel)
PAGE_LIMIT = 100


class OzonReturnError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(code)


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
) -> TResponse:
    for attempt in range(3):
        try:
            raw = await provider.call(
                client_id=client_id,
                api_key=api_key,
                path=path,
                payload=_payload(request),
            )
            if raw is None:
                raise OzonReturnError("ozon_empty_response", "Ozon вернул пустой ответ.")
            return response_type.model_validate(raw)
        except MarketplaceProviderError as exc:
            retryable = (
                exc.status_code == 429
                or (exc.status_code is not None and exc.status_code >= 500)
                or exc.code == "transport_error"
            )
            if not retryable or attempt == 2:
                raise
            await asyncio.sleep(0.05 * (2**attempt))
        except ValidationError as exc:
            raise OzonReturnError(
                "ozon_invalid_response",
                "Ozon вернул ответ неизвестного формата.",
            ) from exc
    raise AssertionError("unreachable")


async def _call_once(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    path: str,
    request: BaseModel,
    response_type: type[TResponse],
) -> TResponse:
    """Call a mutation once; Ozon does not document idempotency keys."""
    raw = await provider.call(
        client_id=client_id,
        api_key=api_key,
        path=path,
        payload=_payload(request),
    )
    if raw is None:
        raise OzonReturnError("ozon_empty_response", "Ozon вернул пустой ответ.")
    try:
        return response_type.model_validate(raw)
    except ValidationError as exc:
        raise OzonReturnError(
            "ozon_invalid_response",
            "Ozon вернул ответ неизвестного формата.",
        ) from exc


async def _request_for_ozon_return(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    request = await session.scalar(
        select(InboundIntakeRequest)
        .options(selectinload(InboundIntakeRequest.lines))
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
    )
    if request is None:
        raise OzonReturnError("request_not_found", "Возврат не найден.")
    if request.operation_type != "return" or request.marketplace != "ozon":
        raise OzonReturnError(
            "not_ozon_return",
            "Получение из Ozon доступно только для возврата Ozon.",
        )
    if request.seller_id is None:
        raise OzonReturnError("seller_missing", "В возврате не выбран селлер.")
    return request


async def _credentials(
    session: AsyncSession,
    request: InboundIntakeRequest,
) -> tuple[str, str]:
    assert request.seller_id is not None
    try:
        return await MarketplaceAccountService(session).stored_credentials(
            request.tenant_id,
            request.seller_id,
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "ozon_not_connected":
            raise OzonReturnError(
                "ozon_not_connected",
                "Сначала подключите кабинет Ozon для этого селлера.",
            ) from exc
        raise


def _status_text(value: object) -> str:
    root = getattr(value, "root", value)
    return str(root or "GIVEOUT_STATUS_UNSPECIFIED")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


async def _all_giveouts(
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> list[OzonGiveoutListResponseGiveoutDetails]:
    result: list[OzonGiveoutListResponseGiveoutDetails] = []
    last_id: int | None = None
    seen: set[int] = set()
    while True:
        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/return/giveout/list",
            request=OzonV1GiveoutListRequest.model_validate(
                {"limit": PAGE_LIMIT, **({"last_id": last_id} if last_id is not None else {})}
            ),
            response_type=OzonV1GiveoutListResponse,
        )
        page = list(response.giveouts or [])
        fresh = [item for item in page if item.giveout_id not in seen]
        result.extend(fresh)
        seen.update(item.giveout_id for item in fresh)
        if len(page) < PAGE_LIMIT or not fresh:
            break
        last_id = max(item.giveout_id for item in fresh)
    return result


async def company_fbs_return_points(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> list[OzonReturnsCompanyFbsInfoResponseDropOffPoints]:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    result: list[OzonReturnsCompanyFbsInfoResponseDropOffPoints] = []
    last_id: int | None = None
    while True:
        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/returns/company/fbs/info",
            request=OzonV1ReturnsCompanyFbsInfoRequest.model_validate(
                {
                    "filter": {},
                    "pagination": {
                        "limit": PAGE_LIMIT,
                        **({"last_id": last_id} if last_id is not None else {}),
                    },
                }
            ),
            response_type=OzonV1ReturnsCompanyFbsInfoResponse,
        )
        page = list(response.drop_off_points or [])
        result.extend(page)
        if not response.has_next or not page:
            break
        last_id = max(point.id for point in page)
    return result


async def _returns_at_warehouse(
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
    warehouse_id: int,
) -> list[OzonGetReturnsListResponseReturnsItem]:
    result: list[OzonGetReturnsListResponseReturnsItem] = []
    last_id: int | None = None
    while True:
        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/returns/list",
            request=OzonV1GetReturnsListRequest.model_validate(
                {
                    "filter": {
                        "warehouse_id": warehouse_id,
                        "return_schema": "FBS",
                    },
                    "limit": PAGE_LIMIT,
                    **({"last_id": last_id} if last_id is not None else {}),
                }
            ),
            response_type=OzonV1GetReturnsListResponse,
        )
        page = list(response.returns or [])
        result.extend(page)
        if not response.has_next or not page:
            break
        last_id = max(item.id for item in page)
    return result


async def _match_product(
    session: AsyncSession,
    request: InboundIntakeRequest,
    item: OzonGetReturnsListResponseReturnsItem,
) -> Product | None:
    assert request.seller_id is not None
    product = item.product
    clauses = []
    if product.offer_id:
        clauses.append(ProductMarketplaceLink.external_offer_id == product.offer_id)
    if product.sku:
        clauses.append(ProductMarketplaceLink.external_sku == str(product.sku))
    if not clauses:
        return None
    product_id = await session.scalar(
        select(ProductMarketplaceLink.product_id).where(
            ProductMarketplaceLink.tenant_id == request.tenant_id,
            ProductMarketplaceLink.seller_id == request.seller_id,
            ProductMarketplaceLink.marketplace == "ozon",
            ProductMarketplaceLink.is_active.is_(True),
            or_(*clauses),
        )
    )
    return await session.get(Product, product_id) if product_id is not None else None


def _return_item_payload(
    item: OzonGetReturnsListResponseReturnsItem,
    product: Product | None,
    *,
    approved: bool,
) -> dict[str, object]:
    return {
        "source_key": str(item.id),
        "return_id": item.id,
        "posting_number": item.posting_number,
        "return_barcode": item.logistic.barcode if item.logistic else None,
        "return_reason_name": item.return_reason_name,
        "return_type": item.type,
        "offer_id": item.product.offer_id,
        "ozon_sku": item.product.sku,
        "product_name": item.product.name,
        "quantity": int(item.product.quantity or 0),
        "approved": approved,
        "product_id": str(product.id) if product else None,
        "wms_sku": product.sku_code if product else None,
        "wms_barcode": product.wb_barcode if product else None,
        "wms_name": product.name if product else None,
        "matched": product is not None,
        "warning": None if product else "Товар не сопоставлен с каталогом",
        "storage_days": item.storage.days if item.storage else None,
        "utilization_forecast_date": (
            item.storage.utilization_forecast_date if item.storage else None
        ),
        "provider_data": item.model_dump(mode="json", by_alias=True),
    }


async def build_preview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> dict[str, object]:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    enabled = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/is-enabled",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutIsEnabledResponse,
    )
    imported = set(
        (
            await session.execute(
                select(InboundOzonReturnGiveout.giveout_id).where(
                    InboundOzonReturnGiveout.request_id == request_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not enabled.enabled:
        return {
            "enabled": False,
            "message": "Получение возвратов по штрихкоду недоступно. Ведите документ руками.",
            "groups": [],
            "imported_giveout_ids": sorted(imported),
        }

    groups: list[dict[str, object]] = []
    for giveout in await _all_giveouts(provider, client_id, api_key):
        info = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/return/giveout/info",
            request=OzonV1GiveoutInfoRequest(giveout_id=giveout.giveout_id),
            response_type=OzonV1GiveoutInfoResponse,
        )
        returns = await _returns_at_warehouse(
            provider,
            client_id,
            api_key,
            giveout.warehouse_id,
        )
        approved_by_name = Counter(
            article.name for article in (info.articles or []) if article.approved
        )
        items: list[dict[str, object]] = []
        for item in returns:
            article_name = item.product.name
            approved = approved_by_name[article_name] > 0
            if approved:
                approved_by_name[article_name] = max(
                    0,
                    approved_by_name[article_name] - int(item.product.quantity or 1),
                )
            items.append(
                _return_item_payload(
                    item,
                    await _match_product(session, request, item),
                    approved=approved,
                )
            )
        storage_days = max(
            (int(cast(int | str | None, item.get("storage_days")) or 0) for item in items),
            default=0,
        )
        utilization_dates = sorted(
            str(item["utilization_forecast_date"])
            for item in items
            if item.get("utilization_forecast_date")
        )
        groups.append(
            {
                "giveout_id": giveout.giveout_id,
                "giveout_status": _status_text(info.giveout_status or giveout.giveout_status),
                "warehouse_id": giveout.warehouse_id,
                "warehouse_name": info.warehouse_name or giveout.warehouse_name,
                "warehouse_address": info.warehouse_address or giveout.warehouse_address,
                "approved_articles_count": giveout.approved_articles_count,
                "total_articles_count": giveout.total_articles_count,
                "created_at": giveout.created_at,
                "storage_days": storage_days,
                "utilization_forecast_date": utilization_dates[0] if utilization_dates else None,
                "already_imported": giveout.giveout_id in imported,
                "items": items,
            }
        )
    return {
        "enabled": True,
        "message": None,
        "groups": groups,
        "imported_giveout_ids": sorted(imported),
    }


async def import_selected_giveouts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    giveout_ids: list[int],
) -> dict[str, int]:
    if not giveout_ids:
        raise OzonReturnError("giveouts_empty", "Выберите хотя бы один пункт выдачи.")
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    if request.status != "draft":
        raise OzonReturnError("not_draft", "Добавлять возвраты можно только в черновик.")
    preview = await build_preview(session, tenant_id, request_id, provider)
    preview_groups = cast(list[object], preview["groups"])
    groups = {
        int(cast(int | str, group["giveout_id"])): group
        for group in preview_groups
        if isinstance(group, dict)
    }
    missing = sorted(set(giveout_ids) - set(groups))
    if missing:
        raise OzonReturnError(
            "giveout_not_found",
            "Выбранная выдача больше недоступна в Ozon.",
        )

    existing = set(
        (
            await session.execute(
                select(InboundOzonReturnGiveout.giveout_id).where(
                    InboundOzonReturnGiveout.request_id == request_id,
                    InboundOzonReturnGiveout.giveout_id.in_(giveout_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    imported_groups = 0
    imported_items = 0
    unmatched_items = 0
    for giveout_id in giveout_ids:
        if giveout_id in existing:
            continue
        group = groups[giveout_id]
        giveout = InboundOzonReturnGiveout(
            tenant_id=tenant_id,
            request_id=request_id,
            giveout_id=giveout_id,
            giveout_status=str(group["giveout_status"]),
            warehouse_external_id=int(group["warehouse_id"]),
            warehouse_name=str(group["warehouse_name"]),
            warehouse_address=str(group["warehouse_address"]),
            approved_articles_count=int(group["approved_articles_count"] or 0),
            total_articles_count=int(group["total_articles_count"] or 0),
            storage_days=int(group["storage_days"] or 0),
            utilization_forecast_date=_parse_date(str(group["utilization_forecast_date"] or "")),
            provider_created_at=_parse_datetime(str(group["created_at"] or "")),
        )
        session.add(giveout)
        await session.flush()
        for raw_item in group["items"]:
            assert isinstance(raw_item, dict)
            quantity = int(raw_item["quantity"] or 0)
            if quantity <= 0:
                continue
            product_id = (
                uuid.UUID(str(raw_item["product_id"])) if raw_item.get("product_id") else None
            )
            line: InboundIntakeLine | None = None
            if product_id is not None:
                line = await session.scalar(
                    select(InboundIntakeLine).where(
                        InboundIntakeLine.request_id == request_id,
                        InboundIntakeLine.product_id == product_id,
                    )
                )
                if line is None:
                    line = InboundIntakeLine(
                        request_id=request_id,
                        product_id=product_id,
                        expected_qty=quantity,
                        actual_qty=None,
                        posted_qty=0,
                        added_by_fulfillment=False,
                        defective_qty=0,
                    )
                    session.add(line)
                    await session.flush()
                else:
                    line.expected_qty += quantity
            else:
                unmatched_items += 1
            session.add(
                InboundOzonReturnItem(
                    tenant_id=tenant_id,
                    request_id=request_id,
                    giveout_record_id=giveout.id,
                    inbound_line_id=line.id if line else None,
                    product_id=product_id,
                    source_key=str(raw_item["source_key"]),
                    external_return_id=int(raw_item["return_id"]),
                    posting_number=str(raw_item["posting_number"] or "") or None,
                    return_barcode=str(raw_item["return_barcode"] or "") or None,
                    return_reason_name=str(raw_item["return_reason_name"] or "") or None,
                    return_type=str(raw_item["return_type"] or "") or None,
                    offer_id=str(raw_item["offer_id"] or "") or None,
                    ozon_sku=int(raw_item["ozon_sku"] or 0) or None,
                    product_name=str(raw_item["product_name"]),
                    quantity=quantity,
                    approved=bool(raw_item["approved"]),
                    provider_data_json=raw_item.get("provider_data"),
                )
            )
            imported_items += 1
        imported_groups += 1
    await session.commit()
    return {
        "giveouts_imported": imported_groups,
        "items_imported": imported_items,
        "unmatched_items": unmatched_items,
    }


async def imported_groups(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[dict[str, object]]:
    await _request_for_ozon_return(session, tenant_id, request_id)
    rows = list(
        (
            await session.execute(
                select(InboundOzonReturnGiveout)
                .options(
                    selectinload(InboundOzonReturnGiveout.items).selectinload(
                        InboundOzonReturnItem.product
                    )
                )
                .where(InboundOzonReturnGiveout.request_id == request_id)
                .order_by(InboundOzonReturnGiveout.provider_created_at, InboundOzonReturnGiveout.id)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return [
        {
            "giveout_id": row.giveout_id,
            "giveout_status": row.giveout_status,
            "warehouse_id": row.warehouse_external_id,
            "warehouse_name": row.warehouse_name,
            "warehouse_address": row.warehouse_address,
            "approved_articles_count": row.approved_articles_count,
            "total_articles_count": row.total_articles_count,
            "storage_days": row.storage_days,
            "utilization_forecast_date": (
                row.utilization_forecast_date.isoformat() if row.utilization_forecast_date else None
            ),
            "items": [
                {
                    "id": str(item.id),
                    "inbound_line_id": (
                        str(item.inbound_line_id) if item.inbound_line_id else None
                    ),
                    "return_id": item.external_return_id,
                    "posting_number": item.posting_number,
                    "return_barcode": item.return_barcode,
                    "return_reason_name": item.return_reason_name,
                    "return_type": item.return_type,
                    "offer_id": item.offer_id,
                    "ozon_sku": item.ozon_sku,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "approved": item.approved,
                    "product_id": str(item.product_id) if item.product_id else None,
                    "wms_sku": item.product.sku_code if item.product else None,
                    "wms_barcode": item.product.wb_barcode if item.product else None,
                    "matched": item.product is not None,
                    "warning": (None if item.product else "Товар не сопоставлен с каталогом"),
                }
                for item in row.items
            ],
        }
        for row in rows
    ]


async def get_giveout_pass_pdf(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> tuple[bytes, str, str]:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    enabled = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/is-enabled",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutIsEnabledResponse,
    )
    if not enabled.enabled:
        raise OzonReturnError(
            "giveout_not_enabled",
            "Получение возвратов по штрихкоду недоступно. Ведите документ руками.",
        )
    response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/get-pdf",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutGetPDFResponse,
    )
    try:
        content = base64.b64decode(response.file_content, validate=True)
    except ValueError as exc:
        raise OzonReturnError(
            "ozon_invalid_file",
            "Ozon вернул повреждённый PDF пропуска.",
        ) from exc
    return (
        content,
        response.file_name or "ozon-return-pass.pdf",
        response.content_type or "application/pdf",
    )


async def get_giveout_pass_png(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> tuple[bytes, str, str]:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/get-png",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutGetPNGResponse,
    )
    try:
        content = base64.b64decode(response.file_content, validate=True)
    except ValueError as exc:
        raise OzonReturnError(
            "ozon_invalid_file",
            "Ozon вернул повреждённое изображение пропуска.",
        ) from exc
    return (
        content,
        response.file_name or "ozon-return-pass.png",
        response.content_type or "image/png",
    )


async def reset_giveout_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> tuple[bytes, str, str]:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    response = await _call_once(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/barcode-reset",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutBarcodeResetResponse,
    )
    try:
        content = base64.b64decode(response.file_content, validate=True)
    except ValueError as exc:
        raise OzonReturnError(
            "ozon_invalid_file",
            "Ozon вернул повреждённый новый штрихкод.",
        ) from exc
    return (
        content,
        response.file_name or "ozon-return-pass-reset.png",
        response.content_type or "image/png",
    )


async def current_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
) -> str:
    request = await _request_for_ozon_return(session, tenant_id, request_id)
    client_id, api_key = await _credentials(session, request)
    response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v1/return/giveout/barcode",
        request=OzonV1Empty(),
        response_type=OzonV1GiveoutGetBarcodeResponse,
    )
    return response.barcode


async def refresh_giveout_statuses(
    session: AsyncSession,
    request: InboundIntakeRequest,
    provider: OzonMarketplaceProvider,
) -> None:
    if request.operation_type != "return" or request.marketplace != "ozon":
        return
    client_id, api_key = await _credentials(session, request)
    giveouts = list(
        (
            await session.execute(
                select(InboundOzonReturnGiveout).where(
                    InboundOzonReturnGiveout.request_id == request.id
                )
            )
        )
        .scalars()
        .all()
    )
    for giveout in giveouts:
        info = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v1/return/giveout/info",
            request=OzonV1GiveoutInfoRequest(giveout_id=giveout.giveout_id),
            response_type=OzonV1GiveoutInfoResponse,
        )
        if info.giveout_status is not None:
            giveout.giveout_status = _status_text(info.giveout_status)
    await session.commit()
