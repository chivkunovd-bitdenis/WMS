"""Physical pick-option sources shared by MP unload and FBS."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import pick_option_location_service
from app.services.sorting_location_service import get_or_create_sorting_location


async def _register_tenant(async_client: AsyncClient, label: str) -> uuid.UUID:
    suffix = f"{label}-{time.time_ns()}"
    email = f"{suffix}@example.com"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": label,
            "slug": suffix,
            "admin_email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        tenant_id = await session.scalar(select(User.tenant_id).where(User.email == email))
        assert tenant_id is not None
        return tenant_id


# TC-NEW-PICK-CONTAINERS-001
@pytest.mark.asyncio
async def test_shared_pick_locations_keep_totals_and_expose_physical_paths(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "pick-container-sources")
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Основной склад",
            code=f"pick-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="A-01-01",
            barcode=f"CELL-{suffix}",
        )
        session.add(cell)
        await session.flush()
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse.id
        )
        seller = Seller(tenant_id=tenant_id, name="Тестовый селлер")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Товар для подбора",
            sku_code=f"PICK-{suffix}",
        )
        session.add(product)
        await session.flush()
        intake = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        pallet = Pallet(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="П-000131",
            barcode=f"PALLET-{suffix}",
            storage_location_id=cell.id,
        )
        direct_box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            internal_barcode=f"BOX-{suffix}",
            container_kind="box",
            storage_location_id=cell.id,
        )
        sorting_cargo = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            internal_barcode=f"SORT-CARGO-{suffix}",
            container_kind="cargo_place",
        )
        session.add_all([intake, pallet, direct_box, sorting_cargo])
        await session.flush()
        nested_box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=intake.id,
            box_number=41,
            internal_barcode=f"INBOUND-BOX-{suffix}",
            pallet_id=pallet.id,
        )
        cargo_place = InboundIntakeCargoPlace(
            tenant_id=tenant_id,
            request_id=intake.id,
            place_number=9,
            internal_barcode=f"INBOUND-CARGO-{suffix}",
            pallet_id=pallet.id,
        )
        session.add_all([nested_box, cargo_place])
        await session.flush()
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=cell.id,
                    product_id=product.id,
                    quantity=5,
                    quantity_unpacked=5,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=cell.id,
                    product_id=product.id,
                    container_kind="pallet",
                    container_id=pallet.id,
                    quantity=6,
                    quantity_unpacked=6,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=cell.id,
                    product_id=product.id,
                    container_kind="box",
                    container_id=direct_box.id,
                    quantity=7,
                    quantity_unpacked=7,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=cell.id,
                    product_id=product.id,
                    container_kind="box",
                    container_id=nested_box.id,
                    quantity=3,
                    quantity_unpacked=3,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=cell.id,
                    product_id=product.id,
                    container_kind="cargo_place",
                    container_id=cargo_place.id,
                    quantity=4,
                    quantity_unpacked=4,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=sorting.id,
                    product_id=product.id,
                    container_kind="cargo_place",
                    container_id=sorting_cargo.id,
                    quantity=2,
                    quantity_unpacked=2,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()

        result = await pick_option_location_service.list_pick_option_locations(
            session,
            tenant_id,
            warehouse.id,
            [product.id],
            {(product.id, cell.id): 2},
        )

        locations = {
            location.storage_location_id: location for location in result[product.id]
        }
        regular = locations[cell.id]
        assert (
            regular.location_code,
            regular.quantity,
            regular.reserved,
            regular.available,
            regular.picked,
        ) == ("A-01-01", 25, 0, 25, 2)
        assert {(source.quantity, source.source_label) for source in regular.sources} == {
            (5, "Россыпью"),
            (6, "Палета П-000131"),
            (7, f"Короб BOX-{suffix}"),
            (3, "Короб КР-000041"),
            (4, "Грузоместо ГМ-000009"),
        }
        loose = next(source for source in regular.sources if source.is_loose)
        assert loose.container_path == ()
        direct_pallet = next(
            source
            for source in regular.sources
            if source.source_label == "Палета П-000131"
        )
        assert [item.kind for item in direct_pallet.container_path] == ["pallet"]
        assert [item.label for item in direct_pallet.container_path] == [
            "Палета П-000131"
        ]
        nested = next(
            source for source in regular.sources if source.source_label == "Короб КР-000041"
        )
        assert [item.kind for item in nested.container_path] == ["pallet", "box"]
        assert [item.label for item in nested.container_path] == [
            "Палета П-000131",
            "Короб КР-000041",
        ]
        cargo = next(
            source
            for source in regular.sources
            if source.source_label == "Грузоместо ГМ-000009"
        )
        assert [item.kind for item in cargo.container_path] == [
            "pallet",
            "cargo_place",
        ]
        assert [item.label for item in cargo.container_path] == [
            "Палета П-000131",
            "Грузоместо ГМ-000009",
        ]

        unassigned = locations[sorting.id]
        assert unassigned.location_code == "Без ячеек"
        assert unassigned.quantity == unassigned.available == 2
        assert unassigned.sources[0].source_label == f"Грузоместо SORT-CARGO-{suffix}"
        assert "__SORTING__" not in repr(unassigned)


# TC-NEW-PICK-CONTAINERS-001
@pytest.mark.asyncio
async def test_container_paths_fail_closed_outside_tenant_and_warehouse(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "pick-container-scope")
    foreign_tenant_id = await _register_tenant(async_client, "pick-container-foreign")
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Основной склад",
            code=f"main-{suffix}",
        )
        other_warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Другой склад",
            code=f"other-{suffix}",
        )
        session.add_all([warehouse, other_warehouse])
        await session.flush()
        location = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="A-FAIL-CLOSED",
            barcode=f"FAIL-CELL-{suffix}",
        )
        seller = Seller(tenant_id=tenant_id, name="Scope seller")
        session.add_all([location, seller])
        await session.flush()
        wrong_warehouse_product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Wrong warehouse container",
            sku_code=f"WRONG-WH-{suffix}",
        )
        wrong_tenant_product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Wrong tenant container",
            sku_code=f"WRONG-TENANT-{suffix}",
        )
        wrong_warehouse_box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=other_warehouse.id,
            internal_barcode=f"OTHER-WH-{suffix}",
            container_kind="box",
        )
        wrong_tenant_box = WarehouseBox(
            tenant_id=foreign_tenant_id,
            warehouse_id=warehouse.id,
            internal_barcode=f"OTHER-TENANT-{suffix}",
            container_kind="box",
        )
        session.add_all(
            [
                wrong_warehouse_product,
                wrong_tenant_product,
                wrong_warehouse_box,
                wrong_tenant_box,
            ]
        )
        await session.flush()
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=location.id,
                    product_id=wrong_warehouse_product.id,
                    container_kind="box",
                    container_id=wrong_warehouse_box.id,
                    quantity=1,
                    quantity_unpacked=1,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=location.id,
                    product_id=wrong_tenant_product.id,
                    container_kind="box",
                    container_id=wrong_tenant_box.id,
                    quantity=1,
                    quantity_unpacked=1,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()

        with pytest.raises(
            pick_option_location_service.PickOptionLocationError
        ) as warehouse_exc:
            await pick_option_location_service.list_pick_option_locations(
                session,
                tenant_id,
                warehouse.id,
                [wrong_warehouse_product.id],
                {},
            )
        assert warehouse_exc.value.code == "invalid_container_reference"

        with pytest.raises(
            pick_option_location_service.PickOptionLocationError
        ) as tenant_exc:
            await pick_option_location_service.list_pick_option_locations(
                session,
                tenant_id,
                warehouse.id,
                [wrong_tenant_product.id],
                {},
            )
        assert tenant_exc.value.code == "invalid_container_reference"
