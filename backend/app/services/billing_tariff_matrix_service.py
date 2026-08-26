from __future__ import annotations

import uuid
from datetime import datetime
from typing import TypedDict, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.billing import (
    BillingTariffMatrixConfig,
    BillingTariffServiceState,
    BillingTariffVersionV2,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User

NON_STORAGE_SERVICE_CODES = ("inbound", "marketplace_outbound", "packing", "return")


class BillingTariffMatrixError(ValueError):
    pass


async def ensure_disabled_tariff_matrix(
    session: AsyncSession, *, tenant: Tenant
) -> BillingTariffMatrixConfig:
    """Create the durable disabled baseline as part of a Tenant transaction."""
    if tenant.id is None:
        await session.flush()
    existing = await session.scalar(
        select(BillingTariffMatrixConfig)
        .where(BillingTariffMatrixConfig.tenant_id == tenant.id)
        .options(selectinload(BillingTariffMatrixConfig.service_states))
    )
    if existing is not None:
        return existing
    config = BillingTariffMatrixConfig(tenant_id=tenant.id)
    config.service_states = [
        BillingTariffServiceState(tenant_id=tenant.id, service_code=service_code, enabled=False)
        for service_code in NON_STORAGE_SERVICE_CODES
    ]
    session.add(config)
    try:
        await session.flush()
    except IntegrityError:
        # A concurrent bootstrap won the unique tenant row.  Its matrix is the
        # only valid result; never leave a silent missing configuration behind.
        existing = await session.scalar(
            select(BillingTariffMatrixConfig)
            .where(BillingTariffMatrixConfig.tenant_id == tenant.id)
            .options(selectinload(BillingTariffMatrixConfig.service_states))
        )
        if existing is None:
            raise
        return cast(BillingTariffMatrixConfig, existing)
    return config


async def get_tariff_matrix(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> BillingTariffMatrixConfig:
    config = await session.scalar(
        select(BillingTariffMatrixConfig)
        .where(BillingTariffMatrixConfig.tenant_id == tenant_id)
        .options(selectinload(BillingTariffMatrixConfig.service_states))
    )
    if config is None:
        raise BillingTariffMatrixError("billing_tariff_matrix_config_missing")
    return config


class TariffVersionDraft(TypedDict):
    seller_id: uuid.UUID | None
    product_id: uuid.UUID | None
    employee_user_id: uuid.UUID | None
    service_code: str
    unit: str
    enabled: bool
    rate: int
    valid_from_at: datetime
    valid_to_at: datetime | None


async def save_tariff_matrix(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    revision: int,
    services: dict[str, bool],
    versions: list[TariffVersionDraft],
) -> BillingTariffMatrixConfig:
    config = await get_tariff_matrix(session, tenant_id=tenant_id)
    if config.revision != revision:
        raise BillingTariffMatrixError("billing_tariff_matrix_stale_revision")
    if set(services) != set(NON_STORAGE_SERVICE_CODES):
        raise BillingTariffMatrixError("billing_tariff_matrix_services_incomplete")
    for draft in versions:
        if draft["service_code"] not in NON_STORAGE_SERVICE_CODES:
            raise BillingTariffMatrixError("billing_tariff_matrix_service_invalid")
        if draft["unit"] not in {"document", "item"} or draft["rate"] < 0:
            raise BillingTariffMatrixError("billing_tariff_matrix_rate_invalid")
        if draft["product_id"] is not None:
            if draft["unit"] != "item" or draft["seller_id"] is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_product_scope_invalid")
            product = await session.scalar(
                select(Product).where(
                    Product.id == draft["product_id"], Product.tenant_id == tenant_id
                )
            )
            if product is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_product_not_found")
        if draft["seller_id"] is not None:
            seller = await session.scalar(
                select(Seller).where(Seller.id == draft["seller_id"], Seller.tenant_id == tenant_id)
            )
            if seller is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_seller_not_found")
        if draft["employee_user_id"] is not None:
            user = await session.scalar(
                select(User).where(
                    User.id == draft["employee_user_id"], User.tenant_id == tenant_id
                )
            )
            if user is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_employee_not_found")
        if draft["valid_from_at"].tzinfo is None or (
            draft["valid_to_at"] is not None and draft["valid_to_at"] <= draft["valid_from_at"]
        ):
            raise BillingTariffMatrixError("billing_tariff_matrix_interval_invalid")
    states = {state.service_code: state for state in config.service_states}
    for service_code, enabled in services.items():
        states[service_code].enabled = enabled
    # Existing rows are immutable; an exact retry is recognised before a new
    # row is appended and new versions may not overlap an existing scope.
    for draft in versions:
        duplicate = await session.scalar(
            select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id == draft["seller_id"],
                BillingTariffVersionV2.product_id == draft["product_id"],
                BillingTariffVersionV2.employee_user_id == draft["employee_user_id"],
                BillingTariffVersionV2.service_code == draft["service_code"],
                BillingTariffVersionV2.unit == draft["unit"],
                BillingTariffVersionV2.valid_from_at == draft["valid_from_at"],
            )
        )
        if duplicate is not None:
            if duplicate.rate != draft["rate"] or duplicate.enabled != draft["enabled"]:
                raise BillingTariffMatrixError("billing_tariff_matrix_interval_overlap")
            continue
        session.add(BillingTariffVersionV2(tenant_id=tenant_id, **draft))
    config.revision += 1
    await session.flush()
    return config
