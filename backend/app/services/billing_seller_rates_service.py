"""Ставки, действующие сейчас для операций конкретного селлера (WMS-549, К2).

Строка «Все товары» по каждой услуге считается тем же расчётом и тем же
приоритетом, что и при начислении денег — `_resolve_v2_tariff` в
billing_ledger_service (товар → селлер → общая, здесь всегда без товара):
второго независимого расчёта нет. Товарные строки — действующие версии V2,
у которых явно указан товар этого селлера; такая версия уже самая точная
по приоритету начисления, поэтому берётся как есть, без пересчёта.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingTariffVersionV2
from app.models.product import Product
from app.services.billing_ledger_service import _resolve_v2_tariff
from app.services.billing_tariff_matrix_service import MATRIX_SERVICE_CODES


@dataclass(frozen=True)
class SellerBillingRateRow:
    service_code: str
    unit: str
    rate_kopecks: int
    valid_from_at: datetime
    product_id: uuid.UUID | None = None
    product_sku: str | None = None
    product_name: str | None = None


async def list_seller_billing_rates(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> list[SellerBillingRateRow]:
    now = datetime.now(UTC)
    rows: list[SellerBillingRateRow] = []

    # «Все товары»: одна строка на услугу, ставкой без учёта товарных
    # переопределений — ровно то, что получит операция без своей ставки.
    for service_code in MATRIX_SERVICE_CODES:
        version = await _resolve_v2_tariff(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=None,
            service_code=service_code,
            occurred_at=now,
        )
        if version is None:
            continue
        rows.append(
            SellerBillingRateRow(
                service_code=service_code,
                unit=version.unit,
                rate_kopecks=version.rate,
                valid_from_at=version.valid_from_at,
            )
        )

    # Товарные ставки: только версии, у которых seller_id — этот селлер (схема
    # BillingTariffVersionV2 гарантирует ck_billing_tariff_v2_scope: версия с
    # product_id обязана иметь и seller_id, чужого товара здесь быть не может).
    # Ставок сотрудников тут нет по построению: у них product_id всегда NULL.
    product_versions = (
        await session.execute(
            select(BillingTariffVersionV2, Product)
            .join(Product, Product.id == BillingTariffVersionV2.product_id)
            .where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id == seller_id,
                BillingTariffVersionV2.product_id.is_not(None),
                BillingTariffVersionV2.enabled.is_(True),
                BillingTariffVersionV2.valid_from_at <= now,
                (
                    BillingTariffVersionV2.valid_to_at.is_(None)
                    | (BillingTariffVersionV2.valid_to_at > now)
                ),
                Product.tenant_id == tenant_id,
            )
        )
    ).all()

    latest: dict[tuple[uuid.UUID, str], tuple[BillingTariffVersionV2, Product]] = {}
    for version, product in product_versions:
        key = (version.product_id, version.service_code)
        current = latest.get(key)
        if current is None or version.valid_from_at > current[0].valid_from_at:
            latest[key] = (version, product)

    def _service_order(service_code: str) -> int:
        try:
            return MATRIX_SERVICE_CODES.index(service_code)
        except ValueError:
            return len(MATRIX_SERVICE_CODES)

    for version, product in sorted(
        latest.values(),
        key=lambda pair: (_service_order(pair[0].service_code), pair[1].name),
    ):
        rows.append(
            SellerBillingRateRow(
                service_code=version.service_code,
                unit=version.unit,
                rate_kopecks=version.rate,
                valid_from_at=version.valid_from_at,
                product_id=product.id,
                product_sku=product.sku_code,
                product_name=product.name,
            )
        )
    return rows
