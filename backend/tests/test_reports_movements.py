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


@pytest.mark.asyncio
@pytest.mark.parametrize("has_recipe_ids", [True, False])
async def test_ozon_report_links_exact_recipe_movement_ids_only(
    async_client: AsyncClient, has_recipe_ids: bool,
) -> None:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger

    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_ids = [await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, quantity_delta=5,
    ) for _ in range(2)]
    movement_ids = [uuid.uuid4() for _ in range(4)]
    async with SessionLocal() as session:
        order = FbsOrder(
            tenant_id=tenant_id, seller_id=uuid.UUID(seller_id), marketplace="ozon",
            wb_order_id=-812345, external_order_id="ORDER-OZON-RECIPE",
            product_id=product_ids[0], warehouse_id=uuid.UUID(warehouse_id),
            created_at_wb=datetime(2026, 8, 1, tzinfo=UTC),
            deadline_at=datetime(2026, 8, 2, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(order)
        await session.flush()
        # Two products and repeated source/product in the same second. The
        # fourth movement is another operation and must not be guessed into order.
        for index, movement_id in enumerate(movement_ids):
            session.add(InventoryMovement(
                id=movement_id, tenant_id=tenant_id,
                product_id=product_ids[index % 2], seller_id=uuid.UUID(seller_id),
                warehouse_id=uuid.UUID(warehouse_id),
                storage_location_id=uuid.UUID(location_id), quantity_delta=-1,
                movement_type="fbs_shipment", created_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
            ))
        await session.flush()
        session.add(FbsShipmentReversalLedger(
            tenant_id=tenant_id, fbs_order_id=order.id, product_id=product_ids[0],
            storage_location_id=uuid.UUID(location_id), quantity=3,
            shipment_movement_id=movement_ids[0],
            ozon_positions_json=[{
                "product_id": str(product_ids[index % 2]),
                "storage_location_id": location_id, "quantity": 1,
                **({"movement_id": str(movement_id)} if has_recipe_ids else {}),
            } for index, movement_id in enumerate(movement_ids[:3])],
        ))
        await session.commit()
    response = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "operation": "FBS"},
    )
    assert response.status_code == 200, response.text
    documents = {row["id"]: row["document"] for row in response.json()["rows"]}
    expected = movement_ids[:3] if has_recipe_ids else movement_ids[:1]
    for movement_id in expected:
        assert documents[str(movement_id)]["number"] == "Заказ ORDER-OZON-RECIPE"
    for movement_id in set(movement_ids) - set(expected):
        assert documents[str(movement_id)] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("search", ["OZON-ONLY-OFFER", "OZON-ONLY-SKU"])
async def test_ozon_identity_search_has_one_scope_for_rows_overview_and_csv(
    async_client: AsyncClient, search: str,
) -> None:
    from app.models.inventory_balance import InventoryBalance
    from app.models.product_marketplace_link import ProductMarketplaceLink

    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, quantity_delta=7,
    )
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, product_id=product_id, quantity_delta=-2,
    )
    # An unrelated product must not inflate search totals.
    unrelated_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, quantity_delta=100,
    )
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, product_id=product_id, quantity_delta=-3,
        created_at=datetime(2026, 7, 31, 12, tzinfo=UTC),
    )
    async with SessionLocal() as session:
        session.add(ProductMarketplaceLink(
            tenant_id=tenant_id, seller_id=uuid.UUID(seller_id), product_id=product_id,
            marketplace="ozon", external_offer_id="OZON-ONLY-OFFER",
            external_sku="OZON-ONLY-SKU", is_active=True,
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id,
            storage_location_id=uuid.UUID(location_id), quantity=15,
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=unrelated_id,
            storage_location_id=uuid.UUID(location_id), quantity=100,
        ))
        await session.commit()
    query = {**PERIOD, "search": search}
    response = await async_client.get("/reports/overview", headers=headers, params=query)
    assert response.status_code == 200, response.text
    overview = response.json()
    assert (overview["in_qty"], overview["out_qty"]) == (7, 2)
    assert overview["current_balance"] == 15
    assert overview["opening_balance"] == 10
    assert overview["comparison"]["previous_out_qty"] == 3
    for grouping in ("seller", "product", "operation"):
        response = await async_client.get(
            "/reports/inventory", headers=headers, params={**query, "group_by": grouping},
        )
        assert response.status_code == 200, response.text
        assert response.json()["rows"]
        if grouping == "product":
            assert [row["product_id"] for row in response.json()["rows"]] == [str(product_id)]
        if grouping == "seller":
            assert response.json()["rows"][0]["current_balance"] == 15
    csv = await async_client.get(
        "/reports/inventory/export.csv", headers=headers, params={**query, "group_by": "product"},
    )
    assert csv.status_code == 200, csv.text
    assert "Moved product" in csv.text
