from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.scan_resolver_service import ScanResolverError, resolve_any_scan


async def _register_tenant(async_client: AsyncClient, label: str) -> uuid.UUID:
    suffix = str(time.time_ns())
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Scan resolver {label} {suffix}",
            "slug": f"scan-resolver-{label}-{suffix}",
            "admin_email": f"scan-resolver-{label}-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return uuid.UUID(me.json()["tenant_id"])


async def _seed_objects(tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    warehouse_one = Warehouse(
        tenant_id=tenant_id,
        name="Основной склад",
        code="main",
        barcode="WAREHOUSE-BARCODE",
    )
    warehouse_two = Warehouse(
        tenant_id=tenant_id,
        name="Резервный склад",
        code="reserve",
        barcode="WAREHOUSE-TWO-BARCODE",
    )
    seller = Seller(tenant_id=tenant_id, name="Селлер сканирования")
    async with SessionLocal() as session:
        session.add_all([warehouse_one, warehouse_two, seller])
        await session.flush()

        cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_one.id,
            code="Cell-A",
            barcode="CELL-BARCODE",
        )
        shared_cell_one = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_one.id,
            code="SHARED-CELL",
            barcode="SHARED-CELL-BARCODE-ONE",
        )
        shared_cell_two = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_two.id,
            code="SHARED-CELL",
            barcode="SHARED-CELL-BARCODE-TWO",
        )
        foreign_warehouse_cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_two.id,
            code="OTHER-CELL",
            barcode="OTHER-CELL-BARCODE",
        )
        collision_cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_one.id,
            code="COLLISION-CODE",
            barcode="COLLISION-CELL-BARCODE",
        )
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Футболка синяя",
            sku_code="PRODUCT-SKU",
            wb_barcode="PRODUCT-BARCODE",
        )
        collision_product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Товар с пересекающимся кодом",
            sku_code="COLLISION-SKU",
            wb_barcode="COLLISION-CODE",
        )
        intake = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_one.id,
            seller_id=seller.id,
            status="sorting",
            display_number="ПРИ-0001",
        )
        session.add_all(
            [
                cell,
                shared_cell_one,
                shared_cell_two,
                foreign_warehouse_cell,
                collision_cell,
                product,
                collision_product,
                intake,
            ]
        )
        await session.flush()

        pallet = InboundIntakeCargoPlace(
            tenant_id=tenant_id,
            request_id=intake.id,
            place_number=1,
            internal_barcode="PALLET-BARCODE",
        )
        inbound_box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=intake.id,
            box_number=2,
            internal_barcode="INBOUND-BOX-BARCODE",
        )
        warehouse_box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse_one.id,
            internal_barcode="BOX-BARCODE",
        )
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller.id,
            warehouse_id=warehouse_one.id,
            wb_supply_id="WB-SUPPLY-SCAN",
            name="Поставка для сканирования",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add_all([pallet, inbound_box, warehouse_box, supply])
        await session.flush()

        cargo_place = FbsTrbx(
            supply_id=supply.id,
            wb_trbx_id="CARGO-PLACE-BARCODE",
        )
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller.id,
            warehouse_id=warehouse_one.id,
            product_id=product.id,
            supply_id=supply.id,
            wb_order_id=880001,
            wb_barcode=product.wb_barcode,
            sticker_code="880001 0001",
            sticker_barcode="ORDER-BARCODE",
            created_at_wb=datetime.now(tz=UTC) - timedelta(hours=1),
            deadline_at=datetime.now(tz=UTC) + timedelta(days=1),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            status=FBS_ORDER_STATUS_IN_SUPPLY,
        )
        session.add_all([cargo_place, order])
        await session.commit()

    return {
        "warehouse_one": warehouse_one.id,
        "warehouse_two": warehouse_two.id,
        "warehouse": warehouse_one.id,
        "cell": cell.id,
        "pallet": pallet.id,
        "box": warehouse_box.id,
        "inbound_box": inbound_box.id,
        "cargo_place": cargo_place.id,
        "product": product.id,
        "fbs_order": order.id,
    }


@pytest.mark.asyncio
async def test_each_supported_type_is_found_by_its_scan_code(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "types")
    seeded = await _seed_objects(tenant_id)
    expectations = {
        "CELL-BARCODE": "cell",
        "PALLET-BARCODE": "pallet",
        "BOX-BARCODE": "box",
        "INBOUND-BOX-BARCODE": "box",
        "CARGO-PLACE-BARCODE": "cargo_place",
        "PRODUCT-BARCODE": "product",
        "ORDER-BARCODE": "fbs_order",
        "WAREHOUSE-BARCODE": "warehouse",
    }

    async with SessionLocal() as session:
        for code, expected_type in expectations.items():
            match = await resolve_any_scan(session, tenant_id, code)
            assert match.type == expected_type
            seeded_key = (
                expected_type if code != "INBOUND-BOX-BARCODE" else "inbound_box"
            )
            assert match.id == seeded[seeded_key]
            assert match.name
        product = await resolve_any_scan(session, tenant_id, "PRODUCT-BARCODE")
        assert product.warehouse_id is None


@pytest.mark.asyncio
async def test_tenant_cannot_resolve_another_tenants_object(
    async_client: AsyncClient,
) -> None:
    tenant_a = await _register_tenant(async_client, "tenant-a")
    tenant_b = await _register_tenant(async_client, "tenant-b")
    await _seed_objects(tenant_a)

    async with SessionLocal() as session:
        with pytest.raises(ScanResolverError) as caught:
            await resolve_any_scan(session, tenant_b, "BOX-BARCODE")
    assert caught.value.code == "scan_not_found"


@pytest.mark.asyncio
async def test_ambiguous_code_returns_all_matches_instead_of_first(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "ambiguous")
    await _seed_objects(tenant_id)

    async with SessionLocal() as session:
        with pytest.raises(ScanResolverError) as caught:
            await resolve_any_scan(session, tenant_id, "COLLISION-CODE")
    assert caught.value.code == "scan_ambiguous"
    assert [match.type for match in caught.value.matches] == ["cell", "product"]


@pytest.mark.asyncio
async def test_unknown_code_returns_clear_failure(async_client: AsyncClient) -> None:
    tenant_id = await _register_tenant(async_client, "unknown")

    async with SessionLocal() as session:
        with pytest.raises(ScanResolverError) as caught:
            await resolve_any_scan(session, tenant_id, "NOT-A-WAREHOUSE-OBJECT")
    assert caught.value.code == "scan_not_found"
    assert caught.value.message == "Объект с таким кодом не найден."


@pytest.mark.asyncio
async def test_cell_code_normalization_removes_controls_trims_and_ignores_case(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "normalization")
    seeded = await _seed_objects(tenant_id)

    async with SessionLocal() as session:
        match = await resolve_any_scan(session, tenant_id, " \u200bcElL-a\u200d\n ")
    assert match.type == "cell"
    assert match.id == seeded["cell"]


@pytest.mark.asyncio
async def test_warehouse_filter_narrows_matches_and_rejects_another_warehouse(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _register_tenant(async_client, "warehouse-filter")
    seeded = await _seed_objects(tenant_id)

    async with SessionLocal() as session:
        with pytest.raises(ScanResolverError) as ambiguous:
            await resolve_any_scan(session, tenant_id, "SHARED-CELL")
        assert ambiguous.value.code == "scan_ambiguous"

        narrowed = await resolve_any_scan(
            session,
            tenant_id,
            "SHARED-CELL",
            warehouse_id=seeded["warehouse_one"],
        )
        assert narrowed.type == "cell"
        assert narrowed.warehouse_id == seeded["warehouse_one"]

        with pytest.raises(ScanResolverError) as wrong_warehouse:
            await resolve_any_scan(
                session,
                tenant_id,
                "OTHER-CELL-BARCODE",
                warehouse_id=seeded["warehouse_one"],
            )
        assert wrong_warehouse.value.code == "scan_not_found"
        assert "выбранном складе" in wrong_warehouse.value.message
