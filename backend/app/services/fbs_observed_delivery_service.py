"""Account for WB delivery observed by polling, without sending a delivery request."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_shipment_source_service as source_svc
from app.services.document_event_service import record_document_event
from app.services.wildberries_fbs_client import fetch_marketplace_supply_order_ids


async def reconcile_observed_wb_delivery(
    session: AsyncSession,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    api_token: str,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> int:
    """Called only after WB supplied done=true; stock and audit remain atomic.

    A supply lock serializes polling against the interactive delivery path.
    Existing shipment/reversal records remain authoritative. Only missing
    movements for mapped orders actually present in WB are created.
    """
    if supply.marketplace != "wb":
        return 0
    # Local import avoids the shipment -> order import -> tracking cycle.
    from app.services.fbs_shipment_service import _write_off_delivered_orders_once

    async with session.begin_nested():
        await session.execute(
            select(FbsSupply.id)
            .where(FbsSupply.id == supply.id, FbsSupply.tenant_id == supply.tenant_id)
            .with_for_update()
        )
        orders = list(
            (
                await session.scalars(
                    select(FbsOrder)
                    .where(
                        FbsOrder.tenant_id == supply.tenant_id,
                        FbsOrder.seller_id == supply.seller_id,
                        FbsOrder.supply_id == supply.id,
                        FbsOrder.marketplace == "wb",
                        FbsOrder.product_id.is_not(None),
                        FbsOrder.status != FBS_ORDER_STATUS_CANCELLED,
                    )
                    .order_by(FbsOrder.id)
                    .with_for_update()
                )
            ).all()
        )
        if not orders:
            return 0
        ledgers = {
            row.fbs_order_id: row
            for row in (
                await session.scalars(
                    select(FbsShipmentReversalLedger).where(
                        FbsShipmentReversalLedger.tenant_id == supply.tenant_id,
                        FbsShipmentReversalLedger.fbs_order_id.in_([o.id for o in orders]),
                    )
                )
            ).all()
        }
        missing = [
            o
            for o in orders
            if o.id not in ledgers
            or (ledgers[o.id].shipment_movement_id is None and ledgers[o.id].reversed_at is None)
        ]
        if not missing:
            return 0
        wb_ids = set(
            await fetch_marketplace_supply_order_ids(
                http_client,
                api_token=api_token,
                supply_id=supply.wb_supply_id,
            )
        )
        missing = [o for o in missing if int(o.wb_order_id) in wb_ids]
        if not missing:
            return 0
        plan = await source_svc.plan_fbs_shipment_sources(
            session,
            tenant_id=supply.tenant_id,
            supply_warehouse_id=supply.warehouse_id,
            requests=[
                source_svc.FbsShipmentSourceRequest(
                    fbs_order_id=o.id,
                    product_id=o.product_id,
                    quantity=1,
                )
                for o in missing
                if o.product_id is not None
            ],
        )
        operation_key = f"wb-observed-delivery:{supply.id}"
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.seller_id == supply.seller_id,
                FbsWbOperation.operation_kind == "supply_delivery_reconciliation",
                FbsWbOperation.idempotency_key == operation_key,
            )
        )
        now = datetime.now(UTC)
        if operation is None:
            operation = FbsWbOperation(
                tenant_id=supply.tenant_id,
                seller_id=supply.seller_id,
                operation_kind="supply_delivery_reconciliation",
                idempotency_key=operation_key,
                wb_object_id=supply.wb_supply_id,
                wb_object_kind="supply",
                local_entity_type="fbs_supply",
                local_entity_id=supply.id,
                state="confirmed",
                confirmed_at=now,
                created_by_user_id=actor_user_id,
                response_summary_json={"wb_done": True, "external_mutation": False},
            )
            session.add(operation)
            await session.flush()
        await _write_off_delivered_orders_once(
            session,
            supply,
            missing,
            actor_user_id,
            source_plan=plan,
            operation=operation,
        )
        if supply.delivered_at is None:
            # Observation time, not a fabricated WB handover timestamp.
            supply.delivered_at = now
        await record_document_event(
            session,
            tenant_id=supply.tenant_id,
            document_type="fbs_supply",
            document_id=supply.id,
            event_type="data_changed",
            source="system",
            actor_user_id=actor_user_id,
            qty=len(missing),
            payload_json={
                "kind": "wb_observed_delivery_stock_reconciled",
                "operation_id": str(operation.id),
                "order_ids": [str(o.id) for o in missing],
            },
        )
        await session.flush()
        return len(missing)
