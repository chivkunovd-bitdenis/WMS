"""FBS product-first picking uses the marketplace-unload write contract."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.fbs_supplies import (
    FbsPickAllocationOut,
    FbsPickScanBody,
    FbsPickScanOut,
    FbsPickSetBody,
)
from app.api.marketplace_unload_requests import (
    MarketplaceUnloadPickAllocationOut,
    MarketplaceUnloadPickScanBody,
    MarketplaceUnloadPickScanOut,
    MarketplaceUnloadPickSetBody,
)
from app.db.session import SessionLocal
from app.models.fbs_order import PICK_STATUS_PENDING, PICK_STATUS_PICKED, FbsOrder
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)

BASE = "/operations/fbs-supplies"


def _schema_without_title(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


def test_fbs_pick_write_models_match_marketplace_unload() -> None:
    """TC-NEW-FBS-PICK-001: the shared screen sends and receives one wire shape."""
    pairs = (
        (FbsPickScanBody, MarketplaceUnloadPickScanBody),
        (FbsPickScanOut, MarketplaceUnloadPickScanOut),
        (FbsPickSetBody, MarketplaceUnloadPickSetBody),
        (FbsPickAllocationOut, MarketplaceUnloadPickAllocationOut),
    )
    for fbs_model, unload_model in pairs:
        assert _schema_without_title(fbs_model) == _schema_without_title(unload_model)


async def _active_pick_count(supply_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(FbsOrderPick.id)).where(
                    FbsOrderPick.fbs_supply_id == supply_id,
                    FbsOrderPick.undone_at.is_(None),
                )
            )
            or 0
        )


async def _seed_two_order_supply(
    async_client: AsyncClient,
) -> tuple[
    dict[str, str],
    uuid.UUID,
    uuid.UUID,
    uuid.UUID,
    list[uuid.UUID],
    str,
]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-UNIFIED-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-UNIFIED-{suffix}",
        barcode=barcode,
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
        order_specs=[(1, timedelta(hours=12)), (2, timedelta(hours=24))],
        barcode=barcode,
    )
    return headers, supply_id, product_id, location_id, order_ids, location_code


@pytest.mark.asyncio
async def test_fbs_pick_set_assigns_two_orders_then_removes_one(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-002: set is a final quantity over per-order assignments."""
    headers, supply_id, product_id, location_id, order_ids, _ = (
        await _seed_two_order_supply(async_client)
    )
    set_two = await async_client.post(
        f"{BASE}/{supply_id}/pick/set",
        headers={**headers, "Idempotency-Key": "fbs-set-two"},
        json={
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "quantity": 2,
        },
    )
    assert set_two.status_code == 200, set_two.text
    assert set_two.json()["quantity"] == 2
    assert await _active_pick_count(supply_id) == 2

    replay_two = await async_client.post(
        f"{BASE}/{supply_id}/pick/set",
        headers={**headers, "Idempotency-Key": "fbs-set-two"},
        json={
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "quantity": 2,
        },
    )
    assert replay_two.status_code == 200, replay_two.text
    assert replay_two.json()["quantity"] == 2
    assert await _active_pick_count(supply_id) == 2

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.id.in_(order_ids))
                )
            ).scalars()
        )
        assert {order.pick_status for order in orders} == {PICK_STATUS_PICKED}

    set_one = await async_client.post(
        f"{BASE}/{supply_id}/pick/set",
        headers={**headers, "Idempotency-Key": "fbs-set-one"},
        json={
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "quantity": 1,
        },
    )
    assert set_one.status_code == 200, set_one.text
    assert set_one.json()["quantity"] == 1
    assert await _active_pick_count(supply_id) == 1

    async with SessionLocal() as session:
        statuses = list(
            await session.scalars(
                select(FbsOrder.pick_status).where(FbsOrder.id.in_(order_ids))
            )
        )
        assert sorted(statuses) == sorted([PICK_STATUS_PENDING, PICK_STATUS_PICKED])


@pytest.mark.asyncio
async def test_fbs_pick_scan_location_then_product_is_idempotent(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-003: a repeated product scan key creates one assignment."""
    headers, supply_id, _product_id, location_id, _order_ids, location_code = (
        await _seed_two_order_supply(async_client)
    )
    location_scan = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": location_code, "storage_location_id": None},
    )
    assert location_scan.status_code == 200, location_scan.text
    assert location_scan.json() == {
        "kind": "location",
        "storage_location_id": str(location_id),
        "location_code": location_code,
        "product_id": None,
        "sku_code": None,
        "product_name": None,
        "picked_qty": None,
        "allocation_quantity": None,
        "container_kind": None,
        "container_id": None,
        "container_code": None,
    }

    options = await async_client.get(f"{BASE}/{supply_id}/pick-options", headers=headers)
    assert options.status_code == 200, options.text
    product_id = options.json()[0]["product_id"]
    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id).limit(1)
        )
        assert order is not None
        barcode = order.wb_barcode
    body = {
        "barcode": barcode,
        "product_id": product_id,
        "storage_location_id": str(location_id),
    }
    scan_headers = {**headers, "Idempotency-Key": "fbs-shared-screen-scan"}
    first = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=scan_headers,
        json=body,
    )
    replay = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=scan_headers,
        json=body,
    )
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert first.json()["kind"] == "product"
    assert first.json()["picked_qty"] == 1
    assert replay.json()["picked_qty"] == 1
    assert replay.json()["allocation_quantity"] == 1
    assert await _active_pick_count(supply_id) == 1


@pytest.mark.asyncio
async def test_fbs_pick_scan_selects_container_and_keeps_it_on_product_pick(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, product_id, location_id, _order_ids, _location_code = (
        await _seed_two_order_supply(async_client)
    )
    async with SessionLocal() as session:
        location = await session.get(StorageLocation, location_id)
        product = await session.get(Product, product_id)
        assert location is not None
        assert product is not None
        box = WarehouseBox(
            tenant_id=location.tenant_id,
            warehouse_id=location.warehouse_id,
            internal_barcode=f"FBS-SOURCE-{uuid.uuid4().hex[:12]}",
            container_kind="box",
            storage_location_id=location.id,
        )
        session.add(box)
        await session.flush()
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == location.tenant_id,
                InventoryBalance.storage_location_id == location.id,
                InventoryBalance.product_id == product.id,
            )
        )
        assert balance is not None
        balance.container_kind = "box"
        balance.container_id = box.id
        await session.commit()
        box_id = box.id
        box_barcode = box.internal_barcode
        product_barcode = product.wb_barcode
        assert product_barcode is not None

    selected = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": box_barcode},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["kind"] == "container"
    assert selected.json()["container_kind"] == "box"
    assert selected.json()["container_id"] == str(box_id)

    picked = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": "fbs-container-product"},
        json={
            "barcode": product_barcode,
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "container_kind": "box",
            "container_id": str(box_id),
        },
    )
    assert picked.status_code == 200, picked.text
    assert picked.json()["kind"] == "product"
    async with SessionLocal() as session:
        stored_pick = await session.scalar(
            select(FbsOrderPick).where(
                FbsOrderPick.fbs_supply_id == supply_id,
                FbsOrderPick.undone_at.is_(None),
            )
        )
        assert stored_pick is not None
        assert stored_pick.source_container_kind == "box"
        assert stored_pick.source_container_id == box_id


@pytest.mark.asyncio
async def test_fbs_pick_set_rejects_quantity_above_waiting_orders(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-004: set cannot invent assignments beyond supply demand."""
    headers, supply_id, product_id, location_id, _order_ids, _ = (
        await _seed_two_order_supply(async_client)
    )
    response = await async_client.post(
        f"{BASE}/{supply_id}/pick/set",
        headers=headers,
        json={
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "quantity": 3,
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "pick_quantity_exceeds_demand"
    assert response.json()["detail"]["context"] == {
        "product_id": str(product_id),
        "requested": 3,
        "maximum": 2,
    }
    assert await _active_pick_count(supply_id) == 0


@pytest.mark.asyncio
async def test_fbs_pick_write_hides_foreign_tenant_supply(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-005: another tenant gets the same not-found boundary."""
    owner_headers, supply_id, product_id, location_id, _order_ids, _ = (
        await _seed_two_order_supply(async_client)
    )
    assert owner_headers
    stranger_headers, _suffix, _tenant_id = await _register_ff_admin(async_client)
    response = await async_client.post(
        f"{BASE}/{supply_id}/pick/set",
        headers=stranger_headers,
        json={
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "quantity": 1,
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "supply_not_found"


@pytest.mark.asyncio
async def test_fbs_pick_scan_works_without_visible_address(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-006: address-off scan selects stock and hides the cell."""
    headers, supply_id, product_id, _location_id, _order_ids, _ = (
        await _seed_two_order_supply(async_client)
    )
    settings = await async_client.patch(
        "/tenant/settings",
        headers=headers,
        json={"address_storage_enabled": False},
    )
    assert settings.status_code == 200, settings.text

    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id).limit(1)
        )
        assert order is not None
        barcode = order.wb_barcode
    response = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": f"address-off-{time.time_ns()}"},
        json={"barcode": barcode, "product_id": str(product_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "product"
    assert response.json()["storage_location_id"] is None
    assert response.json()["location_code"] is None
    assert response.json()["picked_qty"] == 1


@pytest.mark.asyncio
async def test_fbs_pick_scan_works_for_container_in_sorting_without_cell(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-FBS-PICK-007: container stock in the no-cell zone remains pickable."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-CONTAINER-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-CONTAINER-{suffix}",
        barcode=barcode,
    )
    supply_id, _order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=[(1, timedelta(hours=12))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=sorting.id,
                product_id=product_id,
                container_kind="box",
                container_id=uuid.uuid4(),
                quantity=1,
                quantity_unpacked=1,
                quantity_packed=0,
            )
        )
        await session.commit()

    response = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": "container-without-cell"},
        json={"barcode": barcode, "product_id": str(product_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "product"
    assert response.json()["storage_location_id"] is None
    assert response.json()["location_code"] is None
    assert response.json()["picked_qty"] == 1
    assert await _active_pick_count(supply_id) == 1
