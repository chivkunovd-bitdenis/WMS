"""WMS-381. Подписка на систему.

Механика намеренно арифметическая: у организации есть дата, по которую оплачено.
Осталось дней — это вычитание. Доступ закрыт — это сравнение. Ни журнала
начислений, ни счётчиков, ни второго источника правды: разъезжаться нечему.

Пока дата не заполнена (NULL), подписка не применяется вообще. Поэтому выкатка
этого кода не может заблокировать никого, кто работает сегодня.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.core.settings import settings
from app.models.tenant import Tenant

# Московское время: склад работает по нему, и «последний день подписки»
# должен заканчиваться вместе с рабочим днём склада, а не по Гринвичу.
_MSK = timedelta(hours=3)


def today_msk() -> date:
    return (datetime.now(tz=UTC) + _MSK).date()


@dataclass(frozen=True)
class SubscriptionState:
    paid_until: date | None
    days_left: int | None
    blocked: bool
    price_rub: int

    @property
    def enabled(self) -> bool:
        return self.paid_until is not None


def subscription_state(tenant: Tenant, *, today: date | None = None) -> SubscriptionState:
    current_day = today or today_msk()
    paid_until = tenant.subscription_paid_until
    if paid_until is None:
        return SubscriptionState(
            paid_until=None,
            days_left=None,
            blocked=False,
            price_rub=settings.subscription_price_rub,
        )
    # Последний оплаченный день считается рабочим: оплачено «по 30-е» значит,
    # что 30-го человек ещё работает.
    days_left = (paid_until - current_day).days
    return SubscriptionState(
        paid_until=paid_until,
        days_left=max(days_left, 0),
        blocked=days_left < 0,
        price_rub=settings.subscription_price_rub,
    )
