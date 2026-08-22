from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services.billing_configuration_service import (
    BillingConfigurationError,
    create_tariff,
    save_profile,
    validate_inn,
)


def test_validate_inn_accepts_valid_twelve_digit_inn() -> None:
    assert validate_inn("500100732259") == "500100732259"


def test_validate_inn_rejects_invalid_twelve_digit_inn_with_domain_error() -> None:
    with pytest.raises(BillingConfigurationError, match="контрольное число"):
        validate_inn("500100732250")


@pytest.mark.asyncio
async def test_tariff_versions_cannot_overlap_by_unit() -> None:
    session = AsyncMock()
    session.add = Mock()
    tenant_id = uuid4()
    start = date(2026, 1, 1)
    session.scalars = AsyncMock(
        side_effect=[Mock(first=lambda: None), Mock(first=lambda: Mock(valid_from=start))]
    )
    await create_tariff(
        session,
        tenant_id=tenant_id,
        seller_id=None,
        service_code="inbound",
        unit="document",
        amount=Decimal("10.00"),
        valid_from=start,
    )

    with pytest.raises(BillingConfigurationError, match="будущую версию"):
        await create_tariff(
            session,
            tenant_id=tenant_id,
            seller_id=None,
            service_code="inbound",
            unit="item",
            amount=Decimal("1.00"),
            valid_from=start,
        )


@pytest.mark.asyncio
async def test_first_tariff_explicitly_activates_billing_from_its_start_date() -> None:
    session = AsyncMock()
    session.add = Mock()
    tenant = Mock(billing_enabled_from=None)
    session.scalar = AsyncMock(return_value=tenant)
    session.scalars = AsyncMock(return_value=Mock(first=lambda: None))
    start = date(2026, 3, 1)

    await create_tariff(
        session,
        tenant_id=uuid4(),
        seller_id=None,
        service_code="inbound",
        unit="item",
        amount=Decimal("10.00"),
        valid_from=start,
    )

    assert tenant.billing_enabled_from == start


@pytest.mark.asyncio
async def test_tariff_rejects_unknown_service_and_invalid_unit_pair() -> None:
    session = AsyncMock()
    with pytest.raises(BillingConfigurationError, match="Недопустимая услуга"):
        await create_tariff(
            session,
            tenant_id=uuid4(),
            seller_id=None,
            service_code="custom",
            unit="document",
            amount=Decimal("1.00"),
            valid_from=date(2026, 1, 1),
        )
    with pytest.raises(BillingConfigurationError, match="литр-день"):
        await create_tariff(
            session,
            tenant_id=uuid4(),
            seller_id=None,
            service_code="storage_liter_day",
            unit="item",
            amount=Decimal("1.00"),
            valid_from=date(2026, 1, 1),
        )


@pytest.mark.asyncio
async def test_ff_profile_rejects_whitespace_only_bank_details() -> None:
    session = AsyncMock()
    with pytest.raises(BillingConfigurationError, match="банковские поля"):
        await save_profile(
            session,
            tenant_id=uuid4(),
            seller_id=None,
            legal_name="Фулфилмент",
            inn="7707083893",
            bank_name=" ",
            bik="044525225",
            settlement_account="40702810000000000001",
            correspondent_account="30101810400000000225",
        )
