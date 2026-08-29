"""Bridge inbound container composition to physical warehouse putaway."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeRequest,
)
from app.services import inbound_intake_service
from app.services.inbound_intake_service import InboundIntakeError
from app.services.inventory_container_service import ContainerKind


class InboundContainerPutawayError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _pending_container_state(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> tuple[uuid.UUID, int, int] | None:
    if kind == "box":
        container = await session.get(InboundIntakeBox, container_id)
        if container is None or container.tenant_id != tenant_id:
            return None
        request_id = container.request_id
        totals = await session.execute(
            select(
                func.coalesce(
                    func.sum(InboundIntakeBoxLine.quantity - InboundIntakeBoxLine.posted_qty),
                    0,
                ),
                func.count(InboundIntakeBoxLine.id),
            ).where(InboundIntakeBoxLine.box_id == container_id)
        )
    elif kind == "cargo_place":
        cargo_place = await session.get(InboundIntakeCargoPlace, container_id)
        if cargo_place is None or cargo_place.tenant_id != tenant_id:
            return None
        request_id = cargo_place.request_id
        totals = await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        InboundIntakeCargoPlaceLine.quantity
                        - InboundIntakeCargoPlaceLine.posted_qty
                    ),
                    0,
                ),
                func.count(InboundIntakeCargoPlaceLine.id),
            ).where(InboundIntakeCargoPlaceLine.cargo_place_id == container_id)
        )
    else:
        return None
    request = await session.get(InboundIntakeRequest, request_id)
    if (
        request is None
        or request.tenant_id != tenant_id
        or request.warehouse_id != warehouse_id
    ):
        return None
    remaining, line_count = totals.one()
    return request.id, max(0, int(remaining or 0)), int(line_count or 0)


async def putaway_pending_container(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
    destination_location_id: uuid.UUID,
    destination_is_cell: bool,
) -> int | None:
    """Move an inbound box through its canonical putaway path, without committing."""
    state = await _pending_container_state(
        session,
        tenant_id,
        warehouse_id,
        kind,
        container_id,
    )
    if state is None:
        return None
    request_id, pending_qty, line_count = state
    if pending_qty < 1:
        if line_count > 0:
            raise InboundContainerPutawayError("nothing_to_move")
        return None
    if kind != "box" or not destination_is_cell:
        raise InboundContainerPutawayError("container_stock_missing")
    try:
        _request, moved_qty = await inbound_intake_service.apply_box_putaway(
            session,
            tenant_id,
            request_id,
            container_id,
            storage_location_id=destination_location_id,
            performer_id=actor_user_id,
            commit=False,
        )
    except InboundIntakeError as exc:
        code = "nothing_to_move" if exc.code == "nothing_to_putaway" else exc.code
        raise InboundContainerPutawayError(code) from exc
    return moved_qty
