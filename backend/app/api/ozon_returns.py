"""HTTP contract for Ozon return giveouts in an existing inbound-return request."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_reception_access
from app.db.session import get_db
from app.models.inbound_intake import InboundIntakeRequest
from app.models.user import User
from app.services import ozon_return_service as svc
from app.services.marketplace_account_service import MarketplaceAccountError
from app.services.marketplace_provider import (
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.ozon_provider_factory import build_ozon_provider

router = APIRouter(
    prefix="/operations/inbound-intake-requests/{request_id}/ozon-returns",
    tags=["operations"],
)


class OzonReturnItemOut(BaseModel):
    id: str | None = None
    inbound_line_id: str | None = None
    return_id: int | None = None
    posting_number: str | None = None
    return_barcode: str | None = None
    return_reason_name: str | None = None
    return_type: str | None = None
    offer_id: str | None = None
    ozon_sku: int | None = None
    product_name: str
    quantity: int = Field(ge=0)
    approved: bool = False
    product_id: str | None = None
    wms_sku: str | None = None
    wms_barcode: str | None = None
    wms_name: str | None = None
    matched: bool
    warning: str | None = None
    storage_days: int | None = None
    utilization_forecast_date: str | None = None


class OzonFbsReturnPointOut(BaseModel):
    id: int
    name: str | None = None
    address: str | None = None
    place_id: int | None = None
    box_count: int | None = None
    returns_count: int | None = None
    utc_offset: str | None = None
    warehouses_ids: list[str] = Field(default_factory=list)
    pass_count: int | None = None
    pass_required: bool | None = None


class OzonReturnGiveoutOut(BaseModel):
    giveout_id: int
    giveout_status: str
    warehouse_id: int | None = None
    warehouse_name: str
    warehouse_address: str
    approved_articles_count: int = 0
    total_articles_count: int = 0
    created_at: str | None = None
    storage_days: int | None = None
    utilization_forecast_date: str | None = None
    already_imported: bool = False
    items: list[OzonReturnItemOut] = Field(default_factory=list)


class OzonReturnPreviewOut(BaseModel):
    enabled: bool
    message: str | None = None
    groups: list[OzonReturnGiveoutOut] = Field(default_factory=list)
    imported_giveout_ids: list[int] = Field(default_factory=list)


class OzonReturnGiveoutImportIn(BaseModel):
    giveout_ids: list[int] = Field(min_length=1, max_length=500)


class OzonReturnImportOut(BaseModel):
    giveouts_imported: int
    items_imported: int
    unmatched_items: int


class OzonReturnBarcodeOut(BaseModel):
    barcode: str = Field(min_length=1)


async def get_ozon_return_provider() -> OzonMarketplaceProvider:
    """Боевой транспорт, когда он включён настройкой; иначе прежний локальный фейк."""
    return build_ozon_provider()


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, svc.OzonReturnError):
        status_code = {
            "request_not_found": status.HTTP_404_NOT_FOUND,
            "giveouts_empty": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_ozon_return": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "seller_missing": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_draft": status.HTTP_409_CONFLICT,
            "giveout_not_found": status.HTTP_409_CONFLICT,
            "ozon_not_connected": status.HTTP_409_CONFLICT,
            "giveout_not_enabled": status.HTTP_409_CONFLICT,
        }.get(exc.code, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    if isinstance(exc, MarketplaceAccountError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": "Подключите кабинет Ozon для этого селлера."},
        ) from None
    if isinstance(exc, MarketplaceProviderError):
        status_code = (
            status.HTTP_403_FORBIDDEN
            if exc.is_account_blocked
            else status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.status_code == 429 or (exc.status_code is not None and exc.status_code >= 500)
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": provider_error_message(exc)},
        ) from None
    raise exc


@router.get("/preview", response_model=OzonReturnPreviewOut)
async def preview_ozon_returns(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> OzonReturnPreviewOut:
    try:
        return OzonReturnPreviewOut.model_validate(
            await svc.build_preview(session, user.tenant_id, request_id, provider)
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


@router.post("/import", response_model=OzonReturnImportOut)
async def import_ozon_return_giveouts(
    request_id: uuid.UUID,
    body: OzonReturnGiveoutImportIn,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> OzonReturnImportOut:
    try:
        return OzonReturnImportOut.model_validate(
            await svc.import_selected_giveouts(
                session, user.tenant_id, request_id, provider, body.giveout_ids
            )
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


@router.get("/groups", response_model=list[OzonReturnGiveoutOut])
async def get_imported_ozon_return_groups(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[OzonReturnGiveoutOut]:
    try:
        return [
            OzonReturnGiveoutOut.model_validate(group)
            for group in await svc.imported_groups(session, user.tenant_id, request_id)
        ]
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


@router.get("/pass.pdf")
async def get_ozon_return_pass_pdf(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> Response:
    try:
        content, filename, content_type = await svc.get_giveout_pass_pdf(
            session, user.tenant_id, request_id, provider
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/barcode", response_model=OzonReturnBarcodeOut)
async def get_ozon_return_barcode(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> OzonReturnBarcodeOut:
    try:
        return OzonReturnBarcodeOut(
            barcode=await svc.current_barcode(session, user.tenant_id, request_id, provider)
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


@router.post("/refresh-statuses", response_model=list[OzonReturnGiveoutOut])
async def refresh_ozon_return_statuses(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> list[OzonReturnGiveoutOut]:
    request = await session.get(InboundIntakeRequest, request_id)
    if request is None or request.tenant_id != user.tenant_id:
        _raise_service_error(svc.OzonReturnError("request_not_found", "Возврат не найден."))
    assert request is not None
    try:
        if request.operation_type != "return" or request.marketplace != "ozon":
            raise svc.OzonReturnError(
                "not_ozon_return", "Получение из Ozon доступно только для возврата Ozon."
            )
        await svc.refresh_giveout_statuses(session, request, provider)
        return [
            OzonReturnGiveoutOut.model_validate(group)
            for group in await svc.imported_groups(session, user.tenant_id, request_id)
        ]
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


@router.get("/fbs-return-points", response_model=list[OzonFbsReturnPointOut])
async def get_ozon_fbs_return_points(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> list[OzonFbsReturnPointOut]:
    try:
        points = await svc.company_fbs_return_points(
            session, user.tenant_id, request_id, provider
        )
        return [
            OzonFbsReturnPointOut(
                id=point.id,
                name=point.name,
                address=point.address,
                place_id=point.place_id,
                box_count=point.box_count,
                returns_count=point.returns_count,
                utc_offset=point.utc_offset,
                warehouses_ids=list(point.warehouses_ids or []),
                pass_count=point.pass_info.count if point.pass_info else None,
                pass_required=point.pass_info.is_required if point.pass_info else None,
            )
            for point in points
        ]
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None


def _pass_response(content: bytes, filename: str, content_type: str) -> Response:
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pass.png")
async def get_ozon_return_pass_png(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> Response:
    try:
        content, filename, content_type = await svc.get_giveout_pass_png(
            session, user.tenant_id, request_id, provider
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None
    return _pass_response(content, filename, content_type)


@router.post("/barcode/reset.png")
async def reset_ozon_return_barcode(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[OzonMarketplaceProvider, Depends(get_ozon_return_provider)],
) -> Response:
    try:
        content, filename, content_type = await svc.reset_giveout_barcode(
            session, user.tenant_id, request_id, provider
        )
    except Exception as exc:
        _raise_service_error(exc)
        raise AssertionError("unreachable") from None
    return _pass_response(content, filename, content_type)
