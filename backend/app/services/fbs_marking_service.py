"""FBS order marking — WB metadata requirements, pool KIZ, and status sync."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import String, and_, cast, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.models.marking_code import (
    EVENT_WB_ORPHANED,
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    STATUS_RESERVED,
    MarkingCode,
    MarkingCodeEvent,
)
from app.services import ozon_fbs_marking_gate_service as ozon_gate_svc
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
)
from app.services.marketplace_provider import (
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from app.services.marketplace_scope import is_wildberries
from app.services.marking_code_service import normalize_cis, record_event
from app.services.ozon_fbs_process_service import (
    OzonFbsProcessError,
    read_marking_status,
    submit_marking,
)
from app.services.ozon_provider_factory import build_ozon_provider
from app.services.wildberries_client import (
    WildberriesClientError,
    kiz_scan_skips_wb_readback,
    put_marketplace_order_meta,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_errors import WildberriesBusinessError
from app.services.wildberries_fbs_client import (
    MarketplaceMetaDetail,
    MarketplaceOrderMetaRow,
    delete_marketplace_order_meta,
    fetch_marketplace_orders_meta_batch,
    split_marketplace_order_id_batches,
)

logger = logging.getLogger(__name__)

OPERATION_KIND_ORDER_KIZ_BIND = "order_kiz_bind"

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


class FbsMarkingWriteAcceptedError(FbsMarkingError):
    """WB answered this call's metadata PUT; only the readback after it is unconfirmed.

    WMS-579: callers must not infer an accepted write from the error code alone.
    ``wb_pending_confirmation`` is also raised by a reconciling read that found
    no order row, when no PUT happened in that call at all. ``code`` is
    ``wb_pending_confirmation`` when the readback answered without the value (or
    without the order row), or the readback's own WB error code when the read
    itself failed.
    """


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

    required = _norm_list(row.get("requiredMeta", row.get("required_meta")))
    optional = _norm_list(row.get("optionalMeta", row.get("optional_meta")))
    return required, optional


def apply_wb_meta_requirements_to_order(order: FbsOrder, row: dict[str, Any]) -> None:
    required, optional = parse_meta_kinds_from_wb_row(row)
    # /orders/new supplies these lists; historical /orders may omit them.
    # An explicit empty list is a fresh WB snapshot and must clear the old list.
    # Missing or non-list fields do not overwrite previously received facts.
    if isinstance(row.get("requiredMeta", row.get("required_meta")), list):
        order.required_meta_json = required
    if isinstance(row.get("optionalMeta", row.get("optional_meta")), list):
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


def _normalize_decision(decision: str | None) -> str:
    """Ключ вердикта WB без разделителей: sgtinApplied, sgtin_applied и
    sgtin-applied — один и тот же ответ, и расходиться на этом нельзя."""
    if decision is None:
        return ""
    key = decision.strip().lower()
    for separator in ("-", "_", " "):
        key = key.replace(separator, "")
    return key


def map_wb_decision_to_meta_status(decision: str | None) -> str | None:
    if decision is None:
        return None
    key = _normalize_decision(decision)
    mapping = {
        "accepted": META_STATUS_ACCEPTED,
        "filled": META_STATUS_ACCEPTED,
        # Вердикты WB по sgtin. Перечень собран разбором боевых ответов WB
        # 20.08.2026 и записан в docs/BACKLOG-2026-08-19-CHAT-RU.md, раздел H.
        # Раньше их не было в словаре вообще: любой из них считался неизвестным,
        # а неизвестное — «WB ещё не подтвердил», и сдача вставала намертво,
        # хотя ответ WB уже окончательный и ждать нечего.
        #
        # Сдавать можно:
        "sgtinintroduced": META_STATUS_ACCEPTED,  # введён в оборот
        "sgtinsoldb2b": META_STATUS_ACCEPTED,  # продан по B2B, оборот закрыт
        "deadlineexceeded": META_STATUS_ACCEPTED,  # WB не дождался ЧЗ и пропустил
        # Сдавать нельзя — это отказ, а не «подождите»:
        "sgtinemitted": META_STATUS_REJECTED,  # код только эмитирован
        "sgtinapplied": META_STATUS_REJECTED,  # нанесён, но не введён в оборот
        "sgtinappliednotpaid": META_STATUS_REJECTED,
        "sgtinwrittenoff": META_STATUS_REJECTED,
        "sgtinwithdrawn": META_STATUS_REJECTED,
        "sgtinretired": META_STATUS_REJECTED,
        "sgtindisaggregated": META_STATUS_REJECTED,
        "sgtindisaggregation": META_STATUS_REJECTED,
        "sgtinnotfound": META_STATUS_REJECTED,
        "sgtinnogs": META_STATUS_REJECTED,  # потерян разделитель (см. fbs_kiz_service)
        "sgtininvalidformat": META_STATUS_REJECTED,
        "sgtininvalidpattern": META_STATUS_REJECTED,
        "sgtinhasinvalidsymbols": META_STATUS_REJECTED,
        "sgtinhasnonlatinsymbols": META_STATUS_REJECTED,
        "rejected": META_STATUS_REJECTED,
        "invalid": META_STATUS_REJECTED,
        "pending": META_STATUS_PENDING,
        "allowedwithoutcheck": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "replacementrequired": META_STATUS_REPLACEMENT_REQUIRED,
        "optional": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "notrequired": META_STATUS_ALLOWED_WITHOUT_CHECK,
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
                status = normalize_check_status(item.get("checkStatus") or item.get("check_status"))
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
        status = normalize_check_status(item.get("checkStatus") or item.get("check_status"))
        out[(kind, value.strip())] = status or CHECK_STATUS_NEW


def _meta_details_from_wb(details: tuple[MarketplaceMetaDetail, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in details:
        kind = item.key.strip().lower()
        status = map_wb_decision_to_meta_status(item.decision) or META_STATUS_UNKNOWN
        out[kind] = {
            "status": status,
            "value": item.value,
            "decision": item.decision,
            "reason": item.reason,
        }
    return out


# Решения WB, при которых заказ можно сдавать: код принят или не требуется.
_DELIVERY_OK_DECISIONS = frozenset(
    {
        "accepted",
        "filled",
        "optional",
        "notrequired",
        "sgtinintroduced",
        "sgtinsoldb2b",
        "deadlineexceeded",
    }
)

# Вердикты, у которых своя причина: оператору важно знать, что делать, а
# «WB не принял маркировку» не подсказывает ничего.
_DECISION_MESSAGES = {
    "sgtinapplied": (
        "Код нанесён, но не введён в оборот в Честном знаке — "
        "вводит селлер, мы на это повлиять не можем."
    ),
    "sgtinappliednotpaid": "Код не оплачен в Честном знаке — на стороне селлера.",
    "sgtinnogs": "Код без разделителей — отсканируйте Честный знак заново целиком.",
    "sgtinnotfound": "Честный знак не знает такого кода.",
    "sgtinwrittenoff": "Код уже выведен из оборота.",
    "sgtinwithdrawn": "Код отозван в Честном знаке.",
}


def _same_marking_value(local: str | None, remote: str | None) -> bool:
    """Один ли это код с точностью до невидимых разделителей.

    Сканер, работающий как клавиатура, не передаёт GS-разделители (0x1D): у нас
    код оседает склеенным, а WB возвращает его со всеми разделителями. Побайтное
    сравнение объявляло такую пару разными кодами, помечало маркировку как
    «WB подтвердил другой код» и намертво блокировало сдачу — при том, что WB
    код принял (бой 28.08.2026, ИП Рябов, десять заказов).
    """
    if local is None or remote is None:
        return local == remote
    return local.replace("\x1d", "") == remote.replace("\x1d", "")


def compute_delivery_allowed(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> bool:
    if getattr(order, "marketplace", "wb") == "ozon":
        return ozon_gate_svc.compute_delivery_allowed(order, markings)

    required = list(order.required_meta_json or [])
    if not required:
        return True
    for kind in required:
        mark = current_order_marking(markings, kind, include_rejected=True)
        if mark is None:
            return False
        details = mark.meta_details_json if isinstance(mark.meta_details_json, dict) else {}
        if mark.meta_status in {META_STATUS_REJECTED, META_STATUS_REPLACEMENT_REQUIRED}:
            return False
        reason = details.get("reason") if "reason" in details else mark.reason
        if isinstance(reason, str) and reason.strip():
            return False
        remote_value = details.get("value")
        if (kind == MARKING_KIND_SGTIN
                and mark.meta_status == META_STATUS_UNKNOWN and not remote_value):
            return False
        if isinstance(remote_value, str) and not _same_marking_value(mark.value, remote_value):
            return False
        decision = details.get("decision")
        if not isinstance(decision, str):
            return False
        normalized = _normalize_decision(decision)
        if normalized not in _DELIVERY_OK_DECISIONS:
            return False
    return True


def delivery_marking_message(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> str:
    """One short WB status for the existing final delivery confirmation."""
    if getattr(order, "marketplace", "wb") == "ozon":
        return ozon_gate_svc.delivery_message(order, markings)

    if not order.required_meta_json:
        return "WB: маркировка не требуется."
    for kind in order.required_meta_json:
        mark = current_order_marking(markings, kind, include_rejected=True)
        if mark is None:
            return "WB ещё не подтвердил маркировку."
        details = mark.meta_details_json if isinstance(mark.meta_details_json, dict) else {}
        if mark.meta_status == META_STATUS_REPLACEMENT_REQUIRED:
            return "WB подтвердил другой код маркировки."
        if mark.meta_status == META_STATUS_REJECTED:
            named = _DECISION_MESSAGES.get(_normalize_decision(details.get("decision")))
            return named if named else "WB не принял маркировку."
        reason = details.get("reason") if "reason" in details else mark.reason
        if isinstance(reason, str) and reason.strip():
            return f"WB не принял маркировку: {reason.strip()}"
        remote_value = details.get("value")
        if isinstance(remote_value, str) and not _same_marking_value(mark.value, remote_value):
            return "WB подтвердил другой код маркировки."
        decision = details.get("decision")
        if not isinstance(decision, str):
            return "WB ещё не подтвердил маркировку."
        normalized = _normalize_decision(decision)
        if normalized not in _DELIVERY_OK_DECISIONS:
            return "WB ещё не подтвердил маркировку."
    return "WB: маркировка подтверждена."


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
    states: list[dict[str, Any]] = []
    for kind in required + [k for k in optional if k not in required]:
        if order.marketplace == "ozon":
            current = [
                row for row in ozon_gate_svc.current_markings(order, markings) if row.kind == kind
            ]
        else:
            mark = current_order_marking(markings, kind, include_rejected=True)
            current = [mark] if mark is not None else []
        for mark in current:
            states.append(
                {
                    "id": str(mark.id),
                    "kind": kind,
                    "status": mark.meta_status,
                    "reason": mark.reason,
                    "source": mark.source,
                    "value_tail": _marking_value_tail(mark.value),
                }
            )
        if not current:
            states.append(
                {
                    "kind": kind,
                    "status": META_STATUS_MISSING,
                    "reason": None,
                    "source": None,
                    "value_tail": None,
                }
            )
    delivery_allowed = (
        bool(order.metadata_delivery_allowed)
        if order.metadata_delivery_allowed is not None
        else compute_delivery_allowed(order, markings)
    )
    return {
        "required": required,
        "optional": optional,
        "states": states,
        "delivery_allowed": delivery_allowed,
        "last_checked_at": (
            order.metadata_last_checked_at.isoformat() if order.metadata_last_checked_at else None
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
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.id == order_id,
            FbsOrder.tenant_id == tenant_id,
        )
        .options(selectinload(FbsOrder.product_positions))
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
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
    printed_for_line_id: uuid.UUID | None = None,
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
        select(MarkingCode).where(MarkingCode.id == code.id)
        .execution_options(populate_existing=True).with_for_update()
    )
    locked = (await session.execute(stmt)).scalar_one_or_none()
    if locked is None:
        return None
    if (
        locked.status == STATUS_PRINTED
        and printed_for_line_id is not None
        and locked.packaging_task_line_id == printed_for_line_id
    ):
        return locked
    from app.services.marking_code_service import (
        is_unbound_cancelled_wb_code,
        is_unbound_received_code,
    )

    if is_wildberries(order) and await is_unbound_cancelled_wb_code(session, locked):
        return locked
    if await is_unbound_received_code(session, locked):
        return locked
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


def _check_status_for_meta_detail(
    *,
    decision: str,
    meta_status: str,
) -> str:
    """Keep the legacy status consistent with the authoritative WB decision."""
    normalized_decision = decision.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_decision == "required":
        return CHECK_STATUS_NEW
    if meta_status == META_STATUS_ACCEPTED:
        return CHECK_STATUS_OK
    if meta_status == META_STATUS_ALLOWED_WITHOUT_CHECK:
        return CHECK_STATUS_NO_CHECK
    if meta_status in {
        META_STATUS_REJECTED,
        META_STATUS_REPLACEMENT_REQUIRED,
        META_STATUS_UNKNOWN,
    }:
        return CHECK_STATUS_ERROR
    if meta_status == META_STATUS_PENDING:
        return CHECK_STATUS_CHECKING
    return CHECK_STATUS_ERROR


async def _record_wb_orphaned_once(
    session: AsyncSession,
    marking: FbsOrderMarking,
    *,
    reason: str | None,
) -> None:
    if marking.marking_code_id is None:
        return
    # Serialize event creation on the code row.  A check-then-insert without this
    # lock allows two concurrent WB polls to produce duplicate audit facts.
    code = await session.scalar(
        select(MarkingCode).where(MarkingCode.id == marking.marking_code_id).with_for_update()
    )
    if code is None:
        return
    existing = await session.scalar(
        select(MarkingCodeEvent.id).where(
            MarkingCodeEvent.code_id == marking.marking_code_id,
            MarkingCodeEvent.event_type == EVENT_WB_ORPHANED,
        )
    )
    if existing is not None:
        return
    await record_event(
        session,
        code=code,
        event_type=EVENT_WB_ORPHANED,
        actor=None,
        reason=reason,
    )


async def record_pending_kiz_operation(
    session: AsyncSession,
    order: FbsOrder,
    marking: FbsOrderMarking,
    *,
    error_code: str,
    actor_user_id: uuid.UUID | None,
    idempotency_key: str,
    scan_auto_print_id: uuid.UUID | None = None,
) -> None:
    marking.meta_status = META_STATUS_UNKNOWN
    marking.check_status = CHECK_STATUS_ERROR
    marking.reason = "Wildberries не подтвердил результат; нужна сверка."
    operation_key = hashlib.sha256(
        f"{idempotency_key}:{order.id}:{marking.id}".encode()
    ).hexdigest()
    operation = await session.scalar(select(FbsWbOperation).where(
        FbsWbOperation.tenant_id == order.tenant_id,
        FbsWbOperation.seller_id == order.seller_id,
        FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
        FbsWbOperation.idempotency_key == operation_key,
    ).with_for_update())
    if operation is None:
        operation = FbsWbOperation(
            tenant_id=order.tenant_id, seller_id=order.seller_id,
            operation_kind=OPERATION_KIND_ORDER_KIZ_BIND,
            idempotency_key=operation_key,
            request_hash=hashlib.sha256(marking.value.encode()).hexdigest(),
            local_entity_type="fbs_order_marking", local_entity_id=marking.id,
            wb_object_kind="order", wb_object_id=str(order.wb_order_id),
            created_by_user_id=actor_user_id,
            request_summary_json=(
                {"scan_auto_print_id": str(scan_auto_print_id)}
                if scan_auto_print_id is not None
                else None
            ),
        )
        session.add(operation)
    # A later uncertain retry for the same binding reuses its existing key.
    operation.state = WB_OPERATION_STATE_PENDING_CONFIRMATION
    operation.error_code = error_code
    operation.error_context_json = None
    operation.confirmed_at = None
    operation.failed_at = None


async def confirmed_kiz_operation_for_scan_auto_print(
    session: AsyncSession,
    order: FbsOrder,
    marking: FbsOrderMarking,
    scan_auto_print_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> FbsWbOperation | None:
    """Find the confirmed uncertain write owned by this exact product scan."""
    result = await session.execute(
        select(FbsWbOperation)
        .where(
            FbsWbOperation.tenant_id == order.tenant_id,
            FbsWbOperation.seller_id == order.seller_id,
            FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
            FbsWbOperation.local_entity_type == "fbs_order_marking",
            FbsWbOperation.local_entity_id == marking.id,
            FbsWbOperation.wb_object_kind == "order",
            FbsWbOperation.wb_object_id == str(order.wb_order_id),
            FbsWbOperation.created_by_user_id == actor_user_id,
            FbsWbOperation.request_hash
            == hashlib.sha256(marking.value.encode()).hexdigest(),
            FbsWbOperation.state == WB_OPERATION_STATE_CONFIRMED,
            FbsWbOperation.confirmed_at.is_not(None),
        )
        .with_for_update()
    )
    matching = [
        operation
        for operation in result.scalars().all()
        if (operation.request_summary_json or {}).get("scan_auto_print_id")
        == str(scan_auto_print_id)
    ]
    return matching[0] if len(matching) == 1 else None


async def pending_kiz_operation(
    session: AsyncSession,
    marking: FbsOrderMarking,
    *,
    lock: bool = True,
) -> FbsWbOperation | None:
    stmt = select(FbsWbOperation).where(
        FbsWbOperation.tenant_id == marking.tenant_id,
        FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
        FbsWbOperation.local_entity_type == "fbs_order_marking",
        FbsWbOperation.local_entity_id == marking.id,
        FbsWbOperation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION,
    )
    stmt = stmt.with_for_update() if lock else stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


class SyncedMarkings(list[FbsOrderMarking]):
    """`_sync_order_meta_from_wb`'s markings, plus whether the WB answer was
    actually applied or skipped because it was stale (WMS-477 review finding 4).

    Every existing caller only ever indexed or iterated the plain list this
    function used to return, so this stays a drop-in `list[FbsOrderMarking]`;
    `.applied` is a purely additive signal for callers that must not count a
    skipped, stale answer as a real update.
    """

    def __init__(self, markings: list[FbsOrderMarking], *, applied: bool) -> None:
        super().__init__(markings)
        self.applied = applied


def _marking_verdict_fingerprint(
    meta_status: str,
    check_status: str,
    reason: str | None,
    meta_details_json: dict[str, Any] | None,
) -> tuple[str, str, str | None, dict[str, Any] | None]:
    """Point-in-time shape of a marking's WB verdict, for staleness checks.

    Dict equality is structural (order-independent), so this needs no
    serialization — just the field values a fresher writer would change.
    """
    return (meta_status, check_status, reason, meta_details_json)


async def _sync_order_meta_from_wb(
    session: AsyncSession,
    order: FbsOrder,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    meta_batch: list[MarketplaceOrderMetaRow] | None = None,
    expected_marking_ids: set[uuid.UUID] | None = None,
    expected_marking_verdicts: dict[uuid.UUID, tuple[str, str, str | None, dict[str, Any] | None]]
    | None = None,
    expected_order_last_checked_at: datetime | None = None,
) -> SyncedMarkings:
    """Apply one order's WB metadata answer under a row lock.

    `expected_marking_ids` alone (the pre-existing protection) only catches a
    code that was removed or replaced while this order's WB answer was in
    flight — it says nothing about a *different* writer refreshing the very
    same code to a newer verdict in the meantime (WMS-477 review finding 1: a
    slow `pending` from one writer can otherwise land after a fast `accepted`
    from another and silently revert it, or a slow `accepted` land after a
    fresher `rejected`). A caller that pre-fetches markings and a WB batch of
    its own before calling this (the button/minute-cycle batch path) should
    pass `expected_marking_verdicts` (a fingerprint of each marking's verdict
    fields at that same pre-fetch) and `expected_order_last_checked_at` (the
    order's own snapshot); when supplied, a fresher write by anyone else
    between that snapshot and this lock makes this call a no-op, exactly like
    an ID mismatch does.

    A caller that passes neither `expected_marking_ids` nor
    `expected_marking_verdicts` (`get_order_metadata`, `sync_order_marking_statuses`
    — the single-order path behind the "Проверить ЧЗ" button, the WB metadata
    card and the pre-handover sync) gets the same protection for free: this
    function takes that same snapshot itself, right before it does its own
    single-order WB fetch below (WMS-477 review round 2, finding Н1 — this
    call's own single HTTP round trip is exactly the same race, just with a
    shorter window). Only a caller that supplies an already-fetched
    `meta_batch` *without* `expected_marking_verdicts` gets no freshness check
    beyond the ID one, because by then this function has no "before its HTTP"
    moment left to snapshot — no real caller does this today.
    """
    order_id = order.id
    tenant_id = order.tenant_id
    wb_order_id = int(order.wb_order_id)
    before_ids = expected_marking_ids
    verdict_snapshot = expected_marking_verdicts
    checked_at_snapshot = expected_order_last_checked_at
    if before_ids is None:
        # No caller-supplied snapshot: this call is about to read WB itself
        # below (or was handed an already-fetched `meta_batch` without one —
        # same handling either way). Snapshot the verdict fields here, before
        # that happens, so the freshness check after the lock can catch the
        # same race the batch callers already guard against (WMS-477 review
        # finding Н1): a fresher write by anyone else landing in between.
        pre_fetch_markings = list(
            (
                await session.scalars(
                    select(FbsOrderMarking).where(
                        FbsOrderMarking.order_id == order_id,
                        FbsOrderMarking.tenant_id == tenant_id,
                    )
                )
            ).all()
        )
        before_ids = {marking.id for marking in pre_fetch_markings}
        if verdict_snapshot is None:
            verdict_snapshot = {
                marking.id: _marking_verdict_fingerprint(
                    marking.meta_status,
                    marking.check_status,
                    marking.reason,
                    marking.meta_details_json,
                )
                for marking in pre_fetch_markings
            }
            checked_at_snapshot = await session.scalar(
                select(FbsOrder.metadata_last_checked_at).where(FbsOrder.id == order_id)
            )
    batch = meta_batch
    if batch is None:
        batch = await fetch_marketplace_orders_meta_batch(
            http_client,
            api_token=token,
            order_ids=[wb_order_id],
        )
    # Network I/O above may have overlapped with an operator changing the KIZ.
    # Lock and reload the current local state before applying the remote snapshot.
    locked_order = await session.scalar(
        select(FbsOrder).where(FbsOrder.id == order_id)
        .options(selectinload(FbsOrder.markings).selectinload(FbsOrderMarking.marking_code))
        .with_for_update().execution_options(populate_existing=True)
    )
    if locked_order is None:
        raise FbsMarkingError("order_not_found")
    order = locked_order
    markings = list(
        (
            await session.execute(
                select(FbsOrderMarking)
                .where(
                    FbsOrderMarking.tenant_id == tenant_id,
                    FbsOrderMarking.order_id == order_id,
                )
                .order_by(FbsOrderMarking.kind, FbsOrderMarking.value)
                .options(selectinload(FbsOrderMarking.marking_code))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    if {marking.id for marking in markings} != before_ids:
        # The GET describes the previous binding; a completed scan/unbind wins.
        return SyncedMarkings(markings, applied=False)
    if verdict_snapshot is not None and (
        order.metadata_last_checked_at != checked_at_snapshot
        or any(
            _marking_verdict_fingerprint(
                marking.meta_status,
                marking.check_status,
                marking.reason,
                marking.meta_details_json,
            )
            != verdict_snapshot.get(marking.id)
            for marking in markings
        )
    ):
        # Same codes, but someone else already wrote a fresher (or equally
        # fresh) verdict for at least one of them while this HTTP call was in
        # flight — WMS-477 review finding 1. The ID check above only catches a
        # removed/replaced code; this catches the same code changing value.
        return SyncedMarkings(markings, applied=False)
    details_by_kind: dict[str, MarketplaceMetaDetail] = {}
    returned_kinds: set[str] = set()
    returned_details: tuple[MarketplaceMetaDetail, ...] = ()
    returned_row = False
    for row in batch:
        if row.order_id != wb_order_id:
            continue
        returned_row = True
        returned_details = row.meta_details
        for detail in row.meta_details:
            kind = detail.key.strip().lower()
            if kind in FBS_MARKING_KINDS:
                returned_kinds.add(kind)
                details_by_kind[kind] = detail

    if not returned_row:
        # An omitted order supplies no new verdict. Preserve the saved state so
        # pending/sending codes remain eligible for the next minute cycle.
        return SyncedMarkings(markings, applied=False)

    for marking in markings:
        meta_detail = details_by_kind.get(marking.kind)
        current = current_order_marking(markings, marking.kind, include_rejected=True)
        # A returned row is successful only when WB returned the expected kind.
        # A status entry for a value is not enough: treating it as fresh metadata
        # would mask a partial response and could incorrectly advance the local
        # lifecycle state.
        if marking.kind not in returned_kinds:
            marking.meta_status = META_STATUS_UNKNOWN
            marking.check_status = CHECK_STATUS_ERROR
            continue
        if (
            meta_detail is not None and current is marking
            and marking.kind == MARKING_KIND_SGTIN and not meta_detail.value
            and marking.meta_status == META_STATUS_REJECTED
            and await _kiz_write_refused_by_wb(session, marking)
        ):
            # WMS-635 R4.3: WB finally refused this KIZ, so its metadata stays
            # empty. An empty read is no news: the red «WB не принял ЧЗ» verdict
            # stays until the operator replaces or removes the code, or WB itself
            # shows the code (a non-empty answer is applied below as usual).
            continue
        if meta_detail is not None and current is marking:
            # Preserve every received WB detail, including unknown decisions, so a
            # later investigation sees the original remote answer rather than an
            # inferred local state.
            _apply_meta_detail_to_marking(marking, meta_detail)
            decision = meta_detail.decision.strip().lower()
            empty_sgtin = marking.kind == MARKING_KIND_SGTIN and not meta_detail.value
            # WMS-546 P2 (Astra review) — a SGTIN already sent to WB and awaiting
            # its echo (an open `pending_kiz_operation`, WMS-529's uncertain-write
            # path) must not turn `missing` on an empty answer just because WB's
            # own decision says "required": WB asking for a value it hasn't
            # echoed back yet is exactly the same "WB hasn't caught up" signal as
            # an empty `optional` answer, not "this order was never given a
            # code". `missing` drops the order out of both background cycles'
            # open-status selection, so once WB *does* catch up the order would
            # never resolve on its own again (R3/R4). Without an open operation,
            # behaviour is unchanged — WB genuinely has no code for this order.
            awaiting_wb_echo = empty_sgtin and decision == "required" and (
                await pending_kiz_operation(session, marking) is not None
            )
            if decision == "required" and not meta_detail.value and not awaiting_wb_echo:
                marking.meta_status = META_STATUS_MISSING
            elif empty_sgtin:
                # Optional metadata does not confirm the KIZ already bound locally.
                marking.meta_status = META_STATUS_UNKNOWN
            elif meta_detail.value and not _same_marking_value(marking.value, meta_detail.value):
                marking.meta_status = META_STATUS_REPLACEMENT_REQUIRED
            elif map_wb_decision_to_meta_status(meta_detail.decision) is None:
                marking.meta_status = META_STATUS_UNKNOWN
            marking.check_status = _check_status_for_meta_detail(
                decision=meta_detail.decision,
                meta_status=marking.meta_status,
            )
            if marking.meta_status in {META_STATUS_MISSING, META_STATUS_REPLACEMENT_REQUIRED}:
                await _record_wb_orphaned_once(session, marking, reason=marking.reason)
            # A successful GET alone does not establish which binding WB accepted.
            if meta_detail.value and _same_marking_value(marking.value, meta_detail.value):
                operation = await pending_kiz_operation(session, marking)
                if operation is not None:
                    if marking.meta_status in _META_DELIVERY_OK:
                        operation.state = WB_OPERATION_STATE_CONFIRMED
                        operation.confirmed_at = datetime.now(tz=UTC)
                        operation.error_code = None
                        operation.error_context_json = None
                    elif marking.meta_status == META_STATUS_REJECTED:
                        operation.state = WB_OPERATION_STATE_FAILED
                        operation.failed_at = datetime.now(tz=UTC)
                        operation.error_code = "meta_validation_fail"

    if returned_row:
        # Keep the actual WB snapshot, including remote values and keys unknown to
        # the current application.  Local marking rows remain the source for the
        # physical binding, but must never be presented as the remote response.
        order.meta_details_json = _meta_details_from_wb(returned_details)
    order.metadata_delivery_allowed = compute_delivery_allowed(order, markings)
    if returned_row and all(marking.kind in returned_kinds for marking in markings):
        order.metadata_last_checked_at = datetime.now(tz=UTC)
    await session.flush()
    return SyncedMarkings(markings, applied=True)


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
    actor_user_id: uuid.UUID | None,
    api_token: str | None = None,
    ozon_provider: OzonMarketplaceProvider | None = None,
    notify_supply: bool = True,
) -> list[FbsOrderMarking]:
    marking.meta_status = META_STATUS_SENDING
    await session.flush()

    if order.marketplace == "ozon":
        try:
            client_id, api_key = await MarketplaceAccountService(session).stored_credentials(
                tenant_id, order.seller_id
            )
            provider = ozon_provider or build_ozon_provider()
            result = await submit_marking(
                session,
                order=order,
                marking=marking,
                provider=provider,
                client_id=client_id,
                api_key=api_key,
            )
        except (MarketplaceAccountError, MarketplaceProviderError, OzonFbsProcessError) as exc:
            marking.meta_status = META_STATUS_ASSIGNED
            await session.flush()
            raise FbsMarkingError(getattr(exc, "code", "ozon_upstream_error")) from exc
        marking.meta_details_json = result.details
        marking.reason = result.reason
        if result.accepted:
            marking.meta_status = META_STATUS_ACCEPTED
            marking.check_status = CHECK_STATUS_OK
        elif result.pending:
            marking.meta_status = META_STATUS_PENDING
            marking.check_status = CHECK_STATUS_CHECKING
        else:
            marking.meta_status = META_STATUS_REJECTED
            marking.check_status = CHECK_STATUS_ERROR
            await session.flush()
            raise FbsMarkingError(
                "meta_validation_fail",
                context={"reasons": [result.reason or "Ozon отклонил код"]},
            )
        order.metadata_delivery_allowed = compute_delivery_allowed(
            order, await list_order_markings(session, tenant_id, order.id)
        )
        order.metadata_last_checked_at = datetime.now(tz=UTC)
        await session.flush()
        if notify_supply:
            await _notify_supply_marking_update(
                session, tenant_id, order.id, actor_user_id=actor_user_id,
            )
        return await list_order_markings(session, tenant_id, order.id)

    token = api_token or await require_marketplace_token(session, tenant_id, order.seller_id)
    if kiz_scan_skips_wb_readback():
        # WMS-640: the packing scan never calls WB. The code stays bound in WMS and
        # takes the existing «no answer» way: the minute autopoll reads WB and
        # sends it (resend_pending_kiz_bindings).
        marking.meta_status = META_STATUS_ASSIGNED
        raise FbsMarkingError("wb_transport_error")
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

    # WMS-579: from here on WB has answered the PUT, so every failure below is
    # an unknown result of an accepted write, not a refusal of it.
    if kiz_scan_skips_wb_readback():
        # WMS-639: the packing scan never waits for WB's verdict; the accepted
        # write is pending and the background reconciliation reads WB later.
        await session.flush()
        raise FbsMarkingWriteAcceptedError("wb_pending_confirmation")
    try:
        markings = await _sync_order_meta_from_wb(session, order, http_client, token)
    except WildberriesClientError as exc:
        raise FbsMarkingWriteAcceptedError(_wb_error_code(exc)) from exc
    remote_detail = (order.meta_details_json or {}).get(MARKING_KIND_SGTIN) or {}
    if marking.kind == MARKING_KIND_SGTIN and (
        not markings.applied
        or not remote_detail.get("value")
    ):
        raise FbsMarkingWriteAcceptedError("wb_pending_confirmation")
    if notify_supply:
        await _notify_supply_marking_update(
            session, tenant_id, order.id, actor_user_id=actor_user_id,
        )
    return markings


async def reconcile_pending_kiz_operation(
    session: AsyncSession,
    order: FbsOrder,
    marking: FbsOrderMarking,
    operation: FbsWbOperation,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Retry only after a fresh WB row establishes that its KIZ is empty.

    Callers hold the order/packaging locks for this binding. Missing orders,
    stale answers and a different remote KIZ cannot authorize an overwrite.
    An exact value, even with a pending verdict, needs no second PUT.
    """
    markings = await _sync_order_meta_from_wb(session, order, http_client, token)
    if not markings.applied:
        raise FbsMarkingError("wb_pending_confirmation")
    detail = (order.meta_details_json or {}).get(MARKING_KIND_SGTIN)
    if detail is None or (isinstance(detail, dict) and not detail.get("value")):
        try:
            await attach_order_meta_to_wb_and_sync(
                session, order.tenant_id, order, marking, http_client,
                actor_user_id=actor_user_id, api_token=token, notify_supply=False,
            )
        except (WildberriesClientError, FbsMarkingError) as exc:
            if isinstance(exc, FbsMarkingError) and exc.code == "meta_validation_fail":
                operation.state = WB_OPERATION_STATE_FAILED
                operation.failed_at = datetime.now(tz=UTC)
                operation.error_code = exc.code
            else:
                marking.meta_status = META_STATUS_UNKNOWN
                marking.check_status = CHECK_STATUS_ERROR
                marking.reason = "Wildberries не подтвердил результат; нужна сверка."
            raise


async def _kiz_write_refused_by_wb(session: AsyncSession, marking: FbsOrderMarking) -> bool:
    """The KIZ write of this binding was finally refused by WB (failed operation, R4.3)."""
    found = await session.scalar(
        select(FbsWbOperation.id)
        .where(
            FbsWbOperation.tenant_id == marking.tenant_id,
            FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
            FbsWbOperation.local_entity_type == "fbs_order_marking",
            FbsWbOperation.local_entity_id == marking.id,
            FbsWbOperation.state == WB_OPERATION_STATE_FAILED,
        )
        .limit(1)
    )
    return found is not None


def _kiz_write_failed_before_wb(error_code: str | None) -> bool:
    """The PUT itself got a temporary refusal or no answer (429, 408, 5xx, transport)."""
    code = error_code or ""
    return code in {
        "wb_upstream_error_429", "wb_upstream_error_408", "wb_transport_error",
    } or code.startswith("wb_upstream_error_5")


async def resend_pending_kiz_bindings(
    session: AsyncSession,
    order_keys: list[tuple[uuid.UUID, uuid.UUID]],
    http_client: httpx.AsyncClient,
    token: str,
) -> None:
    """WMS-635 R4.2: finish KIZ writes whose WB answer was temporary or lost.

    It reads WB first and sends the same KIZ again only when WB holds no code
    for the order, so a lost answer is never followed by a blind second write.

    WMS-642: no row is locked while WB is called. Every WB call runs after a
    commit; its result is applied by a short transaction that locks in the
    operator's order (order → KIZ → operation) and re-reads the binding. A
    write that landed for a code the operator removed meanwhile is taken back.
    """
    for order_id, tenant_id in order_keys:
        target = await _pending_kiz_resend_target(session, tenant_id, order_id)
        await session.commit()
        if target is None:
            continue
        order, marking, operation = target
        marking_id, operation_id = marking.id, operation.id
        value, wb_order_id = marking.value, int(order.wb_order_id)
        try:
            markings = await _sync_order_meta_from_wb(session, order, http_client, token)
        except WildberriesClientError as exc:
            logger.info("pending KIZ read for order %s not finished yet: %s", order_id, exc)
            await session.rollback()
            continue
        detail = (order.meta_details_json or {}).get(MARKING_KIND_SGTIN)
        remote_value = detail.get("value") if isinstance(detail, dict) else None
        if markings.applied and remote_value and _same_marking_value(value, remote_value):
            # WB already holds this very code: it is sent, only its verdict is pending.
            sent = await _operation_for_update(session, operation_id)
            if sent is not None and sent.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
                sent.error_code = "wb_pending_confirmation"
        await session.commit()
        if not markings.applied or remote_value:
            continue
        target = await _pending_kiz_resend_target(session, tenant_id, order_id)
        await session.commit()
        if target is None or target[1].id != marking_id:
            # The operator replaced or removed this code meanwhile.
            continue
        write_error: WildberriesClientError | None = None
        try:
            await put_marketplace_order_meta(
                http_client, api_token=token, order_id=wb_order_id,
                kind=MARKING_KIND_SGTIN, value=value,
            )
        except WildberriesClientError as exc:
            write_error = exc
        still_bound = await _apply_kiz_resend_write(session, order_id, marking_id, write_error)
        await session.commit()
        if not still_bound and (write_error is None or not _kiz_write_refused(write_error)):
            # The write landed or its answer was lost after the operator removed the code.
            await _take_back_kiz_from_wb(
                session, http_client, token, order_id, operation_id, wb_order_id, value
            )
        elif write_error is None:
            # WB's verdict for the code just written; on no answer the verdict cycle reads it.
            try:
                await _sync_order_meta_from_wb(session, order, http_client, token)
                await session.commit()
            except (WildberriesClientError, FbsMarkingError):
                await session.rollback()
        elif not _kiz_write_refused(write_error):
            logger.info("pending KIZ write for order %s not finished: %s", order_id, write_error)


@dataclass(frozen=True)
class QueuedKizCheck:
    """WB order numbers a supply must not leave with (WMS-642)."""

    not_sent: list[int]
    other_code_in_wb: list[int]


async def send_queued_kiz_of_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> QueuedKizCheck:
    """WMS-642: queued KIZ of a WB supply go to WB before the supply itself.

    The same background resend runs for this supply's orders, and a code taken
    back from WB unsuccessfully is taken back now. The result is read from the
    bindings afterwards, not from the attempts: a current code that WB has not
    taken, or an order where WB holds another code, keeps the supply here.
    """
    not_sent: set[int] = set()
    rows = await _supply_orders_with_queued_kiz(session, tenant_id, supply_id)
    for seller_id in {row.seller_id for row in rows}:
        keys = [(row.id, tenant_id) for row in rows if row.seller_id == seller_id]
        try:
            token = await require_marketplace_token(session, tenant_id, seller_id)
        except FbsMarkingError:
            not_sent.update(int(row.wb_order_id) for row in rows if row.seller_id == seller_id)
            continue
        await resend_pending_kiz_bindings(session, keys, http_client, token)
    not_sent.update(await _finish_failed_take_backs(session, tenant_id, supply_id, http_client))
    other_code: list[int] = []
    for row in await _supply_orders_with_queued_kiz(session, tenant_id, supply_id):
        target = await _pending_kiz_resend_target(session, tenant_id, row.id)
        if target is None:
            continue
        if target[1].meta_status == META_STATUS_REPLACEMENT_REQUIRED:
            other_code.append(int(row.wb_order_id))
        else:
            not_sent.add(int(row.wb_order_id))
    await session.commit()
    return QueuedKizCheck(not_sent=sorted(not_sent), other_code_in_wb=sorted(other_code))


async def _supply_orders_with_queued_kiz(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> list[Any]:
    rows = (
        await session.execute(
            select(FbsOrder.id, FbsOrder.seller_id, FbsOrder.wb_order_id)
            .join(FbsOrderMarking, FbsOrderMarking.order_id == FbsOrder.id)
            .join(
                FbsWbOperation,
                and_(
                    FbsWbOperation.local_entity_id == FbsOrderMarking.id,
                    FbsWbOperation.local_entity_type == "fbs_order_marking",
                    FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
                    FbsWbOperation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION,
                ),
            )
            .where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.supply_id == supply_id,
                FbsOrder.marketplace == "wb",
            )
            .distinct()
        )
    ).all()
    await session.commit()
    return list(rows)


def _kiz_write_refused(exc: WildberriesClientError) -> bool:
    """WB finally refused the code itself; anything else is retried, never dropped."""
    return isinstance(exc, WildberriesBusinessError) or exc.status_code == 400


async def _apply_kiz_resend_write(
    session: AsyncSession,
    order_id: uuid.UUID,
    marking_id: uuid.UUID,
    write_error: WildberriesClientError | None,
) -> bool:
    """Record one background KIZ write; False only when the binding itself is gone."""
    # The operator's lock order (order → KIZ → operation), so no wait cycle.
    order = await session.scalar(
        select(FbsOrder).where(FbsOrder.id == order_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    marking = await session.scalar(
        select(FbsOrderMarking)
        .where(FbsOrderMarking.id == marking_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if marking is None:
        return False
    operation = await pending_kiz_operation(session, marking)
    if operation is None:
        # Another path already settled this binding; the code stays the order's.
        return True
    if write_error is None:
        # WB took the write; the verdict cycle reads WB and confirms it. The
        # operation no longer counts as unsent, so it is never written blindly again.
        operation.error_code = "wb_pending_confirmation"
        return True
    if not _kiz_write_refused(write_error):
        return True
    # A final WB refusal of the code: the row turns red (WMS-635 R4.3).
    code = _wb_error_code(write_error)
    reasons: list[dict[str, Any]] = []
    if isinstance(write_error, WildberriesBusinessError):
        reasons = _meta_validation_reasons(write_error)
        if write_error.meta_validation:
            marking.reason = write_error.meta_validation[0].reason
        code = "meta_validation_fail"
    marking.meta_status = META_STATUS_REJECTED
    marking.check_status = CHECK_STATUS_ERROR
    marking.meta_details_json = {"meta_validation": reasons}
    marking.reason = marking.reason or f"WB не принял код ({code})."
    operation.state = WB_OPERATION_STATE_FAILED
    operation.failed_at = datetime.now(tz=UTC)
    operation.error_code = code
    if order is not None:
        order.metadata_delivery_allowed = False
    return True


_KIZ_TAKE_BACK_FAILED = "kiz_take_back_failed"


async def _take_back_kiz_from_wb(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    token: str,
    order_id: uuid.UUID,
    operation_id: uuid.UUID,
    wb_order_id: int,
    value: str,
) -> bool:
    """Remove from WB a code written after the operator had removed it locally.

    Only when WB holds exactly this code and, right before the delete, the
    order has no KIZ in WMS or only a queued one WB has never received. A
    failed attempt is kept on the closed operation; the handover finishes it
    (``_finish_failed_take_backs``).
    """
    try:
        rows = await fetch_marketplace_orders_meta_batch(
            http_client, api_token=token, order_ids=[wb_order_id]
        )
        remote = _remote_sgtin_value(rows, wb_order_id)
        if not remote or not _same_marking_value(value, remote):
            return True
        current = await session.scalar(
            select(FbsOrderMarking)
            .where(FbsOrderMarking.order_id == order_id, FbsOrderMarking.kind == MARKING_KIND_SGTIN)
            .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        may_be_in_wb = False
        if current is not None:
            queued = await pending_kiz_operation(session, current, lock=False)
            may_be_in_wb = _same_marking_value(current.value, value) or (
                queued is None or not _kiz_write_failed_before_wb(queued.error_code)
            )
        await session.commit()
        if may_be_in_wb:
            # The order's current code may be the one in WB now; leave WB to it.
            return True
        await delete_marketplace_order_meta(
            http_client, api_token=token, order_id=wb_order_id, key=MARKING_KIND_SGTIN
        )
        return True
    except WildberriesClientError as exc:
        logger.warning("KIZ of a removed binding is still in WB for order %s: %s", wb_order_id, exc)
        await session.rollback()
        operation = await _operation_for_update(session, operation_id)
        if operation is not None and operation.state == WB_OPERATION_STATE_FAILED:
            operation.error_code = _KIZ_TAKE_BACK_FAILED
            operation.request_summary_json = {
                **(operation.request_summary_json or {}), "take_back_value": value,
            }
        await session.commit()
        return False


async def _finish_failed_take_backs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[int]:
    """Take back the codes a failed attempt left in WB; WB orders still not done."""
    rows = (
        await session.execute(
            select(FbsWbOperation.id, FbsOrder.id, FbsOrder.wb_order_id, FbsOrder.seller_id)
            .join(
                FbsOrder,
                and_(
                    FbsOrder.tenant_id == FbsWbOperation.tenant_id,
                    FbsOrder.seller_id == FbsWbOperation.seller_id,
                    cast(FbsOrder.wb_order_id, String) == FbsWbOperation.wb_object_id,
                ),
            )
            .where(
                FbsWbOperation.tenant_id == tenant_id,
                FbsWbOperation.operation_kind == OPERATION_KIND_ORDER_KIZ_BIND,
                FbsWbOperation.state == WB_OPERATION_STATE_FAILED,
                FbsWbOperation.error_code == _KIZ_TAKE_BACK_FAILED,
                FbsOrder.supply_id == supply_id,
            )
        )
    ).all()
    await session.commit()
    left: list[int] = []
    for operation_id, order_id, wb_order_id, seller_id in rows:
        operation = await _operation_for_update(session, operation_id)
        summary = (operation.request_summary_json if operation is not None else None) or {}
        value = str(summary.get("take_back_value") or "")
        try:
            token = await require_marketplace_token(session, tenant_id, seller_id)
        except FbsMarkingError:
            left.append(int(wb_order_id))
            continue
        await session.commit()
        done = await _take_back_kiz_from_wb(
            session, http_client, token, order_id, operation_id, int(wb_order_id), value
        )
        if not done:
            left.append(int(wb_order_id))
            continue
        operation = await _operation_for_update(session, operation_id)
        if operation is not None:
            operation.error_code = "kiz_cancelled"
        await session.commit()
    return left


async def _operation_for_update(
    session: AsyncSession, operation_id: uuid.UUID
) -> FbsWbOperation | None:
    operation: FbsWbOperation | None = await session.scalar(
        select(FbsWbOperation)
        .where(FbsWbOperation.id == operation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return operation


def _remote_sgtin_value(rows: list[MarketplaceOrderMetaRow], wb_order_id: int) -> str | None:
    return next(
        (
            detail.value
            for row in rows
            if row.order_id == wb_order_id
            for detail in row.meta_details
            if detail.key.strip().lower() == MARKING_KIND_SGTIN
        ),
        None,
    )


async def _pending_kiz_resend_target(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[FbsOrder, FbsOrderMarking, FbsWbOperation] | None:
    """The order's current bound KIZ with a write not yet sent to WB; nothing is locked."""
    order = await session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )
    marking = await session.scalar(
        select(FbsOrderMarking)
        .where(
            FbsOrderMarking.order_id == order_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
            FbsOrderMarking.meta_status != META_STATUS_REJECTED,
        )
        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    operation = await pending_kiz_operation(session, marking, lock=False) if marking else None
    if (
        order is None or marking is None or operation is None
        or not _kiz_write_failed_before_wb(operation.error_code)
    ):
        # A write WB answered (empty read-back) stays read-only (WMS-546 R2).
        return None
    return order, marking, operation

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
    actor_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")
    markings = await list_order_markings(session, tenant_id, order_id)
    # Карточка заказа Ozon не должна требовать токен Wildberries. Ветки по
    # маркетплейсу здесь не было вовсе: открытие карточки озоновского заказа
    # безусловно шло за чужим токеном и падало, если его нет. Статусы
    # маркировки Ozon обновляются своей ручкой синхронизации.
    if sync_wb and markings and getattr(order, "marketplace", "wb") == "wb":
        token = await require_marketplace_token(session, tenant_id, order.seller_id)
        markings = await _sync_order_meta_from_wb(session, order, http_client, token)
        await _notify_supply_marking_update(
            session,
            tenant_id,
            order_id,
            actor_user_id=actor_user_id,
        )
    return build_order_metadata(order, markings)


async def sync_order_marking_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
    ozon_provider: OzonMarketplaceProvider | None = None,
) -> list[FbsOrderMarking]:
    from app.services.fbs_packaging_integration_service import lock_order_packaging_rows

    order = await _get_order(session, tenant_id, order_id)
    if order is None:
        raise FbsMarkingError("order_not_found")

    markings = await list_order_markings(session, tenant_id, order_id)
    if not markings:
        return markings

    if order.marketplace == "ozon":
        before_ids = {marking.id for marking in markings}
        try:
            client_id, api_key = await MarketplaceAccountService(session).stored_credentials(
                tenant_id, order.seller_id
            )
            result = await read_marking_status(
                posting_number=order.external_order_id or "",
                provider=ozon_provider or build_ozon_provider(),
                client_id=client_id,
                api_key=api_key,
            )
        except (MarketplaceAccountError, MarketplaceProviderError, OzonFbsProcessError) as exc:
            raise FbsMarkingError(getattr(exc, "code", "ozon_upstream_error")) from exc
        await lock_order_packaging_rows(session, tenant_id, order_id)
        refreshed = await _get_order(session, tenant_id, order_id, for_update=True)
        if refreshed is None:
            raise FbsMarkingError("order_not_found")
        order = refreshed
        markings = await list_order_markings(session, tenant_id, order_id)
        if {marking.id for marking in markings} != before_ids:
            # This posting-level response predates the operator's replacement.
            return markings
        ozon_gate_svc.apply_status(
            order,
            markings,
            details=result.details,
            reason=result.reason,
            accepted=result.accepted,
            pending=result.pending,
        )
        order.metadata_delivery_allowed = compute_delivery_allowed(order, markings)
        order.metadata_last_checked_at = datetime.now(tz=UTC)
        await session.flush()
        await _notify_supply_marking_update(
            session,
            tenant_id,
            order_id,
            actor_user_id=actor_user_id,
        )
        return markings

    token = await require_marketplace_token(session, tenant_id, order.seller_id)
    try:
        markings = await _sync_order_meta_from_wb(session, order, http_client, token)
    except WildberriesClientError as exc:
        raise FbsMarkingError(_wb_error_code(exc)) from exc

    await _notify_supply_marking_update(
        session,
        tenant_id,
        order_id,
        actor_user_id=actor_user_id,
    )
    return markings


async def _notify_supply_marking_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    order = await session.get(FbsOrder, order_id)
    if order is None or order.supply_id is None:
        return
    from app.services.fbs_packaging_integration_service import (
        sync_fbs_supply_after_order_marking_update,
    )

    await sync_fbs_supply_after_order_marking_update(
        session,
        tenant_id,
        order_id,
        actor_user_id=actor_user_id,
    )


@dataclass(frozen=True)
class MarkingVerdictsSyncResult:
    """How many orders a batch verdict sync looked at and actually refreshed (WMS-477)."""

    orders_checked: int
    orders_updated: int


async def sync_marking_verdicts_batch(
    session: AsyncSession,
    orders: list[FbsOrder],
    http_client: httpx.AsyncClient,
    token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> MarkingVerdictsSyncResult:
    """Refresh WB verdicts for many orders' marking codes in ≤100-order batches.

    Shared by the per-supply "Проверить в WB" endpoint (WMS-477 R2,
    `sync_marking_verdicts_for_supply` below) and the background verdicts-recheck
    cycle (WMS-477 R5, `fbs_autopoll_service.sync_marking_verdicts_for_seller`) —
    the two callers that need WB's answer for *many* orders' codes at once,
    unlike the existing one-order-at-a-time `sync_order_marking_statuses`.

    Every batch is read from WB before anything is applied to the database: if
    any batch fails, no marking in `orders` is touched at all (R2/R3 — a failed
    check must never look like a partial success), and the original
    `WildberriesClientError` propagates so the caller decides how to isolate the
    failure (R6 — one seller's WB error must not touch another seller's codes
    or stop the rest of the cycle).
    """
    wb_order_ids = list(dict.fromkeys(int(order.wb_order_id) for order in orders))
    if not wb_order_ids:
        return MarkingVerdictsSyncResult(orders_checked=0, orders_updated=0)

    order_ids = [order.id for order in orders]
    expected_marking_ids: dict[uuid.UUID, set[uuid.UUID]] = {}
    marking_fingerprints: dict[
        uuid.UUID, tuple[str, str, str | None, dict[str, Any] | None]
    ] = {}
    marking_rows = (
        await session.execute(
            select(
                FbsOrderMarking.order_id,
                FbsOrderMarking.id,
                FbsOrderMarking.meta_status,
                FbsOrderMarking.check_status,
                FbsOrderMarking.reason,
                FbsOrderMarking.meta_details_json,
            ).where(FbsOrderMarking.order_id.in_(order_ids))
        )
    ).all()
    for row_order_id, marking_id, meta_status, check_status, reason, meta_details_json in (
        marking_rows
    ):
        expected_marking_ids.setdefault(row_order_id, set()).add(marking_id)
        marking_fingerprints[marking_id] = _marking_verdict_fingerprint(
            meta_status, check_status, reason, meta_details_json
        )
    # Snapshotting the order's own "last checked" timestamp alongside the
    # marking fields (WMS-477 review finding 1) closes a gap the ID-only
    # check leaves open: a concurrent writer (the button, the minute cycle
    # itself on another order batch, or the general sweep) can refresh the
    # very same code to a newer verdict without ever changing its ID.
    order_checked_at_snapshot: dict[uuid.UUID, datetime | None] = {
        row_id: checked_at
        for row_id, checked_at in (
            await session.execute(
                select(FbsOrder.id, FbsOrder.metadata_last_checked_at).where(
                    FbsOrder.id.in_(order_ids)
                )
            )
        ).all()
    }

    # Read every batch first: a failure here must leave every marking as it was.
    batches: list[tuple[set[int], list[MarketplaceOrderMetaRow]]] = []
    for chunk in split_marketplace_order_id_batches(wb_order_ids):
        meta_batch = await fetch_marketplace_orders_meta_batch(
            http_client, api_token=token, order_ids=chunk
        )
        batches.append((set(chunk), meta_batch))

    checked = 0
    updated = 0
    for wb_ids_in_batch, meta_batch in batches:
        rows_by_wb_order_id: dict[int, list[MarketplaceOrderMetaRow]] = {}
        for row in meta_batch:
            rows_by_wb_order_id.setdefault(row.order_id, []).append(row)
        for order in orders:
            wb_id = int(order.wb_order_id)
            if wb_id not in wb_ids_in_batch:
                continue
            expected = expected_marking_ids.get(order.id)
            if not expected:
                # The code disappeared between selection and the WB answer —
                # nothing to apply; the next recheck will pick up whatever
                # the operator left behind.
                continue
            checked += 1
            returned_rows = rows_by_wb_order_id.get(wb_id, [])
            if not returned_rows:
                logger.warning(
                    "fbs marking verdicts sync: WB batch response missed order %s",
                    order.id,
                )
                continue
            result = await _sync_order_meta_from_wb(
                session,
                order,
                http_client,
                token,
                meta_batch=returned_rows,
                expected_marking_ids=expected,
                expected_marking_verdicts={mid: marking_fingerprints[mid] for mid in expected},
                expected_order_last_checked_at=order_checked_at_snapshot.get(order.id),
            )
            if not result.applied:
                # A fresher (or equally fresh) verdict already won for this
                # order's code while this batch's HTTP call was in flight —
                # not a real update, and _notify_supply_marking_update below
                # would have nothing new to recompute from (WMS-477 review
                # finding 4: this used to be counted as updated regardless).
                logger.info(
                    "fbs marking verdicts sync: stale WB answer skipped for order %s",
                    order.id,
                )
                continue
            await _notify_supply_marking_update(
                session,
                order.tenant_id,
                order.id,
                actor_user_id=actor_user_id,
            )
            updated += 1
    return MarkingVerdictsSyncResult(orders_checked=checked, orders_updated=updated)


async def sync_marking_verdicts_for_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> MarkingVerdictsSyncResult:
    """WMS-477 R2 — «Проверить в WB»: пересверить все закодированные WB-заказы поставки.

    Заказ участвует, если у него есть хотя бы один код маркировки любого
    статуса (в том числе `unknown` и `rejected` — решение D1 в требованиях):
    пакет WB стоит одинаково независимо от статуса, а заодно подтверждаются
    коды, потерявшие ответ, и обновляются отказы. Заказы без кода и заказы
    других маркетплейсов в выборку не попадают — пустая выборка не делает ни
    одного вызова WB.
    """
    supply = await session.scalar(
        select(FbsSupply).where(
            FbsSupply.id == supply_id,
            FbsSupply.tenant_id == tenant_id,
        )
    )
    if supply is None:
        raise FbsMarkingError("supply_not_found")

    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
            FbsOrder.marketplace == "wb",
            exists(
                select(FbsOrderMarking.id).where(FbsOrderMarking.order_id == FbsOrder.id)
            ),
        )
        .order_by(FbsOrder.id.asc())
    )
    orders = list((await session.execute(stmt)).scalars().all())
    if not orders:
        return MarkingVerdictsSyncResult(orders_checked=0, orders_updated=0)

    token = await require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        return await sync_marking_verdicts_batch(
            session,
            orders,
            http_client,
            token,
            actor_user_id=actor_user_id,
        )
    except WildberriesClientError as exc:
        raise FbsMarkingError(_wb_error_code(exc)) from exc
