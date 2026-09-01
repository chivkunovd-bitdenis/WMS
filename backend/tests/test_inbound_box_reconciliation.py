from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_CONTAINER_REATTACH,
    InventoryMovement,
)
from app.models.user import User
from app.services import (
    inbound_box_reconciliation_service as reconciliation_service,
)
from app.services import (
    inbound_package_catalog_service,
    pick_option_location_service,
    warehouse_map_service,
)
from app.services.catalog_service import create_product, create_warehouse
from app.services.inventory_container_service import resolve_container_scan
from app.services.sorting_location_service import get_or_create_sorting_location


async def _tenant_and_user(async_client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:12]
    email = f"box-reconcile-{suffix}@example.com"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Box reconciliation",
            "slug": f"box-reconcile-{suffix}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        return user.tenant_id, user.id


@pytest.mark.asyncio
async def test_reconciliation_caps_by_current_stock_and_preserves_original_boxes(
    async_client: AsyncClient,
) -> None:
    tenant_id, actor_user_id = await _tenant_and_user(async_client)
    async with SessionLocal() as session:
        technical = await create_warehouse(
            session, tenant_id, name="FBS technical", code=f"tech-{uuid.uuid4().hex[:6]}"
        )
        main = await create_warehouse(
            session, tenant_id, name="Main", code=f"main-{uuid.uuid4().hex[:6]}"
        )
        sorting = await get_or_create_sorting_location(session, tenant_id, main.id)
        product_one = await create_product(
            session,
            tenant_id,
            name="Sneakers",
            sku_code=f"SNEAKERS-{uuid.uuid4().hex[:6]}",
        )
        product_two = await create_product(
            session,
            tenant_id,
            name="Laces",
            sku_code=f"LACES-{uuid.uuid4().hex[:6]}",
        )
        product_zero = await create_product(
            session,
            tenant_id,
            name="Sold out accessory",
            sku_code=f"SOLD-OUT-{uuid.uuid4().hex[:6]}",
        )
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=technical.id,
            status="sorting",
            display_number="№000777",
        )
        session.add(request)
        await session.flush()
        box_one = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=request.id,
            box_number=5,
            internal_barcode=f"INB-{uuid.uuid4().hex[:12].upper()}",
        )
        box_two = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=request.id,
            box_number=6,
            internal_barcode=f"INB-{uuid.uuid4().hex[:12].upper()}",
        )
        session.add_all([box_one, box_two])
        await session.flush()
        session.add_all(
            [
                InboundIntakeBoxLine(
                    box_id=box_one.id, product_id=product_one.id, quantity=4
                ),
                InboundIntakeBoxLine(
                    box_id=box_two.id, product_id=product_one.id, quantity=6
                ),
                InboundIntakeBoxLine(
                    box_id=box_one.id, product_id=product_two.id, quantity=2
                ),
                InboundIntakeBoxLine(
                    box_id=box_two.id, product_id=product_zero.id, quantity=5
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=sorting.id,
                    product_id=product_one.id,
                    quantity=7,
                    quantity_unpacked=5,
                    quantity_packed=2,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=sorting.id,
                    product_id=product_two.id,
                    quantity=3,
                    quantity_unpacked=3,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()
        request_id = request.id
        sorting_id = sorting.id
        main_id = main.id
        product_one_id = product_one.id
        product_two_id = product_two.id
        product_zero_id = product_zero.id
        box_one_id = box_one.id
        box_two_id = box_two.id
        box_one_barcode = box_one.internal_barcode

    async with SessionLocal() as session:
        dry_run = await reconciliation_service.build_reconciliation_plan(
            session,
            request_id=request_id,
            storage_location_id=sorting_id,
        )
        assert dry_run.original_units == 17
        assert dry_run.current_units_considered == 10
        assert dry_run.target_linked_units == 9
        assert dry_run.unchanged_loose_units == 1
        by_key = {
            (row.box_id, row.product_id): row.target_box_qty
            for row in dry_run.allocations
        }
        assert by_key == {
            (box_one_id, product_one_id): 3,
            (box_two_id, product_one_id): 4,
            (box_one_id, product_two_id): 2,
            (box_two_id, product_zero_id): 0,
        }

        applied = await reconciliation_service.apply_reconciliation_plan(
            session,
            request_id=request_id,
            storage_location_id=sorting_id,
            actor_user_id=actor_user_id,
        )
        assert all(row.delta == 0 for row in applied.allocations)

    async with SessionLocal() as session:
        balances = list(
            (
                await session.scalars(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.storage_location_id == sorting_id,
                    )
                )
            ).all()
        )
        quantities = {
            (row.product_id, row.container_id): int(row.quantity) for row in balances
        }
        assert quantities[(product_one_id, box_one_id)] == 3
        assert quantities[(product_one_id, box_two_id)] == 4
        assert quantities[(product_two_id, box_one_id)] == 2
        assert quantities[(product_zero_id, box_two_id)] == 0
        assert quantities[(product_two_id, None)] == 1
        assert sum(row.quantity for row in balances) == 10
        assert sum(row.quantity_packed for row in balances) == 2

        boxes = list(
            (
                await session.scalars(
                    select(InboundIntakeBox).where(
                        InboundIntakeBox.id.in_([box_one_id, box_two_id])
                    )
                )
            ).all()
        )
        assert {box.storage_location_id for box in boxes} == {sorting_id}

        movements_before = int(
            await session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.movement_type
                    == MOVEMENT_TYPE_CONTAINER_REATTACH
                )
            )
            or 0
        )
        assert movements_before == 6
        assert int(
            await session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.movement_type
                    == MOVEMENT_TYPE_CONTAINER_REATTACH,
                    InventoryMovement.container_id.is_not(None),
                )
            )
            or 0
        ) == 3

        scan = await resolve_container_scan(
            session, tenant_id, main_id, box_one_barcode
        )
        assert (scan.kind, scan.id, scan.code) == ("box", box_one_id, "КР-000005")

        pick_options = await pick_option_location_service.list_pick_option_locations(
            session,
            tenant_id,
            main_id,
            [product_one_id],
            {},
        )
        sources = pick_options[product_one_id][0].sources
        assert {(source.quantity, source.source_label) for source in sources} == {
            (3, "Короб КР-000005"),
            (4, "Короб КР-000006"),
        }

        packages = await inbound_package_catalog_service.list_current_packages(
            session, tenant_id
        )
        catalog_box_one = next(item for item in packages if item.id == box_one_id)
        assert catalog_box_one.number == 5
        assert catalog_box_one.internal_barcode == box_one_barcode
        assert catalog_box_one.warehouse_name == "Main"
        assert catalog_box_one.remaining_qty == 5
        catalog_box_two = next(item for item in packages if item.id == box_two_id)
        assert {line.product_id for line in catalog_box_two.lines} == {product_one_id}
        assert catalog_box_two.remaining_qty == 4

        warehouse_map = await warehouse_map_service.get_warehouse_map(
            session, tenant_id, main_id
        )

        def product_units(nodes: list[dict[str, Any]]) -> int:
            total = 0
            for node in nodes:
                if node["kind"] == "product":
                    total += int(node["qty"])
                else:
                    total += product_units(node["children"])
            return total

        assert product_units(warehouse_map["unassigned"]) == 10
        assert sum(
            product_units(cell["children"]) for cell in warehouse_map["cells"]
        ) == 0

        await reconciliation_service.apply_reconciliation_plan(
            session,
            request_id=request_id,
            storage_location_id=sorting_id,
            actor_user_id=actor_user_id,
        )
        movements_after = int(
            await session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.movement_type
                    == MOVEMENT_TYPE_CONTAINER_REATTACH
                )
            )
            or 0
        )
        assert movements_after == movements_before
