"""FBS order marking — push identifiers to WB meta and sync check statuses."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_MARKING_CHECK_STATUSES,
    FBS_MARKING_KINDS,
    FBS_ORDER_MARKING_FROZEN_STATUSES,
    FBS_ORDER_MARKING_WRITE_STATUSES,
    MARKING_KIND_SGTIN,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import STATUS_PRINTED, MarkingCode
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_order_meta,
    put_marketplace_order_meta,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

_META_KIND_FROM_PLURAL: dict[str, str] = {
    "sgtins": MARKING_KIND_SGTIN,
    "uins": "uin",
    "imeis": "imei",
    "gtins": "gtin",
}


class FbsMarkingError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def normalize_check_status(raw: Any) -> str | None:
    """Map WB meta check status to internal enum (best-effort)."""
    if raw is None:
        return None
    if isinstance(raw, int):
        mapping = {
            0: "new",
            1: "checking",
            2: "ok",
            3: "error",
            4: "no_check",
        }
        return mapping.get(raw)
    text = str(raw).strip().lower()
    aliases = {
        "new": "new",
        "checking": "checking",
        "in_progress": "checking",
        "ok": "ok",
        "success": "ok",
        "valid": "ok",
        "error": "error",
        "failed": "error",
        "no_check": "no_check",
        "nocheck": "no_check",
    }
    normalized = aliases.get(text, text)
    if normalized in FBS_MARKING_CHECK_STATUSES:
        return normalized
    return None


def parse_wb_meta_statuses(meta: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Extract {(kind, value): check_status} from WB GET /meta response."""
    out: dict[tuple[str, str], str] = {}
    if not meta:
        return out

    # Nested under "meta" key (some WB responses).
    nested = meta.get("meta")
    if isinstance(nested, dict):
        for key, payload in nested.items():
            kind = key if key in FBS_MARKING_KINDS else _META_KIND_FROM_PLURAL.get(key)
            if kind is None:
                continue
            _collect_meta_entries(out, kind, payload)
        return out
    if isinstance(nested, list):
        for item in nested:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("type")
            if not isinstance(key, str):
                continue
            kind = key if key in FBS_MARKING_KINDS else _META_KIND_FROM_PLURAL.get(key)
            if kind is None:
                continue
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                status = normalize_check_status(
                    item.get("checkStatus") or item.get("check_status")
                )
                if status:
                    out[(kind, value.strip())] = status
        return out

    for plural, kind in _META_KIND_FROM_PLURAL.items():
        payload = meta.get(plural)
        if payload is not None:
            _collect_meta_entries(out, kind, payload)
        singular = meta.get(kind)
        if singular is not None:
            _collect_meta_entries(out, kind, singular)
    return out


def _collect_meta_entries(
    out: dict[tuple[str, str], str],
    kind: str,
    payload: Any,
) -> None:
    if isinstance(payload, str) and payload.strip():
        out[(kind, payload.strip())] = CHECK_STATUS_NEW
        return
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, str) and value.strip():
            status = normalize_check_status(
                payload.get("checkStatus") or payload.get("check_status")
            )
            out[(kind, value.strip())] = status or CHECK_STATUS_NEW
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        if isinstance(item, str) and item.strip():
            out[(kind, item.strip())] = CHECK_STATUS_NEW
            continue
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        status = normalize_check_status(
            item.get("checkStatus") or item.get("check_status")
        )
        out[(kind, value.strip())] = status or CHECK_STATUS_NEW


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsMarkingError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsMarkingError("missing_marketplace_token")
    return token


async def _get_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> FbsOrder | None:
    stmt = select(FbsOrder).where(
        FbsOrder.id == order_id,
        FbsOrder.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _lookup_marking_code(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    cis_code: str,
    for_update: bool = False,
) -> MarkingCode | None:
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.cis_code == cis_code,
        MarkingCode.seller_id == seller_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_order_markings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> list[FbsOrderMarking]:
    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")
    stmt = (
        select(FbsOrderMarking)
        .where(FbsOrderMarking.order_id == order_id)
        .order_by(FbsOrderMarking.kind, FbsOrderMarking.value)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert_order_marking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    kind: str,
    value: str,
    http_client: httpx.AsyncClient,
) -> FbsOrderMarking:
    kind_norm = kind.strip().lower()
    if kind_norm not in FBS_MARKING_KINDS:
        raise FbsMarkingError("invalid_kind")
    value_norm = value.strip()
    if not value_norm:
        raise FbsMarkingError("empty_value")

    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")
    if order.status in FBS_ORDER_MARKING_FROZEN_STATUSES:
        raise FbsMarkingError("order_marking_frozen")
    if order.status not in FBS_ORDER_MARKING_WRITE_STATUSES:
        raise FbsMarkingError("order_marking_frozen")

    code: MarkingCode | None = None
    if kind_norm == MARKING_KIND_SGTIN:
        code = await _lookup_marking_code(
            session,
            tenant_id=tenant_id,
            seller_id=order.seller_id,
            cis_code=value_norm,
            for_update=True,
        )
        if code is not None:
            linked_elsewhere = (
                await session.execute(
                    select(FbsOrderMarking.id).where(
                        FbsOrderMarking.marking_code_id == code.id,
                        FbsOrderMarking.order_id != order_id,
                    )
                )
            ).first()
            if linked_elsewhere is not None:
                raise FbsMarkingError("marking_code_already_assigned")

    token = await _require_marketplace_token(session, tenant_id, order.seller_id)
    try:
        await put_marketplace_order_meta(
            http_client,
            api_token=token,
            order_id=int(order.wb_order_id),
            kind=kind_norm,
            value=value_norm,
        )
    except WildberriesClientError as exc:
        raise FbsMarkingError(_wb_error_code(exc)) from exc

    stmt = select(FbsOrderMarking).where(
        FbsOrderMarking.order_id == order_id,
        FbsOrderMarking.kind == kind_norm,
        FbsOrderMarking.value == value_norm,
    )
    result = await session.execute(stmt)
    existing_row = result.scalar_one_or_none()
    try:
        # Keep both the new row and its code relation inside the savepoint.
        # The unique conflict is on ``marking_code_id``, not merely row creation.
        async with session.begin_nested():
            if existing_row is None:
                row = FbsOrderMarking(
                    order_id=order_id,
                    kind=kind_norm,
                    value=value_norm,
                    check_status=CHECK_STATUS_NEW,
                )
                session.add(row)
            else:
                row = existing_row
                row.check_status = CHECK_STATUS_NEW
            if kind_norm == MARKING_KIND_SGTIN:
                row.marking_code_id = code.id if code is not None else None
            await session.flush()
    except IntegrityError as exc:
        raise FbsMarkingError("marking_code_already_assigned") from exc

    if order.supply_id is not None:
        from app.services.fbs_packaging_integration_service import (
            sync_fbs_supply_after_order_marking_update,
        )

        await sync_fbs_supply_after_order_marking_update(
            session, tenant_id, order_id
        )

    return row


async def sync_order_marking_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[FbsOrderMarking]:
    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")

    markings = await list_order_markings(session, tenant_id, order_id)
    if not markings:
        return markings

    token = await _require_marketplace_token(session, tenant_id, order.seller_id)
    try:
        meta = await fetch_marketplace_order_meta(
            http_client,
            api_token=token,
            order_id=int(order.wb_order_id),
        )
    except WildberriesClientError as exc:
        raise FbsMarkingError(_wb_error_code(exc)) from exc

    status_map = parse_wb_meta_statuses(meta)
    for marking in markings:
        key = (marking.kind, marking.value)
        wb_status = status_map.get(key)
        if wb_status is not None:
            marking.check_status = wb_status

    await session.flush()

    if order.supply_id is not None:
        from app.services.fbs_packaging_integration_service import (
            sync_fbs_supply_after_order_marking_update,
        )

        await sync_fbs_supply_after_order_marking_update(
            session, tenant_id, order_id
        )

    return markings


async def assign_printed_supply_markings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[FbsOrderMarking]:
    """Assign already printed CZ codes one-to-one to FBS orders and push them to WB."""
    supply = (
        await session.execute(
            select(FbsSupply).where(
                FbsSupply.id == supply_id,
                FbsSupply.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if supply is None:
        raise FbsMarkingError("supply_not_found")
    if supply.packaging_task_id is None:
        raise FbsMarkingError("packaging_task_not_found")

    orders = list(
        (
            await session.execute(
                select(FbsOrder)
                .join(Product, Product.id == FbsOrder.product_id)
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.supply_id == supply_id,
                    Product.requires_honest_sign.is_(True),
                )
                .order_by(FbsOrder.created_at.asc(), FbsOrder.id.asc())
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    required_orders: dict[uuid.UUID, list[FbsOrder]] = {}
    for order in orders:
        if order.product_id is None:
            continue
        existing = (
            await session.execute(
                select(FbsOrderMarking.id).where(
                    FbsOrderMarking.order_id == order.id,
                    FbsOrderMarking.kind == MARKING_KIND_SGTIN,
                )
            )
        ).first()
        if existing is None:
            required_orders.setdefault(order.product_id, []).append(order)

    if not required_orders:
        return []

    line_rows = (
        await session.execute(
            select(PackagingTaskLine.id, PackagingTaskLine.product_id).where(
                PackagingTaskLine.task_id == supply.packaging_task_id,
                PackagingTaskLine.product_id.in_(required_orders),
            )
        )
    ).all()
    lines_by_product: dict[uuid.UUID, list[uuid.UUID]] = {}
    for line_id, product_id in line_rows:
        lines_by_product.setdefault(product_id, []).append(line_id)

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    assigned: list[FbsOrderMarking] = []
    for product_id, product_orders in required_orders.items():
        line_ids = lines_by_product.get(product_id, [])
        if not line_ids:
            raise FbsMarkingError("marking_codes_not_printed")
        already_linked = exists(
            select(FbsOrderMarking.id).where(
                FbsOrderMarking.marking_code_id == MarkingCode.id
            )
        )
        codes = list(
            (
                await session.execute(
                    select(MarkingCode)
                    .where(
                        MarkingCode.tenant_id == tenant_id,
                        MarkingCode.seller_id == supply.seller_id,
                        MarkingCode.product_id == product_id,
                        MarkingCode.packaging_task_line_id.in_(line_ids),
                        MarkingCode.status == STATUS_PRINTED,
                        ~already_linked,
                    )
                    .order_by(MarkingCode.printed_at.asc(), MarkingCode.id.asc())
                    .limit(len(product_orders))
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        if len(codes) < len(product_orders):
            raise FbsMarkingError("marking_codes_not_printed")

        for order, code in zip(product_orders, codes, strict=True):
            try:
                await put_marketplace_order_meta(
                    http_client,
                    api_token=token,
                    order_id=int(order.wb_order_id),
                    kind=MARKING_KIND_SGTIN,
                    value=code.cis_code,
                )
            except WildberriesClientError as exc:
                raise FbsMarkingError(_wb_error_code(exc)) from exc
            row = FbsOrderMarking(
                order_id=order.id,
                kind=MARKING_KIND_SGTIN,
                value=code.cis_code,
                check_status=CHECK_STATUS_NEW,
                marking_code_id=code.id,
            )
            session.add(row)
            assigned.append(row)

    await session.flush()
    # WB validates SGTIN asynchronously.  Poll immediately after all PUTs so
    # a synchronous/mock validation result can promote the FBS supply in the
    # same operator action; a still-pending result remains ``new/checking``.
    for order_id in {row.order_id for row in assigned}:
        await sync_order_marking_statuses(session, tenant_id, order_id, http_client)
    return assigned
