from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingLedgerEntry, BillingProfile, BillingTariffVersion
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.staff_packaging_billing_service import rub_to_kopecks


class BillingConfigurationError(ValueError):
    pass


_SERVICE_UNITS: dict[str, frozenset[str]] = {
    "inbound": frozenset({"document", "item"}),
    "marketplace_outbound": frozenset({"document", "item"}),
    "storage_liter_day": frozenset({"liter_day"}),
}


def validate_inn(inn: str) -> str:
    value = inn.strip()
    if not value.isdigit() or len(value) not in (10, 12):
        raise BillingConfigurationError("Проверьте ИНН: должно быть 10 или 12 цифр")
    digits = [int(item) for item in value]
    if len(digits) == 10:
        check = (
            sum(d * w for d, w in zip(digits[:-1], (2, 4, 10, 3, 5, 9, 4, 6, 8), strict=True))
            % 11
            % 10
        )
        if check != digits[-1]:
            raise BillingConfigurationError("Проверьте ИНН: контрольное число не совпадает")
    else:
        weights = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        check_11 = sum(d * w for d, w in zip(digits[:10], weights, strict=True)) % 11 % 10
        check_12 = (
            sum(d * w for d, w in zip(digits[:11], (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), strict=True))
            % 11
            % 10
        )
        if check_11 != digits[-2] or check_12 != digits[-1]:
            raise BillingConfigurationError("Проверьте ИНН: контрольное число не совпадает")
    return value


async def save_profile(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    legal_name: str,
    inn: str,
    kpp: str | None = None,
    bank_name: str | None = None,
    bik: str | None = None,
    settlement_account: str | None = None,
    correspondent_account: str | None = None,
) -> BillingProfile:
    legal_name = legal_name.strip()
    if not legal_name:
        raise BillingConfigurationError("Укажите юридическое наименование")
    validate_inn(inn)
    if seller_id is not None:
        await assert_seller_in_tenant(session, tenant_id=tenant_id, seller_id=seller_id)
    else:
        bank_name = _required_text(bank_name)
        bik = _required_text(bik)
        settlement_account = _required_text(settlement_account)
        correspondent_account = _required_text(correspondent_account)
        if not all((bank_name, bik, settlement_account, correspondent_account)):
            raise BillingConfigurationError("Для реквизитов ФФ заполните банковские поля")
    profile = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id == seller_id
        )
    )
    if profile is None:
        profile = BillingProfile(tenant_id=tenant_id, seller_id=seller_id)
        session.add(profile)
    profile.legal_name = legal_name
    profile.inn = inn.strip()
    profile.kpp = kpp.strip() if kpp else None
    profile.bank_name = _required_text(bank_name)
    profile.bik = _required_text(bik)
    profile.settlement_account = _required_text(settlement_account)
    profile.correspondent_account = _required_text(correspondent_account)
    await session.flush()
    return profile


def _required_text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


async def assert_seller_in_tenant(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller:
    seller = await session.scalar(
        select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
    )
    if seller is None:
        raise BillingConfigurationError("Селлер не найден в текущем tenant")
    return seller


async def create_tariff(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    service_code: str,
    unit: str,
    amount: Decimal,
    valid_from: date,
) -> BillingTariffVersion:
    allowed_units = _SERVICE_UNITS.get(service_code)
    if allowed_units is None:
        raise BillingConfigurationError("Недопустимая услуга")
    if unit not in allowed_units:
        if service_code == "storage_liter_day":
            raise BillingConfigurationError("Для хранения доступен только расчёт за литр-день")
        raise BillingConfigurationError("Недопустимая единица расчёта")
    if amount < 0:
        raise BillingConfigurationError("Ставка не может быть отрицательной")
    if service_code == "storage_liter_day" and unit != "liter_day":
        raise BillingConfigurationError("Для хранения доступен только расчёт за литр-день")
    if seller_id is not None:
        await assert_seller_in_tenant(session, tenant_id=tenant_id, seller_id=seller_id)
    amount_kopecks = rub_to_kopecks(amount)
    # A tenant row is present for every authenticated caller. Lock it to make an
    # empty tariff stream serializable too; locking only existing versions leaves
    # two first writes free to create overlapping open-ended periods.
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    )
    if tenant is None:
        raise BillingConfigurationError("Тенант не найден")
    query = (
        select(BillingTariffVersion)
        .where(
            BillingTariffVersion.tenant_id == tenant_id,
            BillingTariffVersion.seller_id == seller_id,
            BillingTariffVersion.service_code == service_code,
        )
        .order_by(BillingTariffVersion.valid_from.desc())
        .with_for_update()
    )
    previous = (await session.scalars(query)).first()
    if previous and valid_from <= previous.valid_from:
        raise BillingConfigurationError("Дата пересекает будущую версию ставки")
    if previous:
        previous.valid_to = valid_from - timedelta(days=1)
    tariff = BillingTariffVersion(
        tenant_id=tenant_id,
        seller_id=seller_id,
        service_code=service_code,
        unit=unit,
        amount=amount_kopecks,
        valid_from=valid_from,
    )
    if tenant.billing_enabled_from is None:
        tenant.billing_enabled_from = valid_from
    nested = await session.begin_nested()
    try:
        session.add(tariff)
        await session.flush()
    except IntegrityError as exc:
        await nested.rollback()
        raise BillingConfigurationError("Дата пересекает будущую версию ставки") from exc
    else:
        await nested.commit()
    # A missing rate is explicitly a recoverable configuration problem, not a
    # historical price.  Once a covering version is entered, bind only those
    # previously unpriced facts which match this exact tariff stream.
    unpriced_query = select(BillingLedgerEntry).where(
        BillingLedgerEntry.tenant_id == tenant_id,
        BillingLedgerEntry.service_code == service_code,
        BillingLedgerEntry.rate.is_(None),
        BillingLedgerEntry.amount.is_(None),
    )
    if seller_id is not None:
        unpriced_query = unpriced_query.where(BillingLedgerEntry.seller_id == seller_id)
    unpriced = (await session.scalars(unpriced_query)).all()
    for entry in unpriced:
        fact_date = entry.occurred_at.date()
        if entry.occurred_at.tzinfo is not None:
            from zoneinfo import ZoneInfo

            fact_date = entry.occurred_at.astimezone(ZoneInfo("Europe/Moscow")).date()
        if fact_date < valid_from:
            continue
        entry.tariff_version_id = tariff.id
        entry.unit = unit
        entry.rate = amount_kopecks
        quantity = Decimal("1") if unit == "document" else entry.quantity
        entry.quantity = quantity
        entry.amount = int(
            (Decimal(amount_kopecks) * quantity).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    return tariff
