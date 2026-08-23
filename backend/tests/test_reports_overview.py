from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services.tokens import decode_access_token


def _tenant_id(token: str) -> uuid.UUID:
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


async def _seed_movement(
    *, tenant_id: uuid.UUID, product_id: str, seller_id: str, warehouse_id: str,
    storage_location_id: str, quantity_delta: int, created_at: datetime,
    transfer_group_id: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(InventoryMovement(
            tenant_id=tenant_id, product_id=uuid.UUID(product_id), seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id),
            storage_location_id=uuid.UUID(storage_location_id),
            quantity_delta=quantity_delta, movement_type="test_movement", created_at=created_at,
            transfer_group_id=transfer_group_id,
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_reports_overview_rejects_period_longer_than_366_days(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Reports",
            "slug": f"reports-{suffix}",
            "admin_email": f"reports-{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    response = await async_client.get(
        "/reports/overview",
        headers=headers,
        params={"date_from": "2025-01-01T00:00:00Z", "date_to": "2026-01-03T00:00:00Z"},
    )
    assert response.status_code == 422
    assert "366" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reports_overview_requires_authentication(async_client: AsyncClient) -> None:
    response = await async_client.get(
        "/reports/overview",
        params={"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reports_overview_uses_moscow_half_open_dates_and_fills_daily_gaps(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Overview report", "slug": f"overview-{suffix}",
        "admin_email": f"overview-{suffix}@example.com", "password": "password123",
    })
    token = str(registered.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = _tenant_id(token)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    seller_id = seller.json()["id"]
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Main", "code": f"main-{suffix}"}
    )
    warehouse_id = warehouse.json()["id"]
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations", headers=headers, json={"code": "A-01"}
    )
    location_id = location.json()["id"]
    product = await async_client.post("/products", headers=headers, json={
        "name": "Overview product", "sku_code": f"OV-{suffix}", "seller_id": seller_id,
        "length_mm": 1, "width_mm": 1, "height_mm": 1,
    })
    product_id = product.json()["id"]
    await _seed_movement(
        tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
        warehouse_id=warehouse_id, storage_location_id=location_id, quantity_delta=7,
        created_at=datetime(2026, 8, 1, 21, 30, tzinfo=UTC),
    )
    await _seed_movement(
        tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
        warehouse_id=warehouse_id, storage_location_id=location_id, quantity_delta=-4,
        created_at=datetime(2026, 8, 4, 20, 59, 59, 900000, tzinfo=UTC),
    )
    await _seed_movement(
        tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
        warehouse_id=warehouse_id, storage_location_id=location_id, quantity_delta=-40,
        created_at=datetime(2026, 8, 4, 21, 0, tzinfo=UTC),
    )
    transfer_group = uuid.uuid4()
    await _seed_movement(
        tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
        warehouse_id=warehouse_id, storage_location_id=location_id, quantity_delta=100,
        created_at=datetime(2026, 8, 2, 12, tzinfo=UTC), transfer_group_id=transfer_group,
    )
    async with SessionLocal() as session:
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=uuid.UUID(product_id),
            storage_location_id=uuid.UUID(location_id), quantity=23,
        ))
        old_success = datetime.now(UTC) - timedelta(hours=2)
        session.add_all(
            [
                BackgroundJob(
                    tenant_id=tenant_id,
                    job_type="wildberries_cards_sync",
                    status="done",
                    payload_json={"seller_id": seller_id},
                    finished_at=old_success,
                ),
                BackgroundJob(
                    tenant_id=tenant_id,
                    job_type="wildberries_cards_sync",
                    status="failed",
                    payload_json={"seller_id": seller_id},
                    finished_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()

    response = await async_client.get("/reports/overview", headers=headers, params={
        "date_from": "2026-08-02T00:00:00", "date_to": "2026-08-05T00:00:00",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == 23
    assert body["in_qty"] == 7
    assert body["out_qty"] == 4
    assert body["comparison"] == {"previous_out_qty": 0, "change_percent": None, "change": 4}
    assert body["daily"] == [
        {"date": "2026-08-02", "in_qty": 7, "out_qty": 0, "previous_out_qty": 0},
        {"date": "2026-08-03", "in_qty": 0, "out_qty": 0, "previous_out_qty": 0},
        {"date": "2026-08-04", "in_qty": 0, "out_qty": 4, "previous_out_qty": 0},
    ]
    assert body["date_from"] == "2026-08-01T21:00:00+00:00"
    assert body["date_to"] == "2026-08-04T21:00:00+00:00"
    assert body["source_freshness"]["is_stale"] is True
    assert datetime.fromisoformat(body["source_freshness"]["last_updated_at"]) == old_success
    assert body["warnings"][0]["code"] == "wildberries_stale"
    assert body["generated_at"]


@pytest.mark.asyncio
async def test_reports_overview_counts_internal_transfer_only_for_selected_warehouse(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Overview transfer", "slug": f"overview-transfer-{suffix}",
        "admin_email": f"overview-transfer-{suffix}@example.com", "password": "password123",
    })
    token = str(registered.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = _tenant_id(token)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    seller_id = seller.json()["id"]
    product = await async_client.post("/products", headers=headers, json={
        "name": "Transfer product", "sku_code": f"TR-{suffix}", "seller_id": seller_id,
        "length_mm": 1, "width_mm": 1, "height_mm": 1,
    })
    product_id = product.json()["id"]

    warehouse_ids: list[str] = []
    location_ids: list[str] = []
    for index in (1, 2):
        warehouse = await async_client.post("/warehouses", headers=headers, json={
            "name": f"Warehouse {index}", "code": f"transfer-{index}-{suffix}",
        })
        warehouse_ids.append(warehouse.json()["id"])
        location = await async_client.post(
            f"/warehouses/{warehouse_ids[-1]}/locations",
            headers=headers,
            json={"code": f"A-{index}"},
        )
        location_ids.append(location.json()["id"])

    transfer_group = uuid.uuid4()
    for warehouse_id, location_id, quantity_delta in (
        (warehouse_ids[0], location_ids[0], -5),
        (warehouse_ids[1], location_ids[1], 5),
    ):
        await _seed_movement(
            tenant_id=tenant_id,
            product_id=product_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            storage_location_id=location_id,
            quantity_delta=quantity_delta,
            created_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
            transfer_group_id=transfer_group,
        )

    params = {
        "date_from": "2026-08-01T00:00:00Z",
        "date_to": "2026-08-03T00:00:00Z",
    }
    all_warehouses = await async_client.get(
        "/reports/overview", headers=headers, params=params,
    )
    selected_warehouse = await async_client.get(
        "/reports/overview",
        headers=headers,
        params={**params, "warehouse_id": warehouse_ids[0]},
    )

    assert all_warehouses.status_code == 200
    assert all_warehouses.json()["in_qty"] == 0
    assert all_warehouses.json()["out_qty"] == 0
    assert all_warehouses.json()["daily"] == []
    assert selected_warehouse.status_code == 200
    assert selected_warehouse.json()["in_qty"] == 0
    assert selected_warehouse.json()["out_qty"] == 5
    assert selected_warehouse.json()["daily"][0] == {
        "date": "2026-08-01",
        "in_qty": 0,
        "out_qty": 5,
        "previous_out_qty": 0,
    }


@pytest.mark.asyncio
async def test_reports_overview_seller_scope_overrides_requested_seller(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Overview scope", "slug": f"overview-scope-{suffix}",
        "admin_email": f"overview-scope-{suffix}@example.com", "password": "password123",
    })
    admin_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    own_seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Own"})
    other_seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Other"}
    )
    account = await async_client.post("/auth/seller-accounts", headers=admin_headers, json={
        "seller_id": own_seller.json()["id"],
        "email": f"own-{suffix}@example.com",
        "password": "password123",
    })
    assert account.status_code == 201
    login = await async_client.post("/auth/login", json={
        "email": f"own-{suffix}@example.com", "password": "password123",
    })
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await async_client.get("/reports/overview", headers=seller_headers, params={
        "date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z",
        "seller_id": other_seller.json()["id"],
    })
    assert response.status_code == 200
    assert response.json()["current_balance"] == 0
