"""Product-first FBS picking options — TC-NEW-FBS-PICK-OPTIONS."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_reservation import InventoryReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.pallet import Pallet
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service
from tests.inventory_actor_helpers import resolve_test_actor_user_id
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _scan_product,
    _seed_pick_supply,
)

BASE = "/operations/fbs-supplies"


async def _create_location(
    async_client: AsyncClient,
    headers: dict[str, str],
    warehouse_id: uuid.UUID,
    *,
    code: str,
) -> uuid.UUID:
    response = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": code},
    )
    assert response.status_code in (200, 201), response.text
    return uuid.UUID(response.json()["id"])


async def _add_stock(
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: int,
) -> None:
    async with SessionLocal() as session:
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=quantity,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
        )
        await session.commit()


async def _add_location_reservation(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: int,
) -> None:
    async with SessionLocal() as session:
        outbound = OutboundShipmentRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            status="draft",
        )
        session.add(outbound)
        await session.flush()
        line = OutboundShipmentLine(
            request_id=outbound.id,
            product_id=product_id,
            quantity=quantity,
            shipped_qty=0,
            storage_location_id=location_id,
        )
        session.add(line)
        await session.flush()
        session.add(
            InventoryReservation(
                tenant_id=tenant_id,
                outbound_shipment_line_id=line.id,
                product_id=product_id,
                warehouse_id=None,
                storage_location_id=location_id,
                quantity=quantity,
            )
        )
        await session.commit()


async def _pick_options(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
) -> Any:
    return await async_client.get(
        f"{BASE}/{supply_id}/pick-options",
        headers=headers,
    )


# TC-NEW-FBS-PICK-OPTIONS-001
# TC-NEW-PICK-CONTAINERS-001: FBS serializes the shared additive source contract.
@pytest.mark.asyncio
async def test_fbs_pick_options_returns_two_locations_with_inventory_numbers(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, first_location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    second_location_id = await _create_location(
        async_client,
        headers,
        warehouse_id,
        code=f"B-{suffix[-6:]}",
    )
    sku = f"SKU-OPTIONS-{suffix}"
    barcode = f"BAR-OPTIONS-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=sku, barcode=barcode
    )
    supply_id, _order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        first_location_id,
        product_id,
        stock_qty=4,
        order_specs=[
            (1, timedelta(hours=24)),
            (2, timedelta(hours=48)),
            (3, timedelta(hours=72)),
        ],
        barcode=barcode,
    )
    await _add_stock(tenant_id, product_id, second_location_id, 2)
    await _add_location_reservation(
        tenant_id,
        seller_id,
        warehouse_id,
        product_id,
        first_location_id,
        1,
    )
    async with SessionLocal() as session:
        pallet = Pallet(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=f"PALLET-{suffix[-8:]}",
            barcode=f"PALLET-BC-{suffix[-8:]}",
            storage_location_id=first_location_id,
        )
        cargo_place = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            internal_barcode=f"CARGO-{suffix[-8:]}",
            container_kind="cargo_place",
        )
        session.add_all([pallet, cargo_place])
        await session.flush()
        cargo_place.pallet_id = pallet.id
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=first_location_id,
                product_id=product_id,
                container_kind="cargo_place",
                container_id=cargo_place.id,
                quantity=3,
                quantity_unpacked=3,
                quantity_packed=0,
            )
        )
        await session.commit()
        pallet_id = pallet.id
        cargo_place_id = cargo_place.id

    response = await _pick_options(async_client, headers, supply_id)

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    product = response.json()[0]
    assert set(product) == {
        "product_id",
        "sku_code",
        "product_name",
        "planned_qty",
        "picked_qty",
        "locations",
    }
    assert product["product_id"] == str(product_id)
    assert product["sku_code"] == sku
    assert product["product_name"] == "Pick product"
    assert product["planned_qty"] == 3
    assert product["picked_qty"] == 0
    locations = {
        uuid.UUID(location["storage_location_id"]): location
        for location in product["locations"]
    }
    assert set(locations) == {first_location_id, second_location_id}
    assert locations[first_location_id] == {
        "storage_location_id": str(first_location_id),
        "location_code": locations[first_location_id]["location_code"],
        "quantity": 7,
        "reserved": 1,
        "available": 6,
        "picked": 0,
        "sources": [
            {
                "quantity": 3,
                "picked": 0,
                "is_loose": False,
                "source_label": f"Грузоместо CARGO-{suffix[-8:]}",
                "container_path": [
                    {
                        "kind": "pallet",
                        "id": str(pallet_id),
                        "code": f"PALLET-{suffix[-8:]}",
                        "label": f"Палета PALLET-{suffix[-8:]}",
                    },
                    {
                        "kind": "cargo_place",
                        "id": str(cargo_place_id),
                        "code": f"CARGO-{suffix[-8:]}",
                        "label": f"Грузоместо CARGO-{suffix[-8:]}",
                    },
                ],
            },
            {
                "quantity": 4,
                "picked": 0,
                "is_loose": True,
                "source_label": "Россыпью",
                "container_path": [],
            }
        ],
    }
    assert locations[second_location_id] == {
        "storage_location_id": str(second_location_id),
        "location_code": f"B-{suffix[-6:]}",
        "quantity": 2,
        "reserved": 0,
        "available": 2,
        "picked": 0,
        "sources": [
            {
                "quantity": 2,
                "picked": 0,
                "is_loose": True,
                "source_label": "Россыпью",
                "container_path": [],
            }
        ],
    }


# TC-NEW-FBS-PICK-OPTIONS-002
@pytest.mark.asyncio
async def test_fbs_pick_options_reports_active_pick_for_source_location(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-OPTIONS-PICKED-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-OPTIONS-PICKED-{suffix}",
        barcode=barcode,
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
    picked = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert picked.status_code == 200, picked.text

    response = await _pick_options(async_client, headers, supply_id)

    assert response.status_code == 200, response.text
    product = response.json()[0]
    assert product["planned_qty"] == 2
    assert product["picked_qty"] == 1
    source = next(
        location
        for location in product["locations"]
        if location["storage_location_id"] == str(location_id)
    )
    assert source["quantity"] == 1
    assert source["available"] == 1
    assert source["picked"] == 1


# TC-NEW-FBS-PICK-OPTIONS-003
@pytest.mark.asyncio
async def test_fbs_pick_options_keeps_zero_balance_picked_location(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-OPTIONS-ZERO-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-OPTIONS-ZERO-{suffix}",
        barcode=barcode,
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
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    picked = await _scan_product(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        barcode=barcode,
        idempotency_key=str(uuid.uuid4()),
    )
    assert picked.status_code == 200, picked.text

    response = await _pick_options(async_client, headers, supply_id)

    assert response.status_code == 200, response.text
    product = response.json()[0]
    source = next(
        location
        for location in product["locations"]
        if location["storage_location_id"] == str(location_id)
    )
    assert source["quantity"] == 0
    assert source["reserved"] == 0
    assert source["available"] == 0
    assert source["picked"] == 1
    assert source["sources"] == [
        {
            "quantity": 0,
            "picked": 1,
            "is_loose": True,
            "source_label": "Россыпью",
            "container_path": [],
        }
    ]


# TC-NEW-FBS-PICK-OPTIONS-004
@pytest.mark.asyncio
async def test_fbs_pick_options_hides_foreign_tenant_supply(
    async_client: AsyncClient,
) -> None:
    owner_headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, owner_headers, suffix
    )
    barcode = f"BAR-OPTIONS-TENANT-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        owner_headers,
        seller_id,
        sku=f"SKU-OPTIONS-TENANT-{suffix}",
        barcode=barcode,
    )
    supply_id, _order_ids, _location_code = await _seed_pick_supply(
        async_client,
        owner_headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=1,
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    foreign_headers, _foreign_suffix, _foreign_tenant_id = await _register_ff_admin(
        async_client
    )

    response = await _pick_options(async_client, foreign_headers, supply_id)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "supply_not_found"


# TC-NEW-PICK-CONTAINERS-001
@pytest.mark.asyncio
async def test_fbs_pick_options_rejects_invalid_container_reference(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-OPTIONS-BAD-CONTAINER-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-OPTIONS-BAD-CONTAINER-{suffix}",
        barcode=barcode,
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
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=location_id,
                product_id=product_id,
                container_kind="box",
                container_id=uuid.uuid4(),
                quantity=1,
                quantity_unpacked=1,
                quantity_packed=0,
            )
        )
        await session.commit()

    response = await _pick_options(async_client, headers, supply_id)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "invalid_container_reference"


# TC-NEW-FBS-PICK-OPTIONS-005
@pytest.mark.asyncio
async def test_fbs_pick_options_returns_empty_list_for_empty_supply(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, _location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-EMPTY-{time.time_ns()}",
            name="Empty supply",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.commit()
        supply_id = supply.id

    response = await _pick_options(async_client, headers, supply_id)

    assert response.status_code == 200, response.text
    assert response.json() == []
