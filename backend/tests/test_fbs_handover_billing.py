"""WMS-391: handover bills once, before marketplace sorting."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.operation_fact import OperationFact
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import fbs_order_billing_service as billing
from app.services import fbs_shipment_service as shipment
from app.services.fbs_cancellation_service import reverse_fbs_order_billing
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_shipment_warehouse_sc import (
    _delivery_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["success", "marketplace_error", "billing_error", "timeout", "local_error"]
)
async def test_deliver_api_records_work_before_marketplace_sorting(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    seller, warehouse, tenant = await _setup_seller_with_token(async_client, headers, suffix)
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller,
        warehouse,
        tenant,
        wb_order_ids=[391001],
        supply_name="WMS391 handover",
    )
    async with SessionLocal() as session:
        tenant_row = await session.get(Tenant, tenant)
        assert tenant_row is not None
        tenant_row.billing_enabled_from = date(2020, 1, 1)
        await session.commit()
    record = billing.record_fbs_order_confirmed
    if outcome == "billing_error":

        async def fail_charge(session: AsyncSession, order: object, **kwargs: object) -> None:
            assert session.in_nested_transaction()
            await session.execute(text("SELECT * FROM missing_billing_table"))

        monkeypatch.setattr(billing, "record_fbs_order_confirmed", fail_charge)
    if outcome in {"marketplace_error", "timeout"}:

        async def fail_marketplace(*args: object, **kwargs: object) -> None:
            raise WildberriesClientError(
                "transport_error" if outcome == "timeout" else "upstream_error",
                status_code=None if outcome == "timeout" else 502,
            )

        monkeypatch.setattr(
            "app.services.fbs_shipment_service.deliver_marketplace_supply", fail_marketplace
        )
    key = str(uuid.uuid4())
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    payload = {"idempotency_key": key, "confirmed_preflight_version": preflight["version"]}
    url = f"/operations/fbs-supplies/{supply['id']}/deliver"
    confirmed_at = None
    if outcome == "local_error":
        write_off = shipment._write_off_delivered_orders_once

        async def fail_local(*args: object, **kwargs: object) -> None:
            raise RuntimeError("local stock write failed after marketplace confirmation")

        monkeypatch.setattr(shipment, "_write_off_delivered_orders_once", fail_local)
        with pytest.raises(RuntimeError, match="local stock write failed"):
            await async_client.post(url, headers=headers, json=payload)
        async with SessionLocal() as session:
            operation = await session.scalar(
                select(FbsWbOperation).where(FbsWbOperation.idempotency_key == key)
            )
            assert operation is not None and operation.state == "confirmed"
            confirmed_at = operation.confirmed_at
            assert confirmed_at is not None
            assert list(await session.scalars(select(BillingLedgerEntry))) == []
        monkeypatch.setattr(shipment, "_write_off_delivered_orders_once", write_off)
    response = await async_client.post(url, headers=headers, json=payload)
    if outcome in {"marketplace_error", "timeout"}:
        assert response.status_code == (504 if outcome == "timeout" else 502), response.text
        async with SessionLocal() as session:
            assert list(await session.scalars(select(BillingLedgerEntry))) == []
            assert list(await session.scalars(select(OperationFact))) == []
        if outcome == "marketplace_error":
            return

        async def confirmed(*args: object, **kwargs: object) -> str:
            return "confirmed"

        monkeypatch.setattr(
            "app.services.fbs_shipment_service.reconcile_supply_delivered", confirmed
        )
        response = await async_client.post(
            str(response.request.url), headers=headers, json=json.loads(response.request.content)
        )
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        saved_supply = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert order is not None and saved_supply is not None
        assert order.status == "in_delivery"
        if outcome == "billing_error":
            assert list(await session.scalars(select(BillingLedgerEntry))) == []
            assert list(await session.scalars(select(OperationFact))) == []
            monkeypatch.setattr(billing, "record_fbs_order_confirmed", record)
            # Late MP confirmation recovers billing using the persisted handover date.
            order.status = "sorted"
            await billing.record_fbs_order_confirmed(session, order)
            await session.commit()
        facts = [
            fact
            for fact in await session.scalars(select(OperationFact))
            if fact.source_event_id == order.id
        ]
        assert len(facts) == 1
        assert saved_supply.delivered_at is not None
        assert facts[0].occurred_at.replace(tzinfo=UTC) == saved_supply.delivered_at.replace(
            tzinfo=UTC
        )
        if confirmed_at is not None:
            assert facts[0].occurred_at == confirmed_at
        entries = list(await session.scalars(select(BillingLedgerEntry)))
        assert {entry.service_code for entry in entries} == {"fbs_order", "packing"}
        assert all(entry.quantity == Decimal(1) for entry in entries)
        original_ids = {entry.id for entry in entries}
    repeated = await async_client.post(
        str(response.request.url), headers=headers, json=json.loads(response.request.content)
    )
    assert repeated.status_code == 200, repeated.text
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.status = "sorted"
        await billing.record_fbs_order_confirmed(session, order)
        await session.commit()
        assert {
            entry.id for entry in await session.scalars(select(BillingLedgerEntry))
        } == original_ids
        if outcome == "success":
            operation = await session.scalar(
                select(FbsWbOperation).where(FbsWbOperation.idempotency_key == key)
            )
            ledger = await session.scalar(select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order.id
            ))
            assert operation is not None and ledger is not None
            assert operation.confirmed_at is not None
            expected = operation.confirmed_at.replace(tzinfo=UTC)
            order.supply_id = None
            order.status = "cancelled"
            snapshot = operation.request_summary_json
            operation.request_summary_json = {}
            await session.flush()
            # The public handover's ledger proves a detached, later cancelled order.
            assert await billing.confirmed_order_handover_dates(
                session, tenant, [order]
            ) == {order.id: expected}
            ledger.wb_operation_id = None
            operation.request_summary_json = snapshot
            await session.flush()
            # The confirmed request snapshot independently proves the same handover.
            assert await billing.confirmed_order_handover_dates(
                session, tenant, [order]
            ) == {order.id: expected}
            operation.state = "failed"
            await session.flush()
            assert await billing.confirmed_order_handover_dates(session, tenant, [order]) == {}
            operation.state = "confirmed"
            operation.operation_kind = "supply_from_orders"
            await session.flush()
            assert await billing.confirmed_order_handover_dates(session, tenant, [order]) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace,quantities", [("wb", [1]), ("ozon", [2, 3])])
async def test_handover_quantities_import_guard_and_cancellation(
    db_session: AsyncSession, marketplace: str, quantities: list[int]
) -> None:
    session = db_session
    tenant = Tenant(
        name="WMS391", billing_enabled_from=date(2020, 1, 1), slug=f"wms391-{uuid.uuid4().hex}"
    )
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Local seller")
    session.add(seller)
    await session.flush()
    products = [
        Product(tenant_id=tenant.id, seller_id=seller.id, name=str(i), sku_code=str(i))
        for i in range(len(quantities))
    ]
    session.add_all(products)
    await session.flush()
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=products[0].id,
        marketplace=marketplace,
        wb_order_id=391,
        external_order_id="OZ-391",
        status="in_delivery",
        mapping_status="mapped",
        reserve_status="released",
        deadline_at=datetime.now(UTC),
        created_at_wb=datetime.now(UTC) - timedelta(days=5),
    )
    session.add(order)
    await session.flush()
    if marketplace == "ozon":
        session.add_all(
            [
                FbsOrderProduct(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    position_index=index,
                )
                for index, (product, quantity) in enumerate(zip(products, quantities, strict=True))
            ]
        )
        await session.flush()
    await billing.record_fbs_order_confirmed(session, order)
    assert list(await session.scalars(select(BillingLedgerEntry))) == []
    assert list(await session.scalars(select(OperationFact))) == []
    if marketplace == "wb":
        for imported_status in ("sorted", "done"):
            order.status = imported_status
            await billing.record_fbs_order_confirmed(
                session, order, occurred_at=datetime.now(UTC)
            )
        assert list(await session.scalars(select(BillingLedgerEntry))) == []
        assert list(await session.scalars(select(OperationFact))) == []
    moment = datetime.now(UTC)
    order.status = "cancelled"
    await billing.charge_handed_over_orders(session, [order], occurred_at=moment)
    assert list(await session.scalars(select(BillingLedgerEntry))) == []
    order.status = "in_delivery"
    await billing.charge_handed_over_orders(session, [order], occurred_at=moment)
    await billing.charge_handed_over_orders(
        session, [order], occurred_at=moment + timedelta(days=1)
    )
    entries = list(await session.scalars(select(BillingLedgerEntry)))
    assert len(entries) == 2
    assert all(entry.quantity == Decimal(sum(quantities)) for entry in entries)
    assert all(entry.occurred_at.replace(tzinfo=UTC) == moment for entry in entries)
    fact = await session.scalar(select(OperationFact))
    assert fact is not None and fact.item_quantity == sum(quantities)
    order.status = "cancelled"
    await reverse_fbs_order_billing(session, order)
    await reverse_fbs_order_billing(session, order)
    entries = list(await session.scalars(select(BillingLedgerEntry)))
    assert len(entries) == 4
    assert sum(entry.entry_type == "reversal" for entry in entries) == 2
