"""Эндпоинт для кнопки «Заполнить из WB / из Ozon» в окне реквизитов селлера.

Только читает: ничего не сохраняет и не меняет состояние ключей или каталога
(WMS-547 R10 — форма заполняется на фронте, «Сохранить» нажимает человек).
Отдельный модуль, а не billing.py — тот уже 787 строк (порог back_guard.py).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_billing_access
from app.db.session import get_db
from app.models.user import User
from app.services.billing_configuration_service import (
    BillingConfigurationError,
    assert_seller_in_tenant,
)
from app.services.seller_marketplace_requisites_service import (
    SellerRequisitesLookupError,
    lookup_requisites_for_button,
)

router = APIRouter(prefix="/billing/profiles", tags=["billing"])

# Коды из seller_marketplace_requisites_service → HTTP-статус ответа. Текст
# ошибки на экране фронт выбирает сам по detail (как LOOKUP_ERRORS у «Заполнить
# по ИНН»); статус здесь — не часть контракта для фронта, только для логов
# и общей корректности HTTP.
_ERROR_STATUS: dict[str, int] = {
    "key_not_connected": status.HTTP_409_CONFLICT,
    "marketplace_rejected_key": status.HTTP_502_BAD_GATEWAY,
    "marketplace_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "marketplace_unavailable": status.HTTP_502_BAD_GATEWAY,
    "ozon_account_blocked": status.HTTP_403_FORBIDDEN,
    "inn_missing": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


class MarketplaceRequisitesOut(BaseModel):
    inn: str
    legal_name: str | None = None
    kpp: str | None = None


@router.get("/sellers/{seller_id}/marketplace-requisites")
async def get_seller_marketplace_requisites(
    seller_id: uuid.UUID,
    marketplace: Literal["wb", "ozon"],
    user: Annotated[User, Depends(require_billing_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceRequisitesOut:
    """Сведения о продавце по API площадки — только для подстановки в форму."""
    try:
        await assert_seller_in_tenant(session, tenant_id=user.tenant_id, seller_id=seller_id)
    except BillingConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found"
        ) from None
    try:
        requisites = await lookup_requisites_for_button(
            session,
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            marketplace=marketplace,
        )
    except SellerRequisitesLookupError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_502_BAD_GATEWAY),
            detail=exc.code,
        ) from None
    return MarketplaceRequisitesOut(
        inn=requisites.inn,
        legal_name=requisites.legal_name,
        kpp=requisites.kpp,
    )
