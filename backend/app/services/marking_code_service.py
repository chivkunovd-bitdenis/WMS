from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marking_code import (
    EVENT_IMPORTED,
    EVENT_PRINTED,
    EVENT_REPRINTED,
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
)
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.services.catalog_service import get_product

_CIS_MIN_LEN = 15
_CIS_MAX_LEN = 512
_GTIN_RE = re.compile(r"(?<!\d)(\d{14})(?!\d)")
_GS1_GTIN_AI01_RE = re.compile(r"(?:^|\x1d)01(\d{14})")
_CIS_CANDIDATE_RE = re.compile(
    r"[\x1d(]?(?:01)?\d{14}[\x1d)]?(?:21)[\w!\"%&'()*+,\-./:;<=>?]{13,}"
)


class MarkingCodeServiceError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def record_event(
    session: AsyncSession,
    *,
    code: MarkingCode,
    event_type: str,
    actor: uuid.UUID | None,
    document_number: str | None = None,
    packaging_task: PackagingTaskLine | None = None,
    reason: str | None = None,
    copies: int = 1,
) -> MarkingCodeEvent:
    packaging_task_id: uuid.UUID | None = None
    packaging_task_line_id: uuid.UUID | None = None
    if packaging_task is not None:
        packaging_task_line_id = packaging_task.id
        packaging_task_id = packaging_task.task_id

    event = MarkingCodeEvent(
        tenant_id=code.tenant_id,
        seller_id=code.seller_id,
        code_id=code.id,
        pool_id=code.pool_id,
        event_type=event_type,
        packaging_task_id=packaging_task_id,
        packaging_task_line_id=packaging_task_line_id,
        document_number=document_number,
        actor_user_id=actor,
        copies=copies,
        reason=reason,
    )
    session.add(event)
    return event


@dataclass(frozen=True)
class ImportSkipReason:
    reason: str
    count: int


@dataclass(frozen=True)
class MarkingImportResult:
    import_id: uuid.UUID
    accepted_count: int
    skipped_count: int
    linked_count: int
    unlinked_count: int
    skip_reasons: list[ImportSkipReason]


@dataclass(frozen=True)
class MarkingInventoryResult:
    rows: list[ProductMarkingInventoryRow]
    unlinked_available_count: int


@dataclass(frozen=True)
class ProductMarkingCodeRow:
    id: uuid.UUID
    cis_code: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ProductMarkingInventoryRow:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    requires_honest_sign: bool
    available_count: int
    printed_count: int


@dataclass(frozen=True)
class PrintMarkingCodesResult:
    packaging_task_line_id: uuid.UUID
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]


def normalize_cis(raw: str) -> str | None:
    text = raw.strip().replace("\ufeff", "")
    if not text:
        return None
    text = text.replace(" ", "").replace("\n", "").replace("\r", "")
    if len(text) < _CIS_MIN_LEN or len(text) > _CIS_MAX_LEN:
        return None
    if not any(ch.isalnum() for ch in text):
        return None
    return text


def extract_gtin_from_cis(cis: str) -> str | None:
    gs1_match = _GS1_GTIN_AI01_RE.search(cis)
    if gs1_match:
        return gs1_match.group(1)
    match = _GTIN_RE.search(cis)
    return match.group(1) if match else None


def _gtin_lookup_variants(gtin: str) -> list[str]:
    """GTIN in CIS is 14 digits; WB barcodes are often stored as EAN-13."""
    clean = gtin.strip()
    if not clean:
        return []
    variants: list[str] = [clean]
    if len(clean) == 14 and clean.startswith("0"):
        without_leading = clean[1:]
        if without_leading not in variants:
            variants.append(without_leading)
    elif len(clean) == 13:
        with_leading = f"0{clean}"
        if with_leading not in variants:
            variants.append(with_leading)
    return variants


def _parse_csv_rows(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    if not text.strip():
        return []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames:
        lowered = {name.lower().strip(): name for name in reader.fieldnames if name}
        cis_key = (
            lowered.get("cis")
            or lowered.get("киз")
            or lowered.get("code")
            or lowered.get("код")
        )
        gtin_key = lowered.get("gtin") or lowered.get("штрихкод")
        sku_key = lowered.get("sku") or lowered.get("sku_code") or lowered.get("артикул")
        rows: list[dict[str, str]] = []
        for row in reader:
            if cis_key and row.get(cis_key):
                rows.append(
                    {
                        "cis": row[cis_key] or "",
                        "gtin": (row.get(gtin_key) or "") if gtin_key else "",
                        "sku": (row.get(sku_key) or "") if sku_key else "",
                    }
                )
        if rows:
            return rows
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1 and not any(sep in lines[0] for sep in (",", ";", "\t")):
        return [{"cis": ln, "gtin": "", "sku": ""} for ln in lines]
    return []


def _parse_pdf_text_rows(content: bytes) -> list[dict[str, str]]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise MarkingCodeServiceError("pdf_support_unavailable") from exc
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for page in doc:
            text = page.get_text("text")
            for match in _CIS_CANDIDATE_RE.finditer(text):
                cis = normalize_cis(match.group(0))
                if cis is None or cis in seen:
                    continue
                seen.add(cis)
                gtin = extract_gtin_from_cis(cis) or ""
                rows.append({"cis": cis, "gtin": gtin, "sku": ""})
            if not text.strip():
                continue
            for line in text.splitlines():
                cis = normalize_cis(line)
                if cis is None or cis in seen:
                    continue
                if len(cis) >= 20:
                    seen.add(cis)
                    gtin = extract_gtin_from_cis(cis) or ""
                    rows.append({"cis": cis, "gtin": gtin, "sku": ""})
    finally:
        doc.close()
    return rows


def parse_import_file(filename: str, content: bytes) -> list[dict[str, str]]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _parse_pdf_text_rows(content)
    if lower.endswith((".csv", ".txt", ".tsv")):
        return _parse_csv_rows(content)
    raise MarkingCodeServiceError("unsupported_file_type")


async def _resolve_product_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    gtin: str,
    sku: str,
) -> Product | None:
    sku_clean = sku.strip()
    if sku_clean:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.sku_code == sku_clean,
        )
        res = await session.execute(stmt)
        found = res.scalar_one_or_none()
        if found is not None:
            return found
    gtin_clean = gtin.strip()
    if gtin_clean:
        gtin_variants = _gtin_lookup_variants(gtin_clean)
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_barcode.in_(gtin_variants),
        )
        res = await session.execute(stmt)
        found = res.scalar_one_or_none()
        if found is not None:
            return found
    return None


async def relink_unlinked_marking_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> int:
    """Try to attach imported codes (product_id=NULL) to catalog products by GTIN."""
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.seller_id == seller_id,
        MarkingCode.product_id.is_(None),
        MarkingCode.status == STATUS_AVAILABLE,
    )
    codes = list((await session.execute(stmt)).scalars().all())
    linked = 0
    for code in codes:
        gtin = (code.gtin or "").strip() or extract_gtin_from_cis(code.cis_code)
        if not gtin:
            continue
        product = await _resolve_product_for_row(
            session,
            tenant_id,
            seller_id,
            gtin=gtin,
            sku="",
        )
        if product is not None:
            code.product_id = product.id
            linked += 1
    if linked:
        await session.commit()
    return linked


async def import_marking_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    filename: str,
    content: bytes,
    uploaded_by_user_id: uuid.UUID | None,
) -> MarkingImportResult:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        raise MarkingCodeServiceError("seller_not_found")

    product = await get_product(session, tenant_id, product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    if product.seller_id != seller_id:
        raise MarkingCodeServiceError("product_seller_mismatch")

    try:
        parsed_rows = parse_import_file(filename, content)
    except MarkingCodeServiceError:
        raise
    except (UnicodeError, OSError, ValueError) as exc:
        raise MarkingCodeServiceError("parse_failed") from exc

    if not parsed_rows:
        raise MarkingCodeServiceError("empty_file")

    skip_counts: dict[str, int] = {}
    accepted = 0
    batch = MarkingCodeImport(
        tenant_id=tenant_id,
        seller_id=seller_id,
        filename=filename,
        accepted_count=0,
        skipped_count=0,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    session.add(batch)
    await session.flush()

    for row in parsed_rows:
        cis = normalize_cis(row.get("cis", ""))
        if cis is None:
            skip_counts["invalid_format"] = skip_counts.get("invalid_format", 0) + 1
            continue
        existing = await session.execute(
            select(MarkingCode.id).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.cis_code == cis,
            )
        )
        if existing.scalar_one_or_none() is not None:
            skip_counts["duplicate"] = skip_counts.get("duplicate", 0) + 1
            continue
        gtin = (row.get("gtin") or "").strip() or extract_gtin_from_cis(cis)
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product.id,
            import_batch_id=batch.id,
            cis_code=cis,
            gtin=gtin,
            status=STATUS_AVAILABLE,
        )
        session.add(code)
        await session.flush()
        await record_event(
            session,
            code=code,
            event_type=EVENT_IMPORTED,
            actor=uploaded_by_user_id,
        )
        accepted += 1

    skipped = sum(skip_counts.values())
    batch.accepted_count = accepted
    batch.skipped_count = skipped
    batch.skip_reasons_json = json.dumps(skip_counts, ensure_ascii=False) if skip_counts else None
    await session.commit()
    return MarkingImportResult(
        import_id=batch.id,
        accepted_count=accepted,
        skipped_count=skipped,
        linked_count=accepted,
        unlinked_count=0,
        skip_reasons=[ImportSkipReason(k, v) for k, v in sorted(skip_counts.items())],
    )


async def list_inventory(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
) -> MarkingInventoryResult:
    if seller_id is not None:
        await relink_unlinked_marking_codes(session, tenant_id, seller_id)

    product_stmt = select(Product).where(Product.tenant_id == tenant_id)
    if seller_id is not None:
        product_stmt = product_stmt.where(Product.seller_id == seller_id)
    products = list((await session.execute(product_stmt)).scalars().all())

    counts_stmt = (
        select(
            MarkingCode.product_id,
            MarkingCode.status,
            func.count(MarkingCode.id),
        )
        .where(MarkingCode.tenant_id == tenant_id)
        .group_by(MarkingCode.product_id, MarkingCode.status)
    )
    if seller_id is not None:
        counts_stmt = counts_stmt.where(MarkingCode.seller_id == seller_id)
    count_rows = (await session.execute(counts_stmt)).all()
    available_by_product: dict[uuid.UUID, int] = {}
    printed_by_product: dict[uuid.UUID, int] = {}
    unlinked_available = 0
    for product_id, status, cnt in count_rows:
        if product_id is None:
            if status == STATUS_AVAILABLE:
                unlinked_available = int(cnt)
            continue
        if status == STATUS_AVAILABLE:
            available_by_product[product_id] = int(cnt)
        elif status == STATUS_PRINTED:
            printed_by_product[product_id] = int(cnt)

    rows: list[ProductMarkingInventoryRow] = []
    for p in products:
        rows.append(
            ProductMarkingInventoryRow(
                product_id=p.id,
                sku_code=p.sku_code,
                product_name=p.name,
                requires_honest_sign=bool(p.requires_honest_sign),
                available_count=available_by_product.get(p.id, 0),
                printed_count=printed_by_product.get(p.id, 0),
            )
        )
    rows.sort(key=lambda r: r.sku_code)
    return MarkingInventoryResult(
        rows=rows,
        unlinked_available_count=unlinked_available,
    )


async def list_product_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> list[ProductMarkingCodeRow]:
    product = await get_product(session, tenant_id, product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.product_id == product_id,
        )
        .order_by(MarkingCode.created_at.desc())
    )
    codes = list((await session.execute(stmt)).scalars().all())
    return [
        ProductMarkingCodeRow(
            id=code.id,
            cis_code=code.cis_code,
            status=code.status,
            created_at=code.created_at,
        )
        for code in codes
    ]


async def count_available_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = select(func.count(MarkingCode.id)).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.product_id == product_id,
        MarkingCode.status == STATUS_AVAILABLE,
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def print_codes_for_packaging_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_line_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID,
    duplicate_copies: int,
    reprint: bool,
) -> PrintMarkingCodesResult:
    if duplicate_copies not in (1, 2):
        raise MarkingCodeServiceError("invalid_duplicate_copies")

    line_stmt = (
        select(PackagingTaskLine)
        .where(PackagingTaskLine.id == task_line_id)
        .options(selectinload(PackagingTaskLine.task))
    )
    line = (await session.execute(line_stmt)).scalar_one_or_none()
    if line is None:
        raise MarkingCodeServiceError("line_not_found")
    task = line.task
    if task.tenant_id != tenant_id:
        raise MarkingCodeServiceError("line_not_found")

    product = await get_product(session, tenant_id, line.product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    if not product.requires_honest_sign:
        raise MarkingCodeServiceError("marking_not_required")
    if product.seller_id is None:
        raise MarkingCodeServiceError("product_seller_missing")

    from app.services.packaging_task_service import qty_need_pack

    quantity = qty_need_pack(line)
    if quantity < 1:
        raise MarkingCodeServiceError("nothing_to_mark")

    if reprint:
        if int(line.qty_marking_printed) < 1:
            raise MarkingCodeServiceError("nothing_to_reprint")
        stmt = (
            select(MarkingCode)
            .where(
                MarkingCode.packaging_task_line_id == line.id,
                MarkingCode.status == STATUS_PRINTED,
            )
            .order_by(MarkingCode.created_at.asc())
        )
        codes = list((await session.execute(stmt)).scalars().all())
        if not codes:
            raise MarkingCodeServiceError("nothing_to_reprint")
        for code in codes:
            await record_event(
                session,
                code=code,
                event_type=EVENT_REPRINTED,
                actor=acting_user_id,
                document_number=task.document_number,
                packaging_task=line,
                copies=duplicate_copies,
            )
        await session.commit()
        return PrintMarkingCodesResult(
            packaging_task_line_id=line.id,
            quantity=len(codes),
            duplicate_copies=duplicate_copies,
            is_reprint=True,
            codes=[c.cis_code for c in codes],
        )

    if int(line.qty_marking_printed) > 0:
        raise MarkingCodeServiceError("already_printed_use_reprint")

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            MarkingCode.product_id == product.id,
            MarkingCode.status == STATUS_AVAILABLE,
        )
        .order_by(MarkingCode.created_at.asc())
        .limit(quantity)
        .with_for_update()
    )
    codes = list((await session.execute(stmt)).scalars().all())
    if len(codes) < quantity:
        raise MarkingCodeServiceError("insufficient_codes")

    now = datetime.now(UTC)
    for code in codes:
        code.status = STATUS_PRINTED
        code.packaging_task_line_id = line.id
        code.printed_at = now
        code.printed_by_user_id = acting_user_id
        await record_event(
            session,
            code=code,
            event_type=EVENT_PRINTED,
            actor=acting_user_id,
            document_number=task.document_number,
            packaging_task=line,
            copies=duplicate_copies,
        )

    line.qty_marking_printed = quantity
    await session.commit()

    return PrintMarkingCodesResult(
        packaging_task_line_id=line.id,
        quantity=quantity,
        duplicate_copies=duplicate_copies,
        is_reprint=False,
        codes=[c.cis_code for c in codes],
    )


async def assert_packaging_line_marking_done(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line: PackagingTaskLine,
) -> None:
    product = await get_product(session, tenant_id, line.product_id)
    if product is None or not product.requires_honest_sign:
        return
    from app.services.packaging_task_service import qty_done

    done = qty_done(line)
    if done > 0 and int(line.qty_marking_printed) < done:
        raise MarkingCodeServiceError("marking_not_done")
