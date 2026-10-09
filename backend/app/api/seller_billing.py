"""Раздел «Расчёты» в кабинете селлера — только чтение (WMS-549, куски К1 и К2).

Все ручки переиспользуют тот же серверный расчёт, что видит ФФ по этому
селлеру (billing_seller_report_service, billing_invoice_v2_service,
billing_seller_rates_service): второго независимого расчёта нет. Область —
всегда `require_seller_billing_scope`, общая для всех ручек этого роутера;
в сигнатурах нет параметра `seller_id`, поэтому подменить её через строку
запроса нечем. Ручки ФФ `/billing/*` (require_fulfillment_admin) этим файлом
не затрагиваются.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.billing import _invoice_out, _seller_report_error
from app.api.billing_invoice_v2_schemas import InvoiceHistoryOut, InvoiceV2Out
from app.api.billing_invoices_v2 import _invoice_v2_error
from app.api.billing_seller_report_schemas import (
    SellerReportFinancialDetailsOut,
    SellerReportFinancialSummaryOut,
)
from app.api.deps import get_current_user, require_seller_billing_scope
from app.core.settings import settings
from app.db.session import get_db
from app.models.billing import BillingInvoice
from app.models.seller import Seller
from app.models.user import User
from app.services.billing_invoice_v2_service import (
    BillingInvoiceV2Error,
    get_invoice_v2,
    invoice_v2_out,
    list_invoices_v2,
)
from app.services.billing_seller_rates_service import list_seller_billing_rates
from app.services.billing_seller_report_service import (
    SellerReportError,
    build_seller_report,
    seller_details,
    storage_totals,
)

router = APIRouter(prefix="/seller-billing", tags=["seller-billing"])

# WMS-549 F2 (ревью Astra №1): курсор общей истории счетов (list_invoices_v2)
# сам по себе не привязан к tenant/seller — для ФФ это осознанно (см. его
# docstring: фильтры приходят явными параметрами запроса). Но у селлера
# область фиксирована сервером на каждый запрос, и курсор, выданный другому
# селлеру, не должен даже приниматься. Меняем не общий курсор ФФ (это чужой
# контракт), а оборачиваем его подписанным конвертом только на этой ручке:
# наружу отдаём конверт с tenant_id/seller_id, внутрь сервиса передаём
# исходный курсор как есть.
_INVOICE_CURSOR_CONTEXT = b"wms:seller-billing-invoice-cursor:v1"


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _cursor_signature(payload: dict[str, Any]) -> str:
    key = hmac.new(
        settings.jwt_secret_key.encode(), _INVOICE_CURSOR_CONTEXT, hashlib.sha256
    ).digest()
    return hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest()


def _wrap_invoice_list_cursor(
    inner_cursor: str, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    payload = {"tenant_id": str(tenant_id), "seller_id": str(seller_id), "cursor": inner_cursor}
    envelope = {"payload": payload, "signature": _cursor_signature(payload)}
    return base64.urlsafe_b64encode(_canonical_json(envelope)).decode().rstrip("=")


def _unwrap_invoice_list_cursor(
    cursor: str, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        payload = decoded["payload"]
        signature = decoded["signature"]
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise ValueError
        if not hmac.compare_digest(signature, _cursor_signature(payload)):
            raise ValueError
        if payload.get("tenant_id") != str(tenant_id) or payload.get("seller_id") != str(seller_id):
            raise ValueError
        inner = payload.get("cursor")
        if not isinstance(inner, str):
            raise ValueError
        return inner
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="invalid_cursor") from None


class SellerBillingRateOut(BaseModel):
    service_code: str
    unit: str
    rate_kopecks: int
    valid_from_at: datetime
    # Пусто у строки «Все товары»; заполнено у ставки на конкретный товар.
    product_id: uuid.UUID | None = None
    product_sku: str | None = None
    product_name: str | None = None


class SellerBillingRatesOut(BaseModel):
    rates: list[SellerBillingRateOut]


@router.get(
    "/summary", response_model=SellerReportFinancialSummaryOut,
    response_model_exclude={"totals": {"in_work_items"}, "rows": {"__all__": {"in_work_items"}}},
)
async def get_seller_billing_summary(
    *,
    date_from: date,
    date_to: date,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerReportFinancialSummaryOut:
    """Полоса итогов и строка своего селлера — без выбора кем-либо селлера."""
    try:
        report = await build_seller_report(
            session,
            tenant_id=user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_id,
            include_finance=True,
            include_in_work=False,
        )
    except SellerReportError as exc:
        raise _seller_report_error(exc) from exc
    payload = {"rows": report["rows"], "totals": report["totals"]}
    return SellerReportFinancialSummaryOut.model_validate(payload)


@router.get(
    "/details", response_model=SellerReportFinancialDetailsOut,
    response_model_exclude={"totals": {"in_work_items"}, "entries": {"__all__": {"in_work"}}},
)
async def get_seller_billing_details(
    *,
    date_from: date,
    date_to: date,
    limit: int = 50,
    cursor: str | None = None,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerReportFinancialDetailsOut:
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="invalid_limit")
    try:
        payload = await seller_details(
            session,
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            date_from=date_from,
            date_to=date_to,
            include_finance=True,
            include_in_work=False,
            limit=limit,
            cursor=cursor,
        )
    except SellerReportError as exc:
        raise _seller_report_error(exc) from exc
    return SellerReportFinancialDetailsOut.model_validate(payload)


@router.get("/storage-total")
async def get_seller_billing_storage_total(
    *,
    date_from: date,
    date_to: date,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return await storage_totals(
            session,
            tenant_id=user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_id,
        )
    except SellerReportError as exc:
        raise _seller_report_error(exc) from exc


@router.get("/invoices", response_model=InvoiceHistoryOut)
async def list_seller_billing_invoices(
    *,
    status: str | None = None,
    number: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    inner_cursor = (
        _unwrap_invoice_list_cursor(cursor, tenant_id=user.tenant_id, seller_id=seller_id)
        if cursor is not None
        else None
    )
    try:
        result = await list_invoices_v2(
            session,
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            status=status,
            number=number,
            cursor=inner_cursor,
            limit=limit,
        )
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc
    next_cursor = result.get("next_cursor")
    if isinstance(next_cursor, str):
        result["next_cursor"] = _wrap_invoice_list_cursor(
            next_cursor, tenant_id=user.tenant_id, seller_id=seller_id
        )
    return result


@router.get("/invoices/legacy/{invoice_id}", response_model=None)
async def get_seller_billing_legacy_invoice(
    invoice_id: uuid.UUID,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    # Область — тенант и свой селлер сразу в запросе: чужой счёт (включая
    # свой тенант, но чужого селлера) не отличить от несуществующего.
    row = (
        await session.execute(
            select(BillingInvoice, Seller.name)
            .join(Seller)
            .where(
                BillingInvoice.id == invoice_id,
                BillingInvoice.tenant_id == user.tenant_id,
                BillingInvoice.seller_id == seller_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Счёт не найден")
    return _invoice_out(*row)


@router.get("/invoices/v2/{invoice_id}", response_model=InvoiceV2Out)
async def get_seller_billing_invoice_v2(
    invoice_id: uuid.UUID,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        invoice = await get_invoice_v2(session, tenant_id=user.tenant_id, invoice_id=invoice_id)
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc
    if invoice.seller_id != seller_id:
        # get_invoice_v2 проверяет только тенант; счёт чужого селлера того же
        # тенанта дошёл бы иначе — здесь его отличаем от несуществующего тем
        # же 404, чтобы не подтверждать даже сам факт существования счёта.
        raise HTTPException(status_code=404, detail="invoice_not_found")
    return await invoice_v2_out(session, invoice)


@router.get("/rates", response_model=SellerBillingRatesOut)
async def get_seller_billing_rates(
    *,
    seller_id: Annotated[uuid.UUID, Depends(require_seller_billing_scope)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerBillingRatesOut:
    """Действующие сейчас ставки этого селлера (R7) — без периода, без фильтров."""
    rows = await list_seller_billing_rates(session, tenant_id=user.tenant_id, seller_id=seller_id)
    return SellerBillingRatesOut(
        rates=[
            SellerBillingRateOut(
                service_code=row.service_code,
                unit=row.unit,
                rate_kopecks=row.rate_kopecks,
                valid_from_at=row.valid_from_at,
                product_id=row.product_id,
                product_sku=row.product_sku,
                product_name=row.product_name,
            )
            for row in rows
        ]
    )
