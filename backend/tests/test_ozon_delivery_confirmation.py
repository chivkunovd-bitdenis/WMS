"""WMS-375: the Ozon handoff confirms known shortage and ignores polling locks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import fbs_shipment_service as shipment_svc
from app.services.fbs_ozon_packaging_service import prepare_shipment_sources
from app.services.fbs_supply_reconcile_service import (
    create_pending_deliver_operation,
    request_hash_for_deliver,
)
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from tests.test_fbs_ozon_lane import (
    _ozon_handoff_responses,
    _seed_ozon_supply_case,
    _seed_ready_for_handoff,
)


@pytest.mark.parametrize("staged", [False, True])
async def test_ozon_known_shortage_requires_confirmation_and_preserves_exact_source(
    db_session: AsyncSession, staged: bool,
) -> None:
    tenant, _, warehouse, product, order, supply = await _seed_ozon_supply_case(
        db_session, packed=True,
    )
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    if staged:
        await db_session.refresh(order, attribute_names=["product_positions"])
        await prepare_shipment_sources(
            db_session, tenant_id=tenant.id, warehouse_id=warehouse.id, orders=[order],
        )
    balance = await db_session.scalar(select(InventoryBalance).where(
        InventoryBalance.product_id == product.id,
    ))
    assert balance is not None
    source_id = balance.storage_location_id
    balance.quantity = 0
    balance.quantity_unpacked = 0
    balance.quantity_packed = 0
    await db_session.commit()

    preflight = await shipment_svc.preflight_delivery(
        db_session, tenant.id, supply.id, AsyncMock(), actor_user_id=None,
    )
    warnings = [check for check in preflight.checks if check.code == "negative_stock"]
    assert preflight.can_deliver
    assert len(warnings) == 1
    assert warnings[0].severity == "warning" and warnings[0].order_id == order.id
    assert "1 шт." in warnings[0].message
    if not staged:
        assert await db_session.scalar(select(func.count()).select_from(
            FbsShipmentReversalLedger,
        )) == 0
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    provider = OzonMarketplaceProvider(transport=transport)
    with pytest.raises(shipment_svc.FbsShipmentError, match="negative_stock_confirmation_required"):
        await shipment_svc.deliver_supply(
            db_session, tenant.id, supply.id, AsyncMock(), idempotency_key="unconfirmed",
            actor_user_id=None, ozon_provider=provider,
        )
    assert not transport.endpoint_calls
    # Packing/status facts do not invalidate an informed confirmation of minus.
    order.pack_status = "pending"
    order.status = "assembling"
    await db_session.commit()
    for _ in range(2):
        await shipment_svc.deliver_supply(
            db_session, tenant.id, supply.id, AsyncMock(), idempotency_key="confirmed",
            confirmed_preflight_version=preflight.version, actor_user_id=None,
            ozon_provider=provider,
        )
    ledger = await db_session.scalar(select(FbsShipmentReversalLedger).where(
        FbsShipmentReversalLedger.fbs_order_id == order.id,
    ))
    assert ledger is not None and ledger.ozon_positions_json
    assert ledger.negative_quantity == 1
    row = ledger.ozon_positions_json[0]
    assert row["storage_location_id"] == str(source_id)
    movement = await db_session.get(InventoryMovement, uuid.UUID(str(row["movement_id"])))
    assert movement is not None and movement.quantity_delta == -1
    await db_session.refresh(balance)
    assert balance.quantity == -1
    assert sum(path == "/v1/carriage/create" for path, _ in transport.endpoint_calls) == 1


async def test_ozon_shortage_appearing_after_preflight_requires_new_confirmation(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    before = await shipment_svc.preflight_delivery(
        db_session, tenant.id, supply.id, AsyncMock(), actor_user_id=None,
    )
    assert not any(check.code == "negative_stock" for check in before.checks)
    await db_session.execute(update(InventoryBalance).where(
        InventoryBalance.product_id == product.id,
    ).values(quantity=0, quantity_unpacked=0, quantity_packed=0))
    await db_session.commit()
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    with pytest.raises(shipment_svc.FbsShipmentError, match="stale_preflight"):
        await shipment_svc.deliver_supply(
            db_session, tenant.id, supply.id, AsyncMock(), idempotency_key="stale",
            confirmed_preflight_version=before.version, actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )
    assert not transport.endpoint_calls
    assert await db_session.scalar(select(func.count()).select_from(
        FbsShipmentReversalLedger,
    )) == 0
    after = await shipment_svc.preflight_delivery(
        db_session, tenant.id, supply.id, AsyncMock(), actor_user_id=None,
    )
    assert after.version != before.version
    assert any(check.code == "negative_stock" for check in after.checks)


async def test_ozon_stock_polling_is_not_another_delivery(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    held_namespaces = {"ozon"}  # the active stock poll owns the existing seller scope

    @asynccontextmanager
    async def occupied_by_poll(
        lock_session: AsyncSession, seller_id: uuid.UUID, marketplace: str,
    ) -> AsyncIterator[bool]:
        assert lock_session is not db_session and seller_id == supply.seller_id
        acquired = marketplace not in held_namespaces
        if acquired:
            held_namespaces.add(marketplace)
        try:
            yield acquired
        finally:
            if acquired:
                held_namespaces.remove(marketplace)

    monkeypatch.setattr(shipment_svc, "marketplace_seller_lock", occupied_by_poll)
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    delivered = await shipment_svc.deliver_supply(
        db_session, tenant.id, supply.id, AsyncMock(), idempotency_key="during-poll",
        actor_user_id=None, ozon_provider=OzonMarketplaceProvider(transport=transport),
    )
    assert delivered.status == "in_delivery"
    assert held_namespaces == {"ozon"}
    assert sum(path == "/v1/carriage/create" for path, _ in transport.endpoint_calls) == 1


async def test_ozon_known_external_handoff_recovers_without_a_new_minus_confirmation(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    operation = await create_pending_deliver_operation(
        db_session, tenant_id=tenant.id, seller_id=supply.seller_id,
        local_supply_id=supply.id, idempotency_key="approved-before-crash",
        request_hash=request_hash_for_deliver(
            supply_id=supply.id, confirmed_preflight_version=None,
        ), confirmed_preflight_version=None,
    )
    operation.request_summary_json = {
        **(operation.request_summary_json or {}),
        "ozon_handoff_progress": {"carriage_id": 901, "carriage_approved": True},
    }
    await db_session.execute(update(InventoryBalance).where(
        InventoryBalance.product_id == product.id,
    ).values(quantity=0, quantity_unpacked=0, quantity_packed=0))
    await db_session.commit()
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    delivered = await shipment_svc.deliver_supply(
        db_session, tenant.id, supply.id, AsyncMock(), idempotency_key="approved-before-crash",
        actor_user_id=None, ozon_provider=OzonMarketplaceProvider(transport=transport),
    )
    assert delivered.status == "in_delivery"
    assert all(path not in {"/v1/carriage/create", "/v1/carriage/approve"}
               for path, _ in transport.endpoint_calls)
    assert await db_session.scalar(select(func.sum(InventoryBalance.quantity)).where(
        InventoryBalance.product_id == product.id,
    )) == -1
