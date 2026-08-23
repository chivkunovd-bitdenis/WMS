import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_measurement_service import (
    MOSCOW,
    _stock_segments,
    _volume_segments,
    calculation_end_exclusive,
    month_bounds,
    previous_month,
    rebuild_storage_measurements,
)


def _movement(**values: object) -> InventoryMovement:
    return cast(InventoryMovement, SimpleNamespace(**values))


def _dimension_event(**values: object) -> ProductDimensionEvent:
    return cast(ProductDimensionEvent, SimpleNamespace(**values))


def test_previous_month_defaults_to_completed_calendar_month() -> None:
    assert previous_month(date(2026, 8, 22)) == (date(2026, 7, 1), date(2026, 7, 31))


def test_month_bounds_rejects_invalid_month() -> None:
    try:
        month_bounds(2026, 13)
    except ValueError as exc:
        assert str(exc) == "invalid_month"
    else:
        raise AssertionError("invalid month must fail")


def test_stock_segments_keep_fractional_day_boundaries() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    end = datetime(2026, 7, 3, tzinfo=MOSCOW)
    movements = [
        _movement(created_at=datetime(2026, 7, 1, 12, tzinfo=MOSCOW), quantity_delta=2),
        _movement(created_at=datetime(2026, 7, 2, 12, tzinfo=MOSCOW), quantity_delta=-1),
    ]
    segments = _stock_segments(movements, start, end)
    assert segments == [
        (start, datetime(2026, 7, 1, 12, tzinfo=MOSCOW), 0),
        (datetime(2026, 7, 1, 12, tzinfo=MOSCOW), datetime(2026, 7, 2, 12, tzinfo=MOSCOW), 2),
        (datetime(2026, 7, 2, 12, tzinfo=MOSCOW), end, 1),
    ]


def test_stock_segments_reject_negative_reconstructed_stock() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    end = datetime(2026, 7, 2, tzinfo=MOSCOW)

    with pytest.raises(ValueError, match="negative_reconstructed_stock"):
        _stock_segments(
            [_movement(created_at=start, quantity_delta=-1)],
            start,
            end,
        )


def test_stock_segments_net_same_timestamp_internal_movements() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    moved_at = datetime(2026, 7, 1, 12, tzinfo=MOSCOW)
    end = datetime(2026, 7, 2, tzinfo=MOSCOW)

    segments = _stock_segments(
        [
            _movement(created_at=moved_at, quantity_delta=-1),
            _movement(created_at=moved_at, quantity_delta=1),
        ],
        start,
        end,
    )

    assert segments == [(start, moved_at, 0), (moved_at, end, 0)]


def test_current_month_stops_at_current_moscow_instant() -> None:
    now = datetime(2026, 8, 22, 15, 30, tzinfo=MOSCOW)

    assert calculation_end_exclusive(
        date(2026, 8, 1),
        date(2026, 8, 31),
        now=now,
    ) == now
    assert calculation_end_exclusive(
        date(2026, 7, 1),
        date(2026, 7, 31),
        now=now,
    ) == datetime(2026, 8, 1, tzinfo=MOSCOW)


def test_volume_segments_split_continuous_stock_at_dimension_change() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    change_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=2)]
    old = _dimension_event(
        observed_at=start,
        volume_liters=Decimal("1"),
        source="wb",
        applied=False,
        fingerprint="old-wb",
    )
    new = _dimension_event(
        observed_at=change_at,
        volume_liters=Decimal("3"),
        source="wb",
        applied=True,
        fingerprint="new-wb",
    )

    segments = _volume_segments(
        movements, [old, new], start, end, legacy_volume_liters=None
    )

    assert [(left, right, held, volume) for left, right, held, volume, _ in segments] == [
        (start, change_at, 2, Decimal("1")),
        (change_at, end, 2, Decimal("3")),
    ]


def test_volume_segments_do_not_apply_later_measurement_to_earlier_stock() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    measured_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=1)]
    event = _dimension_event(
        observed_at=measured_at,
        volume_liters=Decimal("2"),
        source="manual",
        applied=True,
        fingerprint="manual-measurement",
    )

    segments = _volume_segments(
        movements, [event], start, end, legacy_volume_liters=Decimal("9")
    )

    assert [(held, volume) for _, _, held, volume, _ in segments] == [
        (1, None),
        (1, Decimal("2")),
    ]


def test_wb_observation_after_manual_measurement_does_not_change_storage_volume() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    wb_observed_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=1)]
    manual = _dimension_event(
        observed_at=start,
        volume_liters=Decimal("1"),
        source="manual",
        applied=True,
        fingerprint="manual-measurement",
    )
    wb_observation = _dimension_event(
        observed_at=wb_observed_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=False,
        fingerprint="wb-observation",
    )

    segments = _volume_segments(
        movements,
        [manual, wb_observation],
        start,
        end,
        legacy_volume_liters=None,
    )

    assert [(left, right, volume) for left, right, _, volume, _ in segments] == [
        (start, end, Decimal("1")),
    ]


def test_wb_restore_changes_open_timeline_without_recalculating_closed_period() -> None:
    closed_start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    closed_end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    wb_observed_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    restored_at = datetime(2026, 8, 5, tzinfo=MOSCOW)
    open_end = datetime(2026, 9, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=closed_start, quantity_delta=1)]
    manual = _dimension_event(
        observed_at=closed_start,
        volume_liters=Decimal("1"),
        source="manual",
        applied=False,
        fingerprint="manual-measurement",
    )
    wb_observation = _dimension_event(
        observed_at=wb_observed_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=False,
        fingerprint="wb-observation",
    )
    wb_restore = _dimension_event(
        observed_at=restored_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=True,
        fingerprint="wb-observation:restore-event",
    )

    closed_segments = _volume_segments(
        movements,
        [manual, wb_observation, wb_restore],
        closed_start,
        closed_end,
        legacy_volume_liters=None,
    )
    open_segments = _volume_segments(
        movements,
        [manual, wb_observation, wb_restore],
        closed_start,
        open_end,
        legacy_volume_liters=None,
    )

    assert [(left, right, volume) for left, right, _, volume, _ in closed_segments] == [
        (closed_start, closed_end, Decimal("1")),
    ]
    assert [(left, right, volume) for left, right, _, volume, _ in open_segments] == [
        (closed_start, restored_at, Decimal("1")),
        (restored_at, open_end, Decimal("6")),
    ]


@pytest.mark.asyncio
async def test_rebuild_and_list_cover_fractional_missing_zero_idempotency_and_scope(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Storage calculation",
            "slug": f"storage-calculation-{suffix}",
            "admin_email": f"storage-calculation-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Operational storage", "code": f"storage-{suffix}"},
    )
    assert warehouse_response.status_code == 200, warehouse_response.text
    operational_id = uuid.UUID(str(warehouse_response.json()["id"]))
    period_start, _ = previous_month()
    first_inbound = datetime.combine(
        period_start, datetime.min.time(), MOSCOW
    ) + timedelta(hours=12)
    first_outbound = first_inbound + timedelta(days=1)

    async with SessionLocal() as session:
        operational = await session.get(Warehouse, operational_id)
        assert operational is not None
        tenant_id = operational.tenant_id
        technical = Warehouse(
            tenant_id=tenant_id,
            name="FBS WB technical",
            code=f"fbs-wb-{suffix}",
            is_operational=False,
        )
        calculated_seller = Seller(tenant_id=tenant_id, name="Calculated seller")
        zero_seller = Seller(tenant_id=tenant_id, name="Zero seller")
        session.add_all([technical, calculated_seller, zero_seller])
        await session.flush()
        calculated = Product(
            tenant_id=tenant_id,
            seller_id=calculated_seller.id,
            name="Measured product",
            sku_code=f"MEASURED-{suffix}",
            volume_liters=Decimal("2"),
            dimensions_source="manual",
        )
        missing = Product(
            tenant_id=tenant_id,
            seller_id=calculated_seller.id,
            name="Missing dimensions",
            sku_code=f"MISSING-{suffix}",
        )
        technical_product = Product(
            tenant_id=tenant_id,
            seller_id=calculated_seller.id,
            name="Technical stock",
            sku_code=f"TECHNICAL-{suffix}",
            volume_liters=Decimal("10"),
        )
        session.add_all([calculated, missing, technical_product])
        await session.flush()
        operational_location = await get_or_create_sorting_location(
            session, tenant_id, operational.id
        )
        technical_location = await get_or_create_sorting_location(session, tenant_id, technical.id)
        session.add_all(
            [
                InventoryMovement(
                    tenant_id=tenant_id,
                    product_id=calculated.id,
                    seller_id=calculated_seller.id,
                    storage_location_id=operational_location.id,
                    warehouse_id=operational.id,
                    quantity_delta=3,
                    movement_type="storage_test",
                    created_at=first_inbound,
                ),
                InventoryMovement(
                    tenant_id=tenant_id,
                    product_id=calculated.id,
                    seller_id=calculated_seller.id,
                    storage_location_id=operational_location.id,
                    warehouse_id=operational.id,
                    quantity_delta=-3,
                    movement_type="storage_test",
                    created_at=first_outbound,
                ),
                InventoryMovement(
                    tenant_id=tenant_id,
                    product_id=missing.id,
                    seller_id=calculated_seller.id,
                    storage_location_id=operational_location.id,
                    warehouse_id=operational.id,
                    quantity_delta=1,
                    movement_type="storage_test",
                    created_at=first_inbound,
                ),
                InventoryMovement(
                    tenant_id=tenant_id,
                    product_id=technical_product.id,
                    seller_id=calculated_seller.id,
                    storage_location_id=technical_location.id,
                    warehouse_id=technical.id,
                    quantity_delta=100,
                    movement_type="storage_test",
                    created_at=first_inbound,
                ),
            ]
        )
        await session.commit()
        technical_id = technical.id

    body = {"year": period_start.year, "month": period_start.month}
    first_job = await async_client.post(
        "/operations/storage/measurements/rebuild",
        headers=headers,
        json=body,
    )
    second_job = await async_client.post(
        "/operations/storage/measurements/rebuild",
        headers=headers,
        json=body,
    )
    assert first_job.status_code == 202, first_job.text
    assert second_job.status_code == 202, second_job.text

    for job_id in (first_job.json()["id"], second_job.json()["id"]):
        job = await async_client.get(
            f"/operations/background-jobs/{job_id}", headers=headers
        )
        assert job.status_code == 200, job.text
        assert job.json()["status"] == "done", job.text

    listed = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": period_start.year, "month": period_start.month},
    )
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["tariff_configured"] is False
    assert {row["id"] for row in payload["warehouses"]} == {str(operational_id)}
    by_seller = {row["seller_name"]: row for row in payload["statements"]}
    assert set(by_seller) == {"Calculated seller", "Zero seller"}
    assert by_seller["Zero seller"]["measurements"] == []
    assert by_seller["Zero seller"]["total_liter_days"] == "0"
    calculated_rows = {
        row["sku"]: row for row in by_seller["Calculated seller"]["measurements"]
    }
    assert calculated_rows[f"MEASURED-{suffix}"]["liter_days"] == "6.000000"
    assert calculated_rows[f"MISSING-{suffix}"]["status"] == "missing_dimensions"
    assert by_seller["Calculated seller"]["problem_count"] == 1

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(StorageStatement.id))) == 2
        assert await session.scalar(select(func.count(StorageMeasurement.id))) == 2
        assert await session.scalar(
            select(func.count(StorageStatement.id)).where(
                StorageStatement.warehouse_id == technical_id
            )
        ) == 0

    # A rebuild is part of the background job transaction. If anything after
    # the calculation fails, rolling the job back must retain the last draft.
    extra_movement_at = first_outbound + timedelta(days=1)
    async with SessionLocal() as session:
        operational_location = await get_or_create_sorting_location(
            session, tenant_id, operational_id
        )
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                product_id=calculated.id,
                seller_id=calculated_seller.id,
                storage_location_id=operational_location.id,
                warehouse_id=operational_id,
                quantity_delta=1,
                movement_type="storage_test_after_success",
                created_at=extra_movement_at,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        await rebuild_storage_measurements(
            session,
            tenant_id,
            period_start=period_start,
        )
        changed_liter_days = await session.scalar(
            select(StorageMeasurement.liter_days).where(
                StorageMeasurement.product_id == calculated.id
            )
        )
        assert changed_liter_days != Decimal("6.000000")
        await session.rollback()

    async with SessionLocal() as session:
        preserved_liter_days = await session.scalar(
            select(StorageMeasurement.liter_days).where(
                StorageMeasurement.product_id == calculated.id
            )
        )
        assert preserved_liter_days == Decimal("6.000000")


@pytest.mark.asyncio
async def test_storage_api_rejects_future_month(async_client: AsyncClient) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Future storage",
            "slug": f"future-storage-{suffix}",
            "admin_email": f"future-storage-{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    future = datetime.now(MOSCOW).date().replace(day=1) + timedelta(days=370)

    response = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": future.year, "month": future.month},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "future_month"
