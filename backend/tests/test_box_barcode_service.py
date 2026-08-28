from __future__ import annotations

import re
import uuid
from math import expm1

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeDistributionLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.box_barcode_service import (
    _encode_number,
    generate_box_barcode,
    is_wb_compatible_box_barcode,
)
from app.services.inbound_intake_box_service import _new_barcode as new_inbound_barcode
from app.services.marketplace_unload_box_service import (
    attach_existing_box_by_barcode,
)
from app.services.warehouse_box_service import (
    _new_barcode as new_warehouse_barcode,
)


@pytest.mark.parametrize("prefix", ["WHB", "INB"])
def test_generated_box_barcodes_are_wb_compatible_and_unique(prefix: str) -> None:
    barcodes = {generate_box_barcode(prefix) for _ in range(1_000)}

    assert len(barcodes) == 1_000
    assert all(len(barcode) == 18 for barcode in barcodes)
    assert all(barcode.startswith(f"{prefix}-") for barcode in barcodes)
    assert all(
        re.fullmatch(rf"{prefix}-[0-9A-HJKMNP-TV-Z]{{14}}", barcode)
        for barcode in barcodes
    )
    assert all(is_wb_compatible_box_barcode(barcode) for barcode in barcodes)


def test_every_physical_box_generator_uses_the_shared_format() -> None:
    generated = {
        "WHB": new_warehouse_barcode(),
        "INB": new_inbound_barcode(),
    }

    for prefix, barcode in generated.items():
        assert barcode.startswith(f"{prefix}-")
        assert len(barcode) == 18
        assert is_wb_compatible_box_barcode(barcode)


def test_collision_budget_is_below_one_in_twenty_million_at_ten_million_boxes() -> None:
    possible_suffixes = 1 << 70
    generated_boxes = 10_000_000
    collision_probability = -expm1(
        -(generated_boxes * (generated_boxes - 1)) / (2 * possible_suffixes)
    )

    assert collision_probability < 1 / 20_000_000


@pytest.mark.parametrize(
    "barcode",
    [
        "WHB-ABCDEF123456",
        "INB-ABCDEF123456",
        "custom_box-123",
    ],
)
def test_existing_box_barcode_shapes_remain_valid_inputs(barcode: str) -> None:
    assert is_wb_compatible_box_barcode(barcode)


@pytest.mark.asyncio
async def test_legacy_box_barcodes_attach_through_real_database_path(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-B02-WB-BOX-02: old WHB/INB labels still scan into an MP shipment."""
    assert async_client.base_url == "http://test"

    async with SessionLocal() as session:
        tenant = Tenant(name="Legacy box tenant", slug=f"legacy-box-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()

        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Legacy box warehouse",
            code=f"LEG-{uuid.uuid4().hex[:8]}",
        )
        seller = Seller(tenant_id=tenant.id, name="Legacy box seller")
        session.add_all([warehouse, seller])
        await session.flush()

        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Legacy box product",
            sku_code=f"LEGACY-{uuid.uuid4().hex[:8]}",
        )
        location = StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code="LEGACY-LOC",
            barcode=f"LOC-{uuid.uuid4().hex[:12]}",
        )
        inbound_request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            status="done",
        )
        unload_request = MarketplaceUnloadRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            status="confirmed",
        )
        session.add_all([product, location, inbound_request, unload_request])
        await session.flush()

        legacy_warehouse_box = WarehouseBox(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            internal_barcode="WHB-ABCDEF123456",
        )
        legacy_inbound_box = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=inbound_request.id,
            box_number=1,
            internal_barcode="INB-ABCDEF123456",
        )
        session.add_all([legacy_warehouse_box, legacy_inbound_box])
        await session.flush()

        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    quantity=1,
                    quantity_unpacked=1,
                    quantity_packed=0,
                ),
                InboundIntakeDistributionLine(
                    request_id=inbound_request.id,
                    product_id=product.id,
                    storage_location_id=location.id,
                    quantity=1,
                    box_id=legacy_inbound_box.id,
                ),
                MarketplaceUnloadLine(
                    request_id=unload_request.id,
                    product_id=product.id,
                    quantity=1,
                ),
            ]
        )
        await session.commit()

        attached_whb = await attach_existing_box_by_barcode(
            session,
            tenant.id,
            unload_request.id,
            barcode="WHB-ABCDEF123456",
            actor_user_id=None,
        )
        assert attached_whb.warehouse_box_id == legacy_warehouse_box.id
        assert attached_whb.warehouse_box is not None
        assert attached_whb.warehouse_box.internal_barcode == "WHB-ABCDEF123456"

        attached_inb = await attach_existing_box_by_barcode(
            session,
            tenant.id,
            unload_request.id,
            barcode="INB-ABCDEF123456",
            actor_user_id=None,
        )
        assert attached_inb.warehouse_box_id is None
        assert len(attached_inb.lines) == 1
        assert attached_inb.lines[0].product_id == product.id
        assert attached_inb.lines[0].quantity == 1


@pytest.mark.parametrize(
    "barcode",
    [
        "",
        "A-123",
        "WHB-123456789012345678901234567",
        "WB_123456",
        "wb_123456",
        "WHB 123456",
        "КОРОБ-123456",
        "WHB+123456",
        "WHB/123456",
    ],
)
def test_validator_rejects_values_wb_will_not_accept(barcode: str) -> None:
    assert not is_wb_compatible_box_barcode(barcode)


def test_suffix_encoder_preserves_all_70_random_bits() -> None:
    assert _encode_number(0, 14) == "0" * 14
    assert _encode_number((1 << 70) - 1, 14) == "Z" * 14


@pytest.mark.parametrize("prefix", ["", "FBS", "TOOLONG", "W-B", "ШК"])
def test_generator_rejects_invalid_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        generate_box_barcode(prefix)
