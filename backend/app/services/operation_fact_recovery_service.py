from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import FbsOrderProductPick
from app.models.fbs_order_pick import (
    PICK_EVENT_PICKED,
    PICK_EVENT_UNDONE,
    FbsOrderPick,
    FbsOrderPickEvent,
)
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.operation_fact import OperationFact, OperationFactCutover
from app.models.packaging_task import (
    PACKAGING_EVENT_MANUAL_PACK,
    PACKAGING_EVENT_PREPACKED_EXTERNAL,
    PACKAGING_EVENT_SCAN_PACK,
    PACKAGING_EVENT_UNDO_LAST,
    PackagingTask,
    PackagingTaskEvent,
    PackagingTaskLine,
)
from app.models.product import Product
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.services.operation_fact_service import (
    OperationFactError,
    record_fbs_pick,
    record_inbound_completion,
    record_marketplace_unload,
    record_packaging_event,
    record_storage_fixed,
)


@dataclass(frozen=True)
class OperationFactRecoveryResult:
    found: int
    created: int
    already_present: int
    conflicted: int


async def existing_operation_fact_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Read-only tenant-scoped preflight for the recovery job."""
    rows = await session.scalars(
        select(OperationFact.id).where(OperationFact.tenant_id == tenant_id)
    )
    return len(list(rows))


async def recover_operation_facts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    source_event_ids: dict[str, set[uuid.UUID]] | None = None,
) -> OperationFactRecoveryResult:
    """Rebuild post-cutover facts only from canonical source documents.

    DocumentEvent and the legacy billing ledger are intentionally not read. Sources
    without a durable terminal timestamp remain outside recovery rather than being
    reconstructed from a guessed time.
    """
    cutover = await session.scalar(select(OperationFactCutover).where(OperationFactCutover.id == 1))
    if cutover is None:
        return OperationFactRecoveryResult(found=0, created=0, already_present=0, conflicted=0)

    created = 0
    already_present = 0
    conflicted = 0
    found = 0

    def source_is_selected(source_kind: str, source_event_id: uuid.UUID) -> bool:
        if source_event_ids is None:
            return True
        selected_ids = source_event_ids.get(source_kind)
        return selected_ids is not None and source_event_id in selected_ids

    def occurred_in_scope(occurred_at: datetime | None) -> bool:
        return (
            occurred_at is not None
            and occurred_at >= cutover.occurred_at
            and (period_start is None or occurred_at >= period_start)
            and (period_end is None or occurred_at < period_end)
        )

    async def source_present(
        source_kind: str, source_event_id: uuid.UUID, operation_code: str
    ) -> bool:
        return (
            await session.scalar(
                select(OperationFact.id).where(
                    OperationFact.tenant_id == tenant_id,
                    OperationFact.source_kind == source_kind,
                    OperationFact.source_event_id == source_event_id,
                    OperationFact.operation_code == operation_code,
                )
            )
            is not None
        )

    inbound_stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeRequest.status == "done",
            InboundIntakeRequest.posted_at >= cutover.occurred_at,
        )
        .options(
            selectinload(InboundIntakeRequest.seller),
            selectinload(InboundIntakeRequest.lines).selectinload(InboundIntakeLine.product),
        )
        .order_by(InboundIntakeRequest.posted_at, InboundIntakeRequest.id)
    )
    if period_start is not None:
        inbound_stmt = inbound_stmt.where(InboundIntakeRequest.posted_at >= period_start)
    if period_end is not None:
        inbound_stmt = inbound_stmt.where(InboundIntakeRequest.posted_at < period_end)
    if source_event_ids is not None:
        inbound_ids = source_event_ids.get("inbound_intake_request")
        inbound_stmt = inbound_stmt.where(InboundIntakeRequest.id.in_(inbound_ids or ()))
    for request in (await session.scalars(inbound_stmt)).all():
        found += 1
        operation_code = (
            "return_completed" if request.operation_type == "return" else "inbound_completed"
        )
        if await source_present("inbound_intake_request", request.id, operation_code):
            already_present += 1
            continue
        try:
            await record_inbound_completion(session, request, request.completed_by_user_id)
        except OperationFactError:
            conflicted += 1
        else:
            created += 1

    wb_events = (
        select(FbsOrderPickEvent, FbsOrderPick)
        .join(FbsOrderPick, FbsOrderPick.id == FbsOrderPickEvent.pick_id)
        .where(
            FbsOrderPick.tenant_id == tenant_id,
            FbsOrderPickEvent.created_at >= cutover.occurred_at,
        )
        .order_by(FbsOrderPickEvent.created_at, FbsOrderPickEvent.id)
    )
    if period_start is not None:
        wb_events = wb_events.where(FbsOrderPickEvent.created_at >= period_start)
    if period_end is not None:
        wb_events = wb_events.where(FbsOrderPickEvent.created_at < period_end)
    if source_event_ids is not None:
        wb_ids = source_event_ids.get("fbs_order_pick_event")
        wb_events = wb_events.where(FbsOrderPickEvent.id.in_(wb_ids or ()))
    for event, pick in (await session.execute(wb_events)).all():
        found += 1
        operation_code = (
            "fbs_pick" if event.event_type == PICK_EVENT_PICKED else "fbs_pick_reversal"
        )
        if await source_present("fbs_order_pick_event", event.id, operation_code):
            already_present += 1
            continue
        supply = await session.scalar(
            select(FbsSupply)
            .options(selectinload(FbsSupply.seller))
            .where(FbsSupply.id == pick.fbs_supply_id, FbsSupply.tenant_id == tenant_id)
        )
        product = await session.get(Product, pick.product_id)
        if supply is None or product is None:
            conflicted += 1
            continue
        original_source_event_id: uuid.UUID | None = None
        if event.event_type == PICK_EVENT_UNDONE:
            original_source_event_id = await session.scalar(
                select(FbsOrderPickEvent.id)
                .where(
                    FbsOrderPickEvent.pick_id == pick.id,
                    FbsOrderPickEvent.event_type == PICK_EVENT_PICKED,
                )
                .order_by(FbsOrderPickEvent.created_at, FbsOrderPickEvent.id)
                .limit(1)
            )
            if original_source_event_id is None or not await source_present(
                "fbs_order_pick_event", original_source_event_id, "fbs_pick"
            ):
                conflicted += 1
                continue
        try:
            await record_fbs_pick(
                session,
                supply=supply,
                pick=pick,
                source_event_id=event.id,
                source_kind="fbs_order_pick_event",
                actor_user_id=event.actor_user_id,
                occurred_at=event.created_at,
                reversal=event.event_type == PICK_EVENT_UNDONE,
                original_source_event_id=original_source_event_id,
                product=product,
            )
        except OperationFactError:
            conflicted += 1
        else:
            created += 1

    ozon_picks = (
        select(FbsOrderProductPick)
        .where(
            FbsOrderProductPick.tenant_id == tenant_id,
            or_(
                FbsOrderProductPick.picked_at >= cutover.occurred_at,
                FbsOrderProductPick.undone_at >= cutover.occurred_at,
            ),
        )
        .order_by(FbsOrderProductPick.picked_at, FbsOrderProductPick.id)
    )
    if source_event_ids is not None:
        ozon_ids = source_event_ids.get("fbs_order_product_pick")
        ozon_picks = ozon_picks.where(FbsOrderProductPick.id.in_(ozon_ids or ()))
    for pick in (await session.scalars(ozon_picks)).all():
        if occurred_in_scope(pick.picked_at) and source_is_selected(
            "fbs_order_product_pick", pick.id
        ):
            found += 1
            if await source_present("fbs_order_product_pick", pick.id, "fbs_pick"):
                already_present += 1
            else:
                supply = await session.scalar(
                    select(FbsSupply)
                    .options(selectinload(FbsSupply.seller))
                    .where(FbsSupply.id == pick.fbs_supply_id, FbsSupply.tenant_id == tenant_id)
                )
                product = await session.get(Product, pick.product_id)
                if supply is None or product is None:
                    conflicted += 1
                else:
                    try:
                        await record_fbs_pick(
                            session,
                            supply=supply,
                            pick=pick,
                            source_event_id=pick.id,
                            source_kind="fbs_order_product_pick",
                            actor_user_id=pick.picked_by_user_id,
                            occurred_at=pick.picked_at,
                            product=product,
                        )
                    except OperationFactError:
                        conflicted += 1
                    else:
                        created += 1
        if not occurred_in_scope(pick.undone_at) or not source_is_selected(
            "fbs_order_product_pick", pick.id
        ):
            continue
        undone_at = pick.undone_at
        assert undone_at is not None
        found += 1
        if await source_present("fbs_order_product_pick", pick.id, "fbs_pick_reversal"):
            already_present += 1
            continue
        if not await source_present("fbs_order_product_pick", pick.id, "fbs_pick"):
            conflicted += 1
            continue
        supply = await session.scalar(
            select(FbsSupply)
            .options(selectinload(FbsSupply.seller))
            .where(FbsSupply.id == pick.fbs_supply_id, FbsSupply.tenant_id == tenant_id)
        )
        product = await session.get(Product, pick.product_id)
        if supply is None or product is None:
            conflicted += 1
            continue
        try:
            await record_fbs_pick(
                session,
                supply=supply,
                pick=pick,
                source_event_id=pick.id,
                source_kind="fbs_order_product_pick",
                actor_user_id=pick.undone_by_user_id,
                occurred_at=undone_at,
                reversal=True,
                product=product,
            )
        except OperationFactError:
            conflicted += 1
        else:
            created += 1

    packaging_events = (
        select(PackagingTaskEvent)
        .where(
            PackagingTaskEvent.tenant_id == tenant_id,
            PackagingTaskEvent.created_at >= cutover.occurred_at,
            PackagingTaskEvent.action.in_(
                (
                    PACKAGING_EVENT_MANUAL_PACK,
                    PACKAGING_EVENT_SCAN_PACK,
                    PACKAGING_EVENT_PREPACKED_EXTERNAL,
                    PACKAGING_EVENT_UNDO_LAST,
                )
            ),
        )
        .order_by(PackagingTaskEvent.created_at, PackagingTaskEvent.id)
    )
    if period_start is not None:
        packaging_events = packaging_events.where(PackagingTaskEvent.created_at >= period_start)
    if period_end is not None:
        packaging_events = packaging_events.where(PackagingTaskEvent.created_at < period_end)
    if source_event_ids is not None:
        packaging_ids = source_event_ids.get("packaging_task_event")
        packaging_events = packaging_events.where(PackagingTaskEvent.id.in_(packaging_ids or ()))
    for event in (await session.scalars(packaging_events)).all():
        found += 1
        operation_code = (
            "packing_reversal" if event.action == PACKAGING_EVENT_UNDO_LAST else "packing_completed"
        )
        if await source_present("packaging_task_event", event.id, operation_code):
            already_present += 1
            continue
        task = await session.scalar(
            select(PackagingTask)
            .options(
                selectinload(PackagingTask.lines)
                .selectinload(PackagingTaskLine.product)
                .selectinload(Product.seller)
            )
            .where(PackagingTask.id == event.task_id, PackagingTask.tenant_id == tenant_id)
        )
        line = (
            next((item for item in task.lines if item.id == event.line_id), None) if task else None
        )
        if task is None or line is None:
            conflicted += 1
            continue
        packaging_original_event_id: uuid.UUID | None = None
        if event.action == PACKAGING_EVENT_UNDO_LAST:
            original_event = await session.scalar(
                select(PackagingTaskEvent)
                .where(
                    PackagingTaskEvent.tenant_id == tenant_id,
                    PackagingTaskEvent.task_id == event.task_id,
                    PackagingTaskEvent.event_sequence < event.event_sequence,
                    PackagingTaskEvent.reversed_at.is_not(None),
                    PackagingTaskEvent.action.in_(
                        (PACKAGING_EVENT_MANUAL_PACK, PACKAGING_EVENT_SCAN_PACK)
                    ),
                )
                .order_by(PackagingTaskEvent.event_sequence.desc())
                .limit(1)
            )
            packaging_original_event_id = original_event.id if original_event else None
            if packaging_original_event_id is None or not await source_present(
                "packaging_task_event", packaging_original_event_id, "packing_completed"
            ):
                conflicted += 1
                continue
        try:
            await record_packaging_event(
                session,
                task=task,
                event=event,
                line=line,
                original_event_id=packaging_original_event_id,
            )
        except OperationFactError:
            conflicted += 1
        else:
            created += 1

    unloads = (
        select(MarketplaceUnloadRequest)
        .where(
            MarketplaceUnloadRequest.tenant_id == tenant_id,
            MarketplaceUnloadRequest.status == "shipped",
            or_(
                MarketplaceUnloadRequest.shipped_at >= cutover.occurred_at,
                MarketplaceUnloadRequest.cancelled_at >= cutover.occurred_at,
            ),
        )
        .options(
            selectinload(MarketplaceUnloadRequest.seller),
            selectinload(MarketplaceUnloadRequest.lines).selectinload(MarketplaceUnloadLine.product),
        )
        .order_by(MarketplaceUnloadRequest.shipped_at, MarketplaceUnloadRequest.id)
    )
    if source_event_ids is not None:
        unload_ids = source_event_ids.get("marketplace_unload_request")
        unloads = unloads.where(MarketplaceUnloadRequest.id.in_(unload_ids or ()))
    for unload_request in (await session.scalars(unloads)).all():
        distributed = {
            line.product_id: line.quantity
            for line in unload_request.lines
            if line.quantity > 0
        }
        if occurred_in_scope(unload_request.shipped_at) and source_is_selected(
            "marketplace_unload_request", unload_request.id
        ):
            shipped_at = unload_request.shipped_at
            assert shipped_at is not None
            found += 1
            if await source_present(
                "marketplace_unload_request", unload_request.id, "marketplace_outbound_completed"
            ):
                already_present += 1
            else:
                try:
                    await record_marketplace_unload(
                        session,
                        request=unload_request,
                        distributed=distributed,
                        occurred_at=shipped_at,
                        performer_id=unload_request.completed_by_user_id,
                    )
                except OperationFactError:
                    conflicted += 1
                else:
                    created += 1
        if not occurred_in_scope(unload_request.cancelled_at) or not source_is_selected(
            "marketplace_unload_request", unload_request.id
        ):
            continue
        cancelled_at = unload_request.cancelled_at
        assert cancelled_at is not None
        found += 1
        if await source_present(
            "marketplace_unload_request", unload_request.id, "marketplace_outbound_reversal"
        ):
            already_present += 1
            continue
        if not await source_present(
            "marketplace_unload_request", unload_request.id, "marketplace_outbound_completed"
        ):
            conflicted += 1
            continue
        try:
            await record_marketplace_unload(
                session,
                request=unload_request,
                distributed=distributed,
                occurred_at=cancelled_at,
                performer_id=unload_request.cancelled_by_user_id,
                reversal=True,
            )
        except OperationFactError:
            conflicted += 1
        else:
            created += 1

    storage_stmt = (
        select(StorageStatement)
        .where(
            StorageStatement.tenant_id == tenant_id,
            StorageStatement.status == "fixed",
            StorageStatement.fixed_at >= cutover.occurred_at,
        )
        .options(selectinload(StorageStatement.seller))
        .order_by(StorageStatement.fixed_at, StorageStatement.id)
    )
    if period_start is not None:
        storage_stmt = storage_stmt.where(StorageStatement.fixed_at >= period_start)
    if period_end is not None:
        storage_stmt = storage_stmt.where(StorageStatement.fixed_at < period_end)
    if source_event_ids is not None and not {
        "storage_measurement",
        "storage_statement",
    }.intersection(source_event_ids):
        storage_stmt = storage_stmt.where(StorageStatement.id.in_(()))
    for statement in (await session.scalars(storage_stmt)).all():
        if statement.fixed_at is None:
            conflicted += 1
            continue
        all_measurements = list(
            (
                await session.scalars(
                    select(StorageMeasurement)
                    .where(
                        StorageMeasurement.tenant_id == tenant_id,
                        StorageMeasurement.seller_id == statement.seller_id,
                        StorageMeasurement.warehouse_id == statement.warehouse_id,
                        StorageMeasurement.period_start == statement.period_start,
                        StorageMeasurement.period_end == statement.period_end,
                    )
                    .order_by(StorageMeasurement.id)
                )
            ).all()
        )
        measurements = all_measurements
        if source_event_ids is not None:
            measurement_ids = source_event_ids.get("storage_measurement")
            measurements = [
                measurement
                for measurement in measurements
                if measurement_ids is not None and measurement.id in measurement_ids
            ]
        source_ids = [measurement.id for measurement in measurements]
        if (
            not all_measurements
            and not source_ids
            and source_is_selected("storage_statement", statement.id)
        ):
            source_ids = [statement.id]
        for source_id in source_ids:
            found += 1
            source_kind = "storage_measurement" if measurements else "storage_statement"
            if await source_present(source_kind, source_id, "storage_fixed"):
                already_present += 1
                continue
            try:
                await record_storage_fixed(
                    session,
                    statement=statement,
                    source_event_id=source_id,
                    occurred_at=statement.fixed_at,
                )
            except OperationFactError:
                conflicted += 1
            else:
                created += 1

    return OperationFactRecoveryResult(
        found=found,
        created=created,
        already_present=already_present,
        conflicted=conflicted,
    )
