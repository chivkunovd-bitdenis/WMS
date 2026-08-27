"""Приоритет ставок: товар → селлер → общая.

Модель владельца: ставку можно задать сразу всем селлерам, можно отдельным,
можно отдельным товарам. У кого индивидуальная не задана — действует уровень
выше. Точность всегда важнее даты: раньше среди «нетоварных» ставок побеждала
самая свежая по `valid_from_at`, поэтому общая ставка, заведённая позже,
перебивала индивидуальную ставку селлера.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersionV2
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.billing_ledger_service import _resolve_v2_tariff

# `async_client` поднимает схему базы; сам HTTP-клиент этим тестам не нужен.

OCCURRED = datetime(2026, 8, 20, 12, tzinfo=UTC)


async def _scene() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Арендатор, два селлера и товар первого селлера."""
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as session:
        tenant = Tenant(name=f"Тариф {suffix}", slug=f"tariff-priority-{suffix}")
        session.add(tenant)
        await session.flush()
        priced = Seller(tenant_id=tenant.id, name=f"Со своей ставкой {suffix}")
        plain = Seller(tenant_id=tenant.id, name=f"Без своей ставки {suffix}")
        session.add_all([priced, plain])
        await session.flush()
        product = Product(
            tenant_id=tenant.id,
            seller_id=priced.id,
            name="Платье",
            sku_code=f"sku-{suffix}",
        )
        session.add(product)
        await session.commit()
        return tenant.id, priced.id, plain.id, product.id


def _rate(
    tenant_id: uuid.UUID,
    *,
    rate: int,
    seller_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    valid_from: datetime,
) -> BillingTariffVersionV2:
    return BillingTariffVersionV2(
        tenant_id=tenant_id,
        seller_id=seller_id,
        product_id=product_id,
        employee_user_id=None,
        service_code="inbound",
        unit="item",
        enabled=True,
        rate=rate,
        valid_from_at=valid_from,
    )


async def _resolve(
    tenant_id: uuid.UUID, seller_id: uuid.UUID, product_id: uuid.UUID | None
) -> int | None:
    async with SessionLocal() as session:
        found = await _resolve_v2_tariff(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product_id,
            service_code="inbound",
            occurred_at=OCCURRED,
        )
        return None if found is None else found.rate


@pytest.mark.asyncio
async def test_seller_rate_beats_a_common_rate_created_later(async_client) -> None:
    """TC-NEW-301: общая ставка, заведённая позже, не перебивает селлерскую."""
    tenant_id, priced_seller, plain_seller, _product_id = await _scene()
    async with SessionLocal() as session:
        session.add(
            _rate(
                tenant_id,
                rate=1000,
                seller_id=priced_seller,
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        # Общая ставка заведена ПОЗЖЕ селлерской — именно этот порядок раньше
        # ломал расчёт, потому что сортировка шла по дате начала действия.
        session.add(_rate(tenant_id, rate=9999, valid_from=datetime(2026, 8, 1, tzinfo=UTC)))
        await session.commit()

    assert await _resolve(tenant_id, priced_seller, None) == 1000
    # У кого своей ставки нет — работает общая.
    assert await _resolve(tenant_id, plain_seller, None) == 9999


@pytest.mark.asyncio
async def test_product_rate_beats_seller_and_common(async_client) -> None:
    """TC-NEW-302: цена на товар перебивает и селлерскую, и общую."""
    tenant_id, priced_seller, _plain, product_id = await _scene()
    async with SessionLocal() as session:
        session.add(_rate(tenant_id, rate=9999, valid_from=datetime(2026, 8, 1, tzinfo=UTC)))
        session.add(
            _rate(
                tenant_id,
                rate=1000,
                seller_id=priced_seller,
                valid_from=datetime(2026, 8, 2, tzinfo=UTC),
            )
        )
        session.add(
            _rate(
                tenant_id,
                rate=250,
                seller_id=priced_seller,
                product_id=product_id,
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        await session.commit()

    # Товарная цена самая старая по дате и всё равно побеждает.
    assert await _resolve(tenant_id, priced_seller, product_id) == 250
    # Другой товар того же селлера считается по селлерской ставке.
    assert await _resolve(tenant_id, priced_seller, uuid.uuid4()) == 1000


@pytest.mark.asyncio
async def test_seller_rate_never_leaks_to_another_seller(async_client) -> None:
    """TC-NEW-303: индивидуальная ставка одного селлера не действует на другого."""
    tenant_id, priced_seller, plain_seller, _product_id = await _scene()
    async with SessionLocal() as session:
        session.add(
            _rate(
                tenant_id,
                rate=1000,
                seller_id=priced_seller,
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        await session.commit()

    assert await _resolve(tenant_id, priced_seller, None) == 1000
    # Общей ставки нет вовсе — соседнему селлеру браться неоткуда.
    assert await _resolve(tenant_id, plain_seller, None) is None


@pytest.mark.asyncio
async def test_newer_rate_still_wins_inside_one_level(async_client) -> None:
    """TC-NEW-304: дата решает, но только между ставками одной точности."""
    tenant_id, priced_seller, _plain, _product = await _scene()
    async with SessionLocal() as session:
        session.add(
            _rate(
                tenant_id,
                rate=100,
                seller_id=priced_seller,
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            _rate(
                tenant_id,
                rate=300,
                seller_id=priced_seller,
                valid_from=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
        await session.commit()

    assert await _resolve(tenant_id, priced_seller, None) == 300

    async with SessionLocal() as session:
        stored = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.tenant_id == tenant_id
                    )
                )
            ).all()
        )
    # Обе версии остаются в истории: ставки не переписываются задним числом.
    assert len(stored) == 2
