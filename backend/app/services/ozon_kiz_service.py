"""Ozon-only KIZ commit path; the Wildberries marking path is intentionally untouched."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    META_STATUS_ACCEPTED,
    META_STATUS_REJECTED,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_VOIDED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_RESERVED,
    STATUS_VOID,
    MarkingCode,
)
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.services import fbs_marking_service as marking_svc
from app.services import marking_code_service as marking_code_svc
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.ozon_marking_position_service import (
    OzonMarkingPositionError,
    resolve_marking_position,
)

_POOL_SOURCE = "pool"
_OPERATOR_SOURCE = "operator"
_EXTERNAL_CODE_SOURCE = "external_fbs"


@dataclass(frozen=True)
class OzonKizError(Exception):
    code: str
    message: str


async def _packaging_line(
    session: AsyncSession,
    order: FbsOrder,
    product_id: uuid.UUID,
) -> tuple[PackagingTaskLine, str | None]:
    row = (
        await session.execute(
            select(PackagingTaskLine, PackagingTask.document_number)
            .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
            .join(FbsSupply, FbsSupply.packaging_task_id == PackagingTask.id)
            .where(
                FbsSupply.id == order.supply_id,
                FbsSupply.tenant_id == order.tenant_id,
                PackagingTaskLine.product_id == product_id,
            )
            .limit(1)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise OzonKizError("packaging_line_not_found", "Не найдена строка упаковки товара.")
    return row[0], row[1]


async def _claim_or_create_code(
    session: AsyncSession,
    order: FbsOrder,
    product_id: uuid.UUID,
    value: str,
    line: PackagingTaskLine,
) -> tuple[MarkingCode, bool]:
    code = await session.scalar(
        select(MarkingCode)
        .where(MarkingCode.tenant_id == order.tenant_id, MarkingCode.cis_code == value)
        .with_for_update()
    )
    if code is not None:
        if code.seller_id != order.seller_id:
            raise OzonKizError("cross_seller_code", "Код принадлежит другому селлеру.")
        if code.product_id is not None and code.product_id != product_id:
            raise OzonKizError("code_product_mismatch", "Код принадлежит другому товару.")
        if code.status != STATUS_AVAILABLE:
            raise OzonKizError("duplicate_kiz", "Код маркировки уже использован.")
        code.status = STATUS_RESERVED
        code.packaging_task_line_id = line.id
        return code, True
    code = MarkingCode(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        product_id=product_id,
        cis_code=value,
        source=_EXTERNAL_CODE_SOURCE,
        status=STATUS_APPLIED,
        applied_at=datetime.now(tz=UTC),
        packaging_task_line_id=line.id,
    )
    session.add(code)
    await session.flush()
    return code, False


async def _active_position_markings(
    session: AsyncSession,
    order_id: uuid.UUID,
    order_product_id: uuid.UUID,
) -> list[FbsOrderMarking]:
    return list(
        (
            await session.execute(
                select(FbsOrderMarking)
                .where(
                    FbsOrderMarking.order_id == order_id,
                    FbsOrderMarking.order_product_id == order_product_id,
                    FbsOrderMarking.kind == "sgtin",
                    FbsOrderMarking.meta_status != META_STATUS_REJECTED,
                )
                .order_by(FbsOrderMarking.created_at, FbsOrderMarking.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )


async def _void_replaced(
    session: AsyncSession,
    marking: FbsOrderMarking,
    actor_user_id: uuid.UUID | None,
) -> None:
    code = (
        await session.get(MarkingCode, marking.marking_code_id)
        if marking.marking_code_id
        else None
    )
    if code is not None:
        code.status = STATUS_VOID
        line = (
            await session.get(PackagingTaskLine, code.packaging_task_line_id)
            if code.packaging_task_line_id
            else None
        )
        await marking_code_svc.record_event(
            session,
            code=code,
            event_type=EVENT_VOIDED,
            actor=actor_user_id,
            packaging_task=line,
            reason="replaced_by_ozon_kiz",
            source_process=marking_code_svc.MARKING_SOURCE_PACKING_FBS_PRINT,
        )
        if line is not None:
            field = (
                "qty_marking_printed"
                if marking.source == _POOL_SOURCE
                else "qty_marking_external"
            )
            setattr(line, field, max(0, int(getattr(line, field)) - 1))
    await session.delete(marking)


async def commit_ozon_kiz(
    session: AsyncSession,
    order: FbsOrder,
    value: str,
    confirmed: bool,
    actor_user_id: uuid.UUID | None,
    http_client: httpx.AsyncClient,
    provider: OzonMarketplaceProvider | None = None,
) -> None:
    try:
        position = await resolve_marking_position(session, order, value)
    except OzonMarkingPositionError as error:
        raise OzonKizError(error.code, error.message) from error
    if position.product_id is None:
        raise OzonKizError("product_mapping_missing", "Позиция Ozon не сопоставлена с товаром WMS.")
    if position.quantity <= 0:
        raise OzonKizError("ozon_product_quantity_invalid", "У позиции Ozon неверное количество.")
    active = await _active_position_markings(session, order.id, position.id)
    if any(marking.value == value for marking in active):
        return
    current = active[-1] if len(active) >= position.quantity else None
    if current is not None and not confirmed:
        raise OzonKizError("needs_confirmation", "Для позиции уже внесены все коды маркировки.")

    line, document_number = await _packaging_line(session, order, position.product_id)
    code, from_pool = await _claim_or_create_code(session, order, position.product_id, value, line)
    await marking_code_svc.record_event(
        session,
        code=code,
        event_type=EVENT_APPLIED,
        actor=actor_user_id,
        document_number=document_number,
        packaging_task=line,
        source_process=marking_code_svc.MARKING_SOURCE_PACKING_FBS_PRINT,
    )
    marking = FbsOrderMarking(
        order_id=order.id,
        order_product_id=position.id,
        tenant_id=order.tenant_id,
        kind="sgtin",
        value=value,
        source=_POOL_SOURCE if from_pool else _OPERATOR_SOURCE,
        marking_code_id=code.id,
        meta_details_json=(dict(current.meta_details_json or {}) if current is not None else None),
        created_by_user_id=actor_user_id,
    )
    session.add(marking)
    await session.flush()
    try:
        await marking_svc.attach_order_meta_to_wb_and_sync(
            session,
            order.tenant_id,
            order,
            marking,
            http_client,
            actor_user_id=actor_user_id,
            ozon_provider=provider,
        )
    except marking_svc.FbsMarkingError as error:
        raise OzonKizError(error.code, str(error)) from error
    if current is not None:
        await _void_replaced(session, current, actor_user_id)
    if from_pool:
        line.qty_marking_printed = int(line.qty_marking_printed) + 1
    else:
        line.qty_marking_external = int(line.qty_marking_external) + 1
    required_total = int(
        await session.scalar(
            select(func.coalesce(func.sum(FbsOrderProduct.quantity), 0)).where(
                FbsOrderProduct.order_id == order.id
            )
        )
    )
    accepted_count = int(
        await session.scalar(
            select(func.count(FbsOrderMarking.id)).where(
                FbsOrderMarking.order_id == order.id,
                FbsOrderMarking.meta_status == META_STATUS_ACCEPTED,
            )
        )
    )
    order.metadata_delivery_allowed = required_total > 0 and accepted_count >= required_total
    await session.flush()
