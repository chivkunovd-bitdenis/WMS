from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeDistributionLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_INBOUND_INTAKE
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.services import inventory_service as inv_svc
from app.services import sorting_location_service as sorting_loc_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.billing_ledger_service import (
    BillingLedgerError,
    product_billing_lines,
    record_operational_billing_issue,
    record_operational_charge,
)
from app.services.catalog_service import (
    get_storage_location_in_warehouse,
    get_warehouse,
)
from app.services.defect_warehouse_service import get_or_create_defect_location
from app.services.document_number_service import (
    DOC_TYPE_INBOUND,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)
from app.services.inbound_intake_quantity_service import container_total_for_product
from app.services.inventory_container_service import ContainerKind
from app.services.operation_fact_service import record_inbound_completion
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_RECEIVING = "receiving"
STATUS_SORTING = "sorting"
STATUS_DONE = "done"

OPERATION_TYPE_INBOUND = "inbound"
OPERATION_TYPE_RETURN = "return"
OPERATION_TYPES = frozenset({OPERATION_TYPE_INBOUND, OPERATION_TYPE_RETURN})
RETURN_MARKETPLACES = frozenset({"wildberries", "ozon"})

# Collapsed legacy names (same values — IN-BE-03 updates API labels)
STATUS_PRIMARY_ACCEPTED = STATUS_RECEIVING
STATUS_VERIFYING = STATUS_RECEIVING
STATUS_VERIFIED = STATUS_SORTING
STATUS_POSTED = STATUS_DONE

RECEIVING_STATUSES = frozenset({STATUS_RECEIVING})
SORTING_STATUSES = frozenset({STATUS_SORTING})
DONE_STATUSES = frozenset({STATUS_DONE})


class InboundIntakeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DistributionScanResult:
    kind: str
    active_location: StorageLocation | None
    product_id: uuid.UUID | None
    rows: list[InboundIntakeDistributionLine]


def _loose_qty(line: InboundIntakeLine) -> int:
    """General (non-box) intake quantity; default 0 — never falls back to expected."""
    return line.actual_qty if line.actual_qty is not None else 0


async def effective_actual_qty(
    session: AsyncSession,
    request_id: uuid.UUID,
    line: InboundIntakeLine,
    *,
    request_status: str | None = None,
) -> int:
    """Accepted fact: loose + all containers while receiving; later actual_qty is total."""
    raw = _loose_qty(line)
    status = request_status
    if status is None:
        stmt = select(InboundIntakeRequest.status).where(InboundIntakeRequest.id == request_id)
        res = await session.execute(stmt)
        status = res.scalar_one_or_none()
    if status in SORTING_STATUSES | DONE_STATUSES:
        return raw
    container_total = await container_total_for_product(session, request_id, line.product_id)
    return raw + container_total


def _accepted_qty_for_line(line: InboundIntakeLine) -> int:
    """Accepted quantity for sorting/posting; default 0 — never falls back to expected."""
    return line.actual_qty if line.actual_qty is not None else 0


async def _sorting_source_allocations(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    line: InboundIntakeLine,
    sorting_location_id: uuid.UUID,
    quantity: int,
    preferred_container_kind: ContainerKind | None,
    preferred_container_id: uuid.UUID | None,
) -> list[tuple[ContainerKind | None, uuid.UUID | None, int]]:
    """Resolve only this intake line's physical sources, then legacy loose stock."""
    refs: list[tuple[ContainerKind, uuid.UUID]] = []
    if preferred_container_kind is not None and preferred_container_id is not None:
        refs.append((preferred_container_kind, preferred_container_id))
    else:
        box_ids = list(
            (
                await session.scalars(
                    select(InboundIntakeBox.id)
                    .join(InboundIntakeBoxLine)
                    .where(
                        InboundIntakeBox.request_id == line.request_id,
                        InboundIntakeBox.tenant_id == tenant_id,
                        InboundIntakeBoxLine.product_id == line.product_id,
                    )
                    .order_by(InboundIntakeBox.box_number, InboundIntakeBox.id)
                )
            ).all()
        )
        cargo_ids = list(
            (
                await session.scalars(
                    select(InboundIntakeCargoPlace.id)
                    .join(InboundIntakeCargoPlaceLine)
                    .where(
                        InboundIntakeCargoPlace.request_id == line.request_id,
                        InboundIntakeCargoPlace.tenant_id == tenant_id,
                        InboundIntakeCargoPlaceLine.product_id == line.product_id,
                    )
                    .order_by(
                        InboundIntakeCargoPlace.place_number,
                        InboundIntakeCargoPlace.id,
                    )
                )
            ).all()
        )
        refs.extend(("box", container_id) for container_id in box_ids)
        refs.extend(("cargo_place", container_id) for container_id in cargo_ids)

    remaining = quantity
    allocations: list[tuple[ContainerKind | None, uuid.UUID | None, int]] = []
    for kind, container_id in refs:
        available = int(
            await session.scalar(
                select(sa.func.coalesce(sa.func.sum(InventoryBalance.quantity), 0)).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.product_id == line.product_id,
                    InventoryBalance.storage_location_id == sorting_location_id,
                    InventoryBalance.container_kind == kind,
                    InventoryBalance.container_id == container_id,
                    InventoryBalance.quantity > 0,
                )
            )
            or 0
        )
        moved = min(remaining, available)
        if moved > 0:
            allocations.append((kind, container_id, moved))
            remaining -= moved
        if remaining == 0:
            return allocations

    loose_available = int(
        await session.scalar(
            select(sa.func.coalesce(sa.func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == line.product_id,
                InventoryBalance.storage_location_id == sorting_location_id,
                InventoryBalance.container_kind.is_(None),
                InventoryBalance.container_id.is_(None),
                InventoryBalance.quantity > 0,
            )
        )
        or 0
    )
    moved_loose = min(remaining, loose_available)
    if moved_loose > 0:
        allocations.append((None, None, moved_loose))
        remaining -= moved_loose
    if remaining > 0:
        raise ValueError("insufficient stock")
    return allocations


async def _apply_line_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    line: InboundIntakeLine,
    sorting_location_id: uuid.UUID,
    normal_location_id: uuid.UUID | None,
    quantity: int,
    keep_good_in_sorting: bool = False,
    actor_user_id: uuid.UUID | None,
    source_container_kind: ContainerKind | None = None,
    source_container_id: uuid.UUID | None = None,
    destination_container_kind: ContainerKind | None = None,
    destination_container_id: uuid.UUID | None = None,
) -> None:
    """Put good units into the chosen cell and defective units into service stock."""
    defective_total = min(max(0, line.defective_qty), _accepted_qty_for_line(line))
    good_total = _accepted_qty_for_line(line) - defective_total
    good_quantity = min(quantity, max(0, good_total - line.posted_qty))
    defective_quantity = quantity - good_quantity
    if good_quantity:
        if keep_good_in_sorting:
            pass
        elif normal_location_id is None:
            raise InboundIntakeError("lines_missing_storage")
        else:
            allocations = await _sorting_source_allocations(
                session,
                tenant_id=tenant_id,
                line=line,
                sorting_location_id=sorting_location_id,
                quantity=good_quantity,
                preferred_container_kind=source_container_kind,
                preferred_container_id=source_container_id,
            )
            for from_kind, from_id, source_quantity in allocations:
                await inv_svc.apply_putaway_from_sorting(
                    session,
                    tenant_id,
                    from_storage_location_id=sorting_location_id,
                    to_storage_location_id=normal_location_id,
                    product_id=line.product_id,
                    quantity=source_quantity,
                    inbound_intake_line_id=line.id,
                    actor_user_id=actor_user_id,
                    from_container_kind=from_kind,
                    from_container_id=from_id,
                    to_container_kind=destination_container_kind,
                    to_container_id=destination_container_id,
                )
    if defective_quantity:
        defect_location = await get_or_create_defect_location(session, tenant_id)
        allocations = await _sorting_source_allocations(
            session,
            tenant_id=tenant_id,
            line=line,
            sorting_location_id=sorting_location_id,
            quantity=defective_quantity,
            preferred_container_kind=source_container_kind,
            preferred_container_id=source_container_id,
        )
        for from_kind, from_id, source_quantity in allocations:
            await inv_svc.apply_return_defect_putaway(
                session,
                tenant_id,
                from_storage_location_id=sorting_location_id,
                to_storage_location_id=defect_location.id,
                product_id=line.product_id,
                quantity=source_quantity,
                inbound_intake_line_id=line.id,
                actor_user_id=actor_user_id,
                from_container_kind=from_kind,
                from_container_id=from_id,
            )


async def sync_request_actuals_from_boxes(
    session: AsyncSession,
    req: InboundIntakeRequest,
) -> None:
    """Validate posted qty against loose + containers; does not overwrite loose intake."""
    for ln in req.lines:
        total = await effective_actual_qty(session, req.id, ln, request_status=req.status)
        if ln.posted_qty > total:
            raise InboundIntakeError("actual_below_posted")


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
    created_by_seller_id: uuid.UUID | None = None,
    planned_delivery_date: date | None = None,
    waybill_number: str | None = None,
    operation_type: str = OPERATION_TYPE_INBOUND,
    marketplace: str | None = None,
) -> InboundIntakeRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise InboundIntakeError("warehouse_not_found")
    normalized_operation_type = operation_type.strip().lower()
    if normalized_operation_type not in OPERATION_TYPES:
        raise InboundIntakeError("invalid_operation_type")
    normalized_marketplace = marketplace.strip().lower() if marketplace else None
    if normalized_marketplace is not None and normalized_marketplace not in RETURN_MARKETPLACES:
        raise InboundIntakeError("invalid_marketplace")
    if normalized_operation_type != OPERATION_TYPE_RETURN and normalized_marketplace is not None:
        raise InboundIntakeError("marketplace_only_for_return")
    if seller_id is not None:
        sl = await session.get(Seller, seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise InboundIntakeError("seller_not_found")
    if created_by_seller_id is not None and created_by_seller_id != seller_id:
        raise InboundIntakeError("seller_not_found")
    req = InboundIntakeRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        status=STATUS_DRAFT,
        operation_type=normalized_operation_type,
        marketplace=normalized_marketplace,
        seller_id=seller_id,
        created_by_seller_id=created_by_seller_id,
        planned_delivery_date=planned_delivery_date,
        waybill_number=normalize_waybill_number(waybill_number),
        planned_box_count=None,
    )
    session.add(req)
    await assign_document_number_if_missing(session, tenant_id, DOC_TYPE_INBOUND, req)
    await assign_display_number_if_missing(session, tenant_id, DOC_TYPE_INBOUND, req)
    await session.commit()
    reloaded = await get_request(session, tenant_id, req.id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    if seller_id is not None:
        from app.services.notification_trigger_service import notify_ff_inbound_created

        await notify_ff_inbound_created(session, reloaded)
        await session.commit()
    return reloaded


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[InboundIntakeRequest]:
    stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.tenant_id == tenant_id)
        .options(
            selectinload(InboundIntakeRequest.lines).selectinload(InboundIntakeLine.product),
            selectinload(InboundIntakeRequest.seller),
            selectinload(InboundIntakeRequest.warehouse),
            selectinload(InboundIntakeRequest.boxes),
        )
        .order_by(InboundIntakeRequest.created_at.desc())
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(
            InboundIntakeRequest.seller_id == seller_product_owner_id,
        )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest | None:
    stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeRequest.seller),
            selectinload(InboundIntakeRequest.warehouse),
            selectinload(InboundIntakeRequest.lines).options(
                selectinload(InboundIntakeLine.product),
                selectinload(InboundIntakeLine.storage_location),
            ),
            selectinload(InboundIntakeRequest.boxes).options(
                selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product),
                selectinload(InboundIntakeBox.pallet),
            ),
            selectinload(InboundIntakeRequest.cargo_places)
            .selectinload(InboundIntakeCargoPlace.lines)
            .selectinload(InboundIntakeCargoPlaceLine.product),
        )
    )
    res = await session.execute(stmt)
    req = res.scalar_one_or_none()
    if req is None:
        return None
    if seller_product_owner_id is not None and req.seller_id != seller_product_owner_id:
        return None
    return req


async def get_request_for_receiving_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest | None:
    """Load only the request state and lines needed by a receiving barcode scan."""
    stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .options(selectinload(InboundIntakeRequest.lines))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_request_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> str | None:
    stmt = select(InboundIntakeRequest.status).where(
        InboundIntakeRequest.id == request_id,
        InboundIntakeRequest.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _line_on_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
) -> tuple[InboundIntakeRequest, InboundIntakeLine] | None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        return None
    for ln in req.lines:
        if ln.id == line_id:
            return req, ln
    return None


def normalize_waybill_number(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _request_plan_editable(
    req: InboundIntakeRequest,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> bool:
    if req.status == STATUS_DRAFT:
        return True
    return seller_product_owner_id is not None and req.status == STATUS_SUBMITTED


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    expected_qty: int,
    storage_location_id: uuid.UUID | None = None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if not _request_plan_editable(req, seller_product_owner_id=seller_product_owner_id):
        raise InboundIntakeError("not_draft")
    prod_stmt = select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant_id,
    )
    prod_res = await session.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if product is None:
        raise InboundIntakeError("product_not_found")
    if seller_product_owner_id is not None and product.seller_id != seller_product_owner_id:
        raise InboundIntakeError("product_seller_mismatch")
    if req.seller_id is None:
        req.seller_id = product.seller_id
    elif product.seller_id != req.seller_id:
        raise InboundIntakeError("mixed_seller_lines")
    address_enabled = await tenant_settings_svc.is_address_storage_enabled(
        session, tenant_id
    )
    loc_id: uuid.UUID | None = None
    if address_enabled and storage_location_id is not None:
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(loc):
            raise InboundIntakeError("sorting_location_reserved")
        loc_id = storage_location_id
    line = InboundIntakeLine(
        request_id=request_id,
        product_id=product_id,
        expected_qty=expected_qty,
        actual_qty=(
            expected_qty
            if req.operation_type == OPERATION_TYPE_RETURN
            and req.marketplace in (None, "wildberries")
            else None
        ),
        posted_qty=0,
        storage_location_id=loc_id,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise InboundIntakeError("duplicate_line") from exc
    await session.refresh(line)
    return line


async def update_line_expected_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    expected_qty: int,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if seller_product_owner_id is not None and req.seller_id != seller_product_owner_id:
        raise InboundIntakeError("line_not_found")
    if not _request_plan_editable(req, seller_product_owner_id=seller_product_owner_id):
        raise InboundIntakeError("not_draft")
    if line.posted_qty != 0:
        raise InboundIntakeError("line_already_posted")
    line.expected_qty = expected_qty
    if (
        req.operation_type == OPERATION_TYPE_RETURN
        and req.marketplace in (None, "wildberries")
        and line.posted_qty == 0
    ):
        line.actual_qty = expected_qty
    await session.commit()
    await session.refresh(line)
    return line


async def delete_draft_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> None:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if seller_product_owner_id is not None and req.seller_id != seller_product_owner_id:
        raise InboundIntakeError("line_not_found")
    if not _request_plan_editable(req, seller_product_owner_id=seller_product_owner_id):
        raise InboundIntakeError("not_draft")
    if line.posted_qty != 0:
        raise InboundIntakeError("line_already_posted")
    await session.delete(line)
    await session.commit()


async def delete_draft_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> None:
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if any(line.posted_qty != 0 for line in req.lines):
        raise InboundIntakeError("line_already_posted")
    if any(box_line.posted_qty != 0 for box in req.boxes for box_line in box.lines):
        raise InboundIntakeError("line_already_posted")
    await session.delete(req)
    await session.commit()


async def patch_request_draft(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_delivery_date: date | None = None,
    planned_delivery_date_set: bool = False,
    planned_box_count: int | None = None,
    planned_box_count_set: bool = False,
    waybill_number: str | None = None,
    waybill_number_set: bool = False,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if not _request_plan_editable(req, seller_product_owner_id=seller_product_owner_id):
        raise InboundIntakeError("not_draft")
    if planned_delivery_date_set:
        req.planned_delivery_date = planned_delivery_date
    if planned_box_count_set:
        if planned_box_count is not None and planned_box_count < 1:
            raise InboundIntakeError("invalid_planned_box_count")
        req.planned_box_count = planned_box_count
    if waybill_number_set:
        req.waybill_number = normalize_waybill_number(waybill_number)
    await session.commit()
    await session.refresh(req)
    return req


async def patch_request_planned_delivery(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_delivery_date: date | None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    return await patch_request_draft(
        session,
        tenant_id,
        request_id,
        planned_delivery_date=planned_delivery_date,
        planned_delivery_date_set=True,
        seller_product_owner_id=seller_product_owner_id,
    )


async def set_line_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
) -> InboundIntakeLine:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status not in (
        STATUS_DRAFT,
        STATUS_SUBMITTED,
        *RECEIVING_STATUSES,
        *SORTING_STATUSES,
    ):
        raise InboundIntakeError("not_editable")
    if req.status in SORTING_STATUSES | DONE_STATUSES and line.posted_qty >= _accepted_qty_for_line(
        line
    ):
        raise InboundIntakeError("line_closed")
    if not await tenant_settings_svc.is_address_storage_enabled(session, tenant_id):
        line.storage_location_id = None
        await session.commit()
        await session.refresh(line)
        return line
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise InboundIntakeError("sorting_location_reserved")
    line.storage_location_id = storage_location_id
    await session.commit()
    await session.refresh(line)
    return line


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if len(req.lines) == 0:
        raise InboundIntakeError("submit_empty")
    if req.planned_box_count is None or req.planned_box_count < 1:
        raise InboundIntakeError("planned_boxes_missing")
    req.status = STATUS_SUBMITTED
    req.submitted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(req)
    return req


def _maybe_complete_request(req: InboundIntakeRequest) -> None:
    if req.status != STATUS_SORTING:
        return
    if all(ln.posted_qty >= _accepted_qty_for_line(ln) for ln in req.lines):
        req.status = STATUS_DONE
        if req.posted_at is None:
            req.posted_at = datetime.now(UTC)


async def _record_charge_if_done(
    session: AsyncSession,
    req: InboundIntakeRequest,
    *,
    performer_id: uuid.UUID | None,
) -> None:
    if req.status != STATUS_DONE:
        return
    occurred_at = req.posted_at or datetime.now(UTC)
    # Возврат — тот же документ приёмки с operation_type='return', и работа по
    # нему тарифицируется своей услугой. Раньше в леджер по возврату уходил код
    # «inbound», хотя факт операции уже писался с «return»: ставка возврата была
    # заведена, а начислений по ней не появлялось ни одного.
    service_code = "return" if req.operation_type == OPERATION_TYPE_RETURN else "inbound"
    try:
        await record_operational_charge(
            session,
            tenant_id=req.tenant_id,
            seller_id=req.seller_id,
            source_type="inbound_intake",
            source_id=req.id,
            source=service_code,
            service_code=service_code,
            quantity=Decimal(sum(line.posted_qty for line in req.lines)),
            occurred_at=occurred_at,
            performer_id=performer_id,
            lines=product_billing_lines(
                (
                    line.product_id,
                    Decimal(line.posted_qty),
                    {"inbound_intake_line_id": str(line.id)},
                )
                for line in req.lines if line.posted_qty
            ),
        )
    except BillingLedgerError:
        if req.seller_id is not None:
            await record_operational_billing_issue(
                session,
                tenant_id=req.tenant_id,
                seller_id=req.seller_id,
                occurred_at=occurred_at,
            )
    await record_inbound_completion(session, req, performer_id)


async def primary_accept_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actual_box_count: int | None = None,
) -> InboundIntakeRequest:
    """Start receiving (legacy primary-accept entry point; no auto-box creation)."""
    if actual_box_count is not None and actual_box_count < 0:
        raise InboundIntakeError("invalid_actual_box_count")
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SUBMITTED:
        raise InboundIntakeError("not_submitted")
    if actual_box_count is not None:
        req.actual_box_count = actual_box_count
        if req.planned_box_count is not None:
            req.boxes_discrepancy = actual_box_count != req.planned_box_count
    req.status = STATUS_RECEIVING
    req.primary_accepted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(req)
    return req


async def begin_receiving(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_DRAFT:
        if req.created_by_seller_id is not None:
            raise InboundIntakeError("not_submitted")
        if len(req.lines) == 0:
            raise InboundIntakeError("submit_empty")
        req.status = STATUS_RECEIVING
        req.primary_accepted_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(req)
        if req.operation_type == OPERATION_TYPE_RETURN and req.marketplace in (None, "wildberries"):
            return await complete_receiving(
                session,
                tenant_id,
                request_id,
                actor_user_id=actor_user_id,
            )
        return req
    return await primary_accept_request(session, tenant_id, request_id, actual_box_count=None)


async def create_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    quantity: int,
) -> list[InboundIntakeCargoPlace]:
    if quantity < 1 or quantity > 1000:
        raise InboundIntakeError("invalid_qty")
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status in DONE_STATUSES:
        raise InboundIntakeError("not_editable")
    start_number = max((place.place_number for place in req.cargo_places), default=0) + 1
    created: list[InboundIntakeCargoPlace] = []
    for offset in range(quantity):
        place = InboundIntakeCargoPlace(
            tenant_id=tenant_id,
            request_id=request_id,
            place_number=start_number + offset,
            internal_barcode=f"ICG-{request_id.hex[:8].upper()}-{start_number + offset:04d}",
        )
        session.add(place)
        created.append(place)
    await session.commit()
    for place in created:
        await session.refresh(place)
    return created


async def mark_cargo_place_label_printed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
) -> InboundIntakeCargoPlace:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    place = await session.get(InboundIntakeCargoPlace, place_id)
    if place is None or place.request_id != request_id or place.tenant_id != tenant_id:
        raise InboundIntakeError("cargo_place_not_found")
    place.label_printed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(place)
    return place


async def _request_barcode_index(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: InboundIntakeRequest,
    *,
    include_seller_catalog: bool = False,
) -> dict[str, uuid.UUID]:
    product_ids = {ln.product_id for ln in req.lines}
    if not product_ids and not include_seller_catalog:
        return {}
    idx: dict[str, uuid.UUID] = {}
    if product_ids:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.id.in_(product_ids),
        )
        res = await session.execute(stmt)
        products = list(res.scalars().all())
        for p in products:
            key = p.sku_code.strip()
            if key:
                idx[key] = p.id
    if req.seller_id is not None:
        rows = await list_seller_wb_catalog_rows(
            session,
            tenant_id,
            req.seller_id,
            product_ids=product_ids,
        )
        for row in rows:
            if not include_seller_catalog and row.product_id not in product_ids:
                continue
            sku_key = row.sku_code.strip()
            if sku_key:
                idx[sku_key] = row.product_id
                idx[sku_key.upper()] = row.product_id
            for b in row.wb_barcodes:
                key = str(b).strip()
                if key:
                    idx[key] = row.product_id
                    idx[key.upper()] = row.product_id
            if row.wb_primary_barcode:
                k = row.wb_primary_barcode.strip()
                if k:
                    idx[k] = row.product_id
                    idx[k.upper()] = row.product_id
    return idx


async def _seller_catalog_barcode_index(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> dict[str, uuid.UUID]:
    rows = await list_seller_wb_catalog_rows(session, tenant_id, seller_id)
    idx: dict[str, uuid.UUID] = {}
    for row in rows:
        key = row.sku_code.strip()
        if key:
            idx[key] = row.product_id
            idx[key.upper()] = row.product_id
        for b in row.wb_barcodes:
            k = str(b).strip()
            if k:
                idx[k] = row.product_id
                idx[k.upper()] = row.product_id
        if row.wb_primary_barcode:
            k2 = row.wb_primary_barcode.strip()
            if k2:
                idx[k2] = row.product_id
                idx[k2.upper()] = row.product_id
    return idx


async def add_or_increment_received_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    actual_qty: int = 1,
    request: InboundIntakeRequest | None = None,
) -> InboundIntakeLine:
    if actual_qty < 1:
        raise InboundIntakeError("invalid_qty")
    req = request or await get_request_for_receiving_scan(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_SUBMITTED:
        req.status = STATUS_RECEIVING
        req.primary_accepted_at = datetime.now(UTC)
    elif req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")

    prod_stmt = select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant_id,
    )
    prod_res = await session.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if product is None:
        raise InboundIntakeError("product_not_found")
    if product.seller_id is None:
        raise InboundIntakeError("product_seller_mismatch")
    if req.seller_id is None:
        req.seller_id = product.seller_id
    elif product.seller_id != req.seller_id:
        raise InboundIntakeError("product_seller_mismatch")
    line = next((ln for ln in req.lines if ln.product_id == product_id), None)
    if line is None:
        line = InboundIntakeLine(
            request_id=request_id,
            product_id=product_id,
            expected_qty=0,
            actual_qty=actual_qty,
            posted_qty=0,
            added_by_fulfillment=True,
        )
        session.add(line)
    else:
        new_loose = _loose_qty(line) + actual_qty
        container_total = await container_total_for_product(session, request_id, line.product_id)
        if line.posted_qty > new_loose + container_total:
            raise InboundIntakeError("actual_below_posted")
        line.actual_qty = new_loose
    await session.commit()
    await session.refresh(line)
    return line


async def scan_barcode_to_loose_intake(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    product_id_hint: uuid.UUID | None = None,
) -> InboundIntakeLine:
    """Scan product barcode into general (non-box) intake: +1 to loose actual_qty."""
    raw = barcode.strip()
    if not raw:
        raise InboundIntakeError("barcode_empty")
    if product_id_hint is not None:
        req_stmt = (
            select(InboundIntakeRequest)
            .where(
                InboundIntakeRequest.id == request_id,
                InboundIntakeRequest.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        req = (await session.execute(req_stmt)).scalar_one_or_none()
        if req is None:
            raise InboundIntakeError("request_not_found")
        if req.status == STATUS_SUBMITTED:
            req.status = STATUS_RECEIVING
            req.primary_accepted_at = datetime.now(UTC)
        elif req.status not in RECEIVING_STATUSES:
            raise InboundIntakeError("not_verifying")

        line_stmt = (
            select(InboundIntakeLine)
            .where(
                InboundIntakeLine.request_id == request_id,
                InboundIntakeLine.product_id == product_id_hint,
            )
            .with_for_update()
        )
        line = (await session.execute(line_stmt)).scalar_one_or_none()
        if line is None:
            raise InboundIntakeError("product_not_on_request")
        new_loose = _loose_qty(line) + 1
        container_total = await container_total_for_product(session, request_id, line.product_id)
        if line.posted_qty > new_loose + container_total:
            raise InboundIntakeError("actual_below_posted")
        line.actual_qty = new_loose
        await session.commit()
        await session.refresh(line)
        return line
    req = await get_request_for_receiving_scan(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_SUBMITTED:
        req.status = STATUS_RECEIVING
        req.primary_accepted_at = datetime.now(UTC)
    elif req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    idx = await _request_barcode_index(
        session,
        tenant_id,
        req,
        include_seller_catalog=False,
    )
    product_id = idx.get(raw) or idx.get(raw.upper())
    if product_id is None:
        raise InboundIntakeError("product_not_on_request")
    return await add_or_increment_received_product(
        session,
        tenant_id,
        request_id,
        product_id=product_id,
        actual_qty=1,
        request=req,
    )


async def set_line_actual_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    actual_qty: int,
) -> InboundIntakeLine:
    if actual_qty < 0:
        raise InboundIntakeError("invalid_qty")
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status == STATUS_SUBMITTED:
        req.status = STATUS_RECEIVING
        req.primary_accepted_at = datetime.now(UTC)
    elif req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    container_total = await container_total_for_product(session, request_id, line.product_id)
    if line.posted_qty > actual_qty + container_total:
        raise InboundIntakeError("actual_below_posted")
    line.actual_qty = actual_qty
    await session.commit()
    await session.refresh(line)
    return line


async def set_line_defective_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    defective_qty: int,
) -> InboundIntakeLine:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.operation_type != OPERATION_TYPE_RETURN:
        raise InboundIntakeError("defect_only_for_return")
    if req.status == STATUS_DONE:
        raise InboundIntakeError("already_posted")
    accepted = await effective_actual_qty(
        session,
        request_id,
        line,
        request_status=req.status,
    )
    if defective_qty < 0 or defective_qty > accepted:
        raise InboundIntakeError("defective_qty_exceeds_accepted")
    if line.posted_qty > accepted - defective_qty:
        raise InboundIntakeError("defect_after_good_posted")
    line.defective_qty = defective_qty
    await session.commit()
    await session.refresh(line)
    return line


async def complete_receiving(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    await sync_request_actuals_from_boxes(session, req)
    line_discrepancy = False
    for line in req.lines:
        effective = await effective_actual_qty(session, req.id, line, request_status=req.status)
        line.actual_qty = effective
        if effective != line.expected_qty:
            line_discrepancy = True
    req.has_discrepancy = bool(req.boxes_discrepancy) or line_discrepancy
    req.status = STATUS_SORTING
    req.verified_at = datetime.now(UTC)
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for box in req.boxes:
        box.storage_location_id = sorting_loc.id
    for cargo_place in req.cargo_places:
        cargo_place.storage_location_id = sorting_loc.id
    for line in req.lines:
        qty = _accepted_qty_for_line(line)
        if qty < 1:
            continue
        container_qty = 0
        for box in req.boxes:
            for box_line in box.lines:
                if box_line.product_id != line.product_id or box_line.quantity < 1:
                    continue
                container_qty += int(box_line.quantity)
                await inv_svc.apply_inbound_receive(
                    session,
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    storage_location_id=sorting_loc.id,
                    quantity=int(box_line.quantity),
                    movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
                    inbound_intake_line_id=line.id,
                    actor_user_id=actor_user_id,
                    container_kind="box",
                    container_id=box.id,
                )
        for cargo_place in req.cargo_places:
            for cargo_line in cargo_place.lines:
                if cargo_line.product_id != line.product_id or cargo_line.quantity < 1:
                    continue
                container_qty += int(cargo_line.quantity)
                await inv_svc.apply_inbound_receive(
                    session,
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    storage_location_id=sorting_loc.id,
                    quantity=int(cargo_line.quantity),
                    movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
                    inbound_intake_line_id=line.id,
                    actor_user_id=actor_user_id,
                    container_kind="cargo_place",
                    container_id=cargo_place.id,
                )
        loose_qty = qty - container_qty
        if loose_qty < 0:
            raise InboundIntakeError("actual_below_container_total")
        if loose_qty > 0:
            await inv_svc.apply_inbound_receive(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=sorting_loc.id,
                quantity=loose_qty,
                movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
                inbound_intake_line_id=line.id,
                actor_user_id=actor_user_id,
            )
    await session.commit()
    await session.refresh(req)
    return req


async def complete_verification(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    """Legacy alias for complete_receiving."""
    return await complete_receiving(
        session,
        tenant_id,
        request_id,
        actor_user_id=actor_user_id,
    )


async def receive_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int,
    performer_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status == STATUS_DONE:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_verified")
    accepted = _accepted_qty_for_line(line)
    remaining = accepted - line.posted_qty
    if remaining <= 0:
        raise InboundIntakeError("nothing_to_receive")
    address_enabled = await tenant_settings_svc.is_address_storage_enabled(
        session, tenant_id
    )
    if address_enabled and line.storage_location_id is None:
        raise InboundIntakeError("storage_not_assigned")
    if quantity < 1 or quantity > remaining:
        raise InboundIntakeError("invalid_qty")
    if address_enabled:
        target_loc = await session.get(StorageLocation, line.storage_location_id)
        if target_loc is None or sorting_loc_svc.is_sorting_location(target_loc):
            raise InboundIntakeError("sorting_location_reserved")
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    await _apply_line_putaway(
        session,
        tenant_id,
        line=line,
        sorting_location_id=sorting_loc.id,
        normal_location_id=line.storage_location_id,
        quantity=quantity,
        keep_good_in_sorting=not address_enabled,
        actor_user_id=performer_id,
    )
    line.posted_qty += quantity
    _maybe_complete_request(req)
    await _record_charge_if_done(session, req, performer_id=performer_id)
    await session.commit()
    await session.refresh(req)
    return req


async def post_all_remaining(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    performer_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_DONE:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_verified")
    address_enabled = await tenant_settings_svc.is_address_storage_enabled(
        session, tenant_id
    )
    to_receive: list[tuple[InboundIntakeLine, int]] = []
    for line in req.lines:
        accepted = _accepted_qty_for_line(line)
        rem = accepted - line.posted_qty
        if rem <= 0:
            continue
        good_remaining = max(
            0,
            accepted - min(line.defective_qty, accepted) - line.posted_qty,
        )
        if address_enabled and line.storage_location_id is None and good_remaining > 0:
            raise InboundIntakeError("lines_missing_storage")
        if address_enabled and line.storage_location_id is not None:
            target_loc = await session.get(StorageLocation, line.storage_location_id)
            if target_loc is None or sorting_loc_svc.is_sorting_location(target_loc):
                raise InboundIntakeError("sorting_location_reserved")
        to_receive.append((line, rem))
    if not to_receive:
        _maybe_complete_request(req)
        if req.status != STATUS_DONE:
            raise InboundIntakeError("nothing_to_receive")
        await _record_charge_if_done(session, req, performer_id=performer_id)
        await session.commit()
        await session.refresh(req)
        return req
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for line, rem in to_receive:
        await _apply_line_putaway(
            session,
            tenant_id,
            line=line,
            sorting_location_id=sorting_loc.id,
            normal_location_id=line.storage_location_id,
            quantity=rem,
            keep_good_in_sorting=not address_enabled,
            actor_user_id=performer_id,
        )
        line.posted_qty += rem
    _maybe_complete_request(req)
    await _record_charge_if_done(session, req, performer_id=performer_id)
    await session.commit()
    await session.refresh(req)
    return req


def sorting_remaining_qty(req: InboundIntakeRequest) -> int:
    """Сколько штук ещё не разложено по ячейкам хранения (остаётся в зоне сортировки)."""
    if req.status != STATUS_SORTING:
        return 0
    total = 0
    for ln in req.lines:
        accepted = _accepted_qty_for_line(ln)
        total += max(0, accepted - ln.posted_qty)
    return total


def box_line_remaining_qty(box_line: InboundIntakeBoxLine) -> int:
    return max(0, int(box_line.quantity) - int(box_line.posted_qty))


def box_remaining_qty(box: InboundIntakeBox) -> int:
    return sum(box_line_remaining_qty(ln) for ln in box.lines)


def _box_quantity_total_for_product(
    req: InboundIntakeRequest,
    product_id: uuid.UUID,
) -> int:
    return sum(
        int(bl.quantity)
        for box in req.boxes
        for bl in box.lines
        if bl.product_id == product_id
    )


def _loose_pool_for_product(
    req: InboundIntakeRequest,
    product_id: uuid.UUID,
    accepted: int,
) -> int:
    """Stable accepted quantity that was received outside boxes (rosyp / loose)."""
    return max(0, accepted - _box_quantity_total_for_product(req, product_id))


def _box_lines_by_key(
    req: InboundIntakeRequest,
) -> dict[tuple[uuid.UUID, uuid.UUID], InboundIntakeBoxLine]:
    out: dict[tuple[uuid.UUID, uuid.UUID], InboundIntakeBoxLine] = {}
    for box in req.boxes:
        for bl in box.lines:
            out[(box.id, bl.product_id)] = bl
    return out


def _maybe_set_distribution_completed(req: InboundIntakeRequest) -> None:
    if req.status != STATUS_SORTING:
        return
    if (
        all(
            _accepted_qty_for_line(ln) <= 0 or ln.posted_qty >= _accepted_qty_for_line(ln)
            for ln in req.lines
        )
        and req.distribution_completed_at is None
    ):
        req.distribution_completed_at = datetime.now(UTC)


async def _get_box_for_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
) -> tuple[InboundIntakeRequest, InboundIntakeBox]:
    # Один запрос приёмки — одна транзакционная очередь раскладки. Это не даёт
    # двум операторам одновременно списать общий остаток одного SKU из разных
    # коробов и защищает повторный POST того же короба.
    request_lock_stmt = (
        select(InboundIntakeRequest.id)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    locked_request_id = await session.scalar(request_lock_stmt)
    if locked_request_id is None:
        raise InboundIntakeError("request_not_found")

    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")
    stmt = (
        select(InboundIntakeBox)
        .where(
            InboundIntakeBox.id == box_id,
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBox.tenant_id == tenant_id,
        )
        .options(selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product))
        .with_for_update()
    )
    res = await session.execute(stmt)
    loaded = res.scalar_one_or_none()
    if loaded is None:
        raise InboundIntakeError("box_not_found")
    return req, loaded


async def _top_up_sorting_for_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sorting_location_id: uuid.UUID,
    line: InboundIntakeLine,
    product_id: uuid.UUID,
    qty: int,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Служебный буфер: перед разкладкой в ячейку гарантируем остаток по строке заявки."""
    accepted = _accepted_qty_for_line(line)
    pool = max(0, accepted - line.posted_qty)
    if qty > pool:
        raise InboundIntakeError("qty_exceeds_accepted")
    avail = await inv_svc.available_quantity_at_location(
        session, tenant_id, product_id, sorting_location_id
    )
    if avail >= qty:
        return
    shortfall = min(qty - avail, max(0, pool - avail))
    if shortfall < 1:
        raise InboundIntakeError("qty_exceeds_accepted")
    await inv_svc.apply_inbound_receive(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=sorting_location_id,
        quantity=shortfall,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        inbound_intake_line_id=line.id,
        actor_user_id=actor_user_id,
    )


async def apply_box_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
    line_items: list[tuple[uuid.UUID, int]] | None = None,
    performer_id: uuid.UUID | None,
    commit: bool = True,
) -> tuple[InboundIntakeRequest, int]:
    """Разложить весь короб или указанные (product_id, qty) из сортировки в ячейку."""
    from app.services import inbound_intake_box_service as inbound_box_svc

    req, box = await _get_box_for_putaway(session, tenant_id, request_id, box_id)

    if await inbound_box_svc.request_has_boxes(session, tenant_id, request_id):
        await sync_request_actuals_from_boxes(session, req)

    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise InboundIntakeError("sorting_location_reserved")

    whole_box = line_items is None
    if whole_box:
        line_items = [
            (bl.product_id, box_line_remaining_qty(bl))
            for bl in box.lines
            if box_line_remaining_qty(bl) > 0
        ]
    if not line_items:
        raise InboundIntakeError("nothing_to_putaway")
    moved_qty = sum(qty for _product_id, qty in line_items)

    lines_by_product = {ln.product_id: ln for ln in req.lines}
    box_lines_by_product = {bl.product_id: bl for bl in box.lines}
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )

    for product_id, qty in line_items:
        if qty < 1:
            raise InboundIntakeError("invalid_qty")
        bl = box_lines_by_product.get(product_id)
        if bl is None:
            raise InboundIntakeError("product_not_in_box")
        if qty > box_line_remaining_qty(bl):
            raise InboundIntakeError("qty_exceeds_box_remaining")
        line = lines_by_product.get(product_id)
        if line is None:
            raise InboundIntakeError("product_not_on_request")
        accepted = _accepted_qty_for_line(line)
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if line.posted_qty + qty > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")

        await _top_up_sorting_for_putaway(
            session,
            tenant_id,
            sorting_loc.id,
            line,
            product_id,
            qty,
            actor_user_id=performer_id,
        )

        # FOR UPDATE защищает PostgreSQL. Условные UPDATE ниже дополнительно
        # делают операцию идемпотентной в SQLite-тестах и при повторе запроса:
        # право на количество получает ровно одна транзакция.
        box_claim = await session.execute(
            sa.update(InboundIntakeBoxLine)
            .where(
                InboundIntakeBoxLine.id == bl.id,
                InboundIntakeBoxLine.posted_qty == bl.posted_qty,
                InboundIntakeBoxLine.quantity - InboundIntakeBoxLine.posted_qty >= qty,
            )
            .values(posted_qty=InboundIntakeBoxLine.posted_qty + qty)
            .execution_options(synchronize_session=False)
        )
        if getattr(box_claim, "rowcount", 0) != 1:
            await session.rollback()
            raise InboundIntakeError(
                "nothing_to_putaway" if whole_box else "qty_exceeds_box_remaining"
            )

        line_claim = await session.execute(
            sa.update(InboundIntakeLine)
            .where(
                InboundIntakeLine.id == line.id,
                InboundIntakeLine.posted_qty == line.posted_qty,
                InboundIntakeLine.posted_qty + qty <= accepted,
            )
            .values(posted_qty=InboundIntakeLine.posted_qty + qty)
            .execution_options(synchronize_session=False)
        )
        if getattr(line_claim, "rowcount", 0) != 1:
            await session.rollback()
            raise InboundIntakeError("qty_exceeds_accepted")
        try:
            await _apply_line_putaway(
                session,
                tenant_id,
                line=line,
                sorting_location_id=sorting_loc.id,
                normal_location_id=storage_location_id,
                quantity=qty,
                actor_user_id=performer_id,
                source_container_kind="box",
                source_container_id=box_id,
                destination_container_kind="box" if whole_box else None,
                destination_container_id=box_id if whole_box else None,
            )
        except ValueError as exc:
            if str(exc) == "insufficient stock":
                raise InboundIntakeError("qty_exceeds_accepted") from None
            raise
        set_committed_value(bl, "posted_qty", bl.posted_qty + qty)
        set_committed_value(line, "posted_qty", line.posted_qty + qty)
        session.add(
            InboundIntakeDistributionLine(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity=qty,
                box_id=box_id,
            )
        )

    _maybe_set_distribution_completed(req)
    _maybe_complete_request(req)
    await _record_charge_if_done(session, req, performer_id=performer_id)
    if not commit:
        await session.flush()
        return req, moved_qty
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded, moved_qty


async def resync_sorting_stock_for_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    """
    Довести остаток в зоне «Сортировка» до (принято - уже разложено) по каждому SKU.

    Нужно, если пересчёт делали до закрытия всех коробов или остаток в сортировке разъехался.
    """
    from app.services import inbound_intake_box_service as inbound_box_svc

    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")
    if await inbound_box_svc.request_has_boxes(session, tenant_id, request_id):
        await sync_request_actuals_from_boxes(session, req)

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for line in req.lines:
        accepted = _accepted_qty_for_line(line)
        if accepted <= 0:
            continue
        need = max(0, accepted - line.posted_qty)
        if need <= 0:
            continue
        await _top_up_sorting_for_putaway(
            session,
            tenant_id,
            sorting_loc.id,
            line,
            line.product_id,
            need,
            actor_user_id=actor_user_id,
        )
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded


async def list_distribution_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[InboundIntakeDistributionLine]:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    stmt = (
        select(InboundIntakeDistributionLine)
        .where(InboundIntakeDistributionLine.request_id == request_id)
        .order_by(InboundIntakeDistributionLine.created_at, InboundIntakeDistributionLine.id)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def scan_distribution_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    active_storage_location_id: uuid.UUID | None,
) -> DistributionScanResult:
    raw = barcode.strip()
    if not raw:
        raise InboundIntakeError("barcode_empty")
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.distribution_completed_at is not None:
        raise InboundIntakeError("distribution_completed")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")

    loc_stmt = select(StorageLocation).where(
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.warehouse_id == req.warehouse_id,
        StorageLocation.deleted_at.is_(None),
        sa.or_(
            StorageLocation.barcode == raw,
            StorageLocation.code == raw,
            StorageLocation.code == raw.upper(),
        ),
    )
    loc_res = await session.execute(loc_stmt)
    scanned_loc = loc_res.scalar_one_or_none()
    if scanned_loc is not None:
        if sorting_loc_svc.is_sorting_location(scanned_loc):
            raise InboundIntakeError("sorting_location_reserved")
        return DistributionScanResult(
            kind="location",
            active_location=scanned_loc,
            product_id=None,
            rows=await list_distribution_lines(session, tenant_id, request_id),
        )

    idx = await _request_barcode_index(
        session,
        tenant_id,
        req,
        include_seller_catalog=False,
    )
    product_id = idx.get(raw) or idx.get(raw.upper())
    if product_id is None:
        raise InboundIntakeError("scan_not_found")
    if active_storage_location_id is None:
        raise InboundIntakeError("active_location_required")

    active_loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, active_storage_location_id
    )
    if active_loc is None:
        raise InboundIntakeError("location_not_found")
    if sorting_loc_svc.is_sorting_location(active_loc):
        raise InboundIntakeError("sorting_location_reserved")

    line = next((ln for ln in req.lines if ln.product_id == product_id), None)
    if line is None:
        raise InboundIntakeError("product_not_on_request")
    accepted = _accepted_qty_for_line(line)
    if accepted <= 0:
        raise InboundIntakeError("product_not_accepted")

    stmt = select(InboundIntakeDistributionLine).where(
        InboundIntakeDistributionLine.request_id == request_id
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())

    current_total = sum(int(r.quantity) for r in rows if r.product_id == product_id)
    next_total = max(int(line.posted_qty), current_total) + 1
    if next_total > accepted:
        raise InboundIntakeError("qty_exceeds_accepted")

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    available = await inv_svc.available_quantity_at_location(
        session,
        tenant_id,
        product_id,
        sorting_loc.id,
    )
    if available < max(0, next_total - int(line.posted_qty)):
        raise InboundIntakeError("insufficient_sorting_stock")

    used_loose = sum(
        int(r.quantity) for r in rows if r.product_id == product_id and r.box_id is None
    )
    loose_capacity = _loose_pool_for_product(req, product_id, accepted)
    if used_loose >= loose_capacity:
        raise InboundIntakeError("product_inside_box")

    source_box_id: uuid.UUID | None = None

    existing = next(
        (
            r
            for r in rows
            if r.product_id == product_id
            and r.storage_location_id == active_loc.id
            and r.box_id == source_box_id
        ),
        None,
    )
    if existing is None:
        session.add(
            InboundIntakeDistributionLine(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=active_loc.id,
                quantity=1,
                box_id=source_box_id,
            )
        )
    else:
        existing.quantity += 1

    await session.commit()
    return DistributionScanResult(
        kind="product",
        active_location=active_loc,
        product_id=product_id,
        rows=await list_distribution_lines(session, tenant_id, request_id),
    )


async def replace_distribution_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    lines: list[tuple[uuid.UUID | None, uuid.UUID, uuid.UUID, int]],
) -> list[InboundIntakeDistributionLine]:
    """
    Полностью заменяет строки распределения (черновик).

    lines: список (box_id | None, product_id, storage_location_id, quantity).
    """
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.distribution_completed_at is not None:
        raise InboundIntakeError("distribution_completed")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")

    box_lines_by_key = _box_lines_by_key(req)

    # Whole-box putaway is already committed when the operator later saves the
    # loose draft. Keep only the part of existing box rows that is backed by
    # box_line.posted_qty; discard old, unapplied box drafts from the former UI.
    existing_stmt = (
        select(InboundIntakeDistributionLine)
        .where(InboundIntakeDistributionLine.request_id == request_id)
        .order_by(
            InboundIntakeDistributionLine.created_at.desc(),
            InboundIntakeDistributionLine.id.desc(),
        )
    )
    existing_rows = list((await session.execute(existing_stmt)).scalars().all())
    preserved_box_rows: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, int]] = []
    preserved_by_key: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for row in existing_rows:
        if row.box_id is None:
            continue
        key = (row.box_id, row.product_id)
        box_line = box_lines_by_key.get(key)
        if box_line is None:
            continue
        already_preserved = preserved_by_key.get(key, 0)
        keep_qty = min(int(row.quantity), max(0, int(box_line.posted_qty) - already_preserved))
        if keep_qty < 1:
            continue
        preserved_box_rows.append(
            (row.box_id, row.product_id, row.storage_location_id, keep_qty)
        )
        preserved_by_key[key] = already_preserved + keep_qty

    accepted_by_product: dict[uuid.UUID, int] = {}
    for ln in req.lines:
        accepted_by_product[ln.product_id] = _accepted_qty_for_line(ln)

    sum_by_product: dict[uuid.UUID, int] = {}
    sum_by_box_product: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    sum_loose_by_product: dict[uuid.UUID, int] = {}
    for box_id, product_id, storage_location_id, qty in lines:
        if qty < 1:
            raise InboundIntakeError("invalid_qty")
        accepted = accepted_by_product.get(product_id)
        if accepted is None:
            raise InboundIntakeError("product_not_on_request")
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if box_id is not None:
            box_line = box_lines_by_key.get((box_id, product_id))
            if box_line is None:
                raise InboundIntakeError("product_not_in_box")
            next_box_sum = sum_by_box_product.get((box_id, product_id), 0) + qty
            if next_box_sum > box_line_remaining_qty(box_line):
                raise InboundIntakeError("qty_exceeds_box_remaining")
            sum_by_box_product[(box_id, product_id)] = next_box_sum
        else:
            next_loose_sum = sum_loose_by_product.get(product_id, 0) + qty
            if next_loose_sum > _loose_pool_for_product(req, product_id, accepted):
                raise InboundIntakeError("qty_exceeds_accepted")
            sum_loose_by_product[product_id] = next_loose_sum
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(loc):
            raise InboundIntakeError("sorting_location_reserved")
        next_sum = sum_by_product.get(product_id, 0) + qty
        if next_sum > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")
        sum_by_product[product_id] = next_sum

    await session.execute(
        sa.delete(InboundIntakeDistributionLine).where(
            InboundIntakeDistributionLine.request_id == request_id
        )
    )
    for box_id, product_id, storage_location_id, qty in [*preserved_box_rows, *lines]:
        session.add(
            InboundIntakeDistributionLine(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity=qty,
                box_id=box_id,
            )
        )
    await session.commit()
    return await list_distribution_lines(session, tenant_id, request_id)


async def complete_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    performer_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")

    # Safety net: validate saved distribution lines against accepted quantities
    # right before locking. Even though PUT validates, this protects against races
    # and inconsistent states.
    accepted_by_product: dict[uuid.UUID, int] = {}
    lines_by_product: dict[uuid.UUID, InboundIntakeLine] = {}
    for ln in req.lines:
        accepted_by_product[ln.product_id] = _accepted_qty_for_line(ln)
        lines_by_product[ln.product_id] = ln

    stmt = select(InboundIntakeDistributionLine).where(
        InboundIntakeDistributionLine.request_id == request_id
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())

    if not rows:
        raise InboundIntakeError("distribution_incomplete")

    box_lines_by_key = _box_lines_by_key(req)

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )

    sum_by_product: dict[uuid.UUID, int] = {}
    sum_by_box_product: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    sum_loose_by_product: dict[uuid.UUID, int] = {}
    for r in rows:
        if r.quantity < 1:
            raise InboundIntakeError("invalid_qty")
        accepted = accepted_by_product.get(r.product_id)
        if accepted is None:
            raise InboundIntakeError("product_not_on_request")
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if r.box_id is not None:
            box_line = box_lines_by_key.get((r.box_id, r.product_id))
            if box_line is None:
                raise InboundIntakeError("product_not_in_box")
            next_box_sum = sum_by_box_product.get((r.box_id, r.product_id), 0) + r.quantity
            if next_box_sum > int(box_line.quantity):
                raise InboundIntakeError("qty_exceeds_box_remaining")
            sum_by_box_product[(r.box_id, r.product_id)] = next_box_sum
        else:
            next_loose_sum = sum_loose_by_product.get(r.product_id, 0) + r.quantity
            if next_loose_sum > _loose_pool_for_product(req, r.product_id, accepted):
                raise InboundIntakeError("qty_exceeds_accepted")
            sum_loose_by_product[r.product_id] = next_loose_sum
        target_loc = await session.get(StorageLocation, r.storage_location_id)
        if (
            target_loc is None
            or target_loc.tenant_id != tenant_id
            or target_loc.deleted_at is not None
        ):
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(target_loc):
            raise InboundIntakeError("sorting_location_reserved")
        sum_by_product[r.product_id] = sum_by_product.get(r.product_id, 0) + r.quantity
        line = lines_by_product[r.product_id]
        if max(line.posted_qty, sum_by_product[r.product_id]) > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")

    initial_box_posted_by_key = {
        key: int(box_line.posted_qty) for key, box_line in box_lines_by_key.items()
    }
    initial_box_posted_by_product: dict[uuid.UUID, int] = {}
    for (_box_id, product_id), posted_qty in initial_box_posted_by_key.items():
        initial_box_posted_by_product[product_id] = (
            initial_box_posted_by_product.get(product_id, 0) + posted_qty
        )
    initial_loose_posted_by_product = {
        product_id: max(
            0,
            int(line.posted_qty) - initial_box_posted_by_product.get(product_id, 0),
        )
        for product_id, line in lines_by_product.items()
    }
    distributed_loose_by_product: dict[uuid.UUID, int] = {}
    distributed_box_by_key: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for r in rows:
        line = lines_by_product[r.product_id]
        if r.box_id is None:
            distributed_before = distributed_loose_by_product.get(r.product_id, 0)
            distributed_after = distributed_before + r.quantity
            distributed_loose_by_product[r.product_id] = distributed_after
            quantity_to_post = min(
                r.quantity,
                max(0, distributed_after - initial_loose_posted_by_product.get(r.product_id, 0)),
            )
        else:
            key = (r.box_id, r.product_id)
            distributed_before = distributed_box_by_key.get(key, 0)
            distributed_after = distributed_before + r.quantity
            distributed_box_by_key[key] = distributed_after
            quantity_to_post = min(
                r.quantity,
                max(0, distributed_after - initial_box_posted_by_key.get(key, 0)),
            )
        if quantity_to_post < 1:
            continue
        if r.box_id is not None:
            bl = box_lines_by_key[(r.box_id, r.product_id)]
            quantity_to_post = min(quantity_to_post, box_line_remaining_qty(bl))
            if quantity_to_post < 1:
                continue
        try:
            await _apply_line_putaway(
                session,
                tenant_id,
                line=line,
                sorting_location_id=sorting_loc.id,
                normal_location_id=r.storage_location_id,
                quantity=quantity_to_post,
                actor_user_id=performer_id,
                source_container_kind="box" if r.box_id is not None else None,
                source_container_id=r.box_id,
            )
        except ValueError as exc:
            await session.rollback()
            if "insufficient stock" in str(exc):
                raise InboundIntakeError("insufficient_sorting_stock") from exc
            raise InboundIntakeError("location_not_found") from exc
        line.posted_qty += quantity_to_post
        if r.box_id is not None:
            bl = box_lines_by_key[(r.box_id, r.product_id)]
            bl.posted_qty += quantity_to_post

    _maybe_set_distribution_completed(req)
    _maybe_complete_request(req)
    await _record_charge_if_done(session, req, performer_id=performer_id)
    await session.commit()
    await session.refresh(req)
    return req


async def reopen_receiving(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    """Return request to receiving; reverse sorting-zone stock and clear distribution."""
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_reopenable")
    if any(ln.posted_qty > 0 for ln in req.lines):
        raise InboundIntakeError("already_posted_partial")

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for line in req.lines:
        qty = _accepted_qty_for_line(line)
        if qty < 1:
            continue
        container_qty = 0
        sources: list[tuple[ContainerKind | None, uuid.UUID | None, int]] = []
        for box in req.boxes:
            for box_line in box.lines:
                if box_line.product_id == line.product_id and box_line.quantity > 0:
                    container_qty += int(box_line.quantity)
                    sources.append(("box", box.id, int(box_line.quantity)))
        for cargo_place in req.cargo_places:
            for cargo_line in cargo_place.lines:
                if cargo_line.product_id == line.product_id and cargo_line.quantity > 0:
                    container_qty += int(cargo_line.quantity)
                    sources.append(
                        ("cargo_place", cargo_place.id, int(cargo_line.quantity))
                    )
        loose_qty = qty - container_qty
        if loose_qty < 0:
            raise InboundIntakeError("actual_below_container_total")
        if loose_qty > 0:
            sources.append((None, None, loose_qty))
        for preferred_kind, preferred_id, source_qty in sources:
            try:
                allocations = await _sorting_source_allocations(
                    session,
                    tenant_id=tenant_id,
                    line=line,
                    sorting_location_id=sorting_loc.id,
                    quantity=source_qty,
                    preferred_container_kind=preferred_kind,
                    preferred_container_id=preferred_id,
                )
                for source_kind, source_id, allocated_qty in allocations:
                    await inv_svc.reverse_inbound_receive(
                        session,
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        storage_location_id=sorting_loc.id,
                        quantity=allocated_qty,
                        inbound_intake_line_id=line.id,
                        actor_user_id=actor_user_id,
                        container_kind=source_kind,
                        container_id=source_id,
                    )
            except ValueError as exc:
                if str(exc) == "insufficient stock":
                    raise InboundIntakeError("sorting_stock_unavailable") from exc
                raise

    await session.execute(
        sa.delete(InboundIntakeDistributionLine).where(
            InboundIntakeDistributionLine.request_id == request_id
        )
    )
    req.distribution_completed_at = None
    req.verified_at = None
    req.status = STATUS_RECEIVING
    for line in req.lines:
        container_total = await container_total_for_product(session, request_id, line.product_id)
        accepted = _accepted_qty_for_line(line)
        line.actual_qty = max(0, accepted - container_total)

    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded


async def reopen_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    """Снять фиксацию распределения, если оприходование ещё не выполнялось."""
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_reopenable")
    if req.distribution_completed_at is None:
        raise InboundIntakeError("distribution_not_completed")
    if any(ln.posted_qty > 0 for ln in req.lines):
        raise InboundIntakeError("already_posted_partial")
    req.distribution_completed_at = None
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded
