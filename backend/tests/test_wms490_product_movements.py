"""WMS-490 D2: вкладка «Движения» карточки товара — все движения одного
товара за всю историю, без периода и без лимита 366 дней. Строит их и
обогащает та же функция, что раскрытие товара в отчёте «Остатки и движения»
(`reporting_service.list_product_movements`), порциями по
`MOVEMENT_PAGE_LIMIT` (WMS-531). Новая ручка — `GET
/reports/inventory/product-movements?product_id=&page=`; существующий
`/reports/inventory/movements` не меняется."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.services.reporting_service import MOVEMENT_PAGE_LIMIT, list_product_movements
from app.services.tokens import decode_access_token


async def _context(async_client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, str, str, str]:
    suffix = str(time.time_ns())
    registered = await async_client.post("/auth/register", json={
        "organization_name": "PM History", "slug": f"pmh-{suffix}",
        "admin_email": f"pmh-{suffix}@example.com", "password": "password123",
    })
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    seller = await async_client.post("/sellers", headers=headers, json={"name": "PM seller"})
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "PMH", "code": f"pmh-{suffix}"}
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations", headers=headers, json={"code": "PMH-01"}
    )
    return headers, tenant_id, seller.json()["id"], warehouse.json()["id"], location.json()["id"]


async def _movement(
    *, tenant_id: uuid.UUID, seller_id: str, warehouse_id: str, location_id: str,
    product_id: uuid.UUID | None = None, sku: str = "PMH-SKU", name: str = "Product",
    quantity_delta: int = 1, movement_type: str = "inbound_intake",
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
            created_at=created_at or datetime(2026, 8, 1, 12, tzinfo=UTC),
        ))
        await session.commit()
        return product_id


@pytest.mark.asyncio
async def test_full_history_matches_report_for_the_same_period(
    async_client: AsyncClient,
) -> None:
    """За период, который отчёт способен показать целиком, строки нового
    запроса и раскрытия товара в `/reports/inventory/movements` совпадают."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Товар для сверки", quantity_delta=5,
        created_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
    )
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, product_id=product_id, quantity_delta=-2,
        movement_type="outbound_shipment", created_at=datetime(2026, 8, 1, 11, tzinfo=UTC),
    )

    report = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={
            "date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z",
            "product_id": str(product_id),
        },
    )
    assert report.status_code == 200, report.text
    history = await async_client.get(
        "/reports/inventory/product-movements", headers=headers,
        params={"product_id": str(product_id)},
    )
    assert history.status_code == 200, history.text
    report_rows = report.json()["rows"]
    history_rows = history.json()["rows"]
    assert len(report_rows) == 2
    assert report_rows == history_rows
    assert history.json()["total"] == 2
    assert history.json()["truncated"] is False
    assert history.json()["limit"] == MOVEMENT_PAGE_LIMIT


@pytest.mark.asyncio
async def test_full_history_includes_movements_older_than_a_year(
    async_client: AsyncClient,
) -> None:
    """Лимит 366 дней у отчёта не применяется, когда карточка запрашивает
    всю историю одного товара (без периода) — иначе давняя приёмка исчезла
    бы из «Движений», хотя владелец просил именно «все движения»."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Старый товар", quantity_delta=3,
        created_at=datetime(2020, 1, 15, 9, tzinfo=UTC),
    )
    await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, product_id=product_id, quantity_delta=4,
        created_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
    )

    history = await async_client.get(
        "/reports/inventory/product-movements", headers=headers,
        params={"product_id": str(product_id)},
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["total"] == 2
    quantities = sorted(row["quantity"] for row in body["rows"])
    assert quantities == [3, 4]
    # Новые сверху.
    assert body["rows"][0]["quantity"] == 4


@pytest.mark.asyncio
async def test_full_history_excludes_location_only_movements(
    async_client: AsyncClient,
) -> None:
    """Перемещения между ячейками/складами/тарой — расположение, не приход и
    не расход (AGENTS.md, остаток ≠ расположение) — в «Движениях» их нет."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Перекладываемый", quantity_delta=6,
    )
    for movement_type, delta in (
        ("stock_transfer_out", -6), ("stock_transfer_in", 6),
        ("warehouse_map_move", 0), ("container_reattach", 0), ("transfer", 0),
    ):
        await _movement(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            location_id=location_id, product_id=product_id, quantity_delta=delta,
            movement_type=movement_type,
        )

    history = await async_client.get(
        "/reports/inventory/product-movements", headers=headers,
        params={"product_id": str(product_id)},
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["total"] == 1
    assert [row["operation"] for row in body["rows"]] == ["Приёмка"]


@pytest.mark.asyncio
async def test_full_history_pagination_has_no_duplicates_or_gaps(
    async_client: AsyncClient,
) -> None:
    """250 движений — две порции по 200, без повторов и пропусков; сортировка
    стабильна (created_at desc, id как второй ключ, WMS-531)."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    total_count = 250
    async with SessionLocal() as session:
        product_id = uuid.uuid4()
        session.add(Product(
            id=product_id, tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
            name="Товар с историей", sku_code=f"PMH-BULK-{uuid.uuid4().hex[:6]}",
        ))
        movement_ids: list[uuid.UUID] = []
        for index in range(total_count):
            movement_id = uuid.uuid4()
            movement_ids.append(movement_id)
            session.add(InventoryMovement(
                id=movement_id, tenant_id=tenant_id, product_id=product_id,
                seller_id=uuid.UUID(seller_id), warehouse_id=uuid.UUID(warehouse_id),
                storage_location_id=uuid.UUID(location_id), quantity_delta=1,
                movement_type="inbound_intake",
                created_at=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
            ))
        await session.commit()

    seen_ids: set[str] = set()
    page = 1
    truncated = True
    total_reported = None
    pages_fetched = 0
    while truncated:
        response = await async_client.get(
            "/reports/inventory/product-movements", headers=headers,
            params={"product_id": str(product_id), "page": page},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        total_reported = body["total"]
        for row in body["rows"]:
            assert row["id"] not in seen_ids, "движение повторилось между порциями"
            seen_ids.add(row["id"])
        truncated = body["truncated"]
        pages_fetched += 1
        page += 1
        assert pages_fetched <= 3, "слишком много страниц — похоже на бесконечный цикл"

    assert total_reported == total_count
    assert pages_fetched == 2
    assert seen_ids == {str(mid) for mid in movement_ids}


@pytest.mark.asyncio
async def test_full_history_quantity_sum_matches_accumulated_stock(
    async_client: AsyncClient,
) -> None:
    """Сумма «Штук» всех строк «Движений» равна сумме проведённых изменений
    остатка — историчность не считается вторым независимым способом."""
    headers, tenant_id, seller_id, warehouse_id, location_id = await _context(async_client)
    deltas = [10, -3, 4, -1, 2]
    product_id: uuid.UUID | None = None
    for delta in deltas:
        product_id = await _movement(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            location_id=location_id, product_id=product_id, quantity_delta=delta,
            movement_type="inbound_intake" if delta > 0 else "outbound_shipment",
        )
    assert product_id is not None

    history = await async_client.get(
        "/reports/inventory/product-movements", headers=headers,
        params={"product_id": str(product_id)},
    )
    assert history.status_code == 200, history.text
    rows = history.json()["rows"]
    assert len(rows) == len(deltas)
    assert sum(row["quantity"] for row in rows) == sum(deltas)


@pytest.mark.asyncio
async def test_full_history_is_empty_for_a_foreign_tenant(async_client: AsyncClient) -> None:
    """Товар другой организации — пустой список, как у отчёта (не 404: сам
    отчёт тоже просто ничего не находит по чужому product_id)."""
    _headers_a, tenant_a, seller_a, warehouse_a, location_a = await _context(async_client)
    product_id = await _movement(
        tenant_id=tenant_a, seller_id=seller_a, warehouse_id=warehouse_a,
        location_id=location_a, name="Чужой товар", quantity_delta=9,
    )
    headers_b, *_ = await _context(async_client)

    response = await async_client.get(
        "/reports/inventory/product-movements", headers=headers_b,
        params={"product_id": str(product_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_full_history_is_empty_for_a_foreign_seller_account(
    async_client: AsyncClient,
) -> None:
    """Кабинет селлера видит только движения своих товаров — как в отчёте."""
    headers, tenant_id, seller_own_id, warehouse_id, location_id = await _context(async_client)
    other_seller = await async_client.post(
        "/sellers", headers=headers, json={"name": "Other seller"}
    )
    other_seller_id = other_seller.json()["id"]
    foreign_product_id = await _movement(
        tenant_id=tenant_id, seller_id=other_seller_id, warehouse_id=warehouse_id,
        location_id=location_id, name="Товар другого селлера", quantity_delta=8,
    )

    suffix = str(time.time_ns())
    seller_email = f"pmh-seller-{suffix}@example.com"
    created = await async_client.post(
        "/auth/seller-accounts", headers=headers,
        json={"seller_id": seller_own_id, "email": seller_email, "password": "password123"},
    )
    assert created.status_code == 201, created.text
    login = await async_client.post(
        "/auth/login", json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await async_client.get(
        "/reports/inventory/product-movements", headers=seller_headers,
        params={"product_id": str(foreign_product_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_product_movements_full_history_requires_a_product(
    db_session: AsyncSession,
) -> None:
    """Сервисная гарантия: без периода нельзя раскрыть вид движения — там
    были бы миллионы строк, и это не то, что просил владелец."""
    with pytest.raises(ValueError, match="requires a product"):
        await list_product_movements(
            db_session, uuid.uuid4(), operation="Приёмка",
            date_from=None, date_to=None,
        )


@pytest.mark.asyncio
async def test_list_product_movements_rejects_a_partial_period(
    db_session: AsyncSession,
) -> None:
    """Половинчатый период (только одна из дат) — ошибка, а не тихий переход
    в режим «вся история»."""
    with pytest.raises(ValueError, match="together"):
        await list_product_movements(
            db_session, uuid.uuid4(), product_id=uuid.uuid4(),
            date_from=datetime(2026, 8, 1, tzinfo=UTC), date_to=None,
        )
