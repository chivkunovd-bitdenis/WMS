"""Ozon uses real stock sources without requiring an internal packaging receipt."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrderProduct
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import fbs_shipment_service as shipment_svc
from app.services.fbs_ozon_packaging_service import prepare_shipment_sources
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from tests.test_fbs_ozon_lane import (
    _ozon_handoff_responses,
    _seed_ozon_supply_case,
    _seed_physical_ozon_packaging,
)
from tests.test_ozon_box_assembly import seed_boxes


@pytest.mark.asyncio
async def test_ozon_without_fulfillment_snapshots_stock_before_handoff_and_writes_off_once(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _, warehouse, product, order, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    supply.status = "assembling"
    order.pack_status = "pending"
    position = FbsOrderProduct(
        order_id=order.id,
        product_id=product.id,
        ozon_sku=3001,
        position_index=0,
        quantity=3,
    )
    locations = [
        StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code=f"SOURCE-{index}",
            barcode=f"SOURCE-{uuid.uuid4().hex}",
        )
        for index in range(2)
    ]
    db_session.add_all([position, *locations])
    await db_session.flush()
    db_session.add_all(
        [
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity=quantity,
                quantity_unpacked=quantity,
                quantity_packed=0,
            )
            for location, quantity in zip(locations, [1, 2], strict=True)
        ]
    )
    await db_session.commit()
    await seed_boxes(db_session, order, supply)
    original_handoff = shipment_svc.handoff_supply

    async def inspect_before_external(*args: Any, **kwargs: Any) -> Any:
        # The recipe is durable and stock is intact before the first provider mutation.
        async with SessionLocal() as reader:
            ledger = await reader.scalar(
                select(FbsShipmentReversalLedger).where(
                    FbsShipmentReversalLedger.fbs_order_id == order.id,
                )
            )
            assert ledger is not None and ledger.shipment_movement_id is None
            assert ledger.quantity == 3
            assert sorted(
                int(str(row["quantity"])) for row in ledger.ozon_positions_json or []
            ) == [1, 2]
            stock = (
                await reader.scalars(
                    select(InventoryBalance.quantity).where(
                        InventoryBalance.product_id == product.id,
                    )
                )
            ).all()
            assert sum(stock) == 3
            assert (
                await reader.scalar(
                    select(FbsPackagingFulfillment.id).where(
                        FbsPackagingFulfillment.fbs_order_id == order.id,
                    )
                )
                is None
            )
        return await original_handoff(*args, **kwargs)

    monkeypatch.setattr(shipment_svc, "handoff_supply", inspect_before_external)
    transport = FakeMarketplaceTransport(
        endpoint_responses=_ozon_handoff_responses(),
        endpoint_response_queues={
            "/v1/carriage/get": [{"carriage_id": 901, "status": "new"}]
        },
    )
    key = f"no-receipt-{uuid.uuid4()}"
    for _ in range(2):
        result = await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key=key,
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )
        assert result.status == "in_delivery"
    balances = (
        await db_session.scalars(
            select(InventoryBalance.quantity).where(
                InventoryBalance.product_id == product.id,
            )
        )
    ).all()
    assert sum(balances) == 0
    assert sum(path == "/v1/carriage/approve" for path, _ in transport.endpoint_calls) == 1


@pytest.mark.asyncio
async def test_ozon_missing_product_fails_before_any_provider_handoff(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, _, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    order.product_id = None
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=None,
            ozon_sku=3001,
            position_index=0,
            quantity=2,
        )
    )
    await db_session.commit()
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    with pytest.raises(shipment_svc.FbsShipmentError, match="fbs_shipment_product_missing"):
        await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key=f"missing-{uuid.uuid4()}",
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )
    assert transport.endpoint_calls == []


@pytest.mark.asyncio
async def test_ozon_complete_fulfillment_keeps_its_exact_source(db_session: AsyncSession) -> None:
    tenant, _, warehouse, product, order, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            position_index=0,
            quantity=2,
        )
    )
    await db_session.commit()
    await _seed_physical_ozon_packaging(db_session, order, supply, [(product, 2)])
    await db_session.refresh(order, attribute_names=["product_positions"])
    fulfillment = await db_session.scalar(
        select(FbsPackagingFulfillment).where(
            FbsPackagingFulfillment.fbs_order_id == order.id,
        )
    )
    assert fulfillment is not None and fulfillment.ozon_packed_units_json
    expected_location = fulfillment.ozon_packed_units_json[0]["storage_location_id"]
    ledgers = await prepare_shipment_sources(
        db_session,
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        orders=[order],
    )
    assert ledgers[0].ozon_positions_json == [
        {
            "product_id": str(product.id),
            "storage_location_id": expected_location,
            "quantity": 2,
        }
    ]
    assert ledgers[0].shipment_movement_id is None


@pytest.mark.asyncio
async def test_ozon_shortage_uses_existing_negative_source_policy(db_session: AsyncSession) -> None:
    tenant, _, warehouse, _, order, _ = await _seed_ozon_supply_case(db_session, packed=True)
    await db_session.refresh(order, attribute_names=["product_positions"])
    ledgers = await prepare_shipment_sources(
        db_session,
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        orders=[order],
    )
    assert ledgers[0].negative_quantity == 1
    assert ledgers[0].shipment_movement_id is None
    assert (ledgers[0].ozon_positions_json or [])[0]["source_mode"] == "forced_negative"


@pytest.mark.asyncio
async def test_ozon_staged_recipe_updates_quantity_if_an_earlier_attempt_preceded_assembly(
    db_session: AsyncSession,
) -> None:
    tenant, _, warehouse, product, order, _ = await _seed_ozon_supply_case(db_session, packed=True)
    order.meta_details_json = {"ozon_requirements": {"kinds": []}}
    await db_session.refresh(order, attribute_names=["product_positions"])
    original = (
        await prepare_shipment_sources(
            db_session,
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            orders=[order],
        )
    )[0]
    assert original.quantity == 1
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            position_index=0,
            quantity=3,
        )
    )
    await db_session.flush()
    await db_session.refresh(order, attribute_names=["product_positions"])
    updated = (
        await prepare_shipment_sources(
            db_session,
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            orders=[order],
        )
    )[0]
    assert updated.id == original.id
    assert updated.quantity == 3
    assert sum(int(str(row["quantity"])) for row in updated.ozon_positions_json or []) == 3
