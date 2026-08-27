# ruff: noqa: E501
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.billing import BillingLedgerEntry
from app.services.billing_seller_report_service import _token, build_seller_report
from app.services.storage_measurement_service import MOSCOW, interval_liter_days


def test_exact_storage_interval_clamps_preexisting_stock_to_the_three_day_window() -> None:
    """TC-NEW-004: storage uses the requested half-open Moscow interval, not a month."""
    start = datetime(2026, 8, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 23, tzinfo=MOSCOW)
    movements = [SimpleNamespace(created_at=datetime(2026, 8, 19, 12, tzinfo=UTC), quantity_delta=2)]
    events = [SimpleNamespace(
        observed_at=datetime(2026, 8, 19, 10, tzinfo=UTC), volume_liters=Decimal("1.5"),
        source="manual", applied=True, fingerprint="manual",
    )]

    liter_days, missing = interval_liter_days(
        movements, events, legacy_volume_liters=None, start=start, end=end
    )

    assert liter_days == Decimal("9.0")
    assert missing is False


def test_storage_two_warehouse_total_and_missing_dimension_stay_explicit() -> None:
    """TC-NEW-005: aggregate warehouses once; absent dimensions are never a zero price."""
    start = datetime(2026, 8, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 23, tzinfo=MOSCOW)
    dimension = SimpleNamespace(
        observed_at=datetime(2026, 8, 19, tzinfo=UTC), volume_liters=Decimal("2"),
        source="manual", applied=True, fingerprint="dimension",
    )
    warehouse_a, missing_a = interval_liter_days(
        [SimpleNamespace(created_at=datetime(2026, 8, 19, tzinfo=UTC), quantity_delta=1)],
        [dimension], legacy_volume_liters=None, start=start, end=end,
    )
    warehouse_b, missing_b = interval_liter_days(
        [SimpleNamespace(created_at=datetime(2026, 8, 19, tzinfo=UTC), quantity_delta=3)],
        [], legacy_volume_liters=None, start=start, end=end,
    )

    assert warehouse_a == Decimal("6")
    assert warehouse_b == Decimal(0)
    assert missing_a is False
    assert missing_b is True


def test_storage_fingerprint_token_is_stable_then_changes_with_source_data() -> None:
    """TC-NEW-006: a changed movement changes the signed opaque calculation token."""
    base = {"tenant_id": "tenant", "seller_id": "seller", "moves": [["move-1", 2]]}

    assert _token(base) == _token(dict(base))
    assert _token(base) != _token({**base, "moves": [["move-1", 3]]})


@pytest.mark.asyncio
async def test_finance_off_has_physical_shape_only(async_client) -> None:
    """TC-NEW-001: finance mode changes fields, never the physical rows."""
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Seller report", "slug": f"seller-report-{uuid.uuid4().hex}",
        "admin_email": f"seller-{uuid.uuid4().hex}@example.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller_response = await async_client.post("/sellers", headers=headers, json={"name": "Альфа"})
    seller_id = uuid.UUID(seller_response.json()["id"])

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as session:
        me = await async_client.get("/auth/me", headers=headers)
        user = await session.scalar(select(User).where(User.id == uuid.UUID(me.json()["id"])))
        assert user is not None
        session.add(BillingLedgerEntry(
            tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
            source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=2,
            rate=150, amount=300, occurred_at=datetime(2026, 8, 20, 10, tzinfo=UTC),
        ))
        await session.commit()
        off = await build_seller_report(session, tenant_id=user.tenant_id, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20), include_finance=False)
        on = await build_seller_report(session, tenant_id=user.tenant_id, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20), include_finance=True)

    assert off["rows"][0]["operation_count"] == on["rows"][0]["operation_count"] == 1
    assert "net_total_kopecks" not in off["rows"][0]
    assert on["rows"][0]["net_total_kopecks"] == 300
