"""Deterministic, idempotent order selection for WMS-514 scan printing.

The selection is a workflow fact, not proof that a label left the physical
printer and not proof that the unit was packed.  We store it in the existing
document event stream so a repeated delivery can recover the same order while
the next intentional scan advances to the next unit.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document_event import (
    DOCUMENT_TYPE_FBS_SUPPLY,
    EVENT_DATA_CHANGED,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder
from app.models.fbs_supply import FbsSupply
from app.services.document_event_service import record_document_event
from app.services.fbs_picking_order_service import picking_list_order_key

_EVENT_KIND = "wms514_scan_auto_print"


class FbsScanAutoPrintError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FbsScanAutoPrintSelection:
    scan_id: uuid.UUID
    order_id: uuid.UUID
    wb_order_id: int
    replayed: bool


def _scan_request_digest(supply_id: uuid.UUID, key: str) -> str:
    return hashlib.sha256(f"{supply_id}:{key}".encode()).hexdigest()


def _order_reservation_key(supply_id: uuid.UUID, order_id: uuid.UUID) -> str:
    digest = hashlib.sha256(f"{supply_id}:{order_id}".encode()).hexdigest()
    return f"wms514-order:{digest}"


def _selection_payload(
    *,
    barcode: str,
    order: FbsOrder,
    request_digest: str,
    print_qr: bool,
    print_chz: bool,
) -> dict[str, object]:
    return {
        "kind": _EVENT_KIND,
        "barcode": barcode,
        "request_digest": request_digest,
        "order_id": str(order.id),
        "wb_order_id": int(order.wb_order_id),
        "print_qr": print_qr,
        "print_chz": print_chz,
    }


def _selection_from_event(
    event: DocumentEvent,
    *,
    supply_id: uuid.UUID,
    barcode: str,
    print_qr: bool,
    print_chz: bool,
) -> FbsScanAutoPrintSelection:
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_FBS_SUPPLY
        or event.document_id != supply_id
        or payload.get("kind") != _EVENT_KIND
        or payload.get("barcode") != barcode
        or payload.get("print_qr") != print_qr
        or payload.get("print_chz") != print_chz
    ):
        raise FbsScanAutoPrintError("idempotency_key_reused")
    try:
        order_id = uuid.UUID(str(payload["order_id"]))
        wb_order_id = int(payload["wb_order_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FbsScanAutoPrintError("scan_selection_corrupt") from exc
    return FbsScanAutoPrintSelection(
        scan_id=event.id,
        order_id=order_id,
        wb_order_id=wb_order_id,
        replayed=True,
    )


async def select_order_for_product_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    barcode: str,
    idempotency_key: str,
    print_qr: bool,
    print_chz: bool,
    actor_user_id: uuid.UUID,
) -> FbsScanAutoPrintSelection:
    raw_barcode = barcode.strip()
    key = idempotency_key.strip()
    if not raw_barcode:
        raise FbsScanAutoPrintError("barcode_empty")
    if not key:
        raise FbsScanAutoPrintError("missing_idempotency_key")

    # One supply row is the concurrency boundary for all product scans in the
    # workspace.  Different scan ids therefore cannot select the same unit.
    supply = await session.scalar(
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .with_for_update()
    )
    if supply is None:
        raise FbsScanAutoPrintError("supply_not_found")
    if supply.marketplace != "wb":
        raise FbsScanAutoPrintError("scan_auto_print_wb_only")

    request_digest = _scan_request_digest(supply_id, key)

    orders = list(
        (
            await session.scalars(
                select(FbsOrder)
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.supply_id == supply_id,
                    FbsOrder.seller_id == supply.seller_id,
                    FbsOrder.marketplace == "wb",
                )
                .options(selectinload(FbsOrder.product))
                .order_by(FbsOrder.id)
                .with_for_update()
            )
        ).all()
    )
    matching = [
        order
        for order in orders
        if order.status != FBS_ORDER_STATUS_CANCELLED
        and raw_barcode
        in {
            value
            for value in (
                order.wb_barcode,
                order.product.wb_barcode if order.product is not None else None,
            )
            if value
        }
    ]
    if not matching:
        raise FbsScanAutoPrintError("scan_product_not_found")
    product_ids = {order.product_id for order in matching if order.product_id is not None}
    if len(product_ids) != 1 or any(order.product_id is None for order in matching):
        raise FbsScanAutoPrintError("scan_product_ambiguous")

    while True:
        scan_events = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.tenant_id == tenant_id,
                        DocumentEvent.document_type == DOCUMENT_TYPE_FBS_SUPPLY,
                        DocumentEvent.document_id == supply_id,
                        DocumentEvent.event_type == EVENT_DATA_CHANGED,
                    )
                    .order_by(DocumentEvent.occurred_at, DocumentEvent.id)
                )
            ).all()
        )
        served_order_ids: set[uuid.UUID] = set()
        for event in scan_events:
            payload = event.payload_json or {}
            if payload.get("kind") != _EVENT_KIND:
                continue
            if payload.get("request_digest") == request_digest:
                return _selection_from_event(
                    event,
                    supply_id=supply_id,
                    barcode=raw_barcode,
                    print_qr=print_qr,
                    print_chz=print_chz,
                )
            try:
                served_order_ids.add(uuid.UUID(str(payload["order_id"])))
            except (KeyError, TypeError, ValueError):
                continue

        candidates = [order for order in matching if order.id not in served_order_ids]
        if not candidates:
            raise FbsScanAutoPrintError("scan_product_exhausted")
        selected = min(candidates, key=picking_list_order_key)
        reservation_key = _order_reservation_key(supply_id, selected.id)
        payload = _selection_payload(
            barcode=raw_barcode,
            order=selected,
            request_digest=request_digest,
            print_qr=print_qr,
            print_chz=print_chz,
        )
        inserted = await record_document_event(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_FBS_SUPPLY,
            document_id=supply_id,
            event_type=EVENT_DATA_CHANGED,
            source=SOURCE_USER,
            actor_user_id=actor_user_id,
            product_id=selected.product_id,
            payload_json=payload,
            idempotency_key=reservation_key,
        )
        if not inserted:
            # A concurrent scan reserved this unit.  Reload the durable facts:
            # the same request will find its own event; a different request
            # deterministically advances to the next unit.
            continue
        saved_event = await session.scalar(
            select(DocumentEvent).where(
                DocumentEvent.tenant_id == tenant_id,
                DocumentEvent.idempotency_key == reservation_key,
            )
        )
        if saved_event is None:
            raise FbsScanAutoPrintError("scan_selection_not_saved")
        return FbsScanAutoPrintSelection(
            scan_id=saved_event.id,
            order_id=selected.id,
            wb_order_id=int(selected.wb_order_id),
            replayed=False,
        )
