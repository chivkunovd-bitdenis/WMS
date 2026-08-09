# ruff: noqa: RUF001
"""FBS PVZ shipment — cargo places (count-only trbx), QR print assets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
)
from app.services.fbs_print_asset_service import (
    FbsPrintAssetError,
    ensure_cargo_place_qr_assets,
    map_print_asset,
)
from app.services.fbs_supply_reconcile_service import (
    create_pending_cargo_delete_operation,
    create_pending_cargo_operation,
    get_cargo_delete_operation_by_idempotency,
    get_cargo_operation_by_idempotency,
    mark_cargo_delete_operation_confirmed,
    mark_cargo_operation_confirmed,
    mark_operation_failed,
    mark_operation_pending_confirmation,
    request_hash_for_cargo_places,
    request_hash_for_cargo_places_delete,
)
from app.services.wildberries_client import (
    WildberriesClientError,
    create_marketplace_supply_trbx,
    delete_marketplace_supply_trbx,
    fetch_marketplace_supply_trbx_list,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

MAX_TRBX_SIDE_MM = 600
MAX_TRBX_SIDES_SUM_MM = 1400
MAX_TRBX_WEIGHT_G = 5000
MAX_SUPPLY_TRBX_VOLUME_MM3 = 1_000_000_000
MEASUREMENTS_CONFIRMATION_SOURCE_OPERATOR = "operator_manual_missing_dims"

_CARGO_PLACE_MUTABLE_SUPPLY_STATUSES = frozenset(
    {
        FBS_SUPPLY_STATUS_DRAFT,
        FBS_SUPPLY_STATUS_ASSEMBLING,
        FBS_SUPPLY_STATUS_PACKED,
    }
)


class FbsShipmentPvzError(Exception):
    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code)


@dataclass(frozen=True)
class CargoPlaceDraft:
    client_id: str
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    measurements_confirmed: bool = False
    packaging_box_id: uuid.UUID | None = None


@dataclass(frozen=True)
class TrbxMeta:
    id: uuid.UUID
    wb_trbx_id: str
    packaging_box_id: uuid.UUID | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    sticker_file: str | None


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def _draft_to_dict(draft: CargoPlaceDraft) -> dict[str, Any]:
    return {
        "client_id": draft.client_id,
        "length_mm": draft.length_mm,
        "width_mm": draft.width_mm,
        "height_mm": draft.height_mm,
        "weight_g": draft.weight_g,
        "measurements_confirmed": draft.measurements_confirmed,
    }


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsShipmentPvzError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsShipmentPvzError("missing_marketplace_token")
    return token


async def _get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_trbxes: bool = False,
    with_orders: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    if with_orders:
        stmt = stmt.options(selectinload(FbsSupply.orders))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _require_pvz_supply(supply: FbsSupply) -> None:
    if supply.delivery_type != FBS_DELIVERY_TYPE_PVZ:
        raise FbsShipmentPvzError("wrong_delivery_type")


def _require_cargo_places_mutable_supply(supply: FbsSupply) -> None:
    if supply.status in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentPvzError("supply_bad_status", http_status=409)
    if supply.status not in _CARGO_PLACE_MUTABLE_SUPPLY_STATUSES:
        raise FbsShipmentPvzError("supply_bad_status", http_status=409)


def _normalize_wb_trbx_ids(wb_trbx_ids: list[str]) -> list[str]:
    if not wb_trbx_ids:
        raise FbsShipmentPvzError("empty_cargo_place_selection")
    normalized = list(dict.fromkeys(wb_trbx_ids))
    if not normalized:
        raise FbsShipmentPvzError("empty_cargo_place_selection")
    return normalized


def _resolve_trbxes_for_delete(
    supply: FbsSupply,
    wb_trbx_ids: list[str],
) -> list[FbsTrbx]:
    normalized = _normalize_wb_trbx_ids(wb_trbx_ids)
    by_wb_id = {trbx.wb_trbx_id: trbx for trbx in supply.trbxes}
    missing = [wb_id for wb_id in normalized if wb_id not in by_wb_id]
    if missing:
        raise FbsShipmentPvzError("cargo_place_not_found")
    return [by_wb_id[wb_id] for wb_id in normalized]


async def _remove_local_trbxes(
    session: AsyncSession,
    supply: FbsSupply,
    wb_trbx_ids: list[str],
) -> None:
    by_wb_id = {trbx.wb_trbx_id: trbx for trbx in supply.trbxes}
    for wb_id in wb_trbx_ids:
        trbx = by_wb_id.get(wb_id)
        if trbx is None:
            continue
        await session.delete(trbx)
        if trbx in supply.trbxes:
            supply.trbxes.remove(trbx)
    await session.flush()


def _box_dims_complete(draft: CargoPlaceDraft) -> bool:
    return (
        draft.length_mm is not None
        and draft.width_mm is not None
        and draft.height_mm is not None
        and draft.weight_g is not None
    )


def _measurements_confirmation_audit(
    boxes: list[CargoPlaceDraft],
    *,
    actor_user_id: uuid.UUID,
    confirmation_source: str,
    confirmed_at: datetime,
) -> dict[str, Any] | None:
    """Audit for explicit confirmation when box dims/weight are missing."""
    confirmed_client_ids = [
        draft.client_id
        for draft in boxes
        if draft.measurements_confirmed and not _box_dims_complete(draft)
    ]
    if not confirmed_client_ids:
        return None
    return {
        "actor_user_id": str(actor_user_id),
        "confirmed_at": confirmed_at.isoformat(),
        "source": confirmation_source,
        "confirmed_client_ids": confirmed_client_ids,
    }


def _validate_box_dims(length_mm: int, width_mm: int, height_mm: int, weight_g: int) -> None:
    if max(length_mm, width_mm, height_mm) > MAX_TRBX_SIDE_MM:
        raise FbsShipmentPvzError("trbx_oversized")
    if length_mm + width_mm + height_mm > MAX_TRBX_SIDES_SUM_MM:
        raise FbsShipmentPvzError("trbx_sides_sum_exceeded")
    if weight_g > MAX_TRBX_WEIGHT_G:
        raise FbsShipmentPvzError("trbx_overweight")


def _box_volume_mm3(draft: CargoPlaceDraft) -> int | None:
    if not _box_dims_complete(draft):
        return None
    assert draft.length_mm is not None
    assert draft.width_mm is not None
    assert draft.height_mm is not None
    return draft.length_mm * draft.width_mm * draft.height_mm


def _validate_count_limit(count: int, orders_count: int) -> None:
    if count < 1:
        raise FbsShipmentPvzError("invalid_trbx_count")
    if count > orders_count + 1:
        raise FbsShipmentPvzError("trbx_count_exceeded")


def _preflight_issues_for_boxes(boxes: list[CargoPlaceDraft]) -> list[dict[str, str | None]]:
    issues: list[dict[str, str | None]] = []
    total_volume = 0
    has_volume = True
    for draft in boxes:
        if not _box_dims_complete(draft):
            if not draft.measurements_confirmed:
                issues.append(
                    {
                        "client_id": draft.client_id,
                        "code": "measurements_confirmation_required",
                        "message": "Укажите размеры и вес или подтвердите отсутствие данных.",
                    }
                )
            continue
        assert draft.length_mm is not None
        assert draft.width_mm is not None
        assert draft.height_mm is not None
        assert draft.weight_g is not None
        try:
            _validate_box_dims(
                draft.length_mm,
                draft.width_mm,
                draft.height_mm,
                draft.weight_g,
            )
        except FbsShipmentPvzError as exc:
            issues.append(
                {
                    "client_id": draft.client_id,
                    "code": exc.code,
                    "message": _issue_message(exc.code),
                }
            )
        volume = _box_volume_mm3(draft)
        if volume is None:
            has_volume = False
        else:
            total_volume += volume
    if has_volume and total_volume > MAX_SUPPLY_TRBX_VOLUME_MM3:
        issues.append(
            {
                "client_id": None,
                "code": "trbx_volume_exceeded",
                "message": _issue_message("trbx_volume_exceeded"),
            }
        )
    return issues


def _issue_message(code: str) -> str:
    messages = {
        "trbx_oversized": "Сторона коробки превышает 60 см.",
        "trbx_sides_sum_exceeded": "Сумма сторон коробки превышает 140 см.",
        "trbx_overweight": "Вес коробки превышает 5 кг.",
        "trbx_volume_exceeded": "Суммарный объём грузомест превышает 1 м³.",
        "measurements_confirmation_required": "Нужны размеры или явное подтверждение.",
    }
    return messages.get(code, code)


def _normalize_boxes(count: int, boxes: list[CargoPlaceDraft]) -> list[CargoPlaceDraft]:
    if count < 1:
        raise FbsShipmentPvzError("invalid_trbx_count")
    if boxes and len(boxes) != count:
        raise FbsShipmentPvzError("boxes_count_mismatch")
    if boxes:
        return boxes
    return [
        CargoPlaceDraft(
            client_id=f"box-{idx + 1}",
            length_mm=None,
            width_mm=None,
            height_mm=None,
            weight_g=None,
            measurements_confirmed=False,
        )
        for idx in range(count)
    ]


async def preflight_supply_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    boxes: list[CargoPlaceDraft],
) -> dict[str, Any]:
    effective_boxes = _normalize_boxes(count, boxes)
    return await preflight_cargo_places(
        session,
        tenant_id,
        supply_id,
        effective_boxes,
    )


async def preflight_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    boxes: list[CargoPlaceDraft],
) -> dict[str, Any]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)

    count = len(boxes)
    _validate_count_limit(count, len(supply.orders))

    issues = _preflight_issues_for_boxes(boxes)
    total_volume: int | None = None
    if boxes and all(_box_volume_mm3(box) is not None for box in boxes):
        total_volume = sum(vol for vol in (_box_volume_mm3(box) for box in boxes) if vol)

    return {
        "compatible": not issues,
        "limits": {
            "max_side_mm": MAX_TRBX_SIDE_MM,
            "max_sides_sum_mm": MAX_TRBX_SIDES_SUM_MM,
            "max_weight_g": MAX_TRBX_WEIGHT_G,
            "max_total_volume_m3": MAX_SUPPLY_TRBX_VOLUME_MM3 / 1_000_000_000,
        },
        "summary": {
            "boxes_count": count,
            "orders_count": len(supply.orders),
            "total_volume_m3": (
                total_volume / 1_000_000_000 if total_volume is not None else None
            ),
        },
        "issues": issues,
    }


async def _reconcile_trbxes_from_wb(
    session: AsyncSession,
    supply: FbsSupply,
    wb_trbx_ids: list[str],
    boxes: list[CargoPlaceDraft],
) -> list[FbsTrbx]:
    by_wb_id = {trbx.wb_trbx_id: trbx for trbx in supply.trbxes}
    result: list[FbsTrbx] = []
    for idx, wb_trbx_id in enumerate(wb_trbx_ids):
        trbx = by_wb_id.get(wb_trbx_id)
        draft = boxes[idx] if idx < len(boxes) else None
        if trbx is None:
            trbx = FbsTrbx(
                supply_id=supply.id,
                wb_trbx_id=wb_trbx_id,
                length_mm=draft.length_mm if draft else None,
                width_mm=draft.width_mm if draft else None,
                height_mm=draft.height_mm if draft else None,
                weight_g=draft.weight_g if draft else None,
                packaging_box_id=draft.packaging_box_id if draft else None,
            )
            session.add(trbx)
            supply.trbxes.append(trbx)
        if draft is not None:
            trbx.length_mm = draft.length_mm
            trbx.width_mm = draft.width_mm
            trbx.height_mm = draft.height_mm
            trbx.weight_g = draft.weight_g
            trbx.packaging_box_id = draft.packaging_box_id
        result.append(trbx)
    await session.flush()
    return result


async def _load_qr_assets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    trbx_ids: list[uuid.UUID],
) -> dict[uuid.UUID, FbsPrintAsset]:
    if not trbx_ids:
        return {}
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_trbx_id.in_(trbx_ids),
        FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
        FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
    )
    res = await session.execute(stmt)
    return {asset.fbs_trbx_id: asset for asset in res.scalars().all() if asset.fbs_trbx_id}


def _map_cargo_place(trbx: FbsTrbx, qr_asset: FbsPrintAsset | None) -> dict[str, Any]:
    return {
        "id": str(trbx.id),
        "wb_trbx_id": trbx.wb_trbx_id,
        "length_mm": trbx.length_mm,
        "width_mm": trbx.width_mm,
        "height_mm": trbx.height_mm,
        "weight_g": trbx.weight_g,
        "qr_asset": map_print_asset(qr_asset) if qr_asset is not None else None,
        "applied_at": trbx.qr_applied_at.isoformat() if trbx.qr_applied_at else None,
    }


def _wrap_print_asset_error(exc: FbsPrintAssetError) -> FbsShipmentPvzError:
    return FbsShipmentPvzError(exc.code)


async def _ensure_cargo_qrs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    *,
    trbxes: list[FbsTrbx] | None = None,
) -> None:
    try:
        await ensure_cargo_place_qr_assets(
            session,
            tenant_id,
            supply,
            http_client,
            trbxes=trbxes,
        )
    except FbsPrintAssetError as exc:
        raise _wrap_print_asset_error(exc) from exc


async def list_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        wb_ids = await fetch_marketplace_supply_trbx_list(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    if wb_ids:
        await _reconcile_trbxes_from_wb(session, supply, wb_ids, boxes=[])

    await _ensure_cargo_qrs(session, tenant_id, supply, http_client)
    qr_by_trbx = await _load_qr_assets(session, tenant_id, [t.id for t in supply.trbxes])
    return [_map_cargo_place(trbx, qr_by_trbx.get(trbx.id)) for trbx in supply.trbxes]


async def create_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    boxes: list[CargoPlaceDraft],
    idempotency_key: str,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None = None,
    confirmation_source: str = MEASUREMENTS_CONFIRMATION_SOURCE_OPERATOR,
) -> list[dict[str, Any]]:
    if not idempotency_key.strip():
        raise FbsShipmentPvzError("missing_idempotency_key")

    supply = await _get_supply(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
        with_orders=True,
    )
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)

    effective_boxes = _normalize_boxes(count, boxes)
    if len(effective_boxes) != count:
        raise FbsShipmentPvzError("invalid_trbx_count")

    _validate_count_limit(count, len(supply.orders))
    preflight = await preflight_cargo_places(
        session,
        tenant_id,
        supply_id,
        effective_boxes,
    )
    if not preflight["compatible"]:
        raise FbsShipmentPvzError("cargo_places_preflight_failed")

    boxes_payload = [_draft_to_dict(box) for box in effective_boxes]
    confirmed_at = datetime.now(UTC)
    if any(
        draft.measurements_confirmed and not _box_dims_complete(draft)
        for draft in effective_boxes
    ):
        if actor_user_id is None:
            raise FbsShipmentPvzError("cargo_places_preflight_failed")
        measurements_audit = _measurements_confirmation_audit(
            effective_boxes,
            actor_user_id=actor_user_id,
            confirmation_source=confirmation_source,
            confirmed_at=confirmed_at,
        )
    else:
        measurements_audit = None

    req_hash = request_hash_for_cargo_places(
        supply_id=supply.id,
        count=count,
        boxes=boxes_payload,
    )

    existing_op = await get_cargo_operation_by_idempotency(
        session,
        supply.seller_id,
        idempotency_key,
    )
    if existing_op is not None:
        if existing_op.request_hash != req_hash:
            raise FbsShipmentPvzError("idempotency_key_reused")
        if existing_op.state == WB_OPERATION_STATE_CONFIRMED:
            return await list_cargo_places(session, tenant_id, supply_id, http_client)

        # A timeout after the WB mutation is deliberately never retried blindly.
        # First compare WB's current list with the snapshot persisted before the
        # mutation; only an exact, attributable delta can be finalized safely.
        if existing_op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
            return await _reconcile_pending_cargo_operation(
                session,
                tenant_id,
                supply,
                existing_op,
                effective_boxes,
                http_client,
            )
        if existing_op.state == WB_OPERATION_STATE_PENDING:
            raise FbsShipmentPvzError("wb_pending_confirmation")
        if existing_op.state == WB_OPERATION_STATE_FAILED:
            raise FbsShipmentPvzError(existing_op.error_code or "wb_operation_failed")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    operation = existing_op
    if operation is None:
        # This read is not part of the mutation.  Its snapshot lets a retry
        # distinguish cargo places created by this request from older places.
        try:
            wb_trbx_ids_before = await fetch_marketplace_supply_trbx_list(
                http_client,
                api_token=token,
                supply_id=supply.wb_supply_id,
            )
        except WildberriesClientError as exc:
            raise FbsShipmentPvzError(_wb_error_code(exc)) from exc
        request_summary: dict[str, Any] = {
            "supply_id": str(supply.id),
            "count": count,
            "boxes": boxes_payload,
            "wb_trbx_ids_before": wb_trbx_ids_before,
        }
        if measurements_audit is not None:
            request_summary["measurements_confirmation_audit"] = measurements_audit
        operation = await create_pending_cargo_operation(
            session,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            request_summary=request_summary,
            local_supply_id=supply.id,
        )

    try:
        wb_ids_created = await create_marketplace_supply_trbx(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            amount=count,
        )
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            # The API route intentionally raises after this service call.  A
            # durable checkpoint is therefore required before the HTTP rollback.
            await session.commit()
            raise FbsShipmentPvzError("wb_timeout") from exc
        await mark_operation_failed(
            session,
            operation,
            error_code=_wb_error_code(exc),
            local_supply_id=supply.id,
        )
        await session.commit()
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    return await _finalize_cargo_operation(
        session,
        tenant_id,
        supply,
        operation,
        wb_ids_created,
        effective_boxes,
        http_client,
    )


async def _finalize_cargo_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    operation: Any,
    wb_trbx_ids: list[str],
    boxes: list[CargoPlaceDraft],
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Persist the WB create result before the optional QR projection."""
    trbxes = await _reconcile_trbxes_from_wb(session, supply, wb_trbx_ids, boxes)
    await mark_cargo_operation_confirmed(
        session,
        operation,
        wb_supply_id=supply.wb_supply_id,
        local_supply_id=supply.id,
        response_summary={"wb_trbx_ids": wb_trbx_ids},
    )
    # QR retrieval is a recoverable local projection.  It must not undo a
    # confirmed WB create if its own HTTP request fails.
    await session.commit()
    await _ensure_cargo_qrs(
        session,
        tenant_id,
        supply,
        http_client,
        trbxes=trbxes,
    )
    qr_by_trbx = await _load_qr_assets(session, tenant_id, [t.id for t in trbxes])
    return [_map_cargo_place(trbx, qr_by_trbx.get(trbx.id)) for trbx in trbxes]


async def _reconcile_pending_cargo_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    operation: Any,
    boxes: list[CargoPlaceDraft],
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    summary = operation.request_summary_json or {}
    before_raw = summary.get("wb_trbx_ids_before")
    expected_count = summary.get("count")
    if not isinstance(before_raw, list) or not isinstance(expected_count, int):
        raise FbsShipmentPvzError("wb_pending_confirmation")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        current_ids = await fetch_marketplace_supply_trbx_list(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        # The outcome remains unknown: preserve the journal and never send a
        # second create merely because reconciliation could not be read.
        raise FbsShipmentPvzError(
            "wb_timeout" if exc.code == "transport_error" else _wb_error_code(exc)
        ) from exc

    created_ids = [wb_id for wb_id in current_ids if wb_id not in set(before_raw)]
    if len(created_ids) != expected_count:
        raise FbsShipmentPvzError("wb_pending_confirmation")
    return await _finalize_cargo_operation(
        session,
        tenant_id,
        supply,
        operation,
        created_ids,
        boxes,
        http_client,
    )


async def _finalize_cargo_delete_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    operation: Any,
    wb_trbx_ids: list[str],
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Remove only the requested cargo places locally after WB delete is confirmed."""
    await _remove_local_trbxes(session, supply, wb_trbx_ids)
    await mark_cargo_delete_operation_confirmed(
        session,
        operation,
        wb_supply_id=supply.wb_supply_id,
        local_supply_id=supply.id,
        response_summary={"deleted_wb_trbx_ids": wb_trbx_ids},
    )
    await session.commit()
    return await list_cargo_places(session, tenant_id, supply.id, http_client)


async def _reconcile_pending_cargo_delete_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    operation: Any,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    summary = operation.request_summary_json or {}
    requested_raw = summary.get("wb_trbx_ids")
    if not isinstance(requested_raw, list):
        raise FbsShipmentPvzError("wb_pending_confirmation")
    requested_ids = _normalize_wb_trbx_ids([str(row) for row in requested_raw])

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        current_ids = await fetch_marketplace_supply_trbx_list(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentPvzError(
            "wb_timeout" if exc.code == "transport_error" else _wb_error_code(exc)
        ) from exc

    still_present = [wb_id for wb_id in requested_ids if wb_id in set(current_ids)]
    if not still_present:
        return await _finalize_cargo_delete_operation(
            session,
            tenant_id,
            supply,
            operation,
            requested_ids,
            http_client,
        )

    try:
        await delete_marketplace_supply_trbx(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            trbx_ids=still_present,
        )
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            await session.commit()
            raise FbsShipmentPvzError("wb_timeout") from exc
        await mark_operation_failed(
            session,
            operation,
            error_code=_wb_error_code(exc),
            local_supply_id=supply.id,
        )
        await session.commit()
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    try:
        current_after = await fetch_marketplace_supply_trbx_list(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentPvzError(
            "wb_timeout" if exc.code == "transport_error" else _wb_error_code(exc)
        ) from exc

    still_after = [wb_id for wb_id in requested_ids if wb_id in set(current_after)]
    if still_after:
        raise FbsShipmentPvzError("wb_pending_confirmation")
    return await _finalize_cargo_delete_operation(
        session,
        tenant_id,
        supply,
        operation,
        requested_ids,
        http_client,
    )


async def delete_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    wb_trbx_ids: list[str],
    idempotency_key: str,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    if not idempotency_key.strip():
        raise FbsShipmentPvzError("missing_idempotency_key")

    normalized_ids = _normalize_wb_trbx_ids(wb_trbx_ids)
    supply = await _get_supply(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)
    _require_cargo_places_mutable_supply(supply)

    req_hash = request_hash_for_cargo_places_delete(
        supply_id=supply.id,
        wb_trbx_ids=normalized_ids,
    )
    existing_op = await get_cargo_delete_operation_by_idempotency(
        session,
        supply.seller_id,
        idempotency_key,
    )
    if existing_op is not None:
        if existing_op.request_hash != req_hash:
            raise FbsShipmentPvzError("idempotency_key_reused")
        if existing_op.state == WB_OPERATION_STATE_CONFIRMED:
            return await list_cargo_places(session, tenant_id, supply_id, http_client)
        if existing_op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
            return await _reconcile_pending_cargo_delete_operation(
                session,
                tenant_id,
                supply,
                existing_op,
                http_client,
            )
        if existing_op.state == WB_OPERATION_STATE_PENDING:
            raise FbsShipmentPvzError("wb_pending_confirmation")
        if existing_op.state == WB_OPERATION_STATE_FAILED:
            raise FbsShipmentPvzError(existing_op.error_code or "wb_operation_failed")

    # A confirmed retry must succeed even though the first request already
    # removed the local FbsTrbx rows. Membership is therefore validated only
    # for a genuinely new delete operation.
    _resolve_trbxes_for_delete(supply, normalized_ids)

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    operation = existing_op
    if operation is None:
        operation = await create_pending_cargo_delete_operation(
            session,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            request_summary={
                "supply_id": str(supply.id),
                "wb_trbx_ids": normalized_ids,
            },
            local_supply_id=supply.id,
        )

    try:
        await delete_marketplace_supply_trbx(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            trbx_ids=normalized_ids,
        )
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            await session.commit()
            raise FbsShipmentPvzError("wb_timeout") from exc
        await mark_operation_failed(
            session,
            operation,
            error_code=_wb_error_code(exc),
            local_supply_id=supply.id,
        )
        await session.commit()
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    return await _finalize_cargo_delete_operation(
        session,
        tenant_id,
        supply,
        operation,
        normalized_ids,
        http_client,
    )


# Legacy helpers kept for deprecated /trbx routes.


async def create_trbxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    http_client: httpx.AsyncClient,
    *,
    length_mm: int | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    weight_g: int | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[FbsTrbx]:
    boxes = [
        CargoPlaceDraft(
            client_id=f"legacy-{idx}",
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            weight_g=weight_g,
            measurements_confirmed=(
                length_mm is None and width_mm is None and height_mm is None and weight_g is None
            ),
        )
        for idx in range(count)
    ]
    key = f"legacy-trbx-{supply_id}-{count}-{uuid.uuid4()}"
    places = await create_cargo_places(
        session,
        tenant_id,
        supply_id,
        count,
        boxes,
        key,
        http_client,
        actor_user_id=actor_user_id,
        confirmation_source="legacy_trbx_compatibility",
    )
    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    assert supply is not None
    by_id = {str(t.id): t for t in supply.trbxes}
    return [by_id[p["id"]] for p in places if p["id"] in by_id]


def _trbx_meta(trbx: FbsTrbx) -> TrbxMeta:
    return TrbxMeta(
        id=trbx.id,
        wb_trbx_id=trbx.wb_trbx_id,
        packaging_box_id=trbx.packaging_box_id,
        length_mm=trbx.length_mm,
        width_mm=trbx.width_mm,
        height_mm=trbx.height_mm,
        weight_g=trbx.weight_g,
        sticker_file=trbx.sticker_file,
    )


async def fetch_trbx_stickers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    type: str = "png",
) -> list[TrbxMeta]:
    _ = type
    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)
    await _ensure_cargo_qrs(session, tenant_id, supply, http_client)
    await session.flush()
    return [_trbx_meta(trbx) for trbx in supply.trbxes]


async def supply_has_ready_cargo_place_qrs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
) -> bool:
    if not supply.trbxes:
        return False
    trbx_ids = [trbx.id for trbx in supply.trbxes]
    stmt = select(func.count()).select_from(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_trbx_id.in_(trbx_ids),
        FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
        FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
    )
    result = await session.execute(stmt)
    ready_count = int(result.scalar_one())
    return ready_count == len(trbx_ids)
