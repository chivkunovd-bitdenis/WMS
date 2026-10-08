"""WMS-686: КИЗ на строке товара отгрузки FBO.

КИЗ хранится на строке товара отгрузки (marking_codes.marketplace_unload_line_id).
Связи «КИЗ ↔ короб» нет: товар связан с коробом составом короба, а с КИЗ — этой
колонкой. K (сколько КИЗ у товара в отгрузке) всегда считается COUNT-ом по кодам
строки, независимых счётчиков нет.

Один путь привязки для подбора и упаковки: link_marking_code. Нормализацию кода
делает единая функция FBS (fbs_kiz_service.normalize_scanned_cis), поиск
существующего кода — тем же способом, что в FBS. Никаких обращений к внешним API.

Порядок блокировок: документ (FOR UPDATE) -> строка товара (FOR UPDATE) -> код
(FOR UPDATE). Гонку уникальности (tenant, cis) ловим и повторяем проверки уже
по существующему коду.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_event import (
    DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
    EVENT_DATA_CHANGED,
    SOURCE_SYSTEM,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import FbsOrderMarking
from app.models.marketplace_unload import (
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_IMPORTED,
    EVENT_PRINTED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_DEFECTIVE,
    STATUS_INTRODUCED,
    STATUS_REPLACED,
    STATUS_RESERVED,
    STATUS_SHIPPED,
    STATUS_TRANSFERRED,
    STATUS_VOID,
    MarkingCode,
    MarkingCodeEvent,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.services import fbs_kiz_service as fbs_kiz_svc
from app.services import fbs_marking_service as fbs_marking_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import marking_code_service as marking_code_svc
from app.services.catalog_service import ID_IN_BATCH_SIZE, chunked
from app.services.document_event_service import record_document_event

logger = logging.getLogger(__name__)

FBO_MARKING_PROCESS = marking_code_svc.MARKING_SOURCE_PACKING_FBO
EXTERNAL_CODE_SOURCE = "external_fbs"
_ISSUE_RECEIPT_KIND = "marketplace_unload_kiz_issue_receipt_v1"
# Код в этих состояниях занят/выведен из оборота: на штуку отгрузки его не взять.
_UNUSABLE_STATUSES = frozenset(
    {
        STATUS_RESERVED,
        STATUS_INTRODUCED,
        STATUS_SHIPPED,
        STATUS_TRANSFERRED,
        STATUS_DEFECTIVE,
        STATUS_REPLACED,
        STATUS_VOID,
    }
)


class MarketplaceUnloadKizError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LinkResult:
    marking_code_id: uuid.UUID
    cis_code: str
    product_id: uuid.UUID
    line_id: uuid.UUID
    already_linked: bool
    kiz_count: int
    picked_qty: int


@dataclass(frozen=True)
class KizItem:
    marking_code_id: uuid.UUID
    cis_code: str
    product_id: uuid.UUID | None
    line_id: uuid.UUID
    status: str
    intake_document_number: str | None
    linked_at: datetime | None
    has_label_artifact: bool


@dataclass(frozen=True)
class IssueResult:
    items: list[KizItem]
    shortage: int


@dataclass(frozen=True)
class UnlinkedCode:
    marking_code_id: uuid.UUID
    cis_code: str
    product_id: uuid.UUID | None


# --------------------------------------------------------------------------- helpers


def _normalize_code(raw: str) -> str:
    """Единая нормализация скана КИЗ — функция FBS, без своих разборов."""
    value, hints = fbs_kiz_svc.normalize_scanned_cis(raw)
    if "gs_unrestorable" in hints or not fbs_kiz_svc.is_probably_cis(value):
        raise MarketplaceUnloadKizError("marking_code_invalid")
    return value


async def _lock_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    must_be_editable: bool = True,
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id, lock=True)
    if req is None:
        raise MarketplaceUnloadKizError("not_found")
    if must_be_editable and req.status not in mu_svc.EXECUTION_STATUSES:
        raise MarketplaceUnloadKizError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadKizError("seller_required")
    return req


async def _lock_line(session: AsyncSession, line_id: uuid.UUID) -> None:
    await session.execute(
        select(MarketplaceUnloadLine.id)
        .where(MarketplaceUnloadLine.id == line_id)
        .with_for_update()
    )


async def picked_qty(session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID) -> int:
    """S: сколько штук товара подобрано в отгрузке (сумма аллокаций подбора)."""
    value = await session.scalar(
        select(func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity), 0)).where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
        )
    )
    return int(value or 0)


async def kiz_count(session: AsyncSession, line_id: uuid.UUID) -> int:
    """K: сколько кодов привязано к строке товара отгрузки (только COUNT)."""
    value = await session.scalar(
        select(func.count(MarkingCode.id)).where(MarkingCode.marketplace_unload_line_id == line_id)
    )
    return int(value or 0)


async def kiz_counts_by_product(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """K по каждому товару отгрузки одним запросом (для экрана подбора и упаковки)."""
    rows = await session.execute(
        select(MarketplaceUnloadLine.product_id, func.count(MarkingCode.id))
        .join(MarkingCode, MarkingCode.marketplace_unload_line_id == MarketplaceUnloadLine.id)
        .where(MarketplaceUnloadLine.request_id == request_id)
        .group_by(MarketplaceUnloadLine.product_id)
    )
    return {product_id: int(count) for product_id, count in rows.all()}


count_linked_by_line = kiz_counts_by_product  # имя из ТЗ WMS-686 (§8, BE-B)


async def _find_code(
    session: AsyncSession, tenant_id: uuid.UUID, value: str
) -> MarkingCode | None:
    """Поиск существующего кода — так же, как в FBS (точный cis и нормализованный)."""
    return await fbs_marking_svc._lookup_marking_code_in_tenant(
        session, tenant_id=tenant_id, cis_code=value
    )


async def _lock_code(session: AsyncSession, code_id: uuid.UUID) -> MarkingCode:
    locked = (
        await session.execute(
            select(MarkingCode)
            .where(MarkingCode.id == code_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if locked is None:
        raise MarketplaceUnloadKizError("marking_code_not_found")
    return locked


async def _pool_product_ids(session: AsyncSession, pool_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(MarkingPoolProduct.product_id).where(MarkingPoolProduct.pool_id == pool_id)
    )
    return set(rows.all())


def _gtin_variants(value: str) -> set[str]:
    gtin = marking_code_svc.extract_gtin_from_cis(value)
    if not gtin:
        return set()
    return set(marking_code_svc.gtin_lookup_variants(gtin))


async def _gtin_owner_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    value: str,
) -> set[uuid.UUID]:
    """Товары селлера, чей ШК совпадает с GTIN кода (так же, как сверяет FBS)."""
    variants = _gtin_variants(value)
    if not variants:
        return set()
    owners = set(
        await session.scalars(
            select(Product.id).where(
                Product.tenant_id == tenant_id,
                Product.seller_id == seller_id,
                Product.wb_barcode.in_(variants),
            )
        )
    )
    owners |= set(
        await session.scalars(
            select(ProductBarcode.product_id).where(
                ProductBarcode.tenant_id == tenant_id,
                ProductBarcode.seller_id == seller_id,
                ProductBarcode.barcode.in_(variants),
            )
        )
    )
    return owners


async def _conflicts_with_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    code: MarkingCode | None,
    value: str,
    product_id: uuid.UUID,
) -> bool:
    """Доказано ли, что код принадлежит другому товару (код, пул, GTIN против ШК)."""
    if code is not None and code.product_id is not None:
        return code.product_id != product_id
    if code is not None and code.pool_id is not None:
        members = await _pool_product_ids(session, code.pool_id)
        if members:
            return product_id not in members
    owners = await _gtin_owner_products(session, tenant_id, seller_id, value)
    return bool(owners) and product_id not in owners


async def _infer_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    code: MarkingCode | None,
    value: str,
    plan: dict[uuid.UUID, MarketplaceUnloadLine],
) -> uuid.UUID:
    """Товар по самому коду: известный код, пул или GTIN, совпавший с ШК одного товара."""
    if code is not None and code.product_id is not None:
        if code.product_id in plan:
            return code.product_id
        raise MarketplaceUnloadKizError("marking_code_other_product")
    owners = await _gtin_owner_products(session, tenant_id, seller_id, value)
    matching = owners & set(plan)
    if code is not None and code.pool_id is not None:
        members = (await _pool_product_ids(session, code.pool_id)) & set(plan)
        if len(members) == 1:
            return next(iter(members))
        narrowed = members & matching
        if len(narrowed) == 1:
            return next(iter(narrowed))
        raise MarketplaceUnloadKizError("marking_product_unknown")
    if len(matching) == 1:
        return next(iter(matching))
    raise MarketplaceUnloadKizError("marking_product_unknown")


async def _linked_by_fbs_order(session: AsyncSession, code: MarkingCode) -> bool:
    return (
        await session.scalar(
            select(FbsOrderMarking.id)
            .where(
                FbsOrderMarking.tenant_id == code.tenant_id,
                FbsOrderMarking.marking_code_id == code.id,
            )
            .limit(1)
        )
        is not None
    )


def _release_code(code: MarkingCode) -> None:
    """Снять привязку к строке отгрузки; статус кода не меняется (R18, R20).

    Код, который отсканировали или напечатали, уже физически на вещи: в свободный
    пул он не возвращается (иначе один код окажется на двух вещах). Принятый или
    внешний остаётся applied и может быть привязан заново, печатный остаётся printed.
    """
    code.marketplace_unload_line_id = None


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _events_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[MarkingCodeEvent]]:
    result: dict[uuid.UUID, list[MarkingCodeEvent]] = {}
    for batch in chunked(code_ids, ID_IN_BATCH_SIZE):
        rows = await session.scalars(
            select(MarkingCodeEvent).where(
                MarkingCodeEvent.tenant_id == tenant_id,
                MarkingCodeEvent.code_id.in_(batch),
                MarkingCodeEvent.event_type.in_((EVENT_IMPORTED, EVENT_PRINTED, EVENT_APPLIED)),
            )
        )
        for event in rows.all():
            result.setdefault(event.code_id, []).append(event)
    return result


def _event_source_process(event: MarkingCodeEvent) -> str | None:
    import json

    if not event.meta_json:
        return None
    try:
        meta = json.loads(event.meta_json)
    except ValueError:
        return None
    value = meta.get("source_process") if isinstance(meta, dict) else None
    return value if isinstance(value, str) else None


def _linked_at(
    code: MarkingCode, events: list[MarkingCodeEvent], document_number: str | None
) -> datetime | None:
    """Когда код привязан к этой отгрузке: последнее событие печати/нанесения по её номеру."""
    own = [
        event.created_at
        for event in events
        if document_number is not None
        and event.document_number == document_number
        and event.event_type in (EVENT_PRINTED, EVENT_APPLIED)
        and _event_source_process(event) == FBO_MARKING_PROCESS
    ]
    if own:
        return _aware(max(own))
    return _aware(code.printed_at or code.applied_at or code.created_at)


def _intake_document_number(events: list[MarkingCodeEvent]) -> str | None:
    receipts = [
        event
        for event in events
        if event.event_type == EVENT_IMPORTED
        and _event_source_process(event) == marking_code_svc.MARKING_SOURCE_RECEPTION
        and event.document_number
    ]
    if not receipts:
        return None
    receipts.sort(key=lambda event: _aware(event.created_at) or datetime.min.replace(tzinfo=UTC))
    return receipts[-1].document_number


async def _build_items(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_number: str | None,
    codes: Sequence[MarkingCode],
) -> list[KizItem]:
    if not codes:
        return []
    events = await _events_by_code(session, tenant_id, [code.id for code in codes])
    flags = await marking_code_svc.label_artifact_flags_for_codes(codes)
    items: list[KizItem] = []
    for code, has_artifact in zip(codes, flags, strict=True):
        assert code.marketplace_unload_line_id is not None
        code_events = events.get(code.id, [])
        items.append(
            KizItem(
                marking_code_id=code.id,
                cis_code=code.cis_code,
                product_id=code.product_id,
                line_id=code.marketplace_unload_line_id,
                status=code.status,
                intake_document_number=_intake_document_number(code_events),
                linked_at=_linked_at(code, code_events, document_number),
                has_label_artifact=has_artifact,
            )
        )
    items.sort(
        key=lambda item: (
            item.linked_at or datetime.min.replace(tzinfo=UTC),
            str(item.marking_code_id),
        )
    )
    return items


# --------------------------------------------------------------------------- привязка


async def link_marking_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    raw_code: str,
    product_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> LinkResult:
    """Привязать КИЗ к строке товара отгрузки. Подбор и упаковка идут сюда же.

    Повтор того же кода на той же строке возвращает already_linked без изменений.
    Скан не ходит ни во внешние API, ни в «ЧЗ»: привязка целиком в WMS.
    """
    value = _normalize_code(raw_code)
    req = await _lock_request(session, tenant_id, request_id)
    plan = {ln.product_id: ln for ln in req.lines}
    if product_id is not None and product_id not in plan:
        raise MarketplaceUnloadKizError("marking_product_unknown")
    seller_id = req.seller_id
    assert seller_id is not None

    code: MarkingCode | None = None
    for attempt in (0, 1):
        found = await _find_code(session, tenant_id, value)
        code = None
        resolved_product_id = product_id
        if resolved_product_id is None:
            resolved_product_id = await _infer_product(
                session, tenant_id, seller_id, found, value, plan
            )
        line = plan[resolved_product_id]
        await _lock_line(session, line.id)
        if found is not None:
            code = await _lock_code(session, found.id)
            return await _bind_existing(
                session, req, code, line, value, actor_user_id=actor_user_id
            )
        # Новый (внешний) код: GTIN против ШК товаров плана.
        if await _conflicts_with_product(
            session, tenant_id, seller_id, None, value, resolved_product_id
        ):
            raise MarketplaceUnloadKizError("marking_code_other_product")
        await _assert_room_for_code(session, req, line)
        now = datetime.now(UTC)
        created = MarkingCode(
            tenant_id=tenant_id,
            seller_id=req.seller_id,
            product_id=resolved_product_id,
            cis_code=value,
            source=EXTERNAL_CODE_SOURCE,
            gtin=marking_code_svc.extract_gtin_from_cis(value),
            status=STATUS_APPLIED,
            applied_at=now,
            marketplace_unload_line_id=line.id,
            pool_id=None,
            import_batch_id=None,
            label_artifact_pdf=None,
        )
        try:
            async with session.begin_nested():
                session.add(created)
                await session.flush()
        except IntegrityError:
            # Тот же код уже создал параллельный запрос — разбираем его как существующий.
            if attempt == 1:
                raise MarketplaceUnloadKizError("marking_code_used_elsewhere") from None
            continue
        await marking_code_svc.record_event(
            session,
            code=created,
            event_type=EVENT_APPLIED,
            actor=actor_user_id,
            document_number=req.document_number,
            source_process=FBO_MARKING_PROCESS,
            occurred_at=now,
        )
        await session.commit()
        return LinkResult(
            marking_code_id=created.id,
            cis_code=created.cis_code,
            product_id=resolved_product_id,
            line_id=line.id,
            already_linked=False,
            kiz_count=await kiz_count(session, line.id),
            picked_qty=await picked_qty(session, req.id, resolved_product_id),
        )
    raise MarketplaceUnloadKizError("marking_code_used_elsewhere")  # pragma: no cover


async def _assert_room_for_code(
    session: AsyncSession, req: MarketplaceUnloadRequest, line: MarketplaceUnloadLine
) -> None:
    """K(товар) < S(товар): КИЗ не может быть больше подобранных штук."""
    picked = await picked_qty(session, req.id, line.product_id)
    if await kiz_count(session, line.id) >= picked:
        raise MarketplaceUnloadKizError("marking_quantity_exceeded")


async def _bind_existing(
    session: AsyncSession,
    req: MarketplaceUnloadRequest,
    code: MarkingCode,
    line: MarketplaceUnloadLine,
    value: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> LinkResult:
    if code.seller_id != req.seller_id:
        raise MarketplaceUnloadKizError("marking_code_used_elsewhere")
    if code.marketplace_unload_line_id == line.id:
        return LinkResult(
            marking_code_id=code.id,
            cis_code=code.cis_code,
            product_id=line.product_id,
            line_id=line.id,
            already_linked=True,
            kiz_count=await kiz_count(session, line.id),
            picked_qty=await picked_qty(session, req.id, line.product_id),
        )
    if code.marketplace_unload_line_id is not None:
        other = await session.get(MarketplaceUnloadLine, code.marketplace_unload_line_id)
        if other is not None and other.request_id == req.id:
            raise MarketplaceUnloadKizError("marking_code_other_product")
        raise MarketplaceUnloadKizError("marking_code_other_shipment")
    if await _conflicts_with_product(
        session, req.tenant_id, code.seller_id, code, value, line.product_id
    ):
        raise MarketplaceUnloadKizError("marking_code_other_product")
    if (
        marking_code_svc.is_code_bound(code)
        or code.status in _UNUSABLE_STATUSES
        or await _linked_by_fbs_order(session, code)
    ):
        raise MarketplaceUnloadKizError("marking_code_used_elsewhere")
    await _assert_room_for_code(session, req, line)

    now = datetime.now(UTC)
    code.marketplace_unload_line_id = line.id
    if code.product_id is None:
        code.product_id = line.product_id
    if code.status == STATUS_AVAILABLE:
        code.status = STATUS_APPLIED  # printed остаётся printed (R14)
    code.applied_at = code.applied_at or now
    await marking_code_svc.record_event(
        session,
        code=code,
        event_type=EVENT_APPLIED,
        actor=actor_user_id,
        document_number=req.document_number,
        source_process=FBO_MARKING_PROCESS,
        occurred_at=now,
    )
    await session.commit()
    return LinkResult(
        marking_code_id=code.id,
        cis_code=code.cis_code,
        product_id=line.product_id,
        line_id=line.id,
        already_linked=False,
        kiz_count=await kiz_count(session, line.id),
        picked_qty=await picked_qty(session, req.id, line.product_id),
    )


# --------------------------------------------------------------------------- список


async def list_marking_codes(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> list[KizItem]:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadKizError("not_found")
    line_ids = [ln.id for ln in req.lines]
    codes: list[MarkingCode] = []
    for batch in chunked(line_ids, ID_IN_BATCH_SIZE):
        rows = await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.marketplace_unload_line_id.in_(batch),
            )
        )
        codes.extend(rows.all())
    return await _build_items(session, tenant_id, req.document_number, codes)


# --------------------------------------------------------------------------- отвязка


async def remove_marking_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    marking_code_id: uuid.UUID,
) -> bool:
    """Отвязать ошибочный код от отгрузки. Повтор безопасен: ответ removed=false."""
    req = await _lock_request(session, tenant_id, request_id)
    line_ids = {ln.id for ln in req.lines}
    code = await session.get(MarkingCode, marking_code_id)
    if code is None or code.tenant_id != tenant_id:
        raise MarketplaceUnloadKizError("marking_code_not_found")
    if code.marketplace_unload_line_id not in line_ids:
        await session.rollback()
        return False
    locked = await _lock_code(session, marking_code_id)
    if locked.marketplace_unload_line_id not in line_ids:
        await session.rollback()
        return False
    _release_code(locked)
    await session.commit()
    return True


async def unlink_excess_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    previous_picked: int,
) -> list[UnlinkedCode]:
    """K не может превышать подобранное S: лишние (последние привязанные) коды отвязать.

    Вызывается внутри транзакции подбора (документ уже под замком) и не коммитит.
    previous_picked — подобранное до уменьшения. Если КИЗ было больше и его (коды
    выданы заранее, до подбора), правило «K <= S» ещё до уменьшения не держалось, и
    заранее выданные коды не отвязываются.
    """
    line = await session.scalar(
        select(MarketplaceUnloadLine).where(
            MarketplaceUnloadLine.request_id == request_id,
            MarketplaceUnloadLine.product_id == product_id,
        )
    )
    if line is None:
        return []
    picked = await picked_qty(session, request_id, product_id)
    codes = list(
        (
            await session.scalars(
                select(MarkingCode)
                .where(
                    MarkingCode.tenant_id == tenant_id,
                    MarkingCode.marketplace_unload_line_id == line.id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).all()
    )
    excess = len(codes) - max(0, picked)
    if excess <= 0 or len(codes) > previous_picked:
        return []
    request = await session.get(MarketplaceUnloadRequest, request_id)
    document_number = request.document_number if request is not None else None
    events = await _events_by_code(session, tenant_id, [code.id for code in codes])
    ordered = sorted(
        codes,
        key=lambda code: (
            _linked_at(code, events.get(code.id, []), document_number)
            or datetime.min.replace(tzinfo=UTC),
            str(code.id),
        ),
        reverse=True,
    )
    removed: list[UnlinkedCode] = []
    for code in ordered[:excess]:
        removed.append(UnlinkedCode(code.id, code.cis_code, code.product_id))
        _release_code(code)
    logger.info(
        "marketplace unload %s product %s: unlinked %d KIZ above picked %d",
        request_id,
        product_id,
        len(removed),
        picked,
    )
    return removed


async def unlink_all_codes(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> int:
    """Отмена отгрузки: все её КИЗ отвязываются. Не коммитит."""
    line_ids = list(
        (
            await session.scalars(
                select(MarketplaceUnloadLine.id).where(
                    MarketplaceUnloadLine.request_id == request_id
                )
            )
        ).all()
    )
    total = 0
    for batch in chunked(line_ids, ID_IN_BATCH_SIZE):
        codes = (
            await session.scalars(
                select(MarkingCode)
                .where(
                    MarkingCode.tenant_id == tenant_id,
                    MarkingCode.marketplace_unload_line_id.in_(batch),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).all()
        for code in codes:
            _release_code(code)
            total += 1
    return total


# --------------------------------------------------------------------------- допечатка


def _issue_receipt_key(mutation_id: uuid.UUID) -> str:
    return f"marketplace-unload:kiz-issue:{mutation_id}"


def _issue_request_payload(
    request_id: uuid.UUID, product_id: uuid.UUID, quantity: int | None
) -> dict[str, Any]:
    return {
        "request_id": str(request_id),
        "product_id": str(product_id),
        "quantity": quantity,
    }


async def _issue_replay(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    request_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    mutation_id: uuid.UUID,
    request_payload: dict[str, Any],
) -> IssueResult | None:
    event = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _issue_receipt_key(mutation_id),
        )
    )
    if event is None:
        return None
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_MARKETPLACE_UNLOAD
        or event.document_id != request_id
        or event.actor_user_id != actor_user_id
        or payload.get("kind") != _ISSUE_RECEIPT_KIND
        or payload.get("request") != request_payload
    ):
        raise MarketplaceUnloadKizError("mutation_payload_mismatch")
    saved = payload.get("result")
    if not isinstance(saved, dict):
        raise MarketplaceUnloadKizError("mutation_result_missing")
    code_ids = [uuid.UUID(str(item)) for item in saved.get("code_ids", [])]
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadKizError("not_found")
    by_id: dict[uuid.UUID, MarkingCode] = {}
    for batch in chunked(code_ids, ID_IN_BATCH_SIZE):
        rows = await session.scalars(
            select(MarkingCode).where(MarkingCode.tenant_id == tenant_id, MarkingCode.id.in_(batch))
        )
        by_id.update({code.id: code for code in rows.all()})
    codes = [by_id[code_id] for code_id in code_ids if code_id in by_id]
    # Код мог быть отвязан ✕ после выдачи: повтор возвращает то, что выдано сейчас
    # привязанным к строке, а не новые коды.
    codes = [code for code in codes if code.marketplace_unload_line_id is not None]
    items = await _build_items(session, tenant_id, req.document_number, codes)
    return IssueResult(items=items, shortage=int(saved.get("shortage") or 0))


async def issue_marking_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int | None,
    mutation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> IssueResult:
    """Выдать из пула свободные коды товара: по умолчанию на подобранные штуки без КИЗ
    (S - K), пока подбор не начат — на недостающее по плану (P - K); потолок P - K.

    Всё в одной транзакции: выдача кодов, привязка к строке и квитанция операции.
    Повтор с тем же mutation_id возвращает те же коды.
    """
    request_payload = _issue_request_payload(request_id, product_id, quantity)
    replay = await _issue_replay(
        session,
        tenant_id,
        request_id=request_id,
        actor_user_id=actor_user_id,
        mutation_id=mutation_id,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay

    if quantity is not None and quantity < 1:
        raise MarketplaceUnloadKizError("nothing_to_issue")
    req = await _lock_request(session, tenant_id, request_id)
    line = next((ln for ln in req.lines if ln.product_id == product_id), None)
    if line is None:
        raise MarketplaceUnloadKizError("product_not_in_shipment")
    await _lock_line(session, line.id)

    # Повторная проверка квитанции под замком: параллельный запрос мог успеть первым.
    replay = await _issue_replay(
        session,
        tenant_id,
        request_id=request_id,
        actor_user_id=actor_user_id,
        mutation_id=mutation_id,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay

    # Потолок выдачи — план минус уже привязанные (P - K): коды можно печатать и до
    # подбора. Без quantity выдаём на подобранные штуки без КИЗ (S - K); пока подбор
    # не начат (или все подобранные уже с КИЗ) — на недостающее по плану (P - K).
    linked = await kiz_count(session, line.id)
    plan_room = int(line.quantity) - linked
    if plan_room < 1:
        raise MarketplaceUnloadKizError("nothing_to_issue")
    picked = await picked_qty(session, req.id, product_id)
    if quantity is None:
        wanted = picked - linked if picked > 0 else plan_room
    else:
        wanted = min(quantity, plan_room)
    if wanted < 1:
        # S > 0 и S = K: на подобранные штуки КИЗ уже есть (R21).
        raise MarketplaceUnloadKizError("nothing_to_issue")

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        await session.execute(
            sa.update(DocumentEvent).where(sa.false()).values(idempotency_key=None)
        )
    inserted = await record_document_event(
        session,
        tenant_id=tenant_id,
        document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
        document_id=request_id,
        event_type=EVENT_DATA_CHANGED,
        source=SOURCE_USER if actor_user_id is not None else SOURCE_SYSTEM,
        actor_user_id=actor_user_id,
        product_id=product_id,
        payload_json={"kind": _ISSUE_RECEIPT_KIND, "request": request_payload, "result": None},
        idempotency_key=_issue_receipt_key(mutation_id),
    )
    if not inserted:
        replay = await _issue_replay(
            session,
            tenant_id,
            request_id=request_id,
            actor_user_id=actor_user_id,
            mutation_id=mutation_id,
            request_payload=request_payload,
        )
        assert replay is not None
        return replay

    try:
        printed = await marking_code_svc.print_codes_for_product(
            session,
            tenant_id,
            product_id,
            acting_user_id=actor_user_id,
            quantity=wanted,
            allow_partial=True,
            commit=False,
            source_process=FBO_MARKING_PROCESS,
            document_number=req.document_number,
            marketplace_unload_line_id=line.id,
        )
    except marking_code_svc.MarkingCodeServiceError as exc:
        await session.rollback()
        raise MarketplaceUnloadKizError(exc.code) from None
    if printed.quantity < 1:
        # Пустой пул: ничего не выдано, квитанция не сохраняется (повтор после
        # пополнения пула выдаст коды, а не вернёт пустоту).
        await session.rollback()
        raise MarketplaceUnloadKizError("marking_pool_empty")

    issued_ids = [info.id for info in printed.printed_codes]
    shortage = max(0, wanted - printed.quantity)
    receipt = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _issue_receipt_key(mutation_id),
        )
    )
    assert receipt is not None
    receipt.payload_json = {
        "kind": _ISSUE_RECEIPT_KIND,
        "request": request_payload,
        "result": {"code_ids": [str(code_id) for code_id in issued_ids], "shortage": shortage},
    }
    await session.commit()

    rows = await session.scalars(
        select(MarkingCode).where(
            MarkingCode.tenant_id == tenant_id, MarkingCode.id.in_(issued_ids)
        )
    )
    by_id = {code.id: code for code in rows.all()}
    codes = [by_id[code_id] for code_id in issued_ids if code_id in by_id]
    items = await _build_items(session, tenant_id, req.document_number, codes)
    return IssueResult(items=items, shortage=shortage)

