"""One-shot WMS-675 production repair for the known stale Ozon reserve projection.

Run only in the configured production API container and only after a fresh
receipt confirms every guard below.  This script uses normal SQLAlchemy models
and existing parent/product locks; it never calls conduct, billing, stock
movement, marketplace transport, sync, or a SQL UPDATE.  The default is a
locked dry run.  ``--apply`` is the single authorised commit attempt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
    RESERVE_STATUS_RELEASED,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger as Ledger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.operation_fact import OperationFact
from app.services import fbs_observed_handoff_service as observed
from app.services.fbs_packaging_integration_service import lock_order_batch_packaging_rows

TENANT = uuid.UUID("b80a893b-ab87-42b6-8fd7-6d41502c900f")
SELLER = uuid.UUID("cf6d31c5-944b-4382-af34-636ca9aa8cc3")
SUPPLY = uuid.UUID("b82d1e9a-30d2-4d7b-b52d-9775c3d266e3")
WAREHOUSE = uuid.UUID("2d968c65-4a8d-414e-9076-0f201c2dba63")
EXPECTED_STALE_ORDER_IDS = frozenset(
    uuid.UUID(value)
    for value in (
        "0d45ad7d-956e-4625-9dc5-f10c2e5b453a",
        "4c9f0057-d363-4ec3-9c9b-4006c7f50516",
        "558f8beb-a0b6-489a-a8b6-5dd3a5a494b5",
        "6444a2d9-23e0-4ddf-aa43-87abd03f27a7",
        "6c283f46-7f5b-4620-a322-096f37027c8c",
        "6fc67946-d062-49ba-ad8e-9c061a1177e1",
        "870e99a1-6435-4291-ac7d-cf0a81ab0572",
        "89d0cf5c-8811-4ef7-8420-6aa7037b21c6",
        "a8e915f1-3a6f-45de-9cfb-f9f5cae5acde",
        "b7216c03-b13d-49d8-a3e8-a7c99c29bda6",
        "c2d7a754-f334-431f-89ed-5e47d3e0c7a4",
        "ccdd5eaf-cd9b-456c-8415-0868a52fa0af",
        "d46f4e6a-c28c-4ec6-a8b7-3c9734528f53",
        "e203f00e-db36-46c0-aa1b-192539ab88b8",
    )
)
EXPECTED_FACT_IDS_SHA256 = "03e300457d58916fec01411cbe21231977bfdbdcadcc5663802d958931629722"
EXPECTED_CHARGE_IDS_SHA256 = "7e3c6ecd173fb6ecd11dcf024ee9c94e76786eec4300fe1da67bed0e0dd2b2f8"


def digest(values: object) -> str:
    return hashlib.sha256(
        json.dumps(values, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(code: str) -> None:
    raise RuntimeError(code)


async def locked_state(session) -> tuple[list[FbsOrder], dict[str, object]]:
    """Reload and prove all business guards after ordinary locks are held."""
    supply = await session.scalar(
        select(FbsSupply)
        .where(
            FbsSupply.id == SUPPLY,
            FbsSupply.tenant_id == TENANT,
            FbsSupply.seller_id == SELLER,
            FbsSupply.warehouse_id == WAREHOUSE,
            FbsSupply.source == "wms",
            FbsSupply.marketplace == "ozon",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if supply is None:
        fail("supply_scope_mismatch")
    orders = list(
        await session.scalars(
            select(FbsOrder)
            .where(
                FbsOrder.tenant_id == TENANT,
                FbsOrder.seller_id == SELLER,
                FbsOrder.supply_id == SUPPLY,
                FbsOrder.warehouse_id == WAREHOUSE,
                FbsOrder.marketplace == "ozon",
            )
            .options(selectinload(FbsOrder.product_positions))
            .order_by(FbsOrder.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(orders) != 31 or len({order.id for order in orders}) != 31:
        fail("scope_not_exact31")
    if any(len(order.product_positions) != 1 for order in orders):
        fail("composition_changed")
    if {order.id for order in orders if order.status == "done" and order.product_positions[0].reserved_quantity == 1} != EXPECTED_STALE_ORDER_IDS:
        fail("stale_order_set_changed")
    if any(
        order.product_positions[0].reserved_quantity != (1 if order.id in EXPECTED_STALE_ORDER_IDS else 0)
        for order in orders
    ):
        fail("projection_changed")
    order_ids = [order.id for order in orders]
    positions = [order.product_positions[0] for order in orders]
    if (
        await session.scalars(
            select(FbsOrderReservation)
            .where(FbsOrderReservation.fbs_order_id.in_(order_ids))
            .with_for_update()
        )
    ).first() is not None:
        fail("legacy_reservation_present")
    if (
        await session.scalars(
            select(FbsOrderProductReservation)
            .where(FbsOrderProductReservation.order_product_id.in_([row.id for row in positions]))
            .with_for_update()
        )
    ).first() is not None:
        fail("position_reservation_present")
    ledgers = list(
        await session.scalars(
            select(Ledger)
            .where(Ledger.tenant_id == TENANT, Ledger.fbs_order_id.in_(order_ids))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(ledgers) != 31 or any(item.reversed_at or item.reversal_movement_id for item in ledgers):
        fail("ledger_conflict")
    completed = sum(sum(observed.completed_quantities(item).values()) for item in ledgers)
    operation = await session.scalar(
        select(FbsWbOperation)
        .where(
            FbsWbOperation.tenant_id == TENANT,
            FbsWbOperation.seller_id == SELLER,
            FbsWbOperation.operation_kind == "observed_handoff",
            FbsWbOperation.local_entity_id == SUPPLY,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    evidence = (operation.response_summary_json or {}).get("orders") if operation else {}
    targets = sum(
        sum(int(value) for value in (evidence.get(str(order.id), {}).get("targets") or {}).values())
        for order in orders
    )
    if len(evidence) != 31 or targets != 26 or completed != 26:
        fail("missing_delta_not_zero")
    fact_ids = sorted(
        str(value)
        for value in await session.scalars(
            select(OperationFact.id).where(
                OperationFact.tenant_id == TENANT,
                OperationFact.seller_id == SELLER,
                (OperationFact.document_id.in_(order_ids) | OperationFact.source_event_id.in_(order_ids)),
            )
        )
    )
    charge_ids = sorted(
        str(value)
        for value in await session.scalars(
            select(BillingLedgerEntry.id).where(
                BillingLedgerEntry.tenant_id == TENANT,
                BillingLedgerEntry.seller_id == SELLER,
                BillingLedgerEntry.source_id.in_(order_ids),
            )
        )
    )
    if len(fact_ids) != 26 or digest(fact_ids) != EXPECTED_FACT_IDS_SHA256:
        fail("facts_changed")
    if len(charge_ids) != 52 or digest(charge_ids) != EXPECTED_CHARGE_IDS_SHA256:
        fail("charges_changed")
    return orders, {
        "orders": len(orders),
        "stale_order_ids_sha256": digest(sorted(str(value) for value in EXPECTED_STALE_ORDER_IDS)),
        "ledger_completed": completed,
        "journal_targets": targets,
        "facts_ids_sha256": digest(fact_ids),
        "charges_ids_sha256": digest(charge_ids),
        "position_reserved_quantity": sum(row.reserved_quantity for row in positions),
    }


async def run(apply: bool) -> None:
    receipt: dict[str, object] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "operation": "WMS-675 exact14 stale projection reconciliation",
        "mode": "apply" if apply else "locked_dry_run",
        "external_calls": 0,
        "forbidden_paths": ["conduct_supply", "billing", "movement", "marketplace", "sync", "SQL UPDATE"],
    }
    async with SessionLocal() as session:
        try:
            # Existing lock order: packaging parents, then the affected batch's products.
            ids = sorted(EXPECTED_STALE_ORDER_IDS, key=str)
            await lock_order_batch_packaging_rows(session, TENANT, ids)
            await observed.lock_handoff_batch_products(session, TENANT, SELLER, ids)
            orders, before = await locked_state(session)
            receipt["before"] = before
            if not apply:
                await session.rollback()
                receipt["outcome"] = "DRY_RUN_GUARDS_CONFIRMED_NO_WRITE"
                print(json.dumps(receipt, sort_keys=True))
                return
            # Narrow ORM projection reconciliation only.  Actual reservation rows
            # are already proven absent, so this changes neither availability nor stock.
            for order in orders:
                if order.id in EXPECTED_STALE_ORDER_IDS:
                    order.product_positions[0].reserved_quantity = 0
                    order.reserve_status = RESERVE_STATUS_RELEASED
            await session.flush()
            receipt["changed_positions"] = len(EXPECTED_STALE_ORDER_IDS)
            await session.commit()
            receipt["outcome"] = "COMMIT_RETURNED_READBACK_REQUIRED"
        except Exception as exc:
            await session.rollback()
            receipt["outcome"] = "NO_RETRY_COMMIT_OUTCOME_UNKNOWN_READBACK_REQUIRED"
            receipt["failure_code"] = str(exc) if str(exc).endswith((
                "mismatch", "changed", "present", "conflict", "not_zero"
            )) else "details_suppressed"
    receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="make the one authorised ORM commit")
    asyncio.run(run(parser.parse_args().apply))
