from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SubscriptionPayment(Base):
    """WMS-382. Один платёж за подписку в ЮKassa.

    Единственная причина, по которой эта таблица существует: деньги требуют
    следа, а идентификатор платежа — то, по чему мы отличаем «оплату уже
    засчитали» от «оплатили ещё раз». Без него повторный ответ ЮKassa продлил бы
    подписку дважды за одни деньги. Никакой другой логики здесь нет: остатки и
    сроки по-прежнему считаются арифметикой от даты в организации.
    """

    __tablename__ = "subscription_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_payment_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    amount_rub: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
