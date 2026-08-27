"""Роуты счетов V2 и объединённой истории «Выставленные счета».

Вынесены из `billing.py`: тот файл держит старые начисления, тарифы, профили и
legacy-счета и уже перешагнул порог монолита в `scripts/ci/back_guard.py`.
Префикс и теги те же, поэтому пути и OpenAPI не меняются.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.billing import _seller_filter
from app.api.billing_invoice_v2_schemas import (
    InvoiceHistoryOut,
    InvoiceV2DraftRequest,
    InvoiceV2Out,
)
from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.user import User
from app.services.billing_invoice_v2_service import (
    BillingInvoiceV2Error,
    cancel_invoice_v2,
    create_invoice_v2,
    get_invoice_v2,
    invoice_v2_out,
    list_invoices_v2,
    preview_invoice_v2,
)

router = APIRouter(prefix="/billing", tags=["billing"])


def _invoice_v2_error(exc: BillingInvoiceV2Error) -> HTTPException:
    detail = str(exc)
    if detail in {"seller_not_found", "invoice_not_found"}:
        return HTTPException(status_code=404, detail=detail)
    if detail in {"idempotency_key_payload_mismatch", "idempotency_conflict"}:
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.get("/invoices-v2", response_model=InvoiceHistoryOut)
async def list_billing_invoices_v2(
    *,
    seller_id: str | None = None,
    status: str | None = None,
    number: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return await list_invoices_v2(
            session,
            tenant_id=user.tenant_id,
            seller_id=_seller_filter(seller_id),
            status=status,
            number=number,
            cursor=cursor,
            limit=limit,
        )
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc


@router.post("/invoices-v2/preview", response_model=InvoiceV2Out)
async def preview_billing_invoice_v2(
    body: InvoiceV2DraftRequest,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return await preview_invoice_v2(
            session, tenant_id=user.tenant_id, request=body.model_dump(mode="json")
        )
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc


@router.post("/invoices-v2", response_model=InvoiceV2Out, status_code=status.HTTP_201_CREATED)
async def create_billing_invoice_v2(
    body: InvoiceV2DraftRequest,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        invoice = await create_invoice_v2(
            session,
            tenant_id=user.tenant_id,
            user_id=user.id,
            request=body.model_dump(mode="json"),
            idempotency_key=idempotency_key or "",
        )
        await session.commit()
        return invoice_v2_out(invoice)
    except BillingInvoiceV2Error as exc:
        await session.rollback()
        raise _invoice_v2_error(exc) from exc


@router.get("/invoices-v2/{invoice_id}", response_model=InvoiceV2Out)
async def get_billing_invoice_v2(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return invoice_v2_out(
            await get_invoice_v2(session, tenant_id=user.tenant_id, invoice_id=invoice_id)
        )
    except BillingInvoiceV2Error as exc:
        raise _invoice_v2_error(exc) from exc


@router.post("/invoices-v2/{invoice_id}/cancel", response_model=InvoiceV2Out)
async def cancel_billing_invoice_v2(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        invoice = await cancel_invoice_v2(session, tenant_id=user.tenant_id, invoice_id=invoice_id)
        await session.commit()
        return invoice_v2_out(invoice)
    except BillingInvoiceV2Error as exc:
        await session.rollback()
        raise _invoice_v2_error(exc) from exc
