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
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document_event import (
    DOCUMENT_TYPE_FBS_SUPPLY,
    EVENT_DATA_CHANGED,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import (
    FBS_ORDER_MARKING_FROZEN_STATUSES,
    FBS_ORDER_MARKING_WRITE_STATUSES,
    FBS_ORDER_STATUS_CANCELLED,
    MARKING_KIND_SGTIN,
    META_STATUS_REJECTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.services.document_event_service import record_document_event
from app.services.fbs_picking_order_service import picking_list_order_key

_EVENT_KIND = "wms514_scan_auto_print"
_TARGET_EVENT_KIND = "wms514_scan_auto_print_target"
_PRINT_TARGETS = frozenset({"qr", "chz"})


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


@dataclass(frozen=True)
class FbsScanAutoPrintTargetClaim:
    claimed: bool
    started: bool


@dataclass(frozen=True)
class FbsScanAutoPrintReprintRecovery:
    status: Literal["not_attempted", "available", "started", "outcome_unknown"]
    kiz: str | None = None


@dataclass(frozen=True)
class _FbsScanAutoPrintTargetState:
    started: bool
    active_claim: str | None
    active_marking_id: uuid.UUID | None
    had_release: bool
    released_marking_id: uuid.UUID | None


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
    reprint_chz: bool,
) -> dict[str, object]:
    return {
        "kind": _EVENT_KIND,
        "barcode": barcode,
        "request_digest": request_digest,
        "order_id": str(order.id),
        "wb_order_id": int(order.wb_order_id),
        "print_qr": print_qr,
        "print_chz": print_chz,
        "reprint_chz": reprint_chz,
    }


def _selection_from_event(
    event: DocumentEvent,
    *,
    supply_id: uuid.UUID,
    barcode: str,
    print_qr: bool,
    print_chz: bool,
    reprint_chz: bool,
) -> FbsScanAutoPrintSelection:
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_FBS_SUPPLY
        or event.document_id != supply_id
        or payload.get("kind") != _EVENT_KIND
        or payload.get("barcode") != barcode
        or payload.get("print_qr") != print_qr
        or payload.get("print_chz") != print_chz
        or payload.get("reprint_chz") != reprint_chz
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
    reprint_chz: bool,
    actor_user_id: uuid.UUID,
) -> FbsScanAutoPrintSelection:
    # Fail closed before even reading the supply.  The all-off workstation
    # state is deliberately not a selection mode: it must leave no durable
    # reservation/event and must not consume the first physical unit.
    if not print_qr and not print_chz and not reprint_chz:
        raise FbsScanAutoPrintError("scan_auto_print_disabled")
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
        and (
            not reprint_chz
            or (
                order.status in FBS_ORDER_MARKING_WRITE_STATUSES
                and order.status not in FBS_ORDER_MARKING_FROZEN_STATUSES
            )
        )
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
                    reprint_chz=reprint_chz,
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
            reprint_chz=reprint_chz,
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


def _target_attempt_digest(scan_id: uuid.UUID, target: str, attempt_key: str) -> str:
    return hashlib.sha256(f"{scan_id}:{target}:{attempt_key}".encode()).hexdigest()


def _target_event_key(
    scan_id: uuid.UUID,
    target: str,
    action: str,
    attempt_digest: str,
) -> str:
    digest = hashlib.sha256(
        f"{scan_id}:{target}:{action}:{attempt_digest}".encode()
    ).hexdigest()
    return f"wms514-print:{digest}"


async def _selection_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
    *,
    lock_supply: bool,
) -> DocumentEvent:
    supply_stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id
    )
    if lock_supply:
        supply_stmt = supply_stmt.with_for_update()
    supply = await session.scalar(supply_stmt)
    if supply is None:
        raise FbsScanAutoPrintError("supply_not_found")
    event = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.id == scan_id,
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.document_type == DOCUMENT_TYPE_FBS_SUPPLY,
            DocumentEvent.document_id == supply_id,
            DocumentEvent.event_type == EVENT_DATA_CHANGED,
        )
    )
    if event is None or (event.payload_json or {}).get("kind") != _EVENT_KIND:
        raise FbsScanAutoPrintError("scan_selection_not_found")
    return event


async def _locked_selection_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> DocumentEvent:
    return await _selection_event(
        session,
        tenant_id,
        supply_id,
        scan_id,
        lock_supply=True,
    )


async def _target_state(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
    target: str,
) -> _FbsScanAutoPrintTargetState:
    events = list(
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
    started = False
    active_claim: str | None = None
    active_marking_id: uuid.UUID | None = None
    had_release = False
    released_marking_id: uuid.UUID | None = None
    for event in events:
        payload = event.payload_json or {}
        if (
            payload.get("kind") != _TARGET_EVENT_KIND
            or payload.get("scan_id") != str(scan_id)
            or payload.get("target") != target
        ):
            continue
        action = payload.get("action")
        attempt_digest = payload.get("attempt_digest")
        if not isinstance(attempt_digest, str):
            continue
        if action == "claim" and not started and active_claim is None:
            active_claim = attempt_digest
            try:
                active_marking_id = uuid.UUID(str(payload["marking_id"]))
            except (KeyError, TypeError, ValueError):
                active_marking_id = None
        elif action == "release" and active_claim == attempt_digest:
            had_release = True
            released_marking_id = active_marking_id
            active_claim = None
            active_marking_id = None
        elif action == "started":
            started = True
            active_claim = None
            active_marking_id = None
    return _FbsScanAutoPrintTargetState(
        started=started,
        active_claim=active_claim,
        active_marking_id=active_marking_id,
        had_release=had_release,
        released_marking_id=released_marking_id,
    )


async def _current_reprint_marking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    selection_event: DocumentEvent,
) -> FbsOrderMarking | None:
    try:
        order_id = uuid.UUID(str((selection_event.payload_json or {})["order_id"]))
    except (KeyError, TypeError, ValueError):
        raise FbsScanAutoPrintError("scan_selection_corrupt") from None
    marking: FbsOrderMarking | None = await session.scalar(
        select(FbsOrderMarking)
        .join(FbsOrder, FbsOrder.id == FbsOrderMarking.order_id)
        .where(
            FbsOrderMarking.tenant_id == tenant_id,
            FbsOrderMarking.order_id == order_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
            FbsOrderMarking.meta_status != META_STATUS_REJECTED,
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
        )
        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
        .limit(1)
    )
    return marking


async def recover_released_reprint_kiz(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> FbsScanAutoPrintReprintRecovery:
    """Return only the canonical KIZ of this scan's released print claim.

    A missing claim means the operator still has to scan a KIZ.  An active
    claim is an unknown physical outcome and a started target is already done;
    neither may produce another copy.  A released claim is retryable only while
    its exact marking remains the current active marking of the selected order.
    """
    selection_event = await _selection_event(
        session,
        tenant_id,
        supply_id,
        scan_id,
        lock_supply=False,
    )
    if (selection_event.payload_json or {}).get("reprint_chz") is not True:
        return FbsScanAutoPrintReprintRecovery(status="not_attempted")
    state = await _target_state(session, tenant_id, supply_id, scan_id, "chz")
    if state.started:
        return FbsScanAutoPrintReprintRecovery(status="started")
    if state.active_claim is not None:
        return FbsScanAutoPrintReprintRecovery(status="outcome_unknown")
    if not state.had_release:
        return FbsScanAutoPrintReprintRecovery(status="not_attempted")
    if state.released_marking_id is None:
        return FbsScanAutoPrintReprintRecovery(status="outcome_unknown")
    current = await _current_reprint_marking(
        session, tenant_id, supply_id, selection_event
    )
    if current is None or current.id != state.released_marking_id:
        return FbsScanAutoPrintReprintRecovery(status="outcome_unknown")
    return FbsScanAutoPrintReprintRecovery(status="available", kiz=current.value)


def _validate_target(selection_event: DocumentEvent, target: str) -> None:
    if target not in _PRINT_TARGETS:
        raise FbsScanAutoPrintError("scan_print_target_invalid")
    payload = selection_event.payload_json or {}
    enabled = (
        payload.get("print_qr") is True
        if target == "qr"
        else payload.get("print_chz") is True or payload.get("reprint_chz") is True
    )
    if not enabled:
        raise FbsScanAutoPrintError("scan_print_target_disabled")


def _validate_attempt_key(attempt_key: str) -> str:
    key = attempt_key.strip()
    if not key:
        raise FbsScanAutoPrintError("print_claim_key_required")
    if len(key) > 128:
        raise FbsScanAutoPrintError("print_claim_key_too_long")
    return key


async def claim_scan_print_target(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
    *,
    target: str,
    attempt_key: str,
    actor_user_id: uuid.UUID,
) -> FbsScanAutoPrintTargetClaim:
    key = _validate_attempt_key(attempt_key)
    selection_event = await _locked_selection_event(
        session, tenant_id, supply_id, scan_id
    )
    _validate_target(selection_event, target)
    state = await _target_state(
        session, tenant_id, supply_id, scan_id, target
    )
    if state.started:
        return FbsScanAutoPrintTargetClaim(claimed=False, started=True)
    attempt_digest = _target_attempt_digest(scan_id, target, key)
    if state.active_claim is not None:
        return FbsScanAutoPrintTargetClaim(
            claimed=state.active_claim == attempt_digest,
            started=False,
        )
    marking = (
        await _current_reprint_marking(
            session, tenant_id, supply_id, selection_event
        )
        if target == "chz"
        and (selection_event.payload_json or {}).get("reprint_chz") is True
        else None
    )
    inserted = await record_document_event(
        session,
        tenant_id=tenant_id,
        document_type=DOCUMENT_TYPE_FBS_SUPPLY,
        document_id=supply_id,
        event_type=EVENT_DATA_CHANGED,
        source=SOURCE_USER,
        actor_user_id=actor_user_id,
        product_id=selection_event.product_id,
        payload_json={
            "kind": _TARGET_EVENT_KIND,
            "scan_id": str(scan_id),
            "target": target,
            "action": "claim",
            "attempt_digest": attempt_digest,
            "marking_id": str(marking.id) if marking is not None else None,
        },
        idempotency_key=_target_event_key(
            scan_id, target, "claim", attempt_digest
        ),
    )
    if not inserted:
        replay_state = await _target_state(
            session, tenant_id, supply_id, scan_id, target
        )
        return FbsScanAutoPrintTargetClaim(
            claimed=(
                not replay_state.started
                and replay_state.active_claim == attempt_digest
            ),
            started=replay_state.started,
        )
    return FbsScanAutoPrintTargetClaim(claimed=True, started=False)


async def mark_scan_print_target_started(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
    *,
    target: str,
    attempt_key: str,
    actor_user_id: uuid.UUID,
) -> FbsScanAutoPrintTargetClaim:
    key = _validate_attempt_key(attempt_key)
    selection_event = await _locked_selection_event(
        session, tenant_id, supply_id, scan_id
    )
    _validate_target(selection_event, target)
    state = await _target_state(
        session, tenant_id, supply_id, scan_id, target
    )
    if state.started:
        return FbsScanAutoPrintTargetClaim(claimed=False, started=True)
    attempt_digest = _target_attempt_digest(scan_id, target, key)
    if state.active_claim != attempt_digest:
        raise FbsScanAutoPrintError("scan_print_claim_not_owned")
    await record_document_event(
        session,
        tenant_id=tenant_id,
        document_type=DOCUMENT_TYPE_FBS_SUPPLY,
        document_id=supply_id,
        event_type=EVENT_DATA_CHANGED,
        source=SOURCE_USER,
        actor_user_id=actor_user_id,
        product_id=selection_event.product_id,
        payload_json={
            "kind": _TARGET_EVENT_KIND,
            "scan_id": str(scan_id),
            "target": target,
            "action": "started",
            "attempt_digest": attempt_digest,
        },
        idempotency_key=_target_event_key(scan_id, target, "started", "once"),
    )
    return FbsScanAutoPrintTargetClaim(claimed=False, started=True)


async def release_scan_print_target_claim(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    scan_id: uuid.UUID,
    *,
    target: str,
    attempt_key: str,
    actor_user_id: uuid.UUID,
) -> FbsScanAutoPrintTargetClaim:
    key = _validate_attempt_key(attempt_key)
    selection_event = await _locked_selection_event(
        session, tenant_id, supply_id, scan_id
    )
    _validate_target(selection_event, target)
    state = await _target_state(
        session, tenant_id, supply_id, scan_id, target
    )
    if state.started:
        return FbsScanAutoPrintTargetClaim(claimed=False, started=True)
    attempt_digest = _target_attempt_digest(scan_id, target, key)
    if state.active_claim == attempt_digest:
        await record_document_event(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_FBS_SUPPLY,
            document_id=supply_id,
            event_type=EVENT_DATA_CHANGED,
            source=SOURCE_USER,
            actor_user_id=actor_user_id,
            product_id=selection_event.product_id,
            payload_json={
                "kind": _TARGET_EVENT_KIND,
                "scan_id": str(scan_id),
                "target": target,
                "action": "release",
                "attempt_digest": attempt_digest,
            },
            idempotency_key=_target_event_key(
                scan_id, target, "release", attempt_digest
            ),
        )
    return FbsScanAutoPrintTargetClaim(claimed=False, started=False)
