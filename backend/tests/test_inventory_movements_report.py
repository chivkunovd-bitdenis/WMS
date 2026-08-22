from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inventory_movement import (
    MOVEMENT_TYPE_FBS_SHIPMENT,
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.services.tokens import decode_access_token

# fbs_order_pick — raw movement_type literal from fbs_picking_service.scan_pick_product,
# never promoted to a module constant (see app/models/inventory_movement.py).
_FBS_ORDER_PICK = "fbs_order_pick"


def _tenant_id(token: str) -> uuid.UUID:
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


async def _insert_movement(
    *,
    tenant_id: uuid.UUID,
    product_id: str,
    storage_location_id: str,
    seller_id: str,
    warehouse_id: str,
    quantity_delta: int,
    movement_type: str,
    created_at: datetime,
) -> None:
    async with SessionLocal() as session:
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                product_id=uuid.UUID(product_id),
                storage_location_id=uuid.UUID(storage_location_id),
                seller_id=uuid.UUID(seller_id),
                warehouse_id=uuid.UUID(warehouse_id),
                quantity_delta=quantity_delta,
                movement_type=movement_type,
                created_at=created_at,
            )
        )
        await session.commit()


def _group(
    rows: list[dict[str, Any]], product_id: str
) -> dict[str, dict[str, Any]]:
    row = next(r for r in rows if r["product_id"] == product_id)
    return {g["key"]: g for g in row["groups"]}


@pytest.mark.asyncio
async def test_inventory_movements_summary_groups_and_period_filter(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Report Co",
            "slug": f"report-co-{suffix}",
            "admin_email": f"report-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = _tenant_id(token)

    seller_a = await async_client.post("/sellers", headers=h, json={"name": "Seller A"})
    seller_b = await async_client.post("/sellers", headers=h, json={"name": "Seller B"})
    sid_a = seller_a.json()["id"]
    sid_b = seller_b.json()["id"]

    wh1 = await async_client.post(
        "/warehouses", headers=h, json={"name": "WH1", "code": f"wh1-{suffix}"}
    )
    wid1 = wh1.json()["id"]
    wh2 = await async_client.post(
        "/warehouses", headers=h, json={"name": "WH2", "code": f"wh2-{suffix}"}
    )
    wid2 = wh2.json()["id"]

    loc1 = await async_client.post(
        f"/warehouses/{wid1}/locations", headers=h, json={"code": "A1"}
    )
    loc2 = await async_client.post(
        f"/warehouses/{wid1}/locations", headers=h, json={"code": "A2"}
    )
    loc_wh2 = await async_client.post(
        f"/warehouses/{wid2}/locations", headers=h, json={"code": "B1"}
    )
    lid1 = loc1.json()["id"]
    lid2 = loc2.json()["id"]
    lid_wh2 = loc_wh2.json()["id"]

    p1 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Report Product 1",
            "sku_code": f"RP1-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid_a,
        },
    )
    p2 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Report Product 2",
            "sku_code": f"RP2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid_b,
        },
    )
    pid1 = p1.json()["id"]
    pid2 = p2.json()["id"]

    now = datetime.now(UTC)
    in_window = now - timedelta(hours=1)
    outside_window = now - timedelta(days=30)

    # P1 (seller A, warehouse 1): приёмка +10, перемещение 3 -> 3, FBS-сборка/отгрузка +2/-2.
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid1,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=10,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        created_at=in_window,
    )
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid1,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=-3,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        created_at=in_window,
    )
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid2,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=3,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
        created_at=in_window,
    )
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid2,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=2,
        movement_type=_FBS_ORDER_PICK,
        created_at=in_window,
    )
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid2,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=-2,
        movement_type=MOVEMENT_TYPE_FBS_SHIPMENT,
        created_at=in_window,
    )
    # Вне периода отчёта — не должно попасть в суммы.
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid1,
        seller_id=sid_a,
        warehouse_id=wid1,
        quantity_delta=999,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        created_at=outside_window,
    )
    # На другом складе — должно исключаться фильтром warehouse_id=wid1.
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid1,
        storage_location_id=lid_wh2,
        seller_id=sid_a,
        warehouse_id=wid2,
        quantity_delta=4,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        created_at=in_window,
    )

    # P2 (seller B): расход на МП.
    await _insert_movement(
        tenant_id=tenant_id,
        product_id=pid2,
        storage_location_id=lid1,
        seller_id=sid_b,
        warehouse_id=wid1,
        quantity_delta=-5,
        movement_type=MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
        created_at=in_window,
    )

    date_from = (now - timedelta(days=1)).isoformat()
    date_to = (now + timedelta(days=1)).isoformat()

    res = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": date_from, "date_to": date_to},
    )
    assert res.status_code == 200, res.text
    rows = res.json()

    g1 = _group(rows, pid1)
    # 10 (осн. склад) + 4 (склад 2, фильтр по складу ещё не применён) = 14;
    # +999 из outside_window исключён фильтром по периоду.
    assert g1["intake"]["in_qty"] == 14
    assert g1["intake"]["label"] == "Приёмка"
    assert g1["transfer"]["in_qty"] == 3
    assert g1["transfer"]["out_qty"] == 3
    assert g1["transfer"]["label"] == "Перемещение"
    assert g1["fbs"]["in_qty"] == 2
    assert g1["fbs"]["out_qty"] == 2
    assert g1["fbs"]["label"] == "FBS"

    row1 = next(r for r in rows if r["product_id"] == pid1)
    # intake (оба склада) 14 + transfer_in 3 + fbs pick 2 = 19 total_in;
    # transfer_out 3 + fbs shipment 2 = 5 total_out.
    assert row1["total_in"] == 19
    assert row1["total_out"] == 5
    assert row1["net"] == 14
    assert row1["sku_code"] == f"RP1-{suffix}"
    assert row1["product_name"] == "Report Product 1"
    assert row1["seller_name"] == "Seller A"

    g2 = _group(rows, pid2)
    assert g2["mp_unload"]["out_qty"] == 5
    assert g2["mp_unload"]["label"] == "Отгрузка на МП"
    row2 = next(r for r in rows if r["product_id"] == pid2)
    assert row2["total_out"] == 5

    # Технических имён вроде "stock_transfer_in" в ответе быть не должно.
    body_text = res.text
    assert "stock_transfer_in" not in body_text
    assert "fbs_order_pick" not in body_text
    assert "marketplace_unload" not in body_text

    # Фильтр по складу: движение в wid2 (+4) не должно попадать в приёмку P1.
    res_wh = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": date_from, "date_to": date_to, "warehouse_id": wid1},
    )
    assert res_wh.status_code == 200, res_wh.text
    g1_wh = _group(res_wh.json(), pid1)
    assert g1_wh["intake"]["in_qty"] == 10

    # Фильтр по селлеру: только продукт B.
    res_seller = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": date_from, "date_to": date_to, "seller_id": sid_b},
    )
    assert res_seller.status_code == 200, res_seller.text
    seller_rows = res_seller.json()
    assert {r["product_id"] for r in seller_rows} == {pid2}

    # Поиск по товару.
    res_search = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": date_from, "date_to": date_to, "search": f"RP2-{suffix}"},
    )
    assert res_search.status_code == 200, res_search.text
    search_rows = res_search.json()
    assert {r["product_id"] for r in search_rows} == {pid2}

    # Период, который полностью до всех движений — пусто.
    far_past_from = (now - timedelta(days=400)).isoformat()
    far_past_to = (now - timedelta(days=90)).isoformat()
    res_empty = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": far_past_from, "date_to": far_past_to},
    )
    assert res_empty.status_code == 200
    assert res_empty.json() == []

    # date_to <= date_from -> 422.
    res_bad = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=h,
        params={"date_from": date_to, "date_to": date_from},
    )
    assert res_bad.status_code == 422


@pytest.mark.asyncio
async def test_inventory_movements_summary_seller_scope_forbidden(
    async_client: AsyncClient,
) -> None:
    """Селлер, пробующий override чужим seller_id, получает 403 — так же, как на
    существующем /operations/inventory-balances/summary (общий assert_inventory_read_access).
    """
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Report Scope Co",
            "slug": f"report-scope-{suffix}",
            "admin_email": f"report-scope-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller = await async_client.post("/sellers", headers=h, json={"name": "Scoped Seller"})
    sid = seller.json()["id"]
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=h,
        json={
            "seller_id": sid,
            "email": f"scoped-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert acc.status_code in (200, 201)
    login = await async_client.post(
        "/auth/login",
        json={"email": f"scoped-{suffix}@example.com", "password": "password123"},
    )
    seller_token = str(login.json()["access_token"])
    sh = {"Authorization": f"Bearer {seller_token}"}

    now = datetime.now(UTC)
    date_from = (now - timedelta(days=1)).isoformat()
    date_to = (now + timedelta(days=1)).isoformat()

    other_seller = await async_client.post("/sellers", headers=h, json={"name": "Other Seller"})
    other_sid = other_seller.json()["id"]

    forbidden = await async_client.get(
        "/operations/inventory-movements/summary",
        headers=sh,
        params={"date_from": date_from, "date_to": date_to, "seller_id": other_sid},
    )
    assert forbidden.status_code == 403
