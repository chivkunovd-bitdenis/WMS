from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import inbound_intake_service as svc
from app.services.catalog_service import create_location, create_product, create_warehouse
from app.services.defect_warehouse_service import DEFECT_WAREHOUSE_CODE
from app.services.tokens import decode_access_token


async def _tenant_id(async_client: AsyncClient) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:10]
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Returns test",
            "slug": f"returns-{suffix}",
            "admin_email": f"returns-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(str(decode_access_token(response.json()["access_token"])["tenant_id"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", [None, "wildberries"])
async def test_manual_and_wb_returns_skip_separate_receiving(
    async_client: AsyncClient,
    marketplace: str | None,
) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        warehouse = await create_warehouse(
            session, tenant_id, name="Main", code=f"main-{uuid.uuid4().hex[:6]}"
        )
        product = await create_product(
            session,
            tenant_id,
            name="Returned item",
            sku_code=f"RET-{uuid.uuid4().hex[:6]}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        request = await svc.create_request(
            session,
            tenant_id,
            warehouse_id=warehouse.id,
            operation_type="return",
            marketplace=marketplace,
        )
        line = await svc.add_line(
            session,
            tenant_id,
            request.id,
            product_id=product.id,
            expected_qty=4,
        )
        assert line.actual_qty == 4
        request_id = request.id
    async with SessionLocal() as session:
        started = await svc.begin_receiving(session, tenant_id, request_id)
        assert started.status == svc.STATUS_SORTING
        assert started.lines[0].actual_qty == 4


@pytest.mark.asyncio
async def test_regular_inbound_keeps_expected_and_actual_separate(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        warehouse = await create_warehouse(
            session, tenant_id, name="Main", code=f"main-{uuid.uuid4().hex[:6]}"
        )
        product = await create_product(
            session,
            tenant_id,
            name="Inbound item",
            sku_code=f"IN-{uuid.uuid4().hex[:6]}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        request = await svc.create_request(session, tenant_id, warehouse_id=warehouse.id)
        line = await svc.add_line(
            session,
            tenant_id,
            request.id,
            product_id=product.id,
            expected_qty=4,
        )
        assert line.actual_qty is None
        request_id = request.id
    async with SessionLocal() as session:
        started = await svc.begin_receiving(session, tenant_id, request_id)
        assert started.status == svc.STATUS_RECEIVING


@pytest.mark.asyncio
async def test_return_defects_are_posted_to_one_non_operational_warehouse(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        warehouse = await create_warehouse(
            session, tenant_id, name="Main", code=f"main-{uuid.uuid4().hex[:6]}"
        )
        location = await create_location(session, tenant_id, warehouse.id, code="A-01")
        product = await create_product(
            session,
            tenant_id,
            name="Returned item",
            sku_code=f"RET-{uuid.uuid4().hex[:6]}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        request = await svc.create_request(
            session,
            tenant_id,
            warehouse_id=warehouse.id,
            operation_type="return",
        )
        line = await svc.add_line(
            session,
            tenant_id,
            request.id,
            product_id=product.id,
            expected_qty=5,
            storage_location_id=location.id,
        )
        request_id = request.id
        line_id = line.id
        product_id = product.id
        warehouse_code = warehouse.code
    async with SessionLocal() as session:
        with pytest.raises(svc.InboundIntakeError, match="defective_qty_exceeds_accepted"):
            await svc.set_line_defective_qty(
                session, tenant_id, request_id, line_id, defective_qty=6
            )
        await svc.set_line_defective_qty(
            session, tenant_id, request_id, line_id, defective_qty=2
        )
        await svc.begin_receiving(session, tenant_id, request_id)
        done = await svc.post_all_remaining(session, tenant_id, request_id)
        assert done.status == svc.STATUS_DONE

        balances = list(
            (
                await session.execute(
                    select(InventoryBalance, StorageLocation, Warehouse)
                    .join(
                        StorageLocation,
                        StorageLocation.id == InventoryBalance.storage_location_id,
                    )
                    .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
                    .where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id == product_id,
                    )
                )
            ).all()
        )
        by_warehouse = {
            warehouse_row.code: balance.quantity
            for balance, _, warehouse_row in balances
        }
        assert by_warehouse[warehouse_code] == 3
        assert by_warehouse[DEFECT_WAREHOUSE_CODE] == 2
        defect_warehouses = list(
            (
                await session.scalars(
                    select(Warehouse).where(
                        Warehouse.tenant_id == tenant_id,
                        Warehouse.code == DEFECT_WAREHOUSE_CODE,
                    )
                )
            ).all()
        )
        assert len(defect_warehouses) == 1
        assert defect_warehouses[0].is_operational is False
