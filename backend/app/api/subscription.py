"""WMS-381/382. Состояние подписки, сумма к оплате и оплата через ЮKassa."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, public_base_url, require_fulfillment_admin
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.subscription_payment_service import (
    SubscriptionPaymentError,
    create_payment,
    payments_configured,
    sync_pending_payment,
)
from app.services.subscription_service import subscription_state

router = APIRouter(prefix="/subscription", tags=["subscription"])


class SubscriptionOut(BaseModel):
    enabled: bool
    paid_until: date | None
    days_left: int | None
    blocked: bool
    price_rub: int
    payment_available: bool


class PaymentStartOut(BaseModel):
    confirmation_url: str


class PaymentSyncOut(BaseModel):
    activated: bool


async def _tenant_of(session: AsyncSession, user: User) -> Tenant:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return tenant


def _payment_http_error(exc: SubscriptionPaymentError) -> HTTPException:
    code = exc.args[0] if exc.args else "payments_unavailable"
    if code == "payments_not_configured":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payments_not_configured"
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="payments_unavailable"
    )


@router.get("", response_model=SubscriptionOut)
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionOut:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        return SubscriptionOut(
            enabled=False,
            paid_until=None,
            days_left=None,
            blocked=False,
            price_rub=0,
            payment_available=False,
        )
    state = subscription_state(tenant)
    return SubscriptionOut(
        enabled=state.enabled,
        paid_until=state.paid_until,
        days_left=state.days_left,
        blocked=state.blocked,
        price_rub=state.price_rub,
        payment_available=payments_configured(),
    )


@router.post("/pay", response_model=PaymentStartOut)
async def start_payment(
    request: Request,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentStartOut:
    """Создать платёж и вернуть адрес оплаты. Платит только администратор."""
    tenant = await _tenant_of(session, admin)
    return_url = f"{public_base_url(request)}/ff/settings?tab=subscription"
    try:
        confirmation_url = await create_payment(
            session,
            tenant=tenant,
            return_url=return_url,
            customer_email=admin.email,
        )
    except SubscriptionPaymentError as exc:
        raise _payment_http_error(exc) from None
    return PaymentStartOut(confirmation_url=confirmation_url)


@router.post("/sync", response_model=PaymentSyncOut)
async def sync_payment(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentSyncOut:
    """Спросить ЮKassa, прошла ли оплата, и продлить подписку.

    Ручка доступна любому сотруднику организации: человек, упёршийся в экран
    «подписка закончилась», должен иметь возможность нажать «Проверить оплату»,
    даже если платил не он.
    """
    tenant = await _tenant_of(session, user)
    try:
        activated = await sync_pending_payment(session, tenant=tenant)
    except SubscriptionPaymentError as exc:
        raise _payment_http_error(exc) from None
    return PaymentSyncOut(activated=activated)
