"""Receiving code attachments and read-only Honest Sign checks (WMS-396).

The existing import event owns the receipt association and last check snapshot.
MarkingCode.status remains the warehouse lifecycle used by FBS/printing.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.fbs_order import FbsOrderMarking
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.marking_code import (
    EVENT_IMPORTED,
    STATUS_APPLIED,
    MarkingCode,
    MarkingCodeEvent,
    MarkingReprintRequest,
)
from app.models.product import Product
from app.services import true_api_marking_check as true_api
from app.services.inbound_intake_service import (
    RECEIVING_STATUSES,
    InboundIntakeError,
    effective_actual_qty,
)
from app.services.marking_code_service import extract_gtin_from_cis
from app.services.seller_marking_credentials_service import get_cz_token_for_seller

JOB_TYPE = "inbound_marking_check"


def _meta(event: MarkingCodeEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.meta_json or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


async def _request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID, *, lock: bool = False
) -> InboundIntakeRequest:
    stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.tenant_id == tenant_id, InboundIntakeRequest.id == request_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    req = await session.scalar(stmt)
    if req is None:
        raise InboundIntakeError("request_not_found")
    return req


async def _attachments(session: AsyncSession, req: InboundIntakeRequest) -> list[MarkingCodeEvent]:
    # document_number narrows the existing indexed tenant scope; UUID verifies the association.
    events = (
        await session.scalars(
            select(MarkingCodeEvent)
            .where(
                MarkingCodeEvent.tenant_id == req.tenant_id,
                MarkingCodeEvent.document_number == req.document_number,
                MarkingCodeEvent.event_type == EVENT_IMPORTED,
            )
            .order_by(MarkingCodeEvent.created_at, MarkingCodeEvent.id)
        )
    ).all()
    return [e for e in events if _meta(e).get("request_id") == str(req.id)]


def _item(event: MarkingCodeEvent, code: MarkingCode, product: Product) -> dict[str, Any]:
    meta = _meta(event)
    check = meta.get("cz_check") or {}
    return {
        "id": str(code.id),
        "line_id": meta["line_id"],
        "product_id": str(product.id),
        "article": product.sku_code,
        "cis_code": code.cis_code,
        "cz_status": check.get("status", "pending"),
        "cz_reason": check.get("reason", "Проверим после завершения приёмки"),
        "outer_status": check.get("outer_status"),
        "checked_at": check.get("checked_at"),
    }


async def _active_job(session: AsyncSession, req: InboundIntakeRequest) -> BackgroundJob | None:
    jobs = (
        await session.scalars(
            select(BackgroundJob)
            .where(
                BackgroundJob.tenant_id == req.tenant_id,
                BackgroundJob.job_type == JOB_TYPE,
                BackgroundJob.status.in_(["pending", "running"]),
            )
            .order_by(BackgroundJob.created_at.desc())
        )
    ).all()
    for job in jobs:
        if (job.payload_json or {}).get("request_id") == str(req.id):
            return job
    return None


async def list_codes(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> dict[str, Any]:
    req = await _request(session, tenant_id, request_id)
    events = await _attachments(session, req)
    codes = (
        list(
            (
                await session.scalars(
                    select(MarkingCode).where(
                        MarkingCode.id.in_([event.code_id for event in events]),
                        MarkingCode.tenant_id == tenant_id,
                    )
                )
            ).all()
        )
        if events
        else []
    )
    products = (
        (
            await session.execute(
                select(InboundIntakeLine.id, Product)
                .join(Product, Product.id == InboundIntakeLine.product_id)
                .where(InboundIntakeLine.request_id == req.id, Product.tenant_id == tenant_id)
            )
        ).all()
        if events
        else []
    )
    by_code = {code.id: code for code in codes}
    by_line = {str(line_id): product for line_id, product in products}
    items = [
        _item(event, by_code[event.code_id], by_line[_meta(event)["line_id"]])
        for event in events
        if event.code_id in by_code and _meta(event).get("line_id") in by_line
    ]
    job = await _active_job(session, req)
    # A stopped worker must not leave the operator waiting indefinitely.
    stale = job is not None and job.created_at.replace(tzinfo=UTC) < datetime.now(UTC) - timedelta(
        hours=1
    )
    if stale or (job is None and req.status not in RECEIVING_STATUSES):
        for item in items:
            if item["cz_status"] == "pending":
                item.update(
                    cz_status="unavailable", cz_reason="Проверка прервана. Повторите проверку."
                )
    return {"items": items, "checking": job is not None and not stale}


def normalize_scanned_code(raw: str) -> str:
    code = raw.strip(" \r\n\t")
    if code[:3].lower() == "]d2":
        code = code[3:]
    # Human-readable GS1 AI notation is normalized without losing cryptographic bytes.
    if code.startswith("(01)"):
        code = code.replace("(01)", "01", 1).replace("(21)", "21", 1)
        for ai in ("91", "92", "93"):
            code = code.replace(f"({ai})", f"\x1d{ai}")
    if (
        len(code) > 512
        or len(code) < 20
        or not code.startswith("01")
        or not code[2:16].isdigit()
        or code[16:18] != "21"
        or any(ord(char) < 32 and char != "\x1d" for char in code)
    ):
        raise InboundIntakeError("marking_invalid_code")
    return code


async def attach_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    line_id: uuid.UUID,
    cis_code: str,
    actor_user_id: uuid.UUID,
) -> dict[str, Any]:
    code_text = normalize_scanned_code(cis_code)
    req = await _request(session, tenant_id, request_id, lock=True)
    if req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    line = await session.scalar(
        select(InboundIntakeLine).where(
            InboundIntakeLine.id == line_id,
            InboundIntakeLine.request_id == req.id,
        )
    )
    if line is None:
        raise InboundIntakeError("line_not_found")
    product = await session.get(Product, line.product_id)
    if product is None or product.tenant_id != tenant_id or product.seller_id is None:
        raise InboundIntakeError("product_not_found")
    code = await session.scalar(
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.cis_code == code_text,
        )
        .with_for_update()
    )
    if code is not None:
        if code.seller_id != product.seller_id or code.product_id not in (None, product.id):
            raise InboundIntakeError("marking_code_other_product")
        events = (
            await session.scalars(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.tenant_id == tenant_id,
                    MarkingCodeEvent.code_id == code.id,
                    MarkingCodeEvent.event_type == EVENT_IMPORTED,
                )
            )
        ).all()
        for event in events:
            meta = _meta(event)
            if meta.get("request_id"):
                if meta.get("request_id") == str(req.id) and meta.get("line_id") == str(line.id):
                    await session.commit()
                    return _item(event, code, product)
                raise InboundIntakeError("marking_code_other_receipt")
    count = sum(
        _meta(event).get("line_id") == str(line.id) for event in await _attachments(session, req)
    )
    actual = await effective_actual_qty(session, req.id, line, request_status=req.status)
    if count >= actual:
        raise InboundIntakeError("marking_quantity_exceeded")
    if code is not None:
        is_pool = code.source == "pool" or code.pool_id is not None
        if not is_pool:
            raise InboundIntakeError("marking_code_already_used")
        if code.status != "printed":
            raise InboundIntakeError("marking_code_in_pool")
        if (
            any(
                value is not None
                for value in (
                    code.packaging_task_line_id,
                    code.reserved_at,
                    code.reserved_by_user_id,
                    code.consumed_at,
                    code.transferred_at,
                    code.replaced_by_code_id,
                )
            )
            or await session.scalar(
                select(FbsOrderMarking.id)
                .where(FbsOrderMarking.marking_code_id == code.id)
                .limit(1)
            )
            is not None
        ):
            raise InboundIntakeError("marking_code_already_used")
    if code is None:
        try:
            async with session.begin_nested():
                code = MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=product.seller_id,
                    product_id=product.id,
                    cis_code=code_text,
                    source="external_fbs",
                    gtin=extract_gtin_from_cis(code_text),
                    status=STATUS_APPLIED,
                    applied_at=datetime.now(UTC),
                )
                session.add(code)
                await session.flush()
        except IntegrityError:
            # The same receipt is serialized by its row lock. This conflict is another
            # receipt racing to claim the same tenant-wide unique code.
            raise InboundIntakeError("marking_code_other_receipt") from None
    event = MarkingCodeEvent(
        tenant_id=tenant_id,
        seller_id=product.seller_id,
        code_id=code.id,
        event_type=EVENT_IMPORTED,
        document_number=req.document_number,
        actor_user_id=actor_user_id,
        meta_json=json.dumps(
            {"source_process": "reception", "request_id": str(req.id), "line_id": str(line.id)}
        ),
    )
    session.add(event)
    await session.commit()
    return _item(event, code, product)


async def delete_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    code_id: uuid.UUID,
) -> None:
    req = await _request(session, tenant_id, request_id, lock=True)
    if req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    code = await session.scalar(
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.id == code_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if code is None:
        raise InboundIntakeError("marking_code_not_found")
    events = list(
        (
            await session.scalars(
                select(MarkingCodeEvent)
                .where(
                    MarkingCodeEvent.code_id == code.id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).all()
    )
    own = [
        event
        for event in events
        if event.tenant_id == tenant_id and _meta(event).get("request_id") == str(req.id)
    ]
    if not own:
        raise InboundIntakeError("marking_code_not_found")
    is_printed_pool = (
        code.source == "pool" or code.pool_id is not None
    ) and code.status == "printed"
    if (
        len(own) != 1
        or own[0].event_type != EVENT_IMPORTED
        or _meta(own[0]).get("source_process") != "reception"
        or any(
            value is not None
            for value in (
                code.packaging_task_line_id,
                code.reserved_at,
                code.reserved_by_user_id,
                code.transferred_at,
                code.consumed_at,
                code.replaced_by_code_id,
            )
        )
    ):
        raise InboundIntakeError("marking_code_already_used")
    if not is_printed_pool and (
        len(events) != 1
        or code.status != STATUS_APPLIED
        or code.source != "external_fbs"
        or any(
            value is not None
            for value in (
                code.pool_id,
                code.import_batch_id,
                code.printed_at,
                code.printed_by_user_id,
                code.label_artifact_pdf,
                code.introduced_at,
            )
        )
    ):
        raise InboundIntakeError("marking_code_already_used")
    # These foreign keys otherwise cascade or SET NULL: neither is an input correction.
    for stmt in (
        select(FbsOrderMarking.id).where(FbsOrderMarking.marking_code_id == code.id),
        select(MarkingReprintRequest.id).where(MarkingReprintRequest.code_id == code.id),
        select(MarkingCode.id).where(MarkingCode.replaced_by_code_id == code.id),
    ):
        if await session.scalar(stmt.limit(1)) is not None:
            raise InboundIntakeError("marking_code_already_used")
    await session.execute(delete(MarkingCodeEvent).where(MarkingCodeEvent.id == own[0].id))
    if not is_printed_pool:
        await session.execute(delete(MarkingCode).where(MarkingCode.id == code.id))
    await session.commit()


async def schedule_check(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID, *, force: bool = False
) -> uuid.UUID | None:
    req = await _request(session, tenant_id, request_id, lock=True)
    active = await _active_job(session, req)
    if active is not None:
        if active.created_at.replace(tzinfo=UTC) >= datetime.now(UTC) - timedelta(hours=1):
            await session.commit()
            return None
        active.status = "failed"
        active.error_message = "check_interrupted"
    events = await _attachments(session, req)
    if not force:
        events = [
            event
            for event in events
            if (_meta(event).get("cz_check") or {}).get("status") in {None, "pending"}
        ]
    if not events:
        await session.commit()
        return None
    for event in events:
        meta = _meta(event)
        meta["cz_check"] = {"status": "pending", "reason": "Проверяем в Честном знаке"}
        event.meta_json = json.dumps(meta)
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type=JOB_TYPE,
        status="pending",
        payload_json={"request_id": str(req.id)},
    )
    session.add(job)
    await session.commit()
    return job.id


async def _run_check_job(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        job = await session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update()
        )
        if job is None or job.status != "pending":
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        tenant_id = job.tenant_id
        request_id = uuid.UUID((job.payload_json or {})["request_id"])
        await session.commit()
    # HTTP never holds a database session or lock. Drain only pending attachments;
    # rescans during a manual check must not be missed by the posting trigger.
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            async with SessionLocal() as session:
                req = await _request(session, tenant_id, request_id, lock=True)
                job = await session.get(BackgroundJob, job_id)
                if job is None or job.status != "running":
                    return
                event_ids = [
                    event.id
                    for event in await _attachments(session, req)
                    if (_meta(event).get("cz_check") or {}).get("status") in {None, "pending"}
                ]
                if not event_ids:
                    job.status = "done"
                    job.finished_at = datetime.now(UTC)
                    await session.commit()
                    return
                await session.commit()
            async with SessionLocal() as session:
                rows = (await session.execute(
                    select(MarkingCodeEvent.id, MarkingCode.cis_code, MarkingCode.seller_id)
                    .join(MarkingCode, MarkingCode.id == MarkingCodeEvent.code_id)
                    .where(
                        MarkingCodeEvent.id.in_(event_ids),
                        MarkingCodeEvent.tenant_id == tenant_id,
                        MarkingCode.tenant_id == tenant_id,
                    )
                )).all()
                by_seller: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
                for event_id, code_text, seller_id in rows:
                    by_seller.setdefault(seller_id, []).append((event_id, code_text))
                tokens = {
                    seller_id: await get_cz_token_for_seller(session, tenant_id, seller_id)
                    for seller_id in by_seller
                }
            for seller_id, entries in by_seller.items():
                for offset in range(0, len(entries), true_api.BATCH_SIZE):
                    batch = entries[offset:offset + true_api.BATCH_SIZE]
                    checks = await true_api.check_batch(
                        client, [code for _, code in batch], tokens[seller_id]
                    )
                    async with SessionLocal() as session:
                        # Same lock order as schedule_check: a replacement owns its
                        # pending snapshots before an expired worker can write back.
                        await _request(session, tenant_id, request_id, lock=True)
                        job = await session.get(BackgroundJob, job_id, populate_existing=True)
                        if job is None or job.status != "running":
                            return
                        events = (await session.scalars(
                            select(MarkingCodeEvent)
                            .where(
                                MarkingCodeEvent.id.in_([event_id for event_id, _ in batch]),
                                MarkingCodeEvent.tenant_id == tenant_id,
                            )
                            .with_for_update()
                        )).all()
                        by_event = dict(batch)
                        for event in events:
                            meta = _meta(event)
                            if (meta.get("cz_check") or {}).get("status") not in {None, "pending"}:
                                continue
                            meta["cz_check"] = checks[by_event[event.id]]
                            event.meta_json = json.dumps(meta)
                        await session.commit()


async def run_check_job(job_id: uuid.UUID) -> None:
    try:
        await _run_check_job(job_id)
    except Exception:
        logging.getLogger(__name__).exception("Receiving marking job failed: %s", job_id)
        async with SessionLocal() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None or job.status not in {"pending", "running"}:
                return
            job.status = "failed"
            job.error_message = "check_interrupted"
            job.finished_at = datetime.now(UTC)
            tenant_id = job.tenant_id
            request_raw = (job.payload_json or {}).get("request_id")
            # Persist failure even when the receipt was deleted or payload is corrupt.
            await session.commit()
            try:
                req = await _request(session, tenant_id, uuid.UUID(str(request_raw)), lock=True)
                if await _active_job(session, req) is not None:
                    return  # A newer retry owns its pending snapshots.
                for event in await _attachments(session, req):
                    meta = _meta(event)
                    if (meta.get("cz_check") or {}).get("status") == "pending":
                        meta["cz_check"] = true_api.unavailable()
                        event.meta_json = json.dumps(meta)
                await session.commit()
            except Exception:
                await session.rollback()
                logging.getLogger(__name__).warning(
                    "Could not update receipt attachments for failed marking job %s", job_id
                )


def export_problems(items: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Проблемные КИЗ"
    sheet.append(["Артикул", "Код Честного знака", "Причина"])
    for item in items:
        if item["cz_status"] not in {"problem", "unavailable"}:
            continue
        # Excel XML cannot contain ASCII GS; explicit escape preserves a recoverable code.
        values = [item["article"], item["cis_code"].replace("\x1d", "\\u001d"), item["cz_reason"]]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
            cell.number_format = "@"
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 80
    sheet.column_dimensions["C"].width = 55
    sheet.freeze_panes = "A2"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
