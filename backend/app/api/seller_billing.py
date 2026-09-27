"""Раздел «Расчёты» в кабинете селлера — только чтение (WMS-549, кусок К1).

Ставки селлера (вкладка «Ставки», требование R7) — отдельный кусок К2, сюда
не входят.

Все ручки переиспользуют тот же серверный расчёт, что видит ФФ по этому
селлеру (billing_seller_report_service, billing_invoice_v2_service): второго
независимого расчёта нет. Область — всегда `require_seller_billing_scope`,
общая для всех ручек этого роутера; в сигнатурах нет параметра `seller_id`,
поэтому подменить её через строку запроса нечем. Ручки ФФ `/billing/*`
(require_fulfillment_admin) этим файлом не затрагиваются.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
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
from app.services.billing_seller_report_service import (
    SellerReportError,
    build_seller_report,
    seller_details,
    storage_totals,
)

router = APIRouter(prefix="/seller-billing", tags=["seller-billing"])


@router.get("/summary", response_model=SellerReportFinancialSummaryOut)
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
        )
    except SellerReportError as exc:
        raise _seller_report_error(exc) from exc
    payload = {"rows": report["rows"], "totals": report["totals"]}
    return SellerReportFinancialSummaryOut.model_validate(payload)


@router.get("/details", response_model=SellerReportFinancialDetailsOut)
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
    try:
        return await list_invoices_v2(
            session,
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            status=status,
            number=number,
            cursor=cursor,
            limit=limit,
        )
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc


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
