"""WMS-602: scanner framing/layout must select a cell, never pick a product."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services.fbs_picking_service import FbsPickingError, _resolve_storage_location
from tests.test_fbs_pick_unload_contract import BASE, _active_pick_count, _seed_two_order_supply


@pytest.mark.asyncio
async def test_fbs_cell_scan_formats_and_scope(async_client: AsyncClient) -> None:
    headers, supply_id, product_id, location_id, _, _ = await _seed_two_order_supply(async_client)
    async with SessionLocal() as session:
        cell = await session.get(StorageLocation, location_id)
        assert cell is not None
        cell.code, cell.barcode = "Ж-1-4", "J-1-4"
        tenant_id, warehouse_id = cell.tenant_id, cell.warehouse_id
        await session.commit()
        before = (
            await session.execute(
                select(InventoryBalance.id, InventoryBalance.quantity).where(
                    InventoryBalance.product_id == product_id,
                )
            )
        ).all()

    for code in (
        "J-1-4",
        "Ж-1-4",
        "j-1-4",
        "ж-1-4",
        "О-1-4",
        "о-1-4",
        "]Q3J-1-4",
        "ъЙ3О-1-4",
        "\x02\ufeffJ-1-4\r\n\x03",
    ):
        response = await async_client.post(
            f"{BASE}/{supply_id}/pick/scan",
            headers=headers,
            json={"barcode": code, "storage_location_id": None},
        )
        assert response.status_code == 200, (code, response.text)
        assert response.json()["kind"] == "location", code
        assert response.json()["storage_location_id"] == str(location_id)
    assert await _active_pick_count(supply_id) == 0
    async with SessionLocal() as session:
        after = (
            await session.execute(
                select(InventoryBalance.id, InventoryBalance.quantity).where(
                    InventoryBalance.product_id == product_id,
                )
            )
        ).all()
        assert after == before
        for tenant, warehouse in ((uuid.uuid4(), warehouse_id), (tenant_id, uuid.uuid4())):
            assert (
                await _resolve_storage_location(
                    session,
                    tenant,
                    warehouse_id=warehouse,
                    location_barcode="]Q3J-1-4",
                )
                is None
            )

        other = StorageLocation(
            tenant_id=tenant_id, warehouse_id=warehouse_id, code="О-1-4", barcode="OTHER-CELL"
        )
        session.add(other)
        await session.flush()
        exact = await _resolve_storage_location(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            location_barcode="О-1-4",
        )
        assert exact is not None and exact.id == other.id
        with pytest.raises(FbsPickingError, match="wrong_location"):
            await _resolve_storage_location(
                session,
                tenant_id,
                warehouse_id=warehouse_id,
                location_barcode="]Q3О-1-4",
            )
