"""WMS-397: optional mobile order selection through the existing scan API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProductPick, FbsOrderReservation
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.pallet import Pallet
from app.models.warehouse_box import WarehouseBox
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


@pytest.fixture
async def case(async_client: AsyncClient):
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"WMS397-{suffix}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=barcode, barcode=barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client, headers, tenant_id, seller_id, warehouse_id, location_id,
        product_id, stock_qty=3, barcode=barcode,
        order_specs=[(1, timedelta(hours=48)), (2, timedelta(hours=12))],
    )
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        for index, order_id in enumerate(order_ids):
            order = await session.get(FbsOrder, order_id)
            order.created_at_wb = now - timedelta(days=3 - index)
            session.add(FbsOrderReservation(
                tenant_id=tenant_id, warehouse_id=warehouse_id, product_id=product_id,
                fbs_order_id=order_id, quantity=1,
            ))
        await session.commit()
    return SimpleNamespace(
        headers=headers, tenant_id=tenant_id, seller_id=seller_id,
        warehouse_id=warehouse_id, location_id=location_id, product_id=product_id,
        supply_id=supply_id, order_ids=order_ids, barcode=barcode,
    )


async def scan(client, case, *, key=None, **body):
    return await client.post(
        f"/operations/fbs-supplies/{case.supply_id}/pick/scan",
        headers={**case.headers, "Idempotency-Key": key or str(uuid.uuid4())},
        json={
            "barcode": case.barcode,
            "storage_location_id": str(case.location_id),
            **body,
        },
    )


async def warehouse_snapshot(case):
    async with SessionLocal() as session:
        balances = (await session.execute(select(
            InventoryBalance.id, InventoryBalance.quantity,
            InventoryBalance.quantity_unpacked, InventoryBalance.quantity_packed,
            InventoryBalance.storage_location_id,
            InventoryBalance.container_kind, InventoryBalance.container_id,
        ).where(InventoryBalance.tenant_id == case.tenant_id).order_by(
            InventoryBalance.id
        ))).all()
        movements = (await session.execute(select(
            InventoryMovement.id, InventoryMovement.quantity_delta,
        ).where(InventoryMovement.tenant_id == case.tenant_id).order_by(
            InventoryMovement.id
        ))).all()
        reservations = (await session.execute(select(
            FbsOrderReservation.fbs_order_id, FbsOrderReservation.quantity,
        ).where(FbsOrderReservation.tenant_id == case.tenant_id).order_by(
            FbsOrderReservation.fbs_order_id
        ))).all()
        return balances, movements, reservations


async def picked_order_ids(case):
    async with SessionLocal() as session:
        return set((await session.scalars(select(FbsOrderPick.fbs_order_id).where(
            FbsOrderPick.fbs_supply_id == case.supply_id,
            FbsOrderPick.undone_at.is_(None),
        ))).all())


async def test_explicit_oldest_order_overrides_deadline_without_stock_effects(async_client, case):
    before = await warehouse_snapshot(case)
    response = await scan(async_client, case, order_id=str(case.order_ids[0]))
    assert response.status_code == 200, response.text
    assert response.json()["picked_qty"] == 1
    assert await picked_order_ids(case) == {case.order_ids[0]}
    assert await warehouse_snapshot(case) == before


@pytest.mark.parametrize("body", [{}, {"order_id": None}])
async def test_web_without_order_keeps_earliest_deadline(async_client, case, body):
    before = await warehouse_snapshot(case)
    response = await scan(async_client, case, **body)
    assert response.status_code == 200, response.text
    assert await picked_order_ids(case) == {case.order_ids[1]}
    assert await warehouse_snapshot(case) == before


async def test_replay_keeps_original_order_and_new_key_rejects_already_picked(async_client, case):
    before = await warehouse_snapshot(case)
    first = await scan(async_client, case, key="one-scan", order_id=str(case.order_ids[0]))
    assert first.status_code == 200, first.text
    for requested_order in case.order_ids:
        replay = await scan(
            async_client, case, key="one-scan", order_id=str(requested_order)
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == first.json()
    duplicate = await scan(async_client, case, order_id=str(case.order_ids[0]))
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "order_already_picked"
    assert await picked_order_ids(case) == {case.order_ids[0]}
    next_scan = await scan(async_client, case, order_id=str(case.order_ids[1]))
    assert next_scan.status_code == 200, next_scan.text
    assert await picked_order_ids(case) == set(case.order_ids)
    assert await warehouse_snapshot(case) == before


@pytest.mark.parametrize("invalid", ["other_supply", "other_product", "cancelled", "missing"])
async def test_explicit_invalid_order_does_not_fall_back_to_another_order(
    async_client, case, invalid
):
    requested_id = case.order_ids[0]
    expected_code = "product_not_in_supply"
    if invalid == "other_supply":
        _, other_orders, _ = await _seed_pick_supply(
            async_client, case.headers, case.tenant_id, case.seller_id,
            case.warehouse_id, case.location_id, case.product_id,
            stock_qty=0, barcode=case.barcode, order_specs=[(11, timedelta(hours=1))],
        )
        requested_id = other_orders[0]
    elif invalid == "missing":
        requested_id = uuid.uuid4()
    else:
        other_product = None
        if invalid == "other_product":
            other_product = await _create_product(
                async_client, case.headers, case.seller_id, sku="OTHER", barcode="OTHER"
            )
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, requested_id)
            if invalid == "other_product":
                order.product_id = other_product
            else:
                order.status = "cancelled"
                expected_code = "order_cancelled"
            await session.commit()
    before = await warehouse_snapshot(case)
    response = await scan(async_client, case, order_id=str(requested_id))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == expected_code
    assert await picked_order_ids(case) == set()
    assert await warehouse_snapshot(case) == before


async def test_foreign_tenant_order_product_and_supply_are_not_pickable(async_client, case):
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku="FOREIGN", barcode=case.barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client, headers, tenant_id, seller_id, warehouse_id, location_id,
        product_id, stock_qty=1, barcode=case.barcode,
        order_specs=[(12, timedelta(hours=1))],
    )
    before = await warehouse_snapshot(case)
    for body, code in [
        ({"order_id": str(order_ids[0])}, "product_not_in_supply"),
        ({"order_id": str(case.order_ids[0]), "product_id": str(product_id)}, "wrong_product"),
    ]:
        response = await scan(async_client, case, **body)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == code
    foreign_supply = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan",
        headers={**case.headers, "Idempotency-Key": "foreign-supply"},
        json={"barcode": case.barcode, "order_id": str(order_ids[0])},
    )
    assert foreign_supply.status_code == 404, foreign_supply.text
    assert foreign_supply.json()["detail"]["code"] == "supply_not_found"
    assert await picked_order_ids(case) == set()
    async with SessionLocal() as session:
        assert not (await session.scalars(select(FbsOrderPick))).all()
    assert await warehouse_snapshot(case) == before


@pytest.mark.parametrize("kind", ["pallet", "box", "cargo_place"])
async def test_selected_order_keeps_exact_container_without_wb_movement(async_client, case, kind):
    async with SessionLocal() as session:
        common = dict(
            tenant_id=case.tenant_id, warehouse_id=case.warehouse_id,
            storage_location_id=case.location_id,
        )
        if kind == "pallet":
            container = Pallet(**common, code="WMS397-P", barcode="WMS397-P")
        else:
            container = WarehouseBox(**common, internal_barcode="WMS397-B", container_kind=kind)
        session.add(container)
        await session.flush()
        balance = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == case.product_id,
            InventoryBalance.storage_location_id == case.location_id,
        ))
        balance.container_kind = kind
        balance.container_id = container.id
        container_id = container.id
        await session.commit()
    before = await warehouse_snapshot(case)
    response = await scan(
        async_client, case, order_id=str(case.order_ids[0]),
        container_kind=kind, container_id=str(container_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["allocation_quantity"] == 1
    async with SessionLocal() as session:
        pick = await session.scalar(select(FbsOrderPick).where(
            FbsOrderPick.fbs_order_id == case.order_ids[0]
        ))
        assert pick is not None
        assert pick.source_storage_location_id == case.location_id
        assert (pick.source_container_kind, pick.source_container_id) == (kind, container_id)
        assert pick.inventory_movement_id is None
    assert await warehouse_snapshot(case) == before


@pytest.mark.parametrize("complete_pair", [False, True])
async def test_order_selection_does_not_bypass_container_validation(
    async_client, case, complete_pair
):
    body = {"order_id": str(case.order_ids[0]), "container_kind": "box"}
    if complete_pair:
        body["container_id"] = str(uuid.uuid4())
    before = await warehouse_snapshot(case)
    response = await scan(async_client, case, **body)
    assert response.status_code == (409 if complete_pair else 422), response.text
    if complete_pair:
        assert response.json()["detail"]["code"] == "invalid_container_reference"
    assert await picked_order_ids(case) == set()
    assert await warehouse_snapshot(case) == before


async def test_explicit_ozon_order_uses_existing_position_pick_and_replay(async_client, case):
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client, case.headers, case.tenant_id, case.seller_id,
        case.warehouse_id, case.location_id, case.product_id,
        stock_qty=0, barcode=case.barcode, marketplace="ozon",
        order_specs=[(21, timedelta(hours=48)), (22, timedelta(hours=12))],
    )
    case.supply_id = supply_id
    first = await scan(async_client, case, key="ozon-scan", order_id=str(order_ids[0]))
    assert first.status_code == 200, first.text
    after_first = await warehouse_snapshot(case)
    replay = await scan(async_client, case, key="ozon-scan", order_id=str(order_ids[0]))
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    async with SessionLocal() as session:
        orders = (await session.scalars(select(FbsOrder).where(
            FbsOrder.id.in_(order_ids)
        ))).all()
        assert {order.id for order in orders if order.pick_status == "picked"} == {order_ids[0]}
        picks = (await session.scalars(select(FbsOrderProductPick).where(
            FbsOrderProductPick.fbs_supply_id == supply_id
        ))).all()
        assert len(picks) == 1
        assert picks[0].source_storage_location_id == case.location_id
    assert await warehouse_snapshot(case) == after_first
