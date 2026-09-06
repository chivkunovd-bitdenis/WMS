"""WMS-381. Состояние подписки организации: сколько дней осталось и сумма."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.subscription_service import subscription_state

router = APIRouter(prefix="/subscription", tags=["subscription"])


class SubscriptionOut(BaseModel):
    enabled: bool
    paid_until: date | None
    days_left: int | None
    blocked: bool
    price_rub: int


@router.get("", response_model=SubscriptionOut)
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionOut:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        return SubscriptionOut(
            enabled=False, paid_until=None, days_left=None, blocked=False, price_rub=0
        )
    state = subscription_state(tenant)
    return SubscriptionOut(
        enabled=state.enabled,
        paid_until=state.paid_until,
        days_left=state.days_left,
        blocked=state.blocked,
        price_rub=state.price_rub,
    )
