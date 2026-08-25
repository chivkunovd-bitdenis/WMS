"""FBS server-side pick scans — TC-07, TC-08, TC-09."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    MAPPING_STATUS_MAPPED,
    PACK_STATUS_PACKED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS pick {suffix}",
            "slug": f"fbs-pick-{suffix}",
            "admin_email": f"fbs-pick-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    return headers, suffix, tenant_id


async def _create_seller_and_warehouse(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
    *,
    seller_name: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": seller_name or f"Seller {suffix}"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = uuid.UUID(seller.json()["id"])
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"A-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    location_id = uuid.UUID(location.json()["id"])
    return seller_id, warehouse_id, location_id


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: uuid.UUID,
    *,
    sku: str,
    barcode: str,
    name: str = "Pick product",
) -> uuid.UUID:
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku,
            "seller_id": str(seller_id),
            "wb_barcode": barcode,
        },
    )
    assert product.status_code in (200, 201), product.text
    return uuid.UUID(product.json()["id"])


async def _seed_pick_supply(
    async_client: AsyncClient,
    headers: dict[str, str],
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    stock_qty: int,
    order_specs: list[tuple[int, timedelta]],
    barcode: str,
    marketplace: str = "wb",
    position_quantity: int = 1,
) -> tuple[uuid.UUID, list[uuid.UUID], str]:
    """Create supply with orders; order_specs = (wb_order_id offset, deadline delta)."""
    suffix = str(time.time_ns())
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        if stock_qty > 0:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=location_id,
                quantity_delta=stock_qty,
                movement_type="inbound_intake",
            )
        await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-PICK-{suffix[-8:]}",
            name="Pick supply",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            marketplace=marketplace,
        )
        session.add(supply)
        await session.flush()
        now = datetime.now(tz=UTC)
        order_ids: list[uuid.UUID] = []
        for _idx, (wb_no, deadline_delta) in enumerate(order_specs):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                supply_id=supply.id,
                marketplace=marketplace,
                external_order_id=(f"ozon-{wb_no}" if marketplace == "ozon" else None),
                wb_order_id=700_000 + wb_no,
                wb_barcode=barcode,
                created_at_wb=now - timedelta(hours=1),
                deadline_at=now + deadline_delta,
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
                status=FBS_ORDER_STATUS_IN_SUPPLY,
            )
            session.add(order)
            await session.flush()
            if marketplace == "ozon":
                session.add(
                    FbsOrderProduct(
                        order_id=order.id,
                        product_id=product_id,
                        ozon_sku=wb_no,
                        offer_id=f"offer-{wb_no}",
                        name="Pick product",
                        quantity=position_quantity,
                        position_index=0,
                        reserved_quantity=position_quantity,
                    )
                )
            order_ids.append(order.id)
        await session.commit()
        loc = await session.get(StorageLocation, location_id)
        assert loc is not None
        location_code = loc.code
        return supply.id, order_ids, location_code


async def _scan_location(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
    location_code: str,
) -> Any:
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan-location",
        headers=headers,
        json={"location_barcode": location_code},
    )


async def _scan_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
    *,
    location_id: uuid.UUID,
    barcode: str,
    idempotency_key: str,
) -> Any:
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan-product",
        headers=headers,
        json={
            "location_id": str(location_id),
            "product_barcode": barcode,
            "idempotency_key": idempotency_key,
        },
    )


async def _workspace(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
) -> Any:
    return await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )


# TC-07
@pytest.mark.asyncio
async def test_fbs_pick_scan_location_product_earliest_deadline(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-PICK-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-{suffix}", barcode=barcode
    )
    supply_id, order_ids, location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=48)), (2, timedelta(hours=12))],
        barcode=barcode,
    )

    loc_resp = await _scan_location(async_client, headers, supply_id, location_code)
    assert loc_resp.status_code == 200, loc_resp.text
    assert loc_resp.json()["expected_products"][0]["remaining_qty"] == 2

    pick1 = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert pick1.status_code == 200, pick1.text
    assert pick1.json()["progress"]["picked"] == 1
    picked_order_id = next(
        o["id"] for o in pick1.json()["orders"] if o["pick"]["status"] == "picked"
    )
    assert picked_order_id == str(order_ids[1])

    wrong_loc = await _scan_location(async_client, headers, supply_id, "NO-SUCH-CELL")
    assert wrong_loc.status_code == 404
    assert wrong_loc.json()["detail"]["code"] == "wrong_location"

    wrong_prod = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode="UNKNOWN-BARCODE",
        idempotency_key=str(uuid.uuid4()),
    )
    assert wrong_prod.status_code == 409
    assert wrong_prod.json()["detail"]["code"] == "wrong_product"


# TC-08
@pytest.mark.asyncio
async def test_fbs_pick_concurrent_scan_stock_one_one_success(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-CONC-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-C-{suffix}", barcode=barcode
    )
    supply_id, _order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=1,
        order_specs=[(1, timedelta(hours=24)), (2, timedelta(hours=48))],
        barcode=barcode,
    )

    async def _attempt(key: str) -> int:
        resp = await _scan_product(
            async_client,
            headers,
            supply_id,
            location_id=location_id,
            barcode=barcode,
            idempotency_key=key,
        )
        return resp.status_code

    code_a, code_b = await asyncio.gather(
        _attempt(str(uuid.uuid4())),
        _attempt(str(uuid.uuid4())),
    )
    assert sorted([code_a, code_b]) == [200, 409]

    ws = await _workspace(async_client, headers, supply_id)
    assert ws.status_code == 200, ws.text
    assert ws.json()["progress"]["picked"] == 1

    ws2 = await _workspace(async_client, headers, supply_id)
    assert ws2.json()["progress"] == ws.json()["progress"]


# TC-08 refresh keeps progress
@pytest.mark.asyncio
async def test_fbs_pick_refresh_keeps_progress(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-REF-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-R-{suffix}", barcode=barcode
    )
    supply_id, _order_ids, location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    await _scan_location(async_client, headers, supply_id, location_code)
    pick = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert pick.status_code == 200, pick.text
    before = pick.json()["progress"]
    after = (await _workspace(async_client, headers, supply_id)).json()["progress"]
    assert after == before
    assert after["picked"] == 1


# TC-09
@pytest.mark.asyncio
async def test_fbs_pick_undo_before_pack_returns_to_source(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-UNDO-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-U-{suffix}", barcode=barcode
    )
    supply_id, order_ids, location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=1,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    await _scan_location(async_client, headers, supply_id, location_code)
    pick = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert pick.status_code == 200, pick.text

    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        sorting_bal = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert int(sorting_bal or 0) == 1

    undo = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["progress"]["picked"] == 0
    order_row = next(o for o in undo.json()["orders"] if o["id"] == str(order_ids[0]))
    assert order_row["pick"]["status"] == "pending"

    async with SessionLocal() as session:
        source_bal = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        sorting_bal = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert int(source_bal or 0) == 1
        assert int(sorting_bal or 0) == 0


@pytest.mark.asyncio
async def test_ozon_multi_product_quantity_partial_pick_manual_finish_and_idempotent_undo(
    async_client: AsyncClient,
) -> None:
    """TC-S03-OZON-024: Ozon units remain partial until every imported quantity is picked."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-OZON-PARTIAL-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-OZON-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=3,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
        marketplace="ozon",
        position_quantity=3,
    )

    first = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert first.status_code == 200, first.text
    assert first.json()["progress"]["picked"] == 1
    assert first.json()["progress"]["total"] == 3
    assert first.json()["orders"][0]["pick"]["status"] == "pending"
    assert first.json()["orders"][0]["positions"][0]["picked_quantity"] == 1

    undo_key = str(uuid.uuid4())
    undo = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": undo_key},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["progress"]["picked"] == 0

    replay = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": undo_key},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["progress"]["picked"] == 0

    for expected in (1, 2, 3):
        picked = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/pick/manual",
            headers=headers,
            json={
                "location_id": str(location_id),
                "product_id": str(product_id),
                "order_id": str(order_ids[0]),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert picked.status_code == 200, picked.text
        assert picked.json()["progress"]["picked"] == expected

    assert picked.json()["orders"][0]["pick"]["status"] == "picked"
    assert picked.json()["orders"][0]["positions"][0]["picked_quantity"] == 3


@pytest.mark.asyncio
async def test_fbs_pick_undo_blocked_after_pack(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-PACK-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-P-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=1,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.pack_status = PACK_STATUS_PACKED
        await session.commit()

    blocked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "pick_undo_not_allowed"


# TC-01 / cross-seller stock isolation
@pytest.mark.asyncio
async def test_fbs_pick_rejects_cross_seller_product(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_a, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix, seller_name="Seller A"
    )
    seller_b, _, _ = await _create_seller_and_warehouse(
        async_client, headers, f"{suffix}-b", seller_name="Seller B"
    )
    barcode_a = f"BAR-A-{suffix[-8:]}"
    barcode_b = f"BAR-B-{suffix[-8:]}"
    product_a = await _create_product(
        async_client, headers, seller_a, sku=f"SKU-A-{suffix}", barcode=barcode_a
    )
    product_b = await _create_product(
        async_client, headers, seller_b, sku=f"SKU-B-{suffix}", barcode=barcode_b
    )
    supply_id, _order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_a,
        warehouse_id,
        location_id,
        product_a,
        stock_qty=1,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode_a,
    )
    async with SessionLocal() as session:
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_b,
            storage_location_id=location_id,
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        await session.commit()

    resp = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode_b,
        idempotency_key=str(uuid.uuid4()),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "wrong_product"


@pytest.mark.asyncio
async def test_fbs_pick_idempotency_no_double_pick(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-IDEM-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-I-{suffix}", barcode=barcode
    )
    supply_id, _order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=24)), (2, timedelta(hours=48))],
        barcode=barcode,
    )
    key = str(uuid.uuid4())
    first = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=key,
    )
    second = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=key,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["progress"]["picked"] == 1
    assert second.json()["progress"]["picked"] == 1

    async with SessionLocal() as session:
        picks = list(
            (
                await session.execute(
                    select(FbsOrderPick).where(FbsOrderPick.fbs_supply_id == supply_id)
                )
            ).scalars()
        )
        assert len(picks) == 1


@pytest.mark.asyncio
async def test_fbs_pick_sold_out_order_creates_sorting_stock(async_client: AsyncClient) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-SHORT-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-S-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    resp = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["progress"]["picked"] == 1
    order_row = next(o for o in body["orders"] if o["id"] == str(order_ids[0]))
    assert order_row["pick"]["status"] == "picked"

    async with SessionLocal() as session:
        pick = await session.scalar(
            select(FbsOrderPick).where(FbsOrderPick.fbs_order_id == order_ids[0])
        )
        assert pick is not None
        assert pick.inventory_movement_id is not None
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        sorting_bal = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert int(sorting_bal or 0) == 1
