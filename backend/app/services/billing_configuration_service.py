from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingProfile, BillingTariffVersion
from app.models.seller import Seller


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
    if not legal_name.strip():
        raise BillingConfigurationError("Укажите юридическое наименование")
    validate_inn(inn)
    if seller_id is not None:
        seller = await session.scalar(
            select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
        )
        if seller is None:
            raise BillingConfigurationError("Селлер не найден в текущем tenant")
    elif not all((bank_name, bik, settlement_account, correspondent_account)):
        raise BillingConfigurationError("Для реквизитов ФФ заполните банковские поля")
    profile = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id == seller_id
        )
    )
    if profile is None:
        profile = BillingProfile(tenant_id=tenant_id, seller_id=seller_id)
        session.add(profile)
    profile.legal_name = legal_name.strip()
    profile.inn = inn.strip()
    profile.kpp = kpp.strip() if kpp else None
    profile.bank_name = bank_name.strip() if bank_name else None
    profile.bik = bik.strip() if bik else None
    profile.settlement_account = settlement_account.strip() if settlement_account else None
    profile.correspondent_account = correspondent_account.strip() if correspondent_account else None
    await session.flush()
    return profile


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
        seller = await session.scalar(
            select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
        )
        if seller is None:
            raise BillingConfigurationError("Селлер не найден в текущем tenant")
    query = (
        select(BillingTariffVersion)
        .where(
            BillingTariffVersion.tenant_id == tenant_id,
            BillingTariffVersion.seller_id == seller_id,
            BillingTariffVersion.service_code == service_code,
        )
        .order_by(BillingTariffVersion.valid_from.desc())
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
        amount=amount,
        valid_from=valid_from,
    )
    session.add(tariff)
    await session.flush()
    return tariff
