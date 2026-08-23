"""FBS order marking — WB metadata requirements, pool KIZ, and status sync."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_ERROR,
    CHECK_STATUS_NEW,
    CHECK_STATUS_NO_CHECK,
    CHECK_STATUS_OK,
    FBS_MARKING_CHECK_STATUSES,
    FBS_MARKING_KINDS,
    MARKING_KIND_SGTIN,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_ASSIGNED,
    META_STATUS_MISSING,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    META_STATUS_SENDING,
    META_STATUS_UNKNOWN,
    FbsOrder,
    FbsOrderMarking,
    current_order_marking,
)
from app.models.marking_code import STATUS_AVAILABLE, STATUS_RESERVED, MarkingCode
from app.services.marking_code_service import normalize_cis
from app.services.wildberries_client import (
    WildberriesClientError,
    put_marketplace_order_meta,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_errors import WildberriesBusinessError
from app.services.wildberries_fbs_client import (
    MarketplaceMetaDetail,
    fetch_marketplace_orders_meta_batch,
)

_META_KIND_FROM_PLURAL: dict[str, str] = {
    "sgtins": MARKING_KIND_SGTIN,
    "uins": "uin",
    "imeis": "imei",
    "gtins": "gtin",
}

_META_DELIVERY_OK = frozenset({META_STATUS_ACCEPTED, META_STATUS_ALLOWED_WITHOUT_CHECK})


class FbsMarkingError(Exception):
    def __init__(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.context = context or {}
        super().__init__(code)


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def parse_meta_kinds_from_wb_row(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract normalized required/optional meta kinds from WB order JSON."""

    def _norm_list(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                kind = item.strip().lower()
                if kind in FBS_MARKING_KINDS and kind not in out:
                    out.append(kind)
        return out

    required = _norm_list(row.get("requiredMeta") or row.get("required_meta"))
    optional = _norm_list(row.get("optionalMeta") or row.get("optional_meta"))
    return required, optional


def apply_wb_meta_requirements_to_order(order: FbsOrder, row: dict[str, Any]) -> None:
    required, optional = parse_meta_kinds_from_wb_row(row)
    if required:
        order.required_meta_json = required
    if optional:
        order.optional_meta_json = optional


def normalize_check_status(raw: Any) -> str | None:
    """Map WB meta check status to internal enum (best-effort)."""
    if raw is None:
        return None
    if isinstance(raw, int):
        mapping = {
            0: CHECK_STATUS_NEW,
            1: CHECK_STATUS_CHECKING,
            2: CHECK_STATUS_OK,
            3: CHECK_STATUS_ERROR,
            4: CHECK_STATUS_NO_CHECK,
        }
        return mapping.get(raw)
    text = str(raw).strip().lower()
    aliases = {
        "new": CHECK_STATUS_NEW,
        "checking": CHECK_STATUS_CHECKING,
        "in_progress": CHECK_STATUS_CHECKING,
        "ok": CHECK_STATUS_OK,
        "success": CHECK_STATUS_OK,
        "valid": CHECK_STATUS_OK,
        "error": CHECK_STATUS_ERROR,
        "failed": CHECK_STATUS_ERROR,
        "no_check": CHECK_STATUS_NO_CHECK,
        "nocheck": CHECK_STATUS_NO_CHECK,
    }
    normalized = aliases.get(text, text)
    if normalized in FBS_MARKING_CHECK_STATUSES:
        return normalized
    return None


def map_wb_decision_to_meta_status(decision: str | None) -> str | None:
    if decision is None:
        return None
    key = decision.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "accepted": META_STATUS_ACCEPTED,
        "filled": META_STATUS_ACCEPTED,
        "rejected": META_STATUS_REJECTED,
        "pending": META_STATUS_PENDING,
        "required": META_STATUS_MISSING,
        "optional": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "notrequired": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "allowedwithoutcheck": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "allowed_without_check": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "replacementrequired": META_STATUS_REPLACEMENT_REQUIRED,
        "replacement_required": META_STATUS_REPLACEMENT_REQUIRED,
    }
    return mapping.get(key)


def derive_meta_status(
    *,
    check_status: str | None,
    decision: str | None = None,
    has_value: bool = False,
    sending: bool = False,
) -> str:
    from_decision = map_wb_decision_to_meta_status(decision)
    if from_decision is not None:
        return from_decision
    if sending:
        return META_STATUS_SENDING
    if check_status == CHECK_STATUS_OK:
        return META_STATUS_ACCEPTED
    if check_status == CHECK_STATUS_NO_CHECK:
        return META_STATUS_ALLOWED_WITHOUT_CHECK
    if check_status == CHECK_STATUS_ERROR:
        return META_STATUS_REJECTED
    if check_status in {CHECK_STATUS_CHECKING, CHECK_STATUS_NEW}:
        return META_STATUS_PENDING if has_value else META_STATUS_ASSIGNED
    if has_value:
        return META_STATUS_ASSIGNED
    return META_STATUS_MISSING


def parse_wb_meta_statuses(meta: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Extract {(kind, value): check_status} from WB GET /meta response."""
    out: dict[tuple[str, str], str] = {}
    if not meta:
        return out

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


def _meta_details_from_wb(details: tuple[MarketplaceMetaDetail, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in details:
        kind = item.key.strip().lower()
        if kind not in FBS_MARKING_KINDS:
            continue
        status = map_wb_decision_to_meta_status(item.decision) or META_STATUS_UNKNOWN
        out[kind] = {
            "status": status,
            "value": item.value,
            "decision": item.decision,
            "reason": item.reason,
        }
    return out


def _meta_details_from_markings(markings: list[FbsOrderMarking]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in {marking.kind for marking in markings}:
        mark = current_order_marking(markings, kind, include_rejected=True)
        if mark is None:
            continue
        details = mark.meta_details_json if isinstance(mark.meta_details_json, dict) else {}
        out[mark.kind] = {
            "status": mark.meta_status,
            "value": mark.value,
            "decision": details.get("decision"),
            "reason": mark.reason,
        }
    return out


def _wb_order_verdict(
    order: FbsOrder, markings: list[FbsOrderMarking]
) -> dict[str, Any]:
    """Return the single operator-facing WB verdict and its delivery gate."""
    required = list(order.required_meta_json or [])
    optional = list(getattr(order, "optional_meta_json", None) or [])
    requested = required + [kind for kind in optional if kind not in required]
    states: list[dict[str, Any]] = []
    raw_order_details = getattr(order, "meta_details_json", None)
    order_details: dict[str, Any] = (
        raw_order_details if isinstance(raw_order_details, dict) else {}
    )
    for kind in requested:
        is_required = kind in required
        mark = current_order_marking(markings, kind, include_rejected=True)
        stored_details = order_details.get(kind)
        details: dict[str, Any] = (
            dict(stored_details) if isinstance(stored_details, dict) else {}
        )
        raw_details = getattr(mark, "meta_details_json", None) if mark else None
        if isinstance(raw_details, dict):
            for key, value in raw_details.items():
                if details.get(key) is None and value is not None:
                    details[key] = value
        states.append(
            {
                "kind": kind,
                "required": is_required,
                # WB can return optional/notRequired without a local marking row.
                "decision": details.get("decision"),
                "reason": (
                    details.get("reason")
                    if "reason" in details
                    else getattr(mark, "reason", None)
                ),
                "status": details.get(
                    "status",
                    mark.meta_status if mark else META_STATUS_MISSING,
                ),
            }
        )

    if not states:
        return {
            "signature": "WB: код не требуется",
            "tone": "neutral",
            "reason": None,
            "delivery_allowed": True,
        }
    for state in states:
        if isinstance(state["reason"], str) and state["reason"].strip():
            return {
                "signature": "WB не принял",
                "tone": "stop",
                "reason": state["reason"],
                "delivery_allowed": False,
            }
    decisions = {
        str(state["decision"]).strip().lower().replace("-", "_")
        for state in states
        if state["decision"] is not None
    }
    if "required" in decisions or any(
        state["required"] and state["decision"] is None
        and state["status"] == META_STATUS_MISSING
        for state in states
    ):
        return {
            "signature": "WB: нужен код",
            "tone": "stop",
            "reason": None,
            "delivery_allowed": False,
        }
    if any(
        state["decision"] is None and not state["required"]
        for state in states
    ) or not decisions.issubset(
        {
            "accepted",
            "filled",
            "optional",
            "notrequired",
            "not_required",
            "pending",
            "required",
        }
    ) or any(
        state["decision"] is None and state["status"] not in {META_STATUS_MISSING}
        for state in states
    ):
        return {
            "signature": "Нет ответа WB",
            "tone": "stop",
            "reason": None,
            "delivery_allowed": False,
        }
    if "pending" in decisions:
        return {
            "signature": "WB: проверяет",
            "tone": "neutral",
            "reason": None,
            "delivery_allowed": False,
        }
    if decisions.issubset({"optional", "notrequired", "not_required"}):
        return {
            "signature": "WB: код не требуется",
            "tone": "neutral",
            "reason": None,
            "delivery_allowed": True,
        }
    return {
        "signature": "WB: принято",
        "tone": "ok",
        "reason": None,
        "delivery_allowed": True,
    }


def compute_delivery_allowed(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> bool:
    return bool(_wb_order_verdict(order, markings)["delivery_allowed"])


def _marking_value_tail(value: str | None, length: int = 8) -> str | None:
    """Последние символы кода маркировки — опознавательный хвост для оператора."""
    if not value:
        return None
    cleaned = value.strip()
    return cleaned[-length:] if len(cleaned) > length else cleaned


def build_order_metadata(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> dict[str, Any]:
    required = list(order.required_meta_json or [])
    optional = list(order.optional_meta_json or [])
    raw_order_details = getattr(order, "meta_details_json", None)
    order_details: dict[str, Any] = (
        raw_order_details if isinstance(raw_order_details, dict) else {}
    )
    states: list[dict[str, Any]] = []
    for kind in required + [k for k in optional if k not in required]:
        mark = current_order_marking(markings, kind, include_rejected=True)
        stored_details = order_details.get(kind)
        details = stored_details if isinstance(stored_details, dict) else {}
        if mark is not None:
            states.append(
                {
                    "kind": kind,
                    "status": details.get("status", mark.meta_status),
                    "reason": details.get("reason", mark.reason),
                    "source": mark.source,
                    # Хвост кода — чтобы оператор глазами сверил строку на экране
                    # с тем, что напечатано на этикетке. Весь код не отдаём: он
                    # длинный и в таблицу не помещается.
                    "value_tail": _marking_value_tail(mark.value),
                }
            )
        else:
            states.append(
                {
                    "kind": kind,
                    "status": details.get("status", META_STATUS_MISSING),
                    "reason": details.get("reason"),
                    "source": "wb" if details else None,
                    "value_tail": _marking_value_tail(details.get("value")),
                }
            )
    verdict = _wb_order_verdict(order, markings)
    return {
        "required": required,
        "optional": optional,
        "states": states,
        "delivery_allowed": verdict["delivery_allowed"],
        "verdict": verdict,
        "last_checked_at": (
            order.metadata_last_checked_at.isoformat()
            if order.metadata_last_checked_at
            else None
        ),
    }


def order_marking_blocks_progress(order: FbsOrder) -> bool:
    """True when required WB metadata is missing or rejected (ignores product flag)."""
    required = list(order.required_meta_json or [])
    if not required:
        return False
    for kind in required:
        mark = current_order_marking(list(order.markings), kind)
        if mark is None:
            return True
        if mark.meta_status in {
            META_STATUS_REJECTED,
            META_STATUS_REPLACEMENT_REQUIRED,
            META_STATUS_MISSING,
        }:
            return True
        if mark.meta_status not in _META_DELIVERY_OK:
            return True
    return False


async def require_marketplace_token(
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
    *,
    for_update: bool = False,
) -> FbsOrder | None:
    stmt = select(FbsOrder).where(
        FbsOrder.id == order_id,
        FbsOrder.tenant_id == tenant_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _lookup_marking_code_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cis_code: str,
) -> MarkingCode | None:
    lookup_values = [cis_code]
    normalized = normalize_cis(cis_code)
    if normalized and normalized not in lookup_values:
        lookup_values.append(normalized)
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.cis_code.in_(lookup_values),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _claim_pool_code_if_present(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    cis_raw: str,
) -> MarkingCode | None:
    code = await _lookup_marking_code_in_tenant(
        session,
        tenant_id=tenant_id,
        cis_code=cis_raw,
    )
    if code is None:
        return None
    if code.seller_id != order.seller_id:
        raise FbsMarkingError("cross_seller_code")
    if (
        order.product_id is not None
        and code.product_id is not None
        and code.product_id != order.product_id
    ):
        raise FbsMarkingError("code_product_mismatch")
    stmt = (
        select(MarkingCode)
        .where(MarkingCode.id == code.id)
        .with_for_update()
    )
    locked = (await session.execute(stmt)).scalar_one_or_none()
    if locked is None:
        return None
    if locked.status != STATUS_AVAILABLE:
        raise FbsMarkingError("duplicate_kiz")
    locked.status = STATUS_RESERVED
    await session.flush()
    return locked


def _apply_meta_detail_to_marking(
    marking: FbsOrderMarking,
    detail: MarketplaceMetaDetail,
    *,
    check_status: str | None = None,
) -> None:
    reason_raw = getattr(detail, "reason", None)
    reason = str(reason_raw) if reason_raw is not None else None
    marking.meta_status = derive_meta_status(
        check_status=check_status,
        decision=detail.decision,
        has_value=bool(marking.value),
    )
    marking.reason = reason
    marking.meta_details_json = {
        "decision": detail.decision,
        "value": detail.value,
        "reason": reason,
    }


def _reset_stale_wb_verdict(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> None:
    """Fail closed before applying a fresh WB metadata response."""
    requested = set(order.required_meta_json or []) | set(order.optional_meta_json or [])
    stale_details: dict[str, Any] = {}
    for kind in requested:
        marking = current_order_marking(markings, kind, include_rejected=True)
        if marking is None:
            stale_details[kind] = {
                "status": META_STATUS_MISSING,
                "value": None,
                "decision": None,
                "reason": None,
            }
            continue
        marking.meta_status = META_STATUS_UNKNOWN
        marking.reason = None
        marking.meta_details_json = {
            "decision": None,
            "value": marking.value,
            "reason": None,
        }
        stale_details[kind] = {
            "status": META_STATUS_UNKNOWN,
            "value": marking.value,
            "decision": None,
            "reason": None,
        }
    order.meta_details_json = stale_details
    order.metadata_delivery_allowed = compute_delivery_allowed(order, markings)
    order.metadata_last_checked_at = datetime.now(tz=UTC)


def _marking_sync_signature(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> tuple[tuple[str, uuid.UUID | None, str | None], ...]:
    """Identify the exact order metadata and codes covered by a WB request."""
    requested = set(order.required_meta_json or []) | set(order.optional_meta_json or [])
    signature: list[tuple[str, uuid.UUID | None, str | None]] = []
    for kind in sorted(requested):
        marking = current_order_marking(markings, kind, include_rejected=True)
        signature.append(
            (
                kind,
                marking.id if marking is not None else None,
                marking.value if marking is not None else None,
            )
        )
    return tuple(signature)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _lock_current_marking_state(
    session: AsyncSession,
    order: FbsOrder,
) -> tuple[FbsOrder, list[FbsOrderMarking]]:
    order_stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.id == order.id,
            FbsOrder.tenant_id == order.tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_order = (await session.execute(order_stmt)).scalar_one_or_none()
    if locked_order is None:
        raise FbsMarkingError("order_not_found")
    markings_stmt = (
        select(FbsOrderMarking)
        .where(FbsOrderMarking.order_id == locked_order.id)
        .order_by(FbsOrderMarking.kind, FbsOrderMarking.value)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    markings = list((await session.execute(markings_stmt)).scalars().all())
    return locked_order, markings


def _wb_sync_response_is_stale(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
    *,
    started_at: datetime,
    signature: tuple[tuple[str, uuid.UUID | None, str | None], ...],
) -> bool:
    last_checked_at = order.metadata_last_checked_at
    if last_checked_at is not None and _as_utc(last_checked_at) > started_at:
        return True
    return _marking_sync_signature(order, markings) != signature


async def _sync_order_meta_from_wb(
    session: AsyncSession,
    order: FbsOrder,
    http_client: httpx.AsyncClient,
    token: str,
) -> list[FbsOrderMarking]:
    markings = await list_order_markings(session, order.tenant_id, order.id)
    started_at = datetime.now(tz=UTC)
    signature = _marking_sync_signature(order, markings)
    try:
        batch = await fetch_marketplace_orders_meta_batch(
            http_client,
            api_token=token,
            order_ids=[int(order.wb_order_id)],
        )
    except WildberriesClientError:
        locked_order, current_markings = await _lock_current_marking_state(
            session, order
        )
        if not _wb_sync_response_is_stale(
            locked_order,
            current_markings,
            started_at=started_at,
            signature=signature,
        ):
            _reset_stale_wb_verdict(locked_order, current_markings)
            locked_order.metadata_last_checked_at = started_at
        await session.flush()
        raise

    locked_order, markings = await _lock_current_marking_state(session, order)
    if _wb_sync_response_is_stale(
        locked_order,
        markings,
        started_at=started_at,
        signature=signature,
    ):
        return markings
    order = locked_order
    _reset_stale_wb_verdict(order, markings)
    details_by_kind: dict[str, MarketplaceMetaDetail] = {}
    status_map: dict[tuple[str, str], str] = {}
    for row in batch:
        if row.order_id != int(order.wb_order_id):
            continue
        if row.meta is not None:
            status_map.update(parse_wb_meta_statuses(row.meta))
        for detail in row.meta_details:
            details_by_kind[detail.key.strip().lower()] = detail

    for marking in markings:
        wb_status = status_map.get((marking.kind, marking.value))
        if wb_status is not None:
            marking.check_status = wb_status
        meta_detail = details_by_kind.get(marking.kind)
        current = current_order_marking(markings, marking.kind, include_rejected=True)
        detail_matches = meta_detail is not None and (
            meta_detail.value == marking.value
            or (meta_detail.value is None and current is marking)
        )
        if meta_detail is not None and detail_matches:
            _apply_meta_detail_to_marking(marking, meta_detail, check_status=wb_status)
        elif wb_status is not None:
            marking.meta_status = derive_meta_status(
                check_status=wb_status,
                has_value=True,
            )

    persisted_details = (
        dict(order.meta_details_json)
        if isinstance(order.meta_details_json, dict)
        else {}
    )
    persisted_details.update(_meta_details_from_markings(markings))
    persisted_details.update(_meta_details_from_wb(tuple(details_by_kind.values())))
    order.meta_details_json = persisted_details
    order.metadata_delivery_allowed = compute_delivery_allowed(order, markings)
    # Store when this check started, rather than when its response arrived.
    # The row lock can then compare concurrent results by request order even
    # when an older response is persisted before a newer response returns.
    order.metadata_last_checked_at = started_at
    await session.flush()
    return markings


def _meta_validation_reasons(exc: WildberriesBusinessError) -> list[dict[str, Any]]:
    return [
        {
            "order_id": item.order_id,
            "kind": item.key,
            "value": item.value,
            "decision": item.decision,
            "reason": item.reason,
        }
        for item in exc.meta_validation
    ]


async def attach_order_meta_to_wb_and_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    marking: FbsOrderMarking,
    http_client: httpx.AsyncClient,
    *,
    api_token: str | None = None,
) -> list[FbsOrderMarking]:
    marking.meta_status = META_STATUS_SENDING
    await session.flush()

    token = api_token or await require_marketplace_token(
        session, tenant_id, order.seller_id
    )
    try:
        await put_marketplace_order_meta(
            http_client,
            api_token=token,
            order_id=int(order.wb_order_id),
            kind=marking.kind,
            value=marking.value,
        )
    except WildberriesBusinessError as exc:
        marking.meta_status = META_STATUS_REJECTED
        reasons = _meta_validation_reasons(exc)
        if exc.meta_validation:
            marking.reason = exc.meta_validation[0].reason
        marking.meta_details_json = {"meta_validation": reasons}
        await session.flush()
        raise FbsMarkingError(
            "meta_validation_fail",
            context={"reasons": reasons},
        ) from exc
    except WildberriesClientError as exc:
        marking.meta_status = META_STATUS_ASSIGNED
        raise FbsMarkingError(_wb_error_code(exc)) from exc

    markings = await _sync_order_meta_from_wb(session, order, http_client, token)
    await _notify_supply_marking_update(session, tenant_id, order.id)
    return markings


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


async def get_order_metadata(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    sync_wb: bool = True,
) -> dict[str, Any]:
    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")
    markings = await list_order_markings(session, tenant_id, order_id)
    requested = bool(order.required_meta_json or order.optional_meta_json)
    if sync_wb and (markings or requested):
        token = await require_marketplace_token(session, tenant_id, order.seller_id)
        markings = await _sync_order_meta_from_wb(session, order, http_client, token)
        await _notify_supply_marking_update(session, tenant_id, order_id)
    return build_order_metadata(order, markings)


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
    requested = bool(order.required_meta_json or order.optional_meta_json)
    if not markings and not requested:
        return markings

    token = await require_marketplace_token(session, tenant_id, order.seller_id)
    try:
        markings = await _sync_order_meta_from_wb(session, order, http_client, token)
    except WildberriesClientError as exc:
        raise FbsMarkingError(_wb_error_code(exc)) from exc

    await _notify_supply_marking_update(session, tenant_id, order_id)
    return markings


async def _notify_supply_marking_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> None:
    order = await session.get(FbsOrder, order_id)
    if order is None or order.supply_id is None:
        return
    from app.services.fbs_packaging_integration_service import (
        sync_fbs_supply_after_order_marking_update,
    )

    await sync_fbs_supply_after_order_marking_update(session, tenant_id, order_id)
