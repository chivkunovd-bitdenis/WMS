"""Product composition and operator notes for inbound cargo places."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document_event import (
    DOCUMENT_TYPE_INBOUND_INTAKE,
    EVENT_TARE_LINE_QTY_CHANGED,
)
from app.models.inbound_intake import (
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
)
from app.models.product import Product
from app.services import inbound_intake_service as intake_svc
from app.services.document_event_service import (
    current_document_event_actor,
    record_document_event_safely,
)
from app.services.inbound_intake_service import InboundIntakeError


async def _load_cargo_place(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
) -> InboundIntakeCargoPlace:
    stmt = (
        select(InboundIntakeCargoPlace)
        .where(
            InboundIntakeCargoPlace.id == place_id,
            InboundIntakeCargoPlace.request_id == request_id,
            InboundIntakeCargoPlace.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeCargoPlace.lines).selectinload(
                InboundIntakeCargoPlaceLine.product
            )
        )
        .execution_options(populate_existing=True)
    )
    place = (await session.execute(stmt)).scalar_one_or_none()
    if place is None:
        raise InboundIntakeError("cargo_place_not_found")
    return place


async def set_line_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    quantity: int,
    mutation_id: uuid.UUID | None = None,
) -> InboundIntakeCargoPlace:
    """Create, replace, or remove one product row in an inbound cargo place."""
    if quantity < 0:
        raise InboundIntakeError("invalid_qty")
    request = await intake_svc.get_request(session, tenant_id, request_id, for_update=True)
    if request is None:
        raise InboundIntakeError("request_not_found")
    replay = await intake_svc._claim_intake_mutation(
        session, tenant_id, request_id, mutation_id=mutation_id, action="cargo_quantity",
        payload={"request_id": str(request_id), "place_id": str(place_id),
                 "product_id": str(product_id), "quantity": quantity},
    )
    if replay is not None:
        return await _load_cargo_place(session, tenant_id, request_id, place_id)
    if request.status in intake_svc.SORTING_STATUSES | intake_svc.DONE_STATUSES:
        raise InboundIntakeError("not_editable")
    place = await _load_cargo_place(session, tenant_id, request_id, place_id)
    if not any(line.product_id == product_id for line in request.lines):
        raise InboundIntakeError("product_not_on_request")
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise InboundIntakeError("product_not_found")

    line = next((row for row in place.lines if row.product_id == product_id), None)
    qty_before = int(line.quantity) if line is not None else 0
    if line is not None and quantity < line.posted_qty:
        raise InboundIntakeError("actual_below_posted")
    await intake_svc.redistribute_ff_draft_container(
        session, request, product_id, quantity - qty_before
    )
    if quantity == 0:
        if line is not None:
            await session.delete(line)
    elif line is None:
        session.add(
            InboundIntakeCargoPlaceLine(
                tenant_id=tenant_id,
                cargo_place_id=place.id,
                product_id=product_id,
                quantity=quantity,
            )
        )
    else:
        line.quantity = quantity
    # WMS-056: пишем append-only факт правки состава грузоместа: qty=0 удаляет
    # строку, поэтому иначе восстановить, кто и когда снял, невозможно.
    if qty_before != quantity:
        actor = current_document_event_actor()
        await record_document_event_safely(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
            document_id=request_id,
            event_type=EVENT_TARE_LINE_QTY_CHANGED,
            source=actor.source,
            actor_user_id=actor.actor_user_id,
            qty=quantity,
            product_id=product_id,
            payload_json={
                "container_kind": "cargo_place",
                "container_id": str(place.id),
                "qty_before": qty_before,
                "qty_after": quantity,
            },
        )
    await session.commit()
    return await _load_cargo_place(session, tenant_id, request_id, place_id)


async def scan_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
    *,
    barcode: str,
    product_id_hint: uuid.UUID | None = None,
    mutation_id: uuid.UUID | None = None,
) -> InboundIntakeCargoPlace:
    """Resolve a product scan and add one unit to an inbound cargo place."""
    raw = barcode.strip()
    if not raw:
        raise InboundIntakeError("barcode_empty")
    request = await intake_svc.get_request(session, tenant_id, request_id, for_update=True)
    if request is None:
        raise InboundIntakeError("request_not_found")
    place = await _load_cargo_place(session, tenant_id, request_id, place_id)
    product_id = product_id_hint
    if product_id is None:
        product_id = await intake_svc.resolve_scanned_product_id(
            session, tenant_id, request, raw
        )
        if product_id is None:
            raise InboundIntakeError("barcode_unknown")
    replay = await intake_svc._claim_intake_mutation(
        session, tenant_id, request_id, mutation_id=mutation_id, action="cargo_scan",
        payload={"request_id": str(request_id), "place_id": str(place_id),
                 "product_id": str(product_id), "barcode": raw},
    )
    if replay is not None:
        return place
    if request.status in intake_svc.SORTING_STATUSES | intake_svc.DONE_STATUSES:
        raise InboundIntakeError("not_editable")
    # WMS-473: a seller-catalogue product not yet on the document gets its line here,
    # in the same transaction as the unit that goes into the cargo place.
    await intake_svc.ensure_request_line(
        session, tenant_id, request, product_id,
        create_missing=intake_svc.scan_creates_lines(request),
    )
    line = next((row for row in place.lines if row.product_id == product_id), None)
    return await set_line_quantity(
        session,
        tenant_id,
        request_id,
        place_id,
        product_id,
        quantity=int(line.quantity) + 1 if line is not None else 1,
    )


async def update_free_text(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
    *,
    free_text: str | None,
) -> InboundIntakeCargoPlace:
    place = await _load_cargo_place(session, tenant_id, request_id, place_id)
    place.free_text = free_text.strip() if free_text and free_text.strip() else None
    await session.commit()
    return await _load_cargo_place(session, tenant_id, request_id, place_id)
