"""Подбор снимает товар из конкретной тары, а не «откуда-нибудь из ячейки».

Владелец 29.08.2026: «я же просил на подборе снимать из любой тары товар».
Остаток по таре в `inventory_balances` лежал с самого начала — у строки есть
`container_kind` и `container_id`. Не хватало трёх звеньев: строка подбора не
помнила тару, ручка `pick/set` её не принимала, а списание всегда искало строку
остатка «без тары» и потому физически не могло снять содержимое короба.

TC-NEW-001 — Given товар лежит в коробе в ячейке, When оператор задаёт снятое
количество по этому коробу, Then списывается остаток именно этого короба,
россыпь в той же ячейке не трогается, а строка подбора помнит номер короба.
Negative: количество больше, чем лежит в коробе, отбивается 422 insufficient_available.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_marketplace_unload_and_discrepancy_acts import (  # type: ignore[import-not-found]
    E2E_BARCODE,
    _link_product_wb_barcode,
    _patch_mp_planned_date,
    _patch_packaging_instructions,
    _post_inventory,
    _seller_wb_mp_warehouse,
)

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import MarketplaceUnloadPickAllocation


async def _balances_by_container(location_id: str, product_id: str) -> dict[str | None, int]:
    """Строки остатка по таре: ключ — номер тары, None — россыпь.

    Ручка `/operations/inventory-balances` складывает тару и россыпь в одно
    число, поэтому здесь читаем сами строки: проверяем именно то, что подбор
    списал из нужного короба.
    """
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.storage_location_id == uuid.UUID(location_id),
                    InventoryBalance.product_id == uuid.UUID(product_id),
                )
            )
        ).scalars().all()
    return {
        (str(row.container_id) if row.container_id is not None else None): int(row.quantity)
        for row in rows
    }


async def _loose_balance_id(location_id: str, product_id: str) -> str:
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.storage_location_id == uuid.UUID(location_id),
                    InventoryBalance.product_id == uuid.UUID(product_id),
                    InventoryBalance.container_id.is_(None),
                )
            )
        ).scalar_one()
    return str(row.id)


@pytest.mark.asyncio
async def test_pick_set_takes_stock_from_the_named_container(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "PickBox Co",
            "slug": f"pickbox-{suffix}",
            "admin_email": f"pickbox-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = str(wh.json()["id"])
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = str(pr.json()["id"])
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )

    # Пять штук приходят россыпью в ячейку.
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="PICK-BOX",
    )

    # Заводим короб, ставим его в ту же ячейку и перекладываем в него три штуки.
    box = await async_client.post(
        f"/warehouses/{wid}/sorting-objects", headers=h, json={"kind": "box"}
    )
    assert box.status_code == 201, box.text
    box_id = str(box.json()["id"])
    box_barcode = str(box.json()["barcode"])

    place = await async_client.post(
        f"/warehouses/{wid}/map/move",
        headers=h,
        json={"kind": "box", "id": box_id, "to_kind": "cell", "to_id": loc_id, "qty": 1},
    )
    assert place.status_code == 200, place.text

    balance_id = await _loose_balance_id(loc_id, pid)

    into_box = await async_client.post(
        f"/warehouses/{wid}/map/move",
        headers=h,
        json={
            "kind": "product",
            "id": balance_id,
            "to_kind": "box",
            "to_id": box_id,
            "qty": 3,
        },
    )
    assert into_box.status_code == 200, into_box.text

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = str(mu.json()["id"])
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=h
    )
    assert sub.status_code == 200, sub.text

    # Подбор видит два источника: россыпь и короб.
    options = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}/pick-options", headers=h
    )
    assert options.status_code == 200, options.text
    product_row = next(o for o in options.json() if o["product_id"] == pid)
    loc_row = next(
        loc for loc in product_row["locations"] if loc["storage_location_id"] == loc_id
    )
    kinds = {src["is_loose"] for src in loc_row["sources"]}
    assert kinds == {True, False}
    box_source = next(src for src in loc_row["sources"] if not src["is_loose"])
    assert box_source["quantity"] == 3
    assert box_source["container_path"][-1]["id"] == box_id

    selected_box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=h,
        json={"barcode": box_barcode},
    )
    assert selected_box.status_code == 200, selected_box.text
    assert selected_box.json()["kind"] == "container"
    assert selected_box.json()["container_kind"] == "box"
    assert selected_box.json()["container_id"] == box_id
    assert selected_box.json()["storage_location_id"] == loc_id

    scanned_product = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=h,
        json={
            "barcode": E2E_BARCODE,
            "product_id": pid,
            "storage_location_id": loc_id,
            "container_kind": "box",
            "container_id": box_id,
        },
    )
    assert scanned_product.status_code == 200, scanned_product.text
    assert scanned_product.json()["kind"] == "product"
    assert scanned_product.json()["allocation_quantity"] == 1

    # Негатив: из короба нельзя снять больше, чем в нём лежит.
    too_much = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/set",
        headers=h,
        json={
            "product_id": pid,
            "storage_location_id": loc_id,
            "quantity": 4,
            "container_kind": "box",
            "container_id": box_id,
        },
    )
    assert too_much.status_code == 422, too_much.text
    assert too_much.json()["detail"] == "insufficient_available"

    # Снимаем три штуки именно из короба.
    from_box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/set",
        headers=h,
        json={
            "product_id": pid,
            "storage_location_id": loc_id,
            "quantity": 3,
            "container_kind": "box",
            "container_id": box_id,
        },
    )
    assert from_box.status_code == 200, from_box.text
    assert from_box.json()["quantity"] == 3

    # Короб опустел, россыпь в той же ячейке осталась нетронутой.
    by_container = await _balances_by_container(loc_id, pid)
    assert by_container.get(box_id) == 0
    assert by_container.get(None) == 2

    # Строка подбора помнит, из какого короба сняли.
    async with SessionLocal() as session:
        allocs = (
            await session.execute(
                select(MarketplaceUnloadPickAllocation).where(
                    MarketplaceUnloadPickAllocation.product_id == uuid.UUID(pid)
                )
            )
        ).scalars().all()
    assert len(allocs) == 1
    assert str(allocs[0].container_id) == box_id
    assert allocs[0].container_kind == "box"

    # Повторная загрузка должна вернуть прогресс именно по физическому источнику,
    # иначе поле количества снова показывает ноль и следующий ввод даёт ложную
    # ошибку превышения плана.
    refreshed_options = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}/pick-options", headers=h
    )
    assert refreshed_options.status_code == 200, refreshed_options.text
    refreshed_product = next(
        row for row in refreshed_options.json() if row["product_id"] == pid
    )
    refreshed_location = next(
        row
        for row in refreshed_product["locations"]
        if row["storage_location_id"] == loc_id
    )
    refreshed_box = next(
        source for source in refreshed_location["sources"] if not source["is_loose"]
    )
    refreshed_loose = next(
        source for source in refreshed_location["sources"] if source["is_loose"]
    )
    assert refreshed_location["picked"] == 3
    assert refreshed_box["picked"] == 3
    assert refreshed_loose["picked"] == 0

    # Возврат кладём обратно в тот же короб, а не россыпью.
    back = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/set",
        headers=h,
        json={
            "product_id": pid,
            "storage_location_id": loc_id,
            "quantity": 0,
            "container_kind": "box",
            "container_id": box_id,
        },
    )
    assert back.status_code == 200, back.text

    by_container_back = await _balances_by_container(loc_id, pid)
    assert by_container_back.get(box_id) == 3
    assert by_container_back.get(None) == 2
