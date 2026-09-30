"""WMS-603: FBS scanner resolves an existing box before product lookup."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services.fbs_picking_service import _resolve_fbs_container_scan
from app.services.inventory_container_service import InventoryContainerScanError
from tests.test_fbs_pick_unload_contract import BASE, _seed_two_order_supply


@pytest.mark.asyncio
async def test_fbs_box_scan_variants_select_source_without_movement(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, product_id, location_id, _, _ = await _seed_two_order_supply(
        async_client
    )
    async with SessionLocal() as session:
        location = await session.get(StorageLocation, location_id)
        product = await session.get(Product, product_id)
        assert location is not None and product is not None
        location.code, location.barcode = "Ж-1-4", "J-1-4"
        intake = InboundIntakeRequest(
            tenant_id=location.tenant_id,
            warehouse_id=location.warehouse_id,
            status="receiving",
        )
        session.add(intake)
        await session.flush()
        box = InboundIntakeBox(
            tenant_id=location.tenant_id,
            request_id=intake.id,
            box_number=1,
            internal_barcode="INB-AB12",
            storage_location_id=location_id,
        )
        session.add(box)
        await session.flush()
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == location.tenant_id,
                InventoryBalance.storage_location_id == location_id,
                InventoryBalance.product_id == product_id,
            )
        )
        assert balance is not None and product.wb_barcode is not None
        balance.container_kind, balance.container_id = "box", box.id
        box_id, product_barcode = box.id, product.wb_barcode
        await session.commit()

    cell = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan", headers=headers, json={"barcode": "J-1-4"}
    )
    assert cell.status_code == 200, cell.text
    assert cell.json()["kind"] == "location"
    assert cell.json()["storage_location_id"] == str(location_id)

    async with SessionLocal() as session:
        before_balances = (
            await session.execute(
                select(InventoryBalance.id, InventoryBalance.quantity).where(
                    InventoryBalance.product_id == product_id
                )
            )
        ).all()
        before_movements = await session.scalar(select(func.count(InventoryMovement.id)))

    for scanned in (
        "INB-AB12",          # exact
        "inb-ab12",          # case
        "]Q3INB-AB12",      # AIM prefix
        "шти-фи12",          # scanner keyboard layout
        "ъЙ3шти-фи12",      # AIM prefix in the same layout
        "\x02\ufeffINB-AB12\r\n\x03",  # scanner framing
    ):
        response = await async_client.post(
            f"{BASE}/{supply_id}/pick/scan",
            headers=headers,
            json={"barcode": scanned, "storage_location_id": str(location_id)},
        )
        assert response.status_code == 200, (scanned, response.text)
        assert response.json()["kind"] == "container", scanned
        assert response.json()["container_id"] == str(box_id), scanned
        assert response.json()["storage_location_id"] == str(location_id), scanned

    async with SessionLocal() as session:
        after_balances = (
            await session.execute(
                select(InventoryBalance.id, InventoryBalance.quantity).where(
                    InventoryBalance.product_id == product_id
                )
            )
        ).all()
        after_movements = await session.scalar(select(func.count(InventoryMovement.id)))
        assert after_balances == before_balances
        assert after_movements == before_movements

    picked = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": f"box-source-{uuid.uuid4()}"},
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
        pick = await session.scalar(
            select(FbsOrderPick).where(FbsOrderPick.fbs_supply_id == supply_id)
        )
        assert pick is not None and pick.source_container_id == box_id


@pytest.mark.asyncio
async def test_fbs_box_scan_exact_priority_ambiguity_and_scope(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _, location_id, _, _ = await _seed_two_order_supply(async_client)
    async with SessionLocal() as session:
        location = await session.get(StorageLocation, location_id)
        assert location is not None
        primary = WarehouseBox(
            tenant_id=location.tenant_id,
            warehouse_id=location.warehouse_id,
            internal_barcode="INB-AB12",
            container_kind="box",
            storage_location_id=location_id,
        )
        literal = WarehouseBox(
            tenant_id=location.tenant_id,
            warehouse_id=location.warehouse_id,
            internal_barcode="шти-фи12",
            container_kind="box",
            storage_location_id=location_id,
        )
        wildcard = WarehouseBox(
            tenant_id=location.tenant_id,
            warehouse_id=location.warehouse_id,
            internal_barcode="WB_ABC%9",
            container_kind="box",
            storage_location_id=location_id,
        )
        session.add_all([primary, literal, wildcard])
        await session.commit()
        tenant_id, warehouse_id = location.tenant_id, location.warehouse_id
        primary_id, literal_id, wildcard_id = primary.id, literal.id, wildcard.id

    exact = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": "шти-фи12"},
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["container_id"] == str(literal_id)

    ambiguous = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": "]Q3шти-фи12"},
    )
    assert ambiguous.status_code == 409, ambiguous.text
    assert ambiguous.json()["detail"]["code"] == "invalid_container_reference"

    wildcard_match = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": "wb_abc%9"},
    )
    assert wildcard_match.status_code == 200, wildcard_match.text
    assert wildcard_match.json()["container_id"] == str(wildcard_id)
    not_wildcard = await async_client.post(
        f"{BASE}/{supply_id}/pick/scan",
        headers=headers,
        json={"barcode": "WBXABC79"},
    )
    assert not_wildcard.status_code == 409, not_wildcard.text

    async with SessionLocal() as session:
        for tenant, warehouse in ((uuid.uuid4(), warehouse_id), (tenant_id, uuid.uuid4())):
            with pytest.raises(InventoryContainerScanError, match="container_scan_not_found"):
                await _resolve_fbs_container_scan(session, tenant, warehouse, "inb-ab12")
        resolved = await _resolve_fbs_container_scan(
            session, tenant_id, warehouse_id, "inb-ab12"
        )
        assert resolved.id == primary_id
