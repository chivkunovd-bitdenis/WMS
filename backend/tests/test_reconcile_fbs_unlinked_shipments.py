from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.cli.reconcile_fbs_unlinked_shipments import reconcile
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_DELIVERY, FbsOrder, FbsOrderReservation
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.product import Product
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_shipment_warehouse_sc import (
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-SHIP-STOCK-004 — exact historical repair links one negative movement.
@pytest.mark.asyncio
async def test_reconcile_unlinked_delivered_order_is_guarded_and_idempotent(
    async_client,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_name = f"Seller {suffix}"
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            name="Historical FBS gap",
            sku_code=f"HIST-FBS-{suffix[-8:]}",
            wb_barcode=f"HIST-FBS-BAR-{suffix[-8:]}",
        )
        session.add(product)
        await session.commit()

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950099],
        products=[product],
        supply_name="Historical missing write-off",
    )
    order_id = order_ids[0]
    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        order = await session.get(FbsOrder, order_id)
        assert supply_row is not None and order is not None
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        supply_row.status = FBS_SUPPLY_STATUS_IN_DELIVERY
        supply_row.delivered_at = datetime.now(UTC)
        order.status = FBS_ORDER_STATUS_IN_DELIVERY
        order.reserve_status = "reserved"
        session.add_all(
            [
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product.id,
                    warehouse_id=uuid.UUID(warehouse_id),
                    quantity=1,
                ),
                FbsShipmentReversalLedger(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product.id,
                    storage_location_id=sorting.id,
                    quantity=1,
                ),
            ]
        )
        await session.commit()

    checked = await reconcile(
        seller_name=seller_name,
        apply=False,
        allow_negative=False,
        expected_count=None,
    )
    assert checked["orders"] == 1
    assert checked["units"] == 1

    with pytest.raises(ValueError, match="expected 2 unlinked orders, found 1"):
        await reconcile(
            seller_name=seller_name,
            apply=True,
            allow_negative=True,
            expected_count=2,
        )
    with pytest.raises(ValueError, match="explicit --allow-negative"):
        await reconcile(
            seller_name=seller_name,
            apply=True,
            allow_negative=False,
            expected_count=1,
        )

    applied = await reconcile(
        seller_name=seller_name,
        apply=True,
        allow_negative=True,
        expected_count=1,
    )
    assert applied["orders"] == 1

    async with SessionLocal() as session:
        ledger = await session.scalar(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order_id
            )
        )
        assert ledger is not None and ledger.shipment_movement_id is not None
        movement = await session.get(InventoryMovement, ledger.shipment_movement_id)
        assert movement is not None
        assert movement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT
        assert movement.quantity_delta == -1
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == ledger.storage_location_id,
            )
        )
        assert balance is not None and balance.quantity == -1
        reservation = await session.scalar(
            select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order_id)
        )
        assert reservation is None

    repeated = await reconcile(
        seller_name=seller_name,
        apply=True,
        allow_negative=True,
        expected_count=0,
    )
    assert repeated["orders"] == 0
