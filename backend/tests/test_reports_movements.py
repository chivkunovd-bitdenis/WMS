"""Третий уровень отчёта «Остатки и движения»: сами движения за период."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.services.tokens import decode_access_token


async def _context(async_client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, str, str, str]:
    suffix = str(time.time_ns())
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Movements", "slug": f"mv-{suffix}",
        "admin_email": f"mv-{suffix}@example.com", "password": "password123",
    })
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Movements seller"})
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "MV", "code": f"mv-{suffix}"}
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations", headers=headers, json={"code": "MV-01"}
    )
    return headers, tenant_id, seller.json()["id"], warehouse.json()["id"], location.json()["id"]


async def _movement(
    *, tenant_id: uuid.UUID, seller_id: str, warehouse_id: str, location_id: str,
    product_id: uuid.UUID | None = None, sku: str = "MV-SKU", name: str = "Moved product",
    quantity_delta: int = 1, movement_type: str = "inbound_intake",
    intake_line_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        product_id = product_id or uuid.uuid4()
        if await session.get(Product, product_id) is None:
            session.add(Product(
                id=product_id, tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
                name=name, sku_code=f"{sku}-{uuid.uuid4().hex[:6]}",
            ))
        session.add(InventoryMovement(
            tenant_id=tenant_id, product_id=product_id, seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id), storage_location_id=uuid.UUID(location_id),
            quantity_delta=quantity_delta, movement_type=movement_type,
            inbound_intake_line_id=intake_line_id,
            created_at=created_at or datetime(2026, 8, 1, 12, tzinfo=UTC),
        ))
        await session.commit()
        return product_id


PERIOD = {"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"}


@pytest.mark.asyncio
async def test_movements_of_one_product_carry_name_and_document(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Первый товар", quantity_delta=5,
    )
    response = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "product_id": str(product_id)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["truncated"] is False
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["operation"] == "Приёмка"
    assert row["quantity"] == 5
    assert row["product_name"] == "Первый товар"


@pytest.mark.asyncio
async def test_movements_can_be_opened_by_operation_group(async_client: AsyncClient) -> None:
    """В группировке «по видам движения» третий уровень раньше был недоступен.

    Ручка требовала товар, а у строки «Приёмка» товара нет — она про десяток
    разных. Теперь раскрыть можно и вид движения.
    """
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Приехавший", quantity_delta=3,
        movement_type="inbound_intake",
    )
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Уехавший", quantity_delta=-2,
        movement_type="outbound_shipment",
    )

    response = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "operation": "Приёмка"},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["rows"]
    assert [row["operation"] for row in rows] == ["Приёмка"]
    assert rows[0]["product_name"] == "Приехавший"


@pytest.mark.asyncio
async def test_movements_of_a_return_are_not_filed_under_intake(
    async_client: AsyncClient,
) -> None:
    """Возврат приезжает движением приёмки, но это отдельный вид работы."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    async with SessionLocal() as session:
        request = InboundIntakeRequest(
            tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id), status="done",
            operation_type="return", document_number="RET-1",
        )
        session.add(request)
        await session.flush()
        product = Product(
            tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
            name="Вернувшийся", sku_code=f"RET-{uuid.uuid4().hex[:6]}",
        )
        session.add(product)
        await session.flush()
        line = InboundIntakeLine(
            request_id=request.id, product_id=product.id,
            expected_qty=1, actual_qty=1, posted_qty=1,
        )
        session.add(line)
        await session.commit()
        line_id, product_id = line.id, product.id

    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, product_id=product_id, quantity_delta=1,
        movement_type="inbound_intake", intake_line_id=line_id,
    )

    returns = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "operation": "Возврат"},
    )
    assert returns.status_code == 200, returns.text
    assert [row["operation"] for row in returns.json()["rows"]] == ["Возврат"]

    intakes = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "operation": "Приёмка"},
    )
    assert intakes.json()["rows"] == []


@pytest.mark.asyncio
async def test_movements_say_when_the_list_is_cut(async_client: AsyncClient) -> None:
    """Обрезанный список обязан признаваться: по нему не сходятся итоги."""
    from app.services.reporting_service import list_product_movements

    _headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = uuid.uuid4()
    for _ in range(3):
        await _movement(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            location_id=location_id, product_id=product_id, quantity_delta=1,
        )
    async with SessionLocal() as session:
        rows, truncated = await list_product_movements(
            session, tenant_id, product_id=product_id,
            date_from=datetime(2026, 8, 1, tzinfo=UTC),
            date_to=datetime(2026, 8, 2, tzinfo=UTC),
            limit=2,
        )
    assert len(rows) == 2
    assert truncated is True


@pytest.mark.asyncio
async def test_movements_require_a_product_or_an_operation(async_client: AsyncClient) -> None:
    headers, *_ = await _context(async_client)
    response = await async_client.get(
        "/reports/inventory/movements", headers=headers, params=PERIOD
    )
    assert response.status_code == 422
