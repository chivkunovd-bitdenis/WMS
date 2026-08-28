"""Atomic owner-to-owner stock transfer used by the Loviana/Fashion one-off run."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.marking_code import (
    EVENT_TRANSFERRED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    MarkingCode,
    MarkingCodeEvent,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import inventory_service
from app.services.document_number_service import (
    DOC_TYPE_INBOUND,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    get_sorting_location,
)

MOVEMENT_TYPE_OWNERSHIP_OUT = "ownership_transfer_out"
MOVEMENT_TYPE_OWNERSHIP_IN = "ownership_transfer_in"
MOVEMENT_TYPE_OWNERSHIP_RECEIPT = "ownership_transfer_receipt"
TRANSFERABLE_MARKING_STATUSES = frozenset(
    {STATUS_AVAILABLE, STATUS_PRINTED, STATUS_APPLIED}
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
RUN_NAMESPACE = uuid.UUID("ef91038c-fbe8-4f2f-ad5f-4bb8d293edc6")


class OwnershipTransferError(RuntimeError):
    """The plan is unsafe or no longer matches the approved dry-run."""


@dataclass(frozen=True)
class OwnershipTransferInput:
    row_number: int
    sku: str
    size: str
    source_barcode: str | None
    target_barcode: str | None
    quantity: int
    excluded_reason: str | None = None
    original_target_barcode: str | None = None


@dataclass(frozen=True)
class LocationAllocation:
    location_id: uuid.UUID
    location_code: str
    quantity: int
    physical_before: int
    location_reserved: int
    unpacked_before: int
    packed_before: int
    packed_quantity: int

    def as_dict(self) -> dict[str, object]:
        return {
            "location_id": str(self.location_id),
            "location_code": self.location_code,
            "quantity": self.quantity,
            "physical_before": self.physical_before,
            "location_reserved": self.location_reserved,
            "unpacked_before": self.unpacked_before,
            "packed_before": self.packed_before,
            "packed_quantity": self.packed_quantity,
        }


@dataclass
class OwnershipTransferRow:
    source: OwnershipTransferInput
    source_product_id: uuid.UUID | None = None
    target_product_id: uuid.UUID | None = None
    source_before: int | None = None
    source_reserved: int = 0
    target_before: int | None = None
    transfer_quantity: int = 0
    receipt_quantity: int = 0
    allocations: list[LocationAllocation] = field(default_factory=list)
    marking_code_ids: list[uuid.UUID] = field(default_factory=list)
    marking_codes_blocked: int = 0
    marking_codes_missing: int = 0
    blockers: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.source.excluded_reason is not None:
            return "excluded"
        if self.blockers:
            return "blocked"
        if self.transfer_quantity and self.receipt_quantity:
            return "transfer_and_receipt"
        if self.transfer_quantity:
            return "transfer"
        return "receipt"

    def as_dict(self) -> dict[str, object]:
        target_after = None
        if self.target_before is not None and not self.blockers:
            target_after = self.target_before + self.source.quantity
        source_after = None
        if self.source_before is not None and not self.blockers:
            source_after = self.source_before - self.transfer_quantity
        return {
            "row": self.source.row_number,
            "sku": self.source.sku,
            "size": self.source.size,
            "source_barcode": self.source.source_barcode,
            "target_barcode": self.source.target_barcode,
            "original_target_barcode": self.source.original_target_barcode,
            "quantity": self.source.quantity,
            "status": self.status,
            "excluded_reason": self.source.excluded_reason,
            "blockers": list(self.blockers),
            "source_product_id": str(self.source_product_id) if self.source_product_id else None,
            "target_product_id": str(self.target_product_id) if self.target_product_id else None,
            "source_before": self.source_before,
            "source_reserved": self.source_reserved,
            "source_after": source_after,
            "target_before": self.target_before,
            "target_after": target_after,
            "transfer_quantity": self.transfer_quantity,
            "receipt_quantity": self.receipt_quantity,
            "allocations": [item.as_dict() for item in self.allocations],
            "marking_codes_to_transfer": len(self.marking_code_ids),
            "marking_codes_blocked": self.marking_codes_blocked,
            "marking_codes_missing": self.marking_codes_missing,
        }


@dataclass
class OwnershipTransferPlan:
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    run_id: str
    source_sha256: str
    source_seller_name: str
    target_seller_name: str
    source_seller_id: uuid.UUID | None
    target_seller_id: uuid.UUID | None
    marker_request_id: uuid.UUID
    rows: list[OwnershipTransferRow]
    global_blockers: list[str] = field(default_factory=list)
    already_applied: bool = False

    @property
    def blockers(self) -> list[str]:
        row_blockers = [
            f"row_{row.source.row_number}:{blocker}"
            for row in self.rows
            for blocker in row.blockers
        ]
        return [*self.global_blockers, *row_blockers]

    @property
    def transfer_quantity(self) -> int:
        return sum(row.transfer_quantity for row in self.rows if not row.blockers)

    @property
    def receipt_quantity(self) -> int:
        return sum(row.receipt_quantity for row in self.rows if not row.blockers)

    @property
    def active_quantity(self) -> int:
        return sum(
            row.source.quantity
            for row in self.rows
            if row.source.excluded_reason is None
        )

    @property
    def excluded_quantity(self) -> int:
        return sum(
            row.source.quantity
            for row in self.rows
            if row.source.excluded_reason is not None
        )

    def approval_payload(self) -> dict[str, object]:
        return {
            "tenant_id": str(self.tenant_id),
            "warehouse_id": str(self.warehouse_id),
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "source_seller_name": self.source_seller_name,
            "target_seller_name": self.target_seller_name,
            "source_seller_id": str(self.source_seller_id) if self.source_seller_id else None,
            "target_seller_id": str(self.target_seller_id) if self.target_seller_id else None,
            "marker_request_id": str(self.marker_request_id),
            "already_applied": self.already_applied,
            "global_blockers": list(self.global_blockers),
            "rows": [row.as_dict() for row in self.rows],
        }

    @property
    def approval_token(self) -> str:
        raw = json.dumps(
            self.approval_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            **self.approval_payload(),
            "approval_token": self.approval_token,
            "blockers": self.blockers,
            "summary": {
                "rows_total": len(self.rows),
                "rows_active": sum(
                    row.source.excluded_reason is None for row in self.rows
                ),
                "rows_excluded": sum(
                    row.source.excluded_reason is not None for row in self.rows
                ),
                "active_quantity": self.active_quantity,
                "excluded_quantity": self.excluded_quantity,
                "transfer_quantity": self.transfer_quantity,
                "receipt_quantity": self.receipt_quantity,
                "marking_codes_to_transfer": sum(
                    len(row.marking_code_ids) for row in self.rows
                ),
                "marking_codes_blocked": sum(
                    row.marking_codes_blocked for row in self.rows
                ),
                "marking_codes_missing": sum(
                    row.marking_codes_missing for row in self.rows
                ),
            },
        }


def marker_request_id(tenant_id: uuid.UUID, run_id: str) -> uuid.UUID:
    return uuid.uuid5(RUN_NAMESPACE, f"{tenant_id}:{run_id}:inbound-marker")


def transfer_group_id(
    marker_id: uuid.UUID, row_number: int, location_id: uuid.UUID
) -> uuid.UUID:
    return uuid.uuid5(marker_id, f"row:{row_number}:location:{location_id}")


async def _seller_by_name(
    session: AsyncSession, tenant_id: uuid.UUID, name: str
) -> Seller | None:
    candidates = list(
        (
            await session.execute(select(Seller).where(Seller.tenant_id == tenant_id))
        ).scalars()
    )
    expected = name.strip().casefold()
    rows = [seller for seller in candidates if seller.name.strip().casefold() == expected]
    return rows[0] if len(rows) == 1 else None


async def _products_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_ids: set[uuid.UUID],
    *,
    lock: bool,
) -> dict[tuple[uuid.UUID, str], Product]:
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.seller_id.in_(seller_ids),
        Product.wb_barcode.is_not(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    products = list((await session.execute(stmt)).scalars())
    return {
        (product.seller_id, str(product.wb_barcode).strip()): product
        for product in products
        if product.seller_id is not None and product.wb_barcode
    }


async def _warehouse_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    lock: bool,
) -> list[tuple[InventoryBalance, StorageLocation]]:
    stmt = (
        select(InventoryBalance, StorageLocation)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            InventoryBalance.quantity > 0,
        )
        .order_by(StorageLocation.code, InventoryBalance.id)
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def _product_total_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
    )
    return int(total or 0)


async def _marking_codes_for_transfer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    source_seller_id: uuid.UUID,
    source_product_id: uuid.UUID,
    limit: int,
    *,
    lock: bool,
) -> tuple[list[MarkingCode], int]:
    if limit < 1:
        return [], 0
    eligible_stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == source_seller_id,
            MarkingCode.product_id == source_product_id,
            MarkingCode.status.in_(TRANSFERABLE_MARKING_STATUSES),
            MarkingCode.packaging_task_line_id.is_(None),
        )
        .order_by(MarkingCode.created_at, MarkingCode.id)
        .limit(limit)
    )
    if lock:
        eligible_stmt = eligible_stmt.with_for_update()
    eligible = list((await session.execute(eligible_stmt)).scalars())
    blocked = int(
        await session.scalar(
            select(func.count(MarkingCode.id)).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == source_seller_id,
                MarkingCode.product_id == source_product_id,
                or_(
                    MarkingCode.packaging_task_line_id.is_not(None),
                    MarkingCode.status.not_in(TRANSFERABLE_MARKING_STATUSES),
                ),
            )
        )
        or 0
    )
    return eligible, blocked


async def build_ownership_transfer_plan(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    run_id: str,
    source_sha256: str,
    inputs: list[OwnershipTransferInput],
    source_seller_name: str = "Loviana",
    target_seller_name: str = "ООО Фэшн",
    lock: bool = False,
) -> OwnershipTransferPlan:
    if not RUN_ID_RE.fullmatch(run_id):
        raise OwnershipTransferError("invalid_run_id")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise OwnershipTransferError("invalid_source_sha256")

    marker_id = marker_request_id(tenant_id, run_id)
    source_seller = await _seller_by_name(session, tenant_id, source_seller_name)
    target_seller = await _seller_by_name(session, tenant_id, target_seller_name)
    warehouse = await session.get(Warehouse, warehouse_id)
    global_blockers: list[str] = []
    if source_seller is None:
        global_blockers.append("source_seller_not_found_or_ambiguous")
    if target_seller is None:
        global_blockers.append("target_seller_not_found_or_ambiguous")
    if warehouse is None or warehouse.tenant_id != tenant_id:
        global_blockers.append("warehouse_not_found")

    marker_stmt = select(InboundIntakeRequest).where(
        InboundIntakeRequest.id == marker_id,
        InboundIntakeRequest.tenant_id == tenant_id,
    )
    if lock:
        marker_stmt = marker_stmt.with_for_update()
    marker = (await session.execute(marker_stmt)).scalar_one_or_none()
    already_applied = marker is not None
    if already_applied:
        global_blockers.append("run_already_applied")

    plan = OwnershipTransferPlan(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        run_id=run_id,
        source_sha256=source_sha256,
        source_seller_name=source_seller_name,
        target_seller_name=target_seller_name,
        source_seller_id=source_seller.id if source_seller else None,
        target_seller_id=target_seller.id if target_seller else None,
        marker_request_id=marker_id,
        rows=[OwnershipTransferRow(source=item) for item in inputs],
        global_blockers=global_blockers,
        already_applied=already_applied,
    )
    if (
        source_seller is None
        or target_seller is None
        or warehouse is None
        or warehouse.tenant_id != tenant_id
    ):
        return plan

    active_keys: dict[tuple[str, str], list[OwnershipTransferRow]] = {}
    for row in plan.rows:
        if row.source.excluded_reason is None:
            active_keys.setdefault((row.source.sku.casefold(), row.source.size), []).append(row)
    for duplicates in active_keys.values():
        if len(duplicates) > 1:
            for row in duplicates:
                row.blockers.append("duplicate_active_sku_size")

    products = await _products_by_barcode(
        session,
        tenant_id,
        {source_seller.id, target_seller.id},
        lock=lock,
    )
    for row in plan.rows:
        source = row.source
        if source.excluded_reason is not None:
            continue
        if source.quantity < 1:
            row.blockers.append("invalid_quantity")
            continue
        if not source.target_barcode:
            row.blockers.append("target_barcode_missing")
            continue
        target_product = products.get((target_seller.id, source.target_barcode))
        if target_product is None:
            row.blockers.append("target_product_not_found")
            continue
        row.target_product_id = target_product.id
        row.target_before = await _product_total_in_warehouse(
            session, tenant_id, warehouse_id, target_product.id
        )

        if source.source_barcode is None:
            row.receipt_quantity = source.quantity
            continue
        source_product = products.get((source_seller.id, source.source_barcode))
        if source_product is None:
            row.blockers.append("source_product_not_found")
            continue
        row.source_product_id = source_product.id
        balances = await _warehouse_balances(
            session, tenant_id, warehouse_id, source_product.id, lock=lock
        )
        if any(
            int(balance.quantity)
            != int(balance.quantity_unpacked) + int(balance.quantity_packed)
            for balance, _location in balances
        ):
            row.blockers.append("source_balance_breakdown_mismatch")
            continue
        row.source_before = sum(int(balance.quantity) for balance, _location in balances)
        reserved_map = await inventory_service.reserved_totals_by_product(
            session, tenant_id, [source_product.id], warehouse_id=warehouse_id
        )
        row.source_reserved = int(reserved_map.get(source_product.id, 0))
        transferable_total = max(0, row.source_before - row.source_reserved)
        remaining = min(source.quantity, transferable_total)
        for balance, location in balances:
            if remaining <= 0:
                break
            location_reserved_map = (
                await inventory_service.reserved_totals_by_product_at_location(
                    session, tenant_id, location.id, [source_product.id]
                )
            )
            location_reserved = int(location_reserved_map.get(source_product.id, 0))
            location_available = max(0, int(balance.quantity) - location_reserved)
            take = min(remaining, location_available)
            if take <= 0:
                continue
            packed_quantity = max(0, take - int(balance.quantity_unpacked))
            row.allocations.append(
                LocationAllocation(
                    location_id=location.id,
                    location_code=location.code,
                    quantity=take,
                    physical_before=int(balance.quantity),
                    location_reserved=location_reserved,
                    unpacked_before=int(balance.quantity_unpacked),
                    packed_before=int(balance.quantity_packed),
                    packed_quantity=packed_quantity,
                )
            )
            remaining -= take
        row.transfer_quantity = sum(item.quantity for item in row.allocations)
        row.receipt_quantity = source.quantity - row.transfer_quantity
        codes, blocked_codes = await _marking_codes_for_transfer(
            session,
            tenant_id,
            source_seller.id,
            source_product.id,
            row.transfer_quantity,
            lock=lock,
        )
        row.marking_code_ids = [code.id for code in codes]
        row.marking_codes_blocked = blocked_codes
        if source_product.requires_honest_sign:
            row.marking_codes_missing = max(0, row.transfer_quantity - len(codes))
    return plan


async def _move_packed_credit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: int,
) -> None:
    if quantity <= 0:
        return
    changed = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.storage_location_id == location_id,
            InventoryBalance.quantity_unpacked >= quantity,
        )
        .values(
            quantity_unpacked=InventoryBalance.quantity_unpacked - quantity,
            quantity_packed=InventoryBalance.quantity_packed + quantity,
            updated_at=datetime.now(UTC),
        )
        .returning(InventoryBalance.id)
        .execution_options(synchronize_session=False)
    )
    if changed is None:
        raise OwnershipTransferError("packed_credit_failed")


async def _get_or_create_sorting_location_atomic(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> StorageLocation:
    existing = await get_sorting_location(session, tenant_id, warehouse_id)
    if existing is not None:
        return existing
    location = StorageLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code=SORTING_LOCATION_CODE,
        barcode=f"SORT-{warehouse_id.hex[:12].upper()}",
    )
    session.add(location)
    # A concurrent creator must fail the whole transfer transaction.  Retrying the dry-run
    # is safer than rolling back the idempotency marker in the middle of apply.
    await session.flush()
    return location


async def apply_ownership_transfer_plan(
    session: AsyncSession,
    *,
    approved_token: str,
    plan: OwnershipTransferPlan,
    # Автор указывается явно и без значения по умолчанию: маршрута под передачу
    # владения ещё нет, и когда он появится, забыть про автора будет нельзя.
    actor_user_id: uuid.UUID | None,
) -> InboundIntakeRequest:
    if plan.blockers:
        raise OwnershipTransferError("plan_has_blockers")
    if approved_token != plan.approval_token:
        raise OwnershipTransferError("approval_token_mismatch")
    source_seller_id = plan.source_seller_id
    target_seller_id = plan.target_seller_id
    if source_seller_id is None or target_seller_id is None:
        raise OwnershipTransferError("seller_not_resolved")

    now = datetime.now(UTC)
    has_receipts = plan.receipt_quantity > 0
    sorting_location = None
    if has_receipts:
        sorting_location = await _get_or_create_sorting_location_atomic(
            session,
            tenant_id=plan.tenant_id,
            warehouse_id=plan.warehouse_id,
        )
    request = InboundIntakeRequest(
        id=plan.marker_request_id,
        tenant_id=plan.tenant_id,
        warehouse_id=plan.warehouse_id,
        seller_id=target_seller_id,
        created_by_seller_id=target_seller_id,
        status="sorting" if has_receipts else "done",
        operation_type="inbound",
        submitted_at=now,
        primary_accepted_at=now,
        verified_at=now if has_receipts else None,
        posted_at=None if has_receipts else now,
        distribution_completed_at=None if has_receipts else now,
        waybill_number=(
            "Автоматически создано: перенос Loviana → ООО Фэшн; "
            f"Transfer/24.08; run={plan.run_id[:24]}; sha={plan.source_sha256[:12]}"
        ),
    )
    session.add(request)
    await assign_document_number_if_missing(
        session, plan.tenant_id, DOC_TYPE_INBOUND, request
    )
    await assign_display_number_if_missing(
        session, plan.tenant_id, DOC_TYPE_INBOUND, request
    )
    await session.flush()

    inbound_lines: dict[int, InboundIntakeLine] = {}
    for row in plan.rows:
        if row.source.excluded_reason is not None or row.receipt_quantity <= 0:
            continue
        assert row.target_product_id is not None
        line = InboundIntakeLine(
            id=uuid.uuid5(plan.marker_request_id, f"receipt-line:{row.target_product_id}"),
            request_id=request.id,
            product_id=row.target_product_id,
            expected_qty=row.receipt_quantity,
            actual_qty=row.receipt_quantity,
            added_by_fulfillment=True,
            posted_qty=0,
            storage_location_id=None,
        )
        session.add(line)
        inbound_lines[row.source.row_number] = line
    await session.flush()

    for row in plan.rows:
        if row.source.excluded_reason is not None:
            continue
        assert row.target_product_id is not None
        if row.transfer_quantity:
            assert row.source_product_id is not None
            for allocation in row.allocations:
                group_id = transfer_group_id(
                    plan.marker_request_id, row.source.row_number, allocation.location_id
                )
                await inventory_service.record_movement_and_adjust_balance(
                    session,
                    tenant_id=plan.tenant_id,
                    product_id=row.source_product_id,
                    storage_location_id=allocation.location_id,
                    quantity_delta=-allocation.quantity,
                    movement_type=MOVEMENT_TYPE_OWNERSHIP_OUT,
                    transfer_group_id=group_id,
                    actor_user_id=actor_user_id,
                )
                await inventory_service.record_movement_and_adjust_balance(
                    session,
                    tenant_id=plan.tenant_id,
                    product_id=row.target_product_id,
                    storage_location_id=allocation.location_id,
                    quantity_delta=allocation.quantity,
                    movement_type=MOVEMENT_TYPE_OWNERSHIP_IN,
                    transfer_group_id=group_id,
                    actor_user_id=actor_user_id,
                )
                await _move_packed_credit(
                    session,
                    tenant_id=plan.tenant_id,
                    product_id=row.target_product_id,
                    location_id=allocation.location_id,
                    quantity=allocation.packed_quantity,
                )

        if row.receipt_quantity:
            assert sorting_location is not None
            line = inbound_lines[row.source.row_number]
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=plan.tenant_id,
                product_id=row.target_product_id,
                storage_location_id=sorting_location.id,
                quantity_delta=row.receipt_quantity,
                movement_type=MOVEMENT_TYPE_OWNERSHIP_RECEIPT,
                inbound_intake_line_id=line.id,
                actor_user_id=actor_user_id,
            )

        for code_id in row.marking_code_ids:
            code = await session.get(MarkingCode, code_id)
            if (
                code is None
                or code.tenant_id != plan.tenant_id
                or code.seller_id != source_seller_id
                or code.product_id != row.source_product_id
                or code.status not in TRANSFERABLE_MARKING_STATUSES
                or code.packaging_task_line_id is not None
            ):
                raise OwnershipTransferError("marking_code_changed_after_plan")
            previous_pool_id = code.pool_id
            code.seller_id = target_seller_id
            code.product_id = row.target_product_id
            code.pool_id = None
            session.add(
                MarkingCodeEvent(
                    tenant_id=plan.tenant_id,
                    seller_id=target_seller_id,
                    code_id=code.id,
                    pool_id=None,
                    event_type=EVENT_TRANSFERRED,
                    document_number=request.document_number,
                    reason=f"Loviana → ООО Фэшн; run={plan.run_id}; row={row.source.row_number}",
                    meta_json=json.dumps(
                        {
                            "source_seller_id": str(source_seller_id),
                            "target_seller_id": str(target_seller_id),
                            "source_product_id": str(row.source_product_id),
                            "target_product_id": str(row.target_product_id),
                            "previous_pool_id": str(previous_pool_id) if previous_pool_id else None,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
    await session.flush()
    return request
