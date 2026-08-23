from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    MARKING_KIND_SGTIN,
    META_STATUS_ASSIGNED,
    META_STATUS_PENDING,
    FbsOrder,
    FbsOrderMarking,
    current_order_marking,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import EVENT_REPRINTED, STATUS_PRINTED, MarkingCode
from app.models.packaging_task import PackagingTaskLine
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_packaging_integration_service as pack_int_svc
from app.services import marking_code_service as mc_svc
from app.services.fbs_picking_order_service import picking_list_order_key
from app.services.fbs_print_asset_service import (
    FbsPrintAssetError,
    PrintBatchResult,
    request_supply_print_batch,
)
from app.services.print_template_service import PrintLayout, PrintTemplateServiceError, parse_layout


class FbsOrderTapePrintError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FbsOrderTapePrintedCode:
    id: uuid.UUID
    cis_code: str
    has_label_artifact: bool


@dataclass(frozen=True)
class FbsOrderTapeOrder:
    order_id: uuid.UUID
    wb_order_id: int
    requires_honest_sign: bool
    qr_asset_id: uuid.UUID | None
    codes: list[str] = field(default_factory=list)
    printed_codes: list[FbsOrderTapePrintedCode] = field(default_factory=list)
    shortage: int | None = None


@dataclass(frozen=True)
class FbsOrderTapeError:
    order_id: uuid.UUID
    wb_order_id: int
    code: str
    message: str


@dataclass(frozen=True)
class FbsOrderTapePrintResult:
    orders: list[FbsOrderTapeOrder]
    print_batch: PrintBatchResult | None
    order_errors: list[FbsOrderTapeError]
    shortage: int


async def print_fbs_order_tape(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    order_ids: list[uuid.UUID],
    layout: dict[str, Any] | None,
    allow_partial: bool,
    include_order_qr: bool,
    reprint: bool,
    actor_user_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsOrderTapePrintResult:
    if not order_ids:
        raise FbsOrderTapePrintError("empty_order_set")
    try:
        print_layout = parse_layout(layout or {"units": [{"block": "cz", "copies": 1}]})
    except PrintTemplateServiceError as exc:
        raise FbsOrderTapePrintError(exc.code) from exc
    supply = await _load_supply(session, tenant_id, supply_id)
    if supply is None:
        raise FbsOrderTapePrintError("supply_not_found")
    ordered = _orders_in_requested_order(supply, order_ids)
    if len(ordered) != len(dict.fromkeys(order_ids)):
        raise FbsOrderTapePrintError("order_not_in_supply")
    if set(order_ids) == {order.id for order in supply.orders}:
        ordered.sort(key=picking_list_order_key)
    line_by_product = await _line_by_product(session, tenant_id, supply)
    if not reprint and not allow_partial:
        preflight_shortage = await _preflight_new_code_shortage(session, tenant_id, ordered)
        if preflight_shortage > 0:
            return FbsOrderTapePrintResult(
                orders=[],
                print_batch=None,
                order_errors=[],
                shortage=preflight_shortage,
            )

    batch: PrintBatchResult | None = None
    qr_asset_by_order: dict[uuid.UUID, uuid.UUID] = {}
    errors: list[FbsOrderTapeError] = []
    if include_order_qr:
        try:
            batch = await request_supply_print_batch(
                session,
                tenant_id,
                supply_id,
                kind="order_sticker",
                order_ids=order_ids,
                # L8 (21.08.2026): лента печаталась короче листа подбора. Причина —
                # False здесь означает «перезапросить у WB стикеры по ВСЕМ заказам
                # заново». На полутора сотнях заказов любая осечка WB на одном куске
                # (лимит запросов, таймаут) выбивала эти заказы из ленты молча.
                # True — переиспользуем уже полученные стикеры и просим только то,
                # чего не хватает.
                retry_missing=True,
                http_client=http_client,
            )
        except FbsPrintAssetError as exc:
            raise FbsOrderTapePrintError(exc.code) from exc
        qr_asset_by_order = {
            asset.fbs_order_id: asset.id
            for asset in batch.assets
            if asset.fbs_order_id is not None and asset.status == "ready"
        }
        errors.extend(
            FbsOrderTapeError(
                order_id=err.order_id,
                wb_order_id=err.wb_order_id,
                code=err.code,
                message=err.message,
            )
            for err in batch.order_errors
        )

    result_orders: list[FbsOrderTapeOrder] = []
    shortage_total = 0
    for order in ordered:
        qr_asset_id = qr_asset_by_order.get(order.id)
        if include_order_qr and qr_asset_id is None:
            errors.append(
                FbsOrderTapeError(
                    order_id=order.id,
                    wb_order_id=int(order.wb_order_id),
                    code="order_qr_missing",
                    message="QR заказа WB не получен.",
                )
            )
            continue
        requires_honest_sign = _order_requires_sgtin(order)
        # Поставка со снятым требованием Честного знака печатается как немаркированная:
        # новые коды из пула не выпускаются и в WB не привязываются. Уже отсканированные
        # коды остаются на месте и уходят в WB как обычно.
        honest_sign_skipped = supply.honest_sign_skipped_at is not None
        if not requires_honest_sign or honest_sign_skipped:
            result_orders.append(
                FbsOrderTapeOrder(
                    order_id=order.id,
                    wb_order_id=int(order.wb_order_id),
                    requires_honest_sign=False,
                    qr_asset_id=qr_asset_id,
                )
            )
            continue
        line = line_by_product.get(order.product_id)
        if line is None:
            errors.append(
                FbsOrderTapeError(
                    order_id=order.id,
                    wb_order_id=int(order.wb_order_id),
                    code="packaging_line_not_found",
                    message="Строка упаковки для товара не найдена.",
                )
            )
            continue
        try:
            printed = await _print_or_reprint_order_code(
                session,
                tenant_id,
                order,
                line,
                print_layout,
                allow_partial=allow_partial,
                reprint=reprint,
                actor_user_id=actor_user_id,
            )
        except (mc_svc.MarkingCodeServiceError, marking_svc.FbsMarkingError) as exc:
            errors.append(
                FbsOrderTapeError(
                    order_id=order.id,
                    wb_order_id=int(order.wb_order_id),
                    code=exc.code,
                    message=exc.code,
                )
            )
            continue
        shortage_total += printed.shortage or 0
        if (printed.shortage or 0) > 0 and not allow_partial:
            continue
        code_value = printed.codes[0] if printed.codes else None
        if code_value:
            try:
                marking = _existing_sgtin_marking(order)
                if marking is None:
                    raise marking_svc.FbsMarkingError("order_marking_not_found")
                await marking_svc.attach_order_meta_to_wb_and_sync(
                    session,
                    tenant_id,
                    order,
                    marking,
                    http_client,
                )
            except marking_svc.FbsMarkingError as exc:
                await _mark_printed_sgtin_not_sent(session, order)
                errors.append(
                    FbsOrderTapeError(
                        order_id=order.id,
                        wb_order_id=int(order.wb_order_id),
                        code=exc.code,
                        message=exc.code,
                    )
                )
                continue
        result_orders.append(
            FbsOrderTapeOrder(
                order_id=order.id,
                wb_order_id=int(order.wb_order_id),
                requires_honest_sign=True,
                qr_asset_id=qr_asset_id,
                codes=printed.codes,
                printed_codes=[
                    FbsOrderTapePrintedCode(
                        id=row.id,
                        cis_code=row.cis_code,
                        has_label_artifact=row.has_label_artifact,
                    )
                    for row in printed.printed_codes
                ],
                shortage=printed.shortage,
            )
        )

    if shortage_total > 0 and not allow_partial:
        await session.rollback()
        return FbsOrderTapePrintResult(
            orders=[],
            print_batch=batch,
            order_errors=errors,
            shortage=shortage_total,
        )

    await session.flush()
    await pack_int_svc.try_promote_fbs_supply_if_ready(session, tenant_id, supply_id)
    return FbsOrderTapePrintResult(
        orders=result_orders,
        print_batch=batch,
        order_errors=errors,
        shortage=shortage_total,
    )


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product),
            selectinload(FbsSupply.orders)
            .selectinload(FbsOrder.markings)
            .selectinload(FbsOrderMarking.marking_code),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _orders_in_requested_order(
    supply: FbsSupply,
    order_ids: list[uuid.UUID],
) -> list[FbsOrder]:
    by_id = {order.id: order for order in supply.orders}
    out: list[FbsOrder] = []
    seen: set[uuid.UUID] = set()
    for order_id in order_ids:
        if order_id in seen:
            continue
        seen.add(order_id)
        order = by_id.get(order_id)
        if order is not None:
            out.append(order)
    return out


async def _line_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
) -> dict[uuid.UUID | None, PackagingTaskLine]:
    if supply.packaging_task_id is None:
        return {}
    stmt = (
        select(PackagingTaskLine)
        .options(selectinload(PackagingTaskLine.task))
        .join(PackagingTaskLine.task)
        .where(
            PackagingTaskLine.task_id == supply.packaging_task_id,
            PackagingTaskLine.task.has(tenant_id=tenant_id),
        )
    )
    return {line.product_id: line for line in (await session.execute(stmt)).scalars().all()}


async def _preflight_new_code_shortage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> int:
    product_ids = {
        order.product_id
        for order in orders
        if order.product_id is not None
        and _order_requires_sgtin(order)
        and _existing_sgtin_marking(order) is None
    }
    if not product_ids:
        return 0
    available_by_product = await mc_svc.count_available_for_products_batch(
        session,
        tenant_id,
        product_ids,
    )
    required_by_product: dict[uuid.UUID, int] = {}
    for order in orders:
        if (
            order.product_id is not None
            and _order_requires_sgtin(order)
            and _existing_sgtin_marking(order) is None
        ):
            required_by_product[order.product_id] = required_by_product.get(order.product_id, 0) + 1
    return sum(
        max(0, required - available_by_product.get(product_id, 0))
        for product_id, required in required_by_product.items()
    )


async def _print_or_reprint_order_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    line: PackagingTaskLine,
    layout: PrintLayout,
    *,
    allow_partial: bool,
    reprint: bool,
    actor_user_id: uuid.UUID,
) -> mc_svc.PrintMarkingCodesResult:
    existing = _existing_sgtin_marking(order)
    if existing is not None and existing.source == "operator":
        raise mc_svc.MarkingCodeServiceError("operator_kiz_print_forbidden")
    if existing and existing.marking_code is not None:
        code = existing.marking_code
        if reprint:
            await mc_svc.record_event(
                session,
                code=code,
                event_type=EVENT_REPRINTED,
                actor=actor_user_id,
                document_number=line.task.document_number if line.task else None,
                packaging_task=line,
                copies=mc_svc.cz_copies_from_layout(layout),
                source_process=mc_svc.MARKING_SOURCE_PACKING_FBS_PRINT,
            )
        return mc_svc.PrintMarkingCodesResult(
            packaging_task_line_id=line.id,
            quantity=1,
            duplicate_copies=mc_svc.cz_copies_from_layout(layout),
            is_reprint=reprint,
            codes=[code.cis_code],
            layout=layout,
            printed_codes=(
                mc_svc.PrintedCodeInfo(
                    id=code.id,
                    cis_code=code.cis_code,
                    has_label_artifact=bool(code.label_artifact_pdf),
                ),
            ),
        )
    if reprint:
        raise mc_svc.MarkingCodeServiceError("nothing_to_reprint")

    result = await mc_svc.print_codes_for_packaging_line(
        session,
        tenant_id,
        line.id,
        acting_user_id=actor_user_id,
        layout=layout,
        allow_partial=allow_partial,
        units_to_print=1,
        force_required=_order_requires_sgtin(order),
        commit=False,
    )
    if result.quantity < 1 or not result.printed_codes:
        return result
    printed_code = await session.get(MarkingCode, result.printed_codes[0].id)
    if printed_code is None or printed_code.status != STATUS_PRINTED:
        raise mc_svc.MarkingCodeServiceError("code_not_found")
    await _assign_printed_code_to_order(session, order, printed_code)
    return result


def _existing_sgtin_marking(order: FbsOrder) -> FbsOrderMarking | None:
    return current_order_marking(list(order.markings), MARKING_KIND_SGTIN)


def _order_requires_sgtin(order: FbsOrder) -> bool:
    required = {
        str(kind).strip().lower() for kind in (order.required_meta_json or []) if str(kind).strip()
    }
    return MARKING_KIND_SGTIN in required or bool(
        order.product and order.product.requires_honest_sign
    )


async def _mark_printed_sgtin_not_sent(
    session: AsyncSession,
    order: FbsOrder,
) -> None:
    marking = _existing_sgtin_marking(order)
    if marking is None:
        return
    marking.meta_status = META_STATUS_ASSIGNED
    order.meta_details_json = {
        MARKING_KIND_SGTIN: {
            "status": META_STATUS_ASSIGNED,
            "value": marking.value,
            "reason": None,
        }
    }
    order.metadata_last_checked_at = datetime.now(UTC)
    order.metadata_delivery_allowed = marking_svc.compute_delivery_allowed(
        order,
        list(order.markings),
    )
    await session.flush()


async def _assign_printed_code_to_order(
    session: AsyncSession,
    order: FbsOrder,
    code: MarkingCode,
) -> None:
    existing_other = await session.scalar(
        select(FbsOrderMarking.id).where(
            FbsOrderMarking.marking_code_id == code.id,
            FbsOrderMarking.order_id != order.id,
        )
    )
    if existing_other is not None:
        raise marking_svc.FbsMarkingError("marking_code_already_assigned")
    existing = _existing_sgtin_marking(order)
    try:
        async with session.begin_nested():
            if existing is None:
                existing = FbsOrderMarking(
                    order_id=order.id,
                    tenant_id=order.tenant_id,
                    kind=MARKING_KIND_SGTIN,
                    value=code.cis_code,
                    source="pool",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                    marking_code_id=code.id,
                )
                session.add(existing)
                order.markings.append(existing)
            else:
                if existing.value != code.cis_code:
                    raise marking_svc.FbsMarkingError("kind_already_assigned")
                existing.check_status = CHECK_STATUS_NEW
                existing.meta_status = META_STATUS_PENDING
                existing.marking_code_id = code.id
            now = datetime.now(UTC)
            order.meta_details_json = {
                MARKING_KIND_SGTIN: {
                    "status": META_STATUS_PENDING,
                    "value": code.cis_code,
                    "reason": None,
                }
            }
            order.metadata_last_checked_at = now
            order.metadata_delivery_allowed = marking_svc.compute_delivery_allowed(
                order,
                list(order.markings),
            )
            await session.flush()
    except IntegrityError as exc:
        raise marking_svc.FbsMarkingError("marking_code_already_assigned") from exc
