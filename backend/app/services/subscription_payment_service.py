"""WMS-382. Оплата подписки через ЮKassa.

Вебхука здесь нет намеренно. Магазин в ЮKassa общий с оцифровкой, а вебхук у
магазина один — тронув его настройку, мы сломали бы приём платежей соседнего
продукта. Поэтому статус платежа мы спрашиваем сами: человек вернулся с оплаты
или нажал «Проверить оплату» — идём в ЮKassa и смотрим. Тот же приём используется
в оцифровке рядом.

Продление — арифметика без журналов: к дате, по которую оплачено (или к сегодня,
если она уже прошла), прибавляется месяц. Единственное, что здесь хранится, —
идентификатор платежа, чтобы одна оплата не продлила подписку дважды.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.subscription_payment import SubscriptionPayment
from app.models.tenant import Tenant
from app.services.subscription_service import today_msk

logger = logging.getLogger(__name__)

SUBSCRIPTION_DAYS = 30
REQUEST_TIMEOUT_SECONDS = 20.0
_PENDING_STATUSES = ("pending", "waiting_for_capture")


class SubscriptionPaymentError(ValueError):
    """Код ошибки для экрана: not_configured, unavailable, no_pending."""


def payments_configured() -> bool:
    return bool(settings.yookassa_shop_id.strip() and settings.yookassa_secret_key.strip())


def _auth() -> tuple[str, str]:
    return settings.yookassa_shop_id.strip(), settings.yookassa_secret_key.strip()


def _payments_url(payment_id: str | None = None) -> str:
    base = settings.yookassa_api_base.rstrip("/")
    return f"{base}/v3/payments/{payment_id}" if payment_id else f"{base}/v3/payments"


def _receipt(amount: int, description: str, customer_email: str) -> dict[str, object]:
    """Чек по 54-ФЗ. Без него боевой магазин отказывает: «Receipt is missing».

    Состав позиции тоже проверен на живом магазине: без предмета и способа
    расчёта ЮKassa отвечает «Invalid value of the items.paymentSubject».
    """
    receipt: dict[str, object] = {
        "customer": {"email": customer_email},
        "items": [
            {
                "description": description,
                "quantity": "1.00",
                "amount": {"value": f"{amount}.00", "currency": "RUB"},
                "vat_code": settings.yookassa_vat_code,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ],
    }
    if settings.yookassa_tax_system_code is not None:
        receipt["tax_system_code"] = settings.yookassa_tax_system_code
    return receipt


async def create_payment(
    session: AsyncSession,
    *,
    tenant: Tenant,
    return_url: str,
    customer_email: str,
) -> str:
    """Создать платёж и вернуть адрес оплаты."""
    if not payments_configured():
        raise SubscriptionPaymentError("payments_not_configured")

    amount = settings.subscription_price_rub
    description = "Подписка на складскую систему"
    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": f"{description}, {tenant.name}"[:128],
        "metadata": {"tenant_id": str(tenant.id), "product": "wms"},
        "receipt": _receipt(amount, description, customer_email),
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _payments_url(),
                auth=_auth(),
                headers={"Idempotence-Key": idempotence_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("yookassa create payment failed: %s", exc)
        raise SubscriptionPaymentError("payments_unavailable") from exc

    payment_id = str(data.get("id") or "")
    confirmation = data.get("confirmation")
    confirmation_url = ""
    if isinstance(confirmation, dict):
        confirmation_url = str(confirmation.get("confirmation_url") or "")
    if not payment_id or not confirmation_url:
        logger.warning("yookassa create payment: неполный ответ %s", str(data)[:400])
        raise SubscriptionPaymentError("payments_unavailable")

    session.add(
        SubscriptionPayment(
            tenant_id=tenant.id,
            provider_payment_id=payment_id,
            amount_rub=amount,
            status=str(data.get("status") or "pending"),
        )
    )
    try:
        await session.commit()
    except Exception:
        # Платёж в ЮKassa уже создан, а запись о нём не легла. Человек может
        # заплатить, и без идентификатора в логе мы об этом не узнаем — поэтому
        # он пишется явно, до того как исключение уйдёт наверх.
        await session.rollback()
        logger.exception(
            "payment_saved_failed: платёж создан в ЮKassa, но не записан. "
            "tenant=%s payment=%s сумма=%s",
            tenant.id,
            payment_id,
            amount,
        )
        raise SubscriptionPaymentError("payments_unavailable") from None
    return confirmation_url


def extend_paid_until(tenant: Tenant) -> None:
    """Продлить подписку на месяц: оплаченные дни не сгорают."""
    today = today_msk()
    paid_until = tenant.subscription_paid_until
    base = paid_until if paid_until is not None and paid_until >= today else today
    tenant.subscription_paid_until = base + timedelta(days=SUBSCRIPTION_DAYS)


async def sync_pending_payment(session: AsyncSession, *, tenant: Tenant) -> bool:
    """Спросить ЮKassa про незакрытый платёж. True — подписка продлена."""
    if not payments_configured():
        return False

    tenant_id = tenant.id
    stmt = (
        select(SubscriptionPayment.id, SubscriptionPayment.provider_payment_id)
        .where(
            SubscriptionPayment.tenant_id == tenant_id,
            SubscriptionPayment.status.in_(_PENDING_STATUSES),
        )
        .order_by(SubscriptionPayment.created_at.desc())
    )
    # Спрашиваем про ВСЕ незакрытые платежи, а не только про свежий. Человек мог
    # нажать «Продлить» дважды и оплатить первый счёт: если смотреть только на
    # последний, деньги ушли бы, а срок остался прежним до тех пор, пока ЮKassa
    # не протухнет второй счёт сама.
    payments = (await session.execute(stmt)).all()
    if not payments:
        return False
    # Caller only reads the user/tenant. Release that transaction and connection
    # before HTTP; payment/tenant ORM snapshots must not survive as write inputs.
    await session.commit()

    results: dict[uuid.UUID, tuple[str, bool]] = {}
    for payment_id, provider_payment_id in payments:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _payments_url(provider_payment_id), auth=_auth()
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("yookassa get payment failed: %s", exc)
            raise SubscriptionPaymentError("payments_unavailable") from exc

        results[payment_id] = (str(data.get("status") or ""), bool(data.get("paid")))

    # Serialize settlement for this tenant, then reread both the paid-through
    # date and pending payments. Another poll may have already applied an answer.
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one()
    pending = (await session.scalars(
        select(SubscriptionPayment).where(
            SubscriptionPayment.tenant_id == tenant_id,
            SubscriptionPayment.id.in_(results),
            SubscriptionPayment.status.in_(_PENDING_STATUSES),
        ).order_by(SubscriptionPayment.id).with_for_update()
        .execution_options(populate_existing=True)
    )).all()
    activated = False
    for payment in pending:
        status, paid = results[payment.id]
        if status == "succeeded" and paid:
            payment.status = "succeeded"
            payment.paid_at = datetime.now(tz=UTC)
            extend_paid_until(tenant)
            activated = True
            logger.info(
                "subscription extended: tenant=%s until=%s payment=%s",
                tenant.id,
                tenant.subscription_paid_until,
                payment.provider_payment_id,
            )
            continue
        if status == "canceled":
            payment.status = "canceled"
        elif status:
            payment.status = status

    await session.commit()
    return activated
