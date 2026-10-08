"""WMS-692: просроченные заказы Wildberries остаются в «Новых», группа expired удалена.

Проверки из docs/requirements/WMS-692.md, раздел 5 (классы «навсегда» и «разово').
Проверка C1 лежит в test_fbs_worklist_query_count.py, тест
test_fbs_worklist_keeps_overdue_wb_order_in_new.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_NEW,
    FbsOrder,
)
from app.models.inventory_balance import InventoryBalance
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID
from tests.test_fbs_manual_pick import _manual_pick, _select_manual_location
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock

WORKLIST_URL = "/operations/fbs-orders/worklist"


def _overdue() -> datetime:
    return datetime.now(tz=UTC) - timedelta(hours=1)


async def _set_deadline(order_id: uuid.UUID, deadline: datetime) -> None:
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.deadline_at = deadline
        await session.commit()


async def _worklist_ids(
    async_client: AsyncClient, headers: dict[str, str], **params: str | int
) -> set[str]:
    resp = await async_client.get(WORKLIST_URL, headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return {item["id"] for item in resp.json()["items"]}


@pytest.mark.asyncio
async def test_wb_future_and_ozon_overdue_orders_both_stay_in_new(
    async_client: AsyncClient,
) -> None:
    """C2 (R1, навсегда): WB со сроком в будущем и Ozon с прошедшим сроком оба есть в «Новых»."""
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=2
    )
    wb_future_id, ozon_overdue_id = order_ids
    async with SessionLocal() as session:
        ozon_order = await session.get(FbsOrder, ozon_overdue_id)
        assert ozon_order is not None
        ozon_order.marketplace = "ozon"
        ozon_order.external_order_id = f"ozon-692-{ozon_overdue_id.hex[:10]}"
        ozon_order.deadline_at = _overdue()
        await session.commit()

    ids = await _worklist_ids(
        async_client, headers, seller_id=str(seller_id), status_group="new"
    )
    assert ids == {str(wb_future_id), str(ozon_overdue_id)}


@pytest.mark.asyncio
async def test_overdue_only_wb_warehouse_stays_in_new_filter(
    async_client: AsyncClient,
) -> None:
    """C3 (R2, навсегда): склад WB, где есть только просроченный заказ «Новых», в фильтре есть."""
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    await _set_deadline(order_ids[0], _overdue())

    resp = await async_client.get(
        WORKLIST_URL,
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "new"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(DEFAULT_WB_WAREHOUSE_ID) in {option["id"] for option in body["warehouse_options"]}
    assert {item["id"] for item in body["items"]} == {str(order_ids[0])}


@pytest.mark.asyncio
async def test_expired_status_group_is_removed(async_client: AsyncClient) -> None:
    """C7 (R6, навсегда): группа status_group=expired больше не существует и отвечает 400."""
    headers, seller_id, _, _, _, _order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    resp = await async_client.get(
        WORKLIST_URL,
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "expired"},
    )
    assert resp.status_code == 400, resp.text
    assert "invalid_status_group" in resp.text


@pytest.mark.asyncio
async def test_overdue_wb_order_is_selectable_and_passes_supply_preflight(
    async_client: AsyncClient,
) -> None:
    """C8 (R7, навсегда): просроченный WB-заказ выбирается без блокера deadline_passed.

    Предпроверка поставки (validate_supply_composition) общая для создания поставки,
    добавления в существующую поставку и самой предпроверки, поэтому проверяем её.
    """
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    order_id = order_ids[0]
    await _set_deadline(order_id, _overdue())

    # Предпроверку проверяем первой: она не зависит от списка «Новых» (R1).
    preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={"order_ids": [str(order_id)], "planned_delivery_type": "warehouse_sc"},
    )
    assert preflight.status_code == 200, preflight.text
    assert "deadline_passed" not in {issue["code"] for issue in preflight.json()["issues"]}
    assert preflight.json()["compatible"] is True

    page = await async_client.get(
        WORKLIST_URL,
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "new"},
    )
    assert page.status_code == 200, page.text
    item = page.json()["items"][0]
    assert item["id"] == str(order_id)
    assert item["selection_blockers"] == []


@pytest.mark.asyncio
async def test_cancelled_and_defect_orders_stay_only_in_cancelled_group(
    async_client: AsyncClient,
) -> None:
    """C6 (R5, навсегда): отмена и брак видны только в «Отменённые», статус не меняется.

    Свежий заказ NEW здесь нужен, чтобы утечка статусов в «Отменённые» стала видна.
    """
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=3
    )
    fresh_id, cancelled_id, defect_id = order_ids
    async with SessionLocal() as session:
        for order_id, status in (
            (cancelled_id, FBS_ORDER_STATUS_CANCELLED),
            (defect_id, FBS_ORDER_STATUS_DEFECT),
        ):
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.status = status
            order.deadline_at = _overdue()
        await session.commit()

    new_ids = await _worklist_ids(
        async_client, headers, seller_id=str(seller_id), status_group="new"
    )
    assert new_ids == {str(fresh_id)}
    cancelled_ids = await _worklist_ids(
        async_client, headers, seller_id=str(seller_id), status_group="cancelled"
    )
    assert cancelled_ids == {str(cancelled_id), str(defect_id)}

    async with SessionLocal() as session:
        rows = (
            await session.scalars(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
        ).all()
        statuses = {row.id: row.status for row in rows}
    assert statuses[fresh_id] == FBS_ORDER_STATUS_NEW
    assert statuses[cancelled_id] == FBS_ORDER_STATUS_CANCELLED
    assert statuses[defect_id] == FBS_ORDER_STATUS_DEFECT


@pytest.mark.asyncio
async def test_manual_pick_of_overdue_wb_order_keeps_stock_quantity(
    async_client: AsyncClient,
) -> None:
    """C9 (R8, навсегда), часть подбора: подбор просроченного WB-заказа не списывает остаток.

    Остаток товара — сумма quantity по всем ячейкам и сортировке. Подбор переносит штуку
    из ячейки на сортировку, поэтому строка ячейки уменьшается, а остаток не меняется.
    Упаковка и печать этим тестом не покрыты, см. отчёт тестировщика.
    """
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-692-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-692-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=-1))],
        barcode=barcode,
    )

    async def _stock_quantity() -> int:
        async with SessionLocal() as session:
            total = await session.scalar(
                select(func.sum(InventoryBalance.quantity)).where(
                    InventoryBalance.product_id == product_id,
                )
            )
            return int(total or 0)

    stock_before = await _stock_quantity()
    selected = await _select_manual_location(async_client, headers, supply_id, location_id)
    assert selected.status_code == 200, selected.text
    picked = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=product_id,
        order_id=order_ids[0],
        idempotency_key=str(uuid.uuid4()),
    )
    assert picked.status_code == 200, picked.text
    assert picked.json()["progress"]["picked"] == 1
    assert await _stock_quantity() == stock_before == 2


@pytest.mark.asyncio
async def test_overdue_order_of_other_client_is_not_listed(
    async_client: AsyncClient,
) -> None:
    """C10 (R8, навсегда): просроченный заказ другого клиента не попадает в «Новые» текущего.

    Другой селлер внутри одного клиента этим тестом не покрыт, см. отчёт тестировщика.
    """
    headers_a, seller_a, _, _, _, order_a = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    # У другого клиента два заказа: свежий (ловит утечку уже сейчас) и просроченный
    # (ловит утечку просроченных после WMS-692).
    _headers_b, _seller_b, _, _, _, order_b = await _setup_ff_admin_with_stock(
        async_client, order_count=2
    )
    fresh_b_id, overdue_b_id = order_b
    await _set_deadline(overdue_b_id, _overdue())

    scoped = await _worklist_ids(
        async_client, headers_a, seller_id=str(seller_a), status_group="new"
    )
    assert scoped == {str(order_a[0])}
    unscoped = await _worklist_ids(async_client, headers_a, status_group="new")
    assert str(fresh_b_id) not in unscoped
    assert str(overdue_b_id) not in unscoped


@pytest.mark.asyncio
async def test_tsd_working_queue_still_lists_overdue_wb_order(
    async_client: AsyncClient,
) -> None:
    """C11 (R8, навсегда): очередь ТСД срок не учитывает и просроченный заказ в ней остаётся."""
    headers, _seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    await _set_deadline(order_ids[0], _overdue())

    ids = await _worklist_ids(
        async_client, headers, marketplace="wb", status_group="tsd_working"
    )
    assert ids == {str(order_ids[0])}


@pytest.mark.asyncio
async def test_new_group_returns_all_141_orders_without_truncation(
    async_client: AsyncClient,
) -> None:
    """C15 (Q2, разово): клиент с 141 новым WB-заказом (37 просроченных) видит все 141.

    Число взято из SELECT модератора (раздел 1.1 постановки). Экран запрашивает 500 строк,
    поэтому запрос идёт с limit=500, как в интерфейсе, без подгрузки следующих страниц.
    """
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=141
    )
    overdue_ids = order_ids[:37]
    async with SessionLocal() as session:
        rows = (
            await session.scalars(select(FbsOrder).where(FbsOrder.id.in_(overdue_ids)))
        ).all()
        for row in rows:
            row.deadline_at = _overdue()
        await session.commit()

    resp = await async_client.get(
        WORKLIST_URL,
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "new", "limit": 500},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_cursor"] is None
    returned = {item["id"] for item in body["items"]}
    assert len(returned) == 141
    assert {str(order_id) for order_id in overdue_ids} <= returned
