from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_DEFECTIVE,
    EVENT_IMPORTED,
    EVENT_PRINTED,
    EVENT_REPLACED,
    EVENT_REPRINTED,
    EVENT_SHIPPED,
    REPRINT_STATUS_APPROVED,
    REPRINT_STATUS_PENDING,
    REPRINT_STATUS_REJECTED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_DEFECTIVE,
    STATUS_PRINTED,
    STATUS_REPLACED,
    STATUS_RESERVED,
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
    MarkingPool,
    MarkingPoolProduct,
    MarkingReprintRequest,
)
from app.models.packaging_task import (
    STATUS_DRAFT,
    STATUS_IN_PROGRESS,
    PackagingTask,
    PackagingTaskLine,
)
from app.models.print_template import LAYOUT_BLOCK_CZ
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services.catalog_service import get_product
from app.services.document_number_service import (
    DOC_TYPE_MARKING_IMPORT,
    assign_document_number_if_missing,
)
from app.services.print_template_service import (
    LayoutUnit,
    PrintLayout,
    parse_layout,
    resolve_default_print_template,
)

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
    document_number: str
    accepted_count: int
    skipped_count: int
    skip_reasons: list[ImportSkipReason]
    pools: list[PoolImportResultRow]


@dataclass(frozen=True)
class PoolImportSpec:
    title: str
    product_ids: list[uuid.UUID]
    gtin: str | None = None


@dataclass(frozen=True)
class PoolImportResultRow:
    pool_id: uuid.UUID
    gtin: str
    title: str
    accepted: int
    duplicates: int
    invalid: int


@dataclass(frozen=True)
class ImportPreviewGroup:
    gtin: str
    codes_count: int
    suggested_title: str


@dataclass(frozen=True)
class MarkingImportPreviewResult:
    groups: list[ImportPreviewGroup]
    total_codes: int
    invalid_count: int
    duplicates_in_file: int


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
    has_label_artifact: bool


@dataclass(frozen=True)
class SharedBasketRow:
    pool_id: uuid.UUID
    gtin: str
    title: str
    available: int
    printed: int
    products_count: int


@dataclass(frozen=True)
class ProductMarkingInventoryRow:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    requires_honest_sign: bool
    available_count: int
    printed_count: int
    personal_available: int
    personal_printed: int
    shared_baskets: list[SharedBasketRow]


@dataclass(frozen=True)
class PrintedCodeInfo:
    id: uuid.UUID
    cis_code: str
    has_label_artifact: bool


@dataclass(frozen=True)
class PrintMarkingCodesResult:
    packaging_task_line_id: uuid.UUID
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]
    layout: PrintLayout
    shortage: int | None = None
    printed_codes: tuple[PrintedCodeInfo, ...] = ()


@dataclass(frozen=True)
class PrintAllLineResult:
    packaging_task_line_id: uuid.UUID
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    quantity: int
    shortage: int
    codes: list[str]


@dataclass(frozen=True)
class PrintAllMarkingCodesResult:
    packaging_task_id: uuid.UUID
    quantity: int
    duplicate_copies: int
    codes: list[str]
    layout: PrintLayout
    lines: list[PrintAllLineResult]
    dry_run: bool


def cz_copies_from_layout(layout: PrintLayout) -> int:
    total = sum(unit.copies for unit in layout.units if unit.block == LAYOUT_BLOCK_CZ)
    return total if total > 0 else 1


def _printed_code_infos(codes: list[MarkingCode]) -> tuple[PrintedCodeInfo, ...]:
    return tuple(
        PrintedCodeInfo(
            id=code.id,
            cis_code=code.cis_code,
            has_label_artifact=is_printable_label_artifact(code.label_artifact_pdf, code.cis_code),
        )
        for code in codes
    )


def resolve_print_layout(
    layout: PrintLayout | dict[str, object] | None,
    *,
    duplicate_copies: int | None,
) -> PrintLayout:
    if layout is not None:
        return layout if isinstance(layout, PrintLayout) else parse_layout(layout)
    copies = duplicate_copies if duplicate_copies is not None else 2
    if copies not in (1, 2):
        raise MarkingCodeServiceError("invalid_duplicate_copies")
    return PrintLayout(units=[LayoutUnit(block=LAYOUT_BLOCK_CZ, copies=copies)])


@dataclass(frozen=True)
class PoolProductRow:
    id: uuid.UUID
    sku_code: str
    name: str


@dataclass(frozen=True)
class PoolProductsResult:
    pool_id: uuid.UUID
    products: list[PoolProductRow]


def _pool_linked_product_flags(
    products_map: dict[uuid.UUID, list[PoolProductRow]],
    pool_id: uuid.UUID,
) -> tuple[int, bool]:
    linked_products_count = len(products_map.get(pool_id, []))
    return linked_products_count, linked_products_count >= 2


@dataclass(frozen=True)
class PoolListRow:
    id: uuid.UUID
    title: str
    gtin: str
    products: list[PoolProductRow]
    linked_products_count: int
    is_shared: bool
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None
    forecast_days_threshold: int | None
    consumption_7d: int
    loaded: int
    used: int


@dataclass(frozen=True)
class PoolImportBatchRow:
    import_id: uuid.UUID
    document_number: str | None
    filename: str
    accepted_count: int
    created_at: datetime


@dataclass(frozen=True)
class PoolDetailRow:
    id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    gtin: str
    products: list[PoolProductRow]
    linked_products_count: int
    is_shared: bool
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None
    forecast_days_threshold: int | None
    consumption_7d: int
    loaded: int
    used: int
    import_batches: list[PoolImportBatchRow]


@dataclass(frozen=True)
class PoolCodeRow:
    id: uuid.UUID
    cis_masked: str
    status: str
    created_at: datetime
    printed_by: str | None
    document_number: str | None


@dataclass(frozen=True)
class LedgerEventRow:
    id: uuid.UUID
    created_at: datetime
    event_type: str
    cis_masked: str | None
    pool_title: str | None
    gtin: str | None
    product_name: str | None
    product_sku: str | None
    seller_name: str | None
    document_number: str | None
    actor_email: str | None
    aggregated_count: int | None = None


@dataclass(frozen=True)
class LedgerPage:
    rows: list[LedgerEventRow]
    total: int


@dataclass(frozen=True)
class CodeHistoryRow:
    id: uuid.UUID
    created_at: datetime
    event_type: str
    document_number: str | None
    actor_email: str | None
    copies: int
    reason: str | None


def mask_cis_code(cis: str) -> str:
    tail = cis[-12:] if len(cis) > 12 else cis
    return f"…{tail}"


def normalize_cis_mask_query(mask: str) -> str:
    text = mask.strip()
    if text.startswith("…"):
        text = text[1:]
    elif text.startswith("..."):
        text = text[3:]
    return text.strip()


_LEDGER_EXPORT_MAX = 10_000

_LEDGER_CSV_HEADER = (
    "created_at",
    "event_type",
    "cis_masked",
    "pool_title",
    "gtin",
    "product_name",
    "product_sku",
    "seller_name",
    "document_number",
    "actor_email",
)

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


def _extract_cis_codes_from_text(text: str, seen: set[str]) -> list[str]:
    found: list[str] = []
    for match in _CIS_CANDIDATE_RE.finditer(text):
        cis = normalize_cis(match.group(0))
        if cis is None or cis in seen:
            continue
        seen.add(cis)
        found.append(cis)
    if text.strip():
        for line in text.splitlines():
            # Product titles on seller PDF pages are not CIS; only lines that match GS1 CIS shape.
            if not _CIS_CANDIDATE_RE.search(line):
                continue
            cis = normalize_cis(line)
            if cis is None or cis in seen:
                continue
            seen.add(cis)
            found.append(cis)
    return found


def _single_page_pdf_bytes(doc: object, page_index: int) -> bytes:
    import fitz  # pymupdf

    src = cast(fitz.Document, doc)
    single = fitz.open()
    try:
        single.insert_pdf(src, from_page=page_index, to_page=page_index)
        return cast(bytes, single.tobytes())
    finally:
        single.close()


def _parse_pdf_label_rows(content: bytes) -> list[dict[str, str | bytes]]:
    from app.services.marking_label_artifact_service import extract_label_artifacts_from_pdf

    try:
        artifacts = extract_label_artifacts_from_pdf(content)
    except RuntimeError as exc:
        raise MarkingCodeServiceError("pdf_support_unavailable") from exc
    rows: list[dict[str, str | bytes]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        cis = normalize_cis(artifact.cis)
        if cis is None or cis in seen:
            continue
        seen.add(cis)
        rows.append(
            {
                "cis": cis,
                "gtin": artifact.gtin,
                "sku": "",
                "label_pdf": artifact.label_pdf,
            },
        )
    return rows


def is_printable_label_artifact(pdf_bytes: bytes | None, cis_code: str | None = None) -> bool:
    if not pdf_bytes:
        return False
    try:
        import fitz  # pymupdf
    except ImportError:
        return False

    expected = normalize_cis(cis_code or "") if cis_code else None
    seen: set[str] = set()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_index in range(doc.page_count):
            _extract_cis_codes_from_text(doc[page_index].get_text("text"), seen)
    except Exception:
        return False
    finally:
        doc.close()
    if expected is not None and expected not in seen:
        return False
    return len(seen) == 1


def _parse_pdf_text_rows(content: bytes) -> list[dict[str, str]]:
    return [
        {"cis": str(row["cis"]), "gtin": str(row["gtin"]), "sku": str(row.get("sku") or "")}
        for row in _parse_pdf_label_rows(content)
    ]


def parse_import_file(filename: str, content: bytes) -> list[dict[str, str | bytes]]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _parse_pdf_label_rows(content)
    if lower.endswith((".csv", ".txt", ".tsv")):
        return [{**row, "label_pdf": b""} for row in _parse_csv_rows(content)]
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


async def _get_pool_or_error(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
) -> MarkingPool:
    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise MarkingCodeServiceError("pool_not_found")
    return pool


async def _validate_pool_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> None:
    if not product_ids:
        return
    unique_ids = list(dict.fromkeys(product_ids))
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(unique_ids),
    )
    products = list((await session.execute(stmt)).scalars().all())
    if len(products) != len(unique_ids):
        raise MarkingCodeServiceError("product_not_found")
    for product in products:
        if product.seller_id != seller_id:
            raise MarkingCodeServiceError("product_seller_mismatch")


async def _pool_products_result(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
) -> PoolProductsResult:
    stmt = (
        select(Product)
        .join(MarkingPoolProduct, MarkingPoolProduct.product_id == Product.id)
        .where(
            MarkingPoolProduct.tenant_id == tenant_id,
            MarkingPoolProduct.pool_id == pool_id,
        )
        .order_by(Product.sku_code.asc())
    )
    products = list((await session.execute(stmt)).scalars().all())
    return PoolProductsResult(
        pool_id=pool_id,
        products=[
            PoolProductRow(id=p.id, sku_code=p.sku_code, name=p.name) for p in products
        ],
    )


async def _apply_pool_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> None:
    pool = await _get_pool_or_error(session, tenant_id, pool_id)
    unique_ids = list(dict.fromkeys(product_ids))
    await _validate_pool_products(session, tenant_id, pool.seller_id, unique_ids)

    existing_stmt = select(MarkingPoolProduct).where(
        MarkingPoolProduct.tenant_id == tenant_id,
        MarkingPoolProduct.pool_id == pool_id,
    )
    existing = list((await session.execute(existing_stmt)).scalars().all())
    new_ids = set(unique_ids)
    for link in existing:
        if link.product_id not in new_ids:
            await session.delete(link)

    existing_ids = {link.product_id for link in existing}
    for product_id in unique_ids:
        if product_id not in existing_ids:
            session.add(
                MarkingPoolProduct(
                    tenant_id=tenant_id,
                    pool_id=pool_id,
                    product_id=product_id,
                )
            )


async def set_pool_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> PoolProductsResult:
    await _apply_pool_products(session, tenant_id, pool_id, product_ids)
    await session.commit()
    return await _pool_products_result(session, tenant_id, pool_id)


async def add_pool_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> PoolProductsResult:
    pool = await _get_pool_or_error(session, tenant_id, pool_id)
    unique_ids = list(dict.fromkeys(product_ids))
    await _validate_pool_products(session, tenant_id, pool.seller_id, unique_ids)

    if not unique_ids:
        return await _pool_products_result(session, tenant_id, pool_id)

    existing_stmt = select(MarkingPoolProduct.product_id).where(
        MarkingPoolProduct.tenant_id == tenant_id,
        MarkingPoolProduct.pool_id == pool_id,
        MarkingPoolProduct.product_id.in_(unique_ids),
    )
    existing_ids = set((await session.execute(existing_stmt)).scalars().all())
    for product_id in unique_ids:
        if product_id not in existing_ids:
            session.add(
                MarkingPoolProduct(
                    tenant_id=tenant_id,
                    pool_id=pool_id,
                    product_id=product_id,
                )
            )

    await session.commit()
    return await _pool_products_result(session, tenant_id, pool_id)


async def remove_pool_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> PoolProductsResult:
    await _get_pool_or_error(session, tenant_id, pool_id)
    unique_ids = list(dict.fromkeys(product_ids))
    if not unique_ids:
        return await _pool_products_result(session, tenant_id, pool_id)

    links_stmt = select(MarkingPoolProduct).where(
        MarkingPoolProduct.tenant_id == tenant_id,
        MarkingPoolProduct.pool_id == pool_id,
        MarkingPoolProduct.product_id.in_(unique_ids),
    )
    for link in (await session.execute(links_stmt)).scalars().all():
        await session.delete(link)

    await session.commit()
    return await _pool_products_result(session, tenant_id, pool_id)


async def create_marking_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    gtin: str,
    title: str,
) -> MarkingPool:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        raise MarkingCodeServiceError("seller_not_found")
    gtin_clean = gtin.strip()
    title_clean = title.strip()
    if not gtin_clean or not title_clean:
        raise MarkingCodeServiceError("invalid_pool_spec")
    pool = MarkingPool(
        tenant_id=tenant_id,
        seller_id=seller_id,
        gtin=gtin_clean,
        title=title_clean,
    )
    session.add(pool)
    await session.commit()
    await session.refresh(pool)
    return pool


def _group_cis_codes_from_rows(
    parsed_rows: list[dict[str, str | bytes]],
) -> tuple[dict[str, list[str]], int, int, dict[str, bytes]]:
    seen_in_upload: set[str] = set()
    by_gtin: dict[str, list[str]] = {}
    label_pdf_by_cis: dict[str, bytes] = {}
    invalid_count = 0
    duplicate_count = 0
    for row in parsed_rows:
        cis = normalize_cis(str(row.get("cis", "")))
        if cis is None:
            invalid_count += 1
            continue
        if cis in seen_in_upload:
            duplicate_count += 1
            continue
        seen_in_upload.add(cis)
        gtin = str(row.get("gtin") or "").strip() or extract_gtin_from_cis(cis)
        if not gtin:
            invalid_count += 1
            continue
        by_gtin.setdefault(gtin, []).append(cis)
        label_pdf = row.get("label_pdf")
        if isinstance(label_pdf, bytes) and label_pdf and cis not in label_pdf_by_cis:
            label_pdf_by_cis[cis] = label_pdf
    return by_gtin, invalid_count, duplicate_count, label_pdf_by_cis


async def _try_insert_imported_code(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    pool_id: uuid.UUID,
    import_batch_id: uuid.UUID,
    cis_code: str,
    gtin: str,
    label_pdf: bytes | None = None,
) -> MarkingCode | None:
    conn = await session.connection()
    insert_cls = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
    code_id = uuid.uuid4()
    stmt = (
        insert_cls(MarkingCode)
        .values(
            id=code_id,
            tenant_id=tenant_id,
            seller_id=seller_id,
            pool_id=pool_id,
            import_batch_id=import_batch_id,
            cis_code=cis_code,
            gtin=gtin,
            status=STATUS_AVAILABLE,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "cis_code"])
        .returning(MarkingCode.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one_or_none()
    if inserted_id is None:
        return None
    code = await session.get(MarkingCode, inserted_id)
    if code is None:
        raise MarkingCodeServiceError("import_insert_failed")
    if label_pdf:
        code.label_artifact_pdf = label_pdf
    return code


async def preview_marking_import(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    files: list[tuple[str, bytes]],
) -> MarkingImportPreviewResult:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        raise MarkingCodeServiceError("seller_not_found")
    if not files:
        raise MarkingCodeServiceError("empty_file")

    parsed_rows: list[dict[str, str | bytes]] = []
    for filename, content in files:
        try:
            rows = parse_import_file(filename, content)
        except MarkingCodeServiceError:
            raise
        except (UnicodeError, OSError, ValueError) as exc:
            raise MarkingCodeServiceError("parse_failed") from exc
        parsed_rows.extend(rows)

    if not parsed_rows:
        raise MarkingCodeServiceError("empty_file")

    grouped = _group_cis_codes_from_rows(parsed_rows)
    by_gtin, invalid_count, duplicates_in_file, _label_pdfs = grouped
    if not by_gtin:
        raise MarkingCodeServiceError("no_valid_codes")

    groups: list[ImportPreviewGroup] = []
    total_codes = 0
    for gtin, cis_list in sorted(by_gtin.items()):
        stmt = select(MarkingPool).where(
            MarkingPool.tenant_id == tenant_id,
            MarkingPool.seller_id == seller_id,
            MarkingPool.gtin == gtin,
        )
        pool = (await session.execute(stmt)).scalar_one_or_none()
        suggested = pool.title if pool is not None else f"GTIN …{gtin[-4:]}"
        groups.append(
            ImportPreviewGroup(
                gtin=gtin,
                codes_count=len(cis_list),
                suggested_title=suggested,
            )
        )
        total_codes += len(cis_list)

    return MarkingImportPreviewResult(
        groups=groups,
        total_codes=total_codes,
        invalid_count=invalid_count,
        duplicates_in_file=duplicates_in_file,
    )


def _resolve_pool_spec(
    gtin: str,
    pool_specs: list[PoolImportSpec],
) -> PoolImportSpec | None:
    for spec in pool_specs:
        if spec.gtin and spec.gtin.strip() == gtin:
            return spec
    if len(pool_specs) == 1 and not pool_specs[0].gtin:
        return pool_specs[0]
    return None


async def get_or_create_marking_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    gtin: str,
    title: str,
) -> MarkingPool:
    stmt = select(MarkingPool).where(
        MarkingPool.tenant_id == tenant_id,
        MarkingPool.seller_id == seller_id,
        MarkingPool.gtin == gtin,
    )
    pool = (await session.execute(stmt)).scalar_one_or_none()
    title_clean = title.strip() or f"GTIN …{gtin[-4:]}"
    if pool is not None:
        if title_clean and pool.title != title_clean:
            pool.title = title_clean
        return pool
    pool = MarkingPool(
        tenant_id=tenant_id,
        seller_id=seller_id,
        gtin=gtin,
        title=title_clean,
    )
    session.add(pool)
    await session.flush()
    return pool


async def _pool_ids_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> list[uuid.UUID]:
    stmt = select(MarkingPoolProduct.pool_id).where(
        MarkingPoolProduct.tenant_id == tenant_id,
        MarkingPoolProduct.product_id == product_id,
    )
    return list((await session.execute(stmt)).scalars().all())


def _marking_supply_key(pool_ids: list[uuid.UUID], product_id: uuid.UUID) -> tuple[str, ...]:
    if pool_ids:
        return ("pool", *(str(pool_id) for pool_id in sorted(pool_ids, key=str)))
    return ("product", str(product_id))


async def _code_filter_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> tuple[ColumnElement[bool] | None, Product | None]:
    product = await get_product(session, tenant_id, product_id)
    if product is None:
        return None, None
    pool_ids = await _pool_ids_for_product(session, tenant_id, product_id)
    code_filter: ColumnElement[bool]
    if pool_ids:
        code_filter = MarkingCode.pool_id.in_(pool_ids)
    else:
        code_filter = MarkingCode.product_id == product.id
    return code_filter, product


async def import_marking_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    files: list[tuple[str, bytes]],
    pool_specs: list[PoolImportSpec],
    uploaded_by_user_id: uuid.UUID | None,
) -> MarkingImportResult:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        raise MarkingCodeServiceError("seller_not_found")
    if not files:
        raise MarkingCodeServiceError("empty_file")

    parsed_rows: list[dict[str, str | bytes]] = []
    filenames: list[str] = []
    for filename, content in files:
        try:
            rows = parse_import_file(filename, content)
        except MarkingCodeServiceError:
            raise
        except (UnicodeError, OSError, ValueError) as exc:
            raise MarkingCodeServiceError("parse_failed") from exc
        parsed_rows.extend(rows)
        filenames.append(filename)

    if not parsed_rows:
        raise MarkingCodeServiceError("empty_file")

    for spec in pool_specs:
        await _validate_pool_products(session, tenant_id, seller_id, spec.product_ids)

    batch = MarkingCodeImport(
        tenant_id=tenant_id,
        seller_id=seller_id,
        filename=", ".join(filenames)[:512],
        accepted_count=0,
        skipped_count=0,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    session.add(batch)
    await session.flush()
    document_number = await assign_document_number_if_missing(
        session,
        tenant_id,
        DOC_TYPE_MARKING_IMPORT,
        batch,
    )
    assert document_number is not None

    by_gtin, invalid_count, duplicate_count, label_pdf_by_cis = _group_cis_codes_from_rows(
        parsed_rows
    )

    pool_results: list[PoolImportResultRow] = []
    total_accepted = 0

    for gtin, cis_list in sorted(by_gtin.items()):
        pool_spec = _resolve_pool_spec(gtin, pool_specs)
        title = pool_spec.title if pool_spec is not None else f"GTIN …{gtin[-4:]}"
        product_ids = pool_spec.product_ids if pool_spec is not None else []
        pool = await get_or_create_marking_pool(
            session,
            tenant_id,
            seller_id,
            gtin=gtin,
            title=title,
        )
        if product_ids:
            await _apply_pool_products(session, tenant_id, pool.id, product_ids)

        pool_accepted = 0
        pool_duplicates = 0
        pool_invalid = 0

        for cis in cis_list:
            code = await _try_insert_imported_code(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
                import_batch_id=batch.id,
                cis_code=cis,
                gtin=gtin,
                label_pdf=label_pdf_by_cis.get(cis),
            )
            if code is None:
                pool_duplicates += 1
                continue
            await record_event(
                session,
                code=code,
                event_type=EVENT_IMPORTED,
                actor=uploaded_by_user_id,
                document_number=document_number,
            )
            pool_accepted += 1

        pool_results.append(
            PoolImportResultRow(
                pool_id=pool.id,
                gtin=gtin,
                title=pool.title,
                accepted=pool_accepted,
                duplicates=pool_duplicates,
                invalid=pool_invalid,
            )
        )
        total_accepted += pool_accepted
        duplicate_count += pool_duplicates

    total_skipped = invalid_count + duplicate_count
    skip_counts: dict[str, int] = {}
    if invalid_count:
        skip_counts["invalid_format"] = invalid_count
    if duplicate_count:
        skip_counts["duplicate"] = duplicate_count

    batch.accepted_count = total_accepted
    batch.skipped_count = total_skipped
    batch.skip_reasons_json = json.dumps(skip_counts, ensure_ascii=False) if skip_counts else None
    await session.commit()

    return MarkingImportResult(
        import_id=batch.id,
        document_number=document_number,
        accepted_count=total_accepted,
        skipped_count=total_skipped,
        skip_reasons=[ImportSkipReason(k, v) for k, v in sorted(skip_counts.items())],
        pools=pool_results,
    )


async def list_inventory(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
) -> MarkingInventoryResult:
    product_stmt = select(Product).where(Product.tenant_id == tenant_id)
    if seller_id is not None:
        product_stmt = product_stmt.where(Product.seller_id == seller_id)
    products = list((await session.execute(product_stmt)).scalars().all())

    counts_stmt = (
        select(
            MarkingCode.product_id,
            MarkingCode.pool_id,
            MarkingCode.status,
            func.count(MarkingCode.id),
        )
        .where(MarkingCode.tenant_id == tenant_id)
        .group_by(MarkingCode.product_id, MarkingCode.pool_id, MarkingCode.status)
    )
    if seller_id is not None:
        counts_stmt = counts_stmt.where(MarkingCode.seller_id == seller_id)
    count_rows = (await session.execute(counts_stmt)).all()
    available_by_product: dict[uuid.UUID, int] = {}
    printed_by_product: dict[uuid.UUID, int] = {}
    available_by_pool: dict[uuid.UUID, int] = {}
    printed_by_pool: dict[uuid.UUID, int] = {}
    unlinked_available = 0
    for product_id, pool_id, status, cnt in count_rows:
        count = int(cnt)
        if product_id is None and pool_id is None:
            if status == STATUS_AVAILABLE:
                unlinked_available = count
            continue
        if pool_id is not None:
            if status == STATUS_AVAILABLE:
                available_by_pool[pool_id] = available_by_pool.get(pool_id, 0) + count
            elif status == STATUS_PRINTED:
                printed_by_pool[pool_id] = printed_by_pool.get(pool_id, 0) + count
            continue
        if product_id is not None:
            if status == STATUS_AVAILABLE:
                available_by_product[product_id] = available_by_product.get(product_id, 0) + count
            elif status == STATUS_PRINTED:
                printed_by_product[product_id] = printed_by_product.get(product_id, 0) + count

    pool_links_stmt = select(MarkingPoolProduct.pool_id, MarkingPoolProduct.product_id).where(
        MarkingPoolProduct.tenant_id == tenant_id,
    )
    if seller_id is not None:
        pool_links_stmt = pool_links_stmt.join(
            MarkingPool, MarkingPool.id == MarkingPoolProduct.pool_id
        ).where(MarkingPool.seller_id == seller_id)
    pool_links = (await session.execute(pool_links_stmt)).all()
    linked_count: dict[uuid.UUID, int] = {}
    pools_by_product: dict[uuid.UUID, list[uuid.UUID]] = {}
    for pool_id, product_id in pool_links:
        linked_count[pool_id] = linked_count.get(pool_id, 0) + 1
        pools_by_product.setdefault(product_id, []).append(pool_id)

    shared_pool_ids = {pid for pid, cnt in linked_count.items() if cnt >= 2}
    pool_meta: dict[uuid.UUID, MarkingPool] = {}
    if shared_pool_ids:
        pool_rows = (
            await session.execute(
                select(MarkingPool).where(
                    MarkingPool.tenant_id == tenant_id,
                    MarkingPool.id.in_(shared_pool_ids),
                )
            )
        ).scalars().all()
        pool_meta = {p.id: p for p in pool_rows}

    rows: list[ProductMarkingInventoryRow] = []
    for p in products:
        personal_available = available_by_product.get(p.id, 0)
        personal_printed = printed_by_product.get(p.id, 0)
        shared_baskets: list[SharedBasketRow] = []
        for pool_id in pools_by_product.get(p.id, []):
            products_in_pool = linked_count.get(pool_id, 0)
            pool_available = available_by_pool.get(pool_id, 0)
            pool_printed = printed_by_pool.get(pool_id, 0)
            if products_in_pool == 1:
                personal_available += pool_available
                personal_printed += pool_printed
            elif products_in_pool >= 2:
                meta = pool_meta.get(pool_id)
                if meta is None:
                    continue
                shared_baskets.append(
                    SharedBasketRow(
                        pool_id=pool_id,
                        gtin=meta.gtin,
                        title=meta.title,
                        available=pool_available,
                        printed=pool_printed,
                        products_count=products_in_pool,
                    )
                )
        shared_baskets.sort(key=lambda b: b.title)
        has_pool_link = bool(pools_by_product.get(p.id))
        is_cz_relevant = (
            bool(p.requires_honest_sign)
            or personal_available > 0
            or bool(shared_baskets)
            or has_pool_link
        )
        if not is_cz_relevant:
            continue
        rows.append(
            ProductMarkingInventoryRow(
                product_id=p.id,
                sku_code=p.sku_code,
                product_name=p.name,
                requires_honest_sign=bool(p.requires_honest_sign),
                available_count=personal_available,
                printed_count=personal_printed,
                personal_available=personal_available,
                personal_printed=personal_printed,
                shared_baskets=shared_baskets,
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
    code_filter, product = await _code_filter_for_product(session, tenant_id, product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    if code_filter is None:
        return []

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            code_filter,
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
            has_label_artifact=is_printable_label_artifact(code.label_artifact_pdf, code.cis_code),
        )
        for code in codes
    ]


async def count_available_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    code_filter, product = await _code_filter_for_product(session, tenant_id, product_id)
    if product is None or code_filter is None:
        return 0
    stmt = select(func.count(MarkingCode.id)).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.seller_id == product.seller_id,
        MarkingCode.status == STATUS_AVAILABLE,
        code_filter,
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def count_available_for_products_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: set[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}

    counts: dict[uuid.UUID, int] = dict.fromkeys(product_ids, 0)

    pool_stmt = (
        select(
            MarkingPoolProduct.product_id,
            func.count(func.distinct(MarkingCode.id)),
        )
        .join(
            MarkingCode,
            (MarkingCode.pool_id == MarkingPoolProduct.pool_id)
            & (MarkingCode.tenant_id == MarkingPoolProduct.tenant_id),
        )
        .join(Product, Product.id == MarkingPoolProduct.product_id)
        .where(
            MarkingPoolProduct.tenant_id == tenant_id,
            MarkingPoolProduct.product_id.in_(product_ids),
            MarkingCode.status == STATUS_AVAILABLE,
            MarkingCode.seller_id == Product.seller_id,
        )
        .group_by(MarkingPoolProduct.product_id)
    )
    for product_id, available in (await session.execute(pool_stmt)).all():
        counts[product_id] = int(available)

    linked_products = select(MarkingPoolProduct.product_id).where(
        MarkingPoolProduct.tenant_id == tenant_id,
        MarkingPoolProduct.product_id.in_(product_ids),
    )
    product_stmt = (
        select(MarkingCode.product_id, func.count(MarkingCode.id))
        .join(Product, Product.id == MarkingCode.product_id)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.product_id.in_(product_ids),
            MarkingCode.product_id.not_in(linked_products),
            MarkingCode.status == STATUS_AVAILABLE,
            MarkingCode.seller_id == Product.seller_id,
        )
        .group_by(MarkingCode.product_id)
    )
    for product_id, available in (await session.execute(product_stmt)).all():
        counts[product_id] = int(available)

    return counts


async def print_codes_for_packaging_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_line_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID,
    layout: PrintLayout | dict[str, object] | None = None,
    allow_partial: bool = False,
    reprint: bool = False,
    reprint_code_ids: list[uuid.UUID] | None = None,
    duplicate_copies: int | None = None,
    units_to_print: int | None = None,
    commit: bool = True,
) -> PrintMarkingCodesResult:
    print_layout = resolve_print_layout(layout, duplicate_copies=duplicate_copies)
    event_copies = cz_copies_from_layout(print_layout)

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
    if task.status not in (STATUS_DRAFT, STATUS_IN_PROGRESS):
        raise MarkingCodeServiceError("task_not_active")

    product = await get_product(session, tenant_id, line.product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    if not product.requires_honest_sign:
        raise MarkingCodeServiceError("marking_not_required")
    if product.seller_id is None:
        raise MarkingCodeServiceError("product_seller_missing")

    from app.services.packaging_task_service import qty_need_pack

    quantity_needed = qty_need_pack(line)
    if quantity_needed < 1:
        raise MarkingCodeServiceError("nothing_to_mark")

    line_id = line.id

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
        if reprint_code_ids is not None:
            if not reprint_code_ids:
                raise MarkingCodeServiceError("invalid_reprint_selection")
            wanted = set(reprint_code_ids)
            codes = [code for code in codes if code.id in wanted]
            if len(codes) != len(wanted):
                raise MarkingCodeServiceError("code_not_found")
        for code in codes:
            await record_event(
                session,
                code=code,
                event_type=EVENT_REPRINTED,
                actor=acting_user_id,
                document_number=task.document_number,
                packaging_task=line,
                copies=event_copies,
            )
        if commit:
            await session.commit()
        else:
            await session.flush()
        return PrintMarkingCodesResult(
            packaging_task_line_id=line_id,
            quantity=len(codes),
            duplicate_copies=event_copies,
            is_reprint=True,
            codes=[c.cis_code for c in codes],
            layout=print_layout,
            printed_codes=_printed_code_infos(codes),
        )

    if int(line.qty_marking_printed) > 0 and units_to_print is None:
        raise MarkingCodeServiceError("already_printed_use_reprint")

    already_printed = int(line.qty_marking_printed)
    remaining_need = quantity_needed - already_printed
    if remaining_need < 1:
        raise MarkingCodeServiceError("marking_complete")

    if units_to_print is not None:
        if units_to_print < 1:
            raise MarkingCodeServiceError("invalid_print_quantity")
        target_qty = min(units_to_print, remaining_need)
    else:
        target_qty = quantity_needed

    code_filter, filter_product = await _code_filter_for_product(
        session,
        tenant_id,
        product.id,
    )
    if filter_product is None or code_filter is None:
        raise MarkingCodeServiceError("product_not_found")

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            MarkingCode.status == STATUS_AVAILABLE,
            code_filter,
        )
        .order_by(MarkingCode.created_at.asc())
        .limit(target_qty)
        .with_for_update(skip_locked=True)
    )
    codes = list((await session.execute(stmt)).scalars().all())
    available = len(codes)
    shortage = max(0, target_qty - available)

    if shortage > 0 and not allow_partial:
        if commit:
            await session.rollback()
        return PrintMarkingCodesResult(
            packaging_task_line_id=line_id,
            quantity=0,
            duplicate_copies=event_copies,
            is_reprint=False,
            codes=[],
            layout=print_layout,
            shortage=shortage,
        )

    quantity = available if shortage > 0 else target_qty
    if quantity < 1:
        if commit:
            await session.rollback()
        return PrintMarkingCodesResult(
            packaging_task_line_id=line_id,
            quantity=0,
            duplicate_copies=event_copies,
            is_reprint=False,
            codes=[],
            layout=print_layout,
            shortage=shortage if shortage > 0 else target_qty,
        )

    now = datetime.now(UTC)
    for code in codes[:quantity]:
        code.status = STATUS_RESERVED
        code.reserved_by_user_id = acting_user_id
        code.reserved_at = now
    await session.flush()

    for code in codes[:quantity]:
        code.status = STATUS_PRINTED
        code.product_id = product.id
        code.packaging_task_line_id = line.id
        code.printed_at = now
        code.printed_by_user_id = acting_user_id
        code.reserved_by_user_id = None
        code.reserved_at = None
        await record_event(
            session,
            code=code,
            event_type=EVENT_PRINTED,
            actor=acting_user_id,
            document_number=task.document_number,
            packaging_task=line,
            copies=event_copies,
        )

    line.qty_marking_printed = already_printed + quantity
    if commit:
        await session.commit()
    else:
        await session.flush()

    printed_slice = codes[:quantity]
    return PrintMarkingCodesResult(
        packaging_task_line_id=line_id,
        quantity=quantity,
        duplicate_copies=event_copies,
        is_reprint=False,
        codes=[c.cis_code for c in printed_slice],
        layout=print_layout,
        shortage=shortage if shortage > 0 else None,
        printed_codes=_printed_code_infos(printed_slice),
    )


CATALOG_PRINT_LINE_SENTINEL = uuid.UUID(int=0)


async def print_codes_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID,
    quantity: int,
    layout: PrintLayout | dict[str, object] | None = None,
    allow_partial: bool = False,
    duplicate_copies: int | None = None,
) -> PrintMarkingCodesResult:
    if quantity < 1:
        raise MarkingCodeServiceError("invalid_print_quantity")

    print_layout = resolve_print_layout(layout, duplicate_copies=duplicate_copies)
    event_copies = cz_copies_from_layout(print_layout)

    product = await get_product(session, tenant_id, product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    if not product.requires_honest_sign:
        raise MarkingCodeServiceError("marking_not_required")
    if product.seller_id is None:
        raise MarkingCodeServiceError("product_seller_missing")

    code_filter, filter_product = await _code_filter_for_product(
        session,
        tenant_id,
        product.id,
    )
    if filter_product is None or code_filter is None:
        raise MarkingCodeServiceError("product_not_found")

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            MarkingCode.status == STATUS_AVAILABLE,
            code_filter,
        )
        .order_by(MarkingCode.created_at.asc())
        .limit(quantity)
        .with_for_update(skip_locked=True)
    )
    codes = list((await session.execute(stmt)).scalars().all())
    available = len(codes)
    shortage = max(0, quantity - available)

    if shortage > 0 and not allow_partial:
        await session.rollback()
        return PrintMarkingCodesResult(
            packaging_task_line_id=CATALOG_PRINT_LINE_SENTINEL,
            quantity=0,
            duplicate_copies=event_copies,
            is_reprint=False,
            codes=[],
            layout=print_layout,
            shortage=shortage,
        )

    print_quantity = available if shortage > 0 else quantity
    if print_quantity < 1:
        await session.rollback()
        return PrintMarkingCodesResult(
            packaging_task_line_id=CATALOG_PRINT_LINE_SENTINEL,
            quantity=0,
            duplicate_copies=event_copies,
            is_reprint=False,
            codes=[],
            layout=print_layout,
            shortage=shortage if shortage > 0 else quantity,
        )

    now = datetime.now(UTC)
    for code in codes[:print_quantity]:
        code.status = STATUS_RESERVED
        code.reserved_by_user_id = acting_user_id
        code.reserved_at = now
    await session.flush()

    for code in codes[:print_quantity]:
        code.status = STATUS_PRINTED
        code.product_id = product.id
        code.printed_at = now
        code.printed_by_user_id = acting_user_id
        code.reserved_by_user_id = None
        code.reserved_at = None
        await record_event(
            session,
            code=code,
            event_type=EVENT_PRINTED,
            actor=acting_user_id,
            document_number=None,
            packaging_task=None,
            copies=event_copies,
        )

    await session.commit()

    printed_slice = codes[:print_quantity]
    return PrintMarkingCodesResult(
        packaging_task_line_id=CATALOG_PRINT_LINE_SENTINEL,
        quantity=print_quantity,
        duplicate_copies=event_copies,
        is_reprint=False,
        codes=[c.cis_code for c in printed_slice],
        layout=print_layout,
        shortage=shortage if shortage > 0 else None,
        printed_codes=_printed_code_infos(printed_slice),
    )


async def _find_product_by_scan_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    barcode: str,
) -> Product | None:
    code = barcode.strip()
    if not code:
        return None
    lower = code.lower()
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        or_(
            func.lower(Product.sku_code) == lower,
            func.lower(Product.wb_barcode) == lower,
        ),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def scan_print_for_packaging_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
    *,
    product_barcode: str,
    acting_user_id: uuid.UUID,
) -> PrintMarkingCodesResult:
    task_stmt = (
        select(PackagingTask)
        .where(PackagingTask.id == packaging_task_id, PackagingTask.tenant_id == tenant_id)
        .options(selectinload(PackagingTask.lines))
    )
    task = (await session.execute(task_stmt)).scalar_one_or_none()
    if task is None:
        raise MarkingCodeServiceError("task_not_found")

    product = await _find_product_by_scan_barcode(session, tenant_id, product_barcode)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")

    line = next((ln for ln in task.lines if ln.product_id == product.id), None)
    if line is None:
        raise MarkingCodeServiceError("line_not_in_task")

    default_template = await resolve_default_print_template(
        session,
        tenant_id,
        product_id=product.id,
        seller_id=product.seller_id,
    )
    return await print_codes_for_packaging_line(
        session,
        tenant_id,
        line.id,
        acting_user_id=acting_user_id,
        layout=default_template.layout,
        allow_partial=False,
        units_to_print=1,
    )


async def _load_packaging_task_for_marking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
) -> PackagingTask:
    task_stmt = (
        select(PackagingTask)
        .where(PackagingTask.id == packaging_task_id, PackagingTask.tenant_id == tenant_id)
        .options(
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.product),
        )
    )
    task = (await session.execute(task_stmt)).scalar_one_or_none()
    if task is None:
        raise MarkingCodeServiceError("task_not_found")
    return task


def _lines_needing_marking(task: PackagingTask) -> list[PackagingTaskLine]:
    from app.services.packaging_task_service import qty_need_pack

    out: list[PackagingTaskLine] = []
    for line in task.lines:
        product = line.product
        if product is None or not product.requires_honest_sign:
            continue
        remaining = qty_need_pack(line) - int(line.qty_marking_printed)
        if remaining > 0:
            out.append(line)
    return out


async def _ordered_lines_needing_marking(
    session: AsyncSession,
    task: PackagingTask,
) -> list[PackagingTaskLine]:
    lines = _lines_needing_marking(task)
    if not lines:
        return []
    loc_ids = {ln.storage_location_id for ln in lines}
    stmt = select(StorageLocation.id, StorageLocation.code).where(
        StorageLocation.id.in_(loc_ids),
    )
    code_by_id = {row[0]: row[1] for row in (await session.execute(stmt)).all()}
    return sorted(lines, key=lambda ln: code_by_id.get(ln.storage_location_id, ""))


async def _resolve_line_print_layout(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line: PackagingTaskLine,
    *,
    global_layout: PrintLayout | dict[str, object] | None,
) -> PrintLayout:
    if global_layout is not None:
        return resolve_print_layout(global_layout, duplicate_copies=None)
    product = line.product
    if product is None:
        raise MarkingCodeServiceError("product_not_found")
    template = await resolve_default_print_template(
        session,
        tenant_id,
        product_id=product.id,
        seller_id=product.seller_id,
    )
    return template.layout


async def _preview_all_lines_print(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lines: list[PackagingTaskLine],
    *,
    allow_partial: bool,
) -> list[PrintAllLineResult]:
    """Preview print-all with shared pool budget (same filters as issuance)."""
    from app.services.packaging_task_service import qty_need_pack

    budget: dict[tuple[str, ...], int] = {}
    pool_ids_cache: dict[uuid.UUID, list[uuid.UUID]] = {}
    results: list[PrintAllLineResult] = []

    for line in lines:
        product = line.product
        if product is None:
            raise MarkingCodeServiceError("product_not_found")

        if line.product_id not in pool_ids_cache:
            pool_ids_cache[line.product_id] = await _pool_ids_for_product(
                session,
                tenant_id,
                line.product_id,
            )
        pool_ids = pool_ids_cache[line.product_id]
        supply_key = _marking_supply_key(pool_ids, line.product_id)

        if supply_key not in budget:
            budget[supply_key] = await count_available_for_product(
                session,
                tenant_id,
                line.product_id,
            )

        remaining = qty_need_pack(line) - int(line.qty_marking_printed)
        available = budget[supply_key]
        shortage = max(0, remaining - available)
        if shortage > 0 and not allow_partial:
            quantity = 0
            codes: list[str] = []
        else:
            quantity = min(remaining, available) if shortage > 0 else remaining
            codes = [f"__preview_{line.id}_{i}" for i in range(quantity)]
            budget[supply_key] -= quantity

        results.append(
            PrintAllLineResult(
                packaging_task_line_id=line.id,
                product_id=product.id,
                sku_code=product.sku_code,
                product_name=product.name,
                quantity=quantity,
                shortage=shortage,
                codes=codes,
            ),
        )

    return results


async def print_all_for_packaging_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID,
    layout: PrintLayout | dict[str, object] | None = None,
    allow_partial: bool = False,
    dry_run: bool = False,
) -> PrintAllMarkingCodesResult:
    task = await _load_packaging_task_for_marking(session, tenant_id, packaging_task_id)
    lines = await _ordered_lines_needing_marking(session, task)
    if not lines:
        raise MarkingCodeServiceError("nothing_to_mark")

    response_layout = await _resolve_line_print_layout(
        session,
        tenant_id,
        lines[0],
        global_layout=layout,
    )
    duplicate_copies = cz_copies_from_layout(response_layout)

    print_line_results: list[PrintAllLineResult] = []

    if dry_run:
        previews = await _preview_all_lines_print(
            session,
            tenant_id,
            lines,
            allow_partial=allow_partial,
        )
        print_line_results = [
            PrintAllLineResult(
                packaging_task_line_id=preview.packaging_task_line_id,
                product_id=preview.product_id,
                sku_code=preview.sku_code,
                product_name=preview.product_name,
                quantity=preview.quantity,
                shortage=preview.shortage,
                codes=[],
            )
            for preview in previews
        ]
        total_qty = sum(r.quantity for r in print_line_results)
        return PrintAllMarkingCodesResult(
            packaging_task_id=packaging_task_id,
            quantity=total_qty,
            duplicate_copies=duplicate_copies,
            codes=[],
            layout=response_layout,
            lines=print_line_results,
            dry_run=True,
        )

    if not allow_partial:
        previews = await _preview_all_lines_print(
            session,
            tenant_id,
            lines,
            allow_partial=False,
        )
        if any(p.shortage > 0 for p in previews):
            return PrintAllMarkingCodesResult(
                packaging_task_id=packaging_task_id,
                quantity=0,
                duplicate_copies=duplicate_copies,
                codes=[],
                layout=response_layout,
                lines=[
                    PrintAllLineResult(
                        packaging_task_line_id=p.packaging_task_line_id,
                        product_id=p.product_id,
                        sku_code=p.sku_code,
                        product_name=p.product_name,
                        quantity=0,
                        shortage=p.shortage,
                        codes=[],
                    )
                    for p in previews
                ],
                dry_run=False,
            )

    line_results: list[PrintAllLineResult] = []
    all_codes: list[str] = []
    total_qty = 0
    try:
        for line in lines:
            line_id = line.id
            line_product_id = line.product_id
            line_layout = await _resolve_line_print_layout(
                session,
                tenant_id,
                line,
                global_layout=layout,
            )
            result = await print_codes_for_packaging_line(
                session,
                tenant_id,
                line_id,
                acting_user_id=acting_user_id,
                layout=line_layout,
                allow_partial=allow_partial,
                commit=False,
            )
            product = await get_product(session, tenant_id, line_product_id)
            sku = product.sku_code if product is not None else ""
            name = product.name if product is not None else ""
            shortage = int(result.shortage or 0)
            if shortage > 0 and not allow_partial:
                await session.rollback()
                failure_lines = [
                    PrintAllLineResult(
                        packaging_task_line_id=lr.packaging_task_line_id,
                        product_id=lr.product_id,
                        sku_code=lr.sku_code,
                        product_name=lr.product_name,
                        quantity=0,
                        shortage=0,
                        codes=[],
                    )
                    for lr in line_results
                ]
                failure_lines.append(
                    PrintAllLineResult(
                        packaging_task_line_id=line_id,
                        product_id=line_product_id,
                        sku_code=sku,
                        product_name=name,
                        quantity=0,
                        shortage=shortage,
                        codes=[],
                    ),
                )
                return PrintAllMarkingCodesResult(
                    packaging_task_id=packaging_task_id,
                    quantity=0,
                    duplicate_copies=duplicate_copies,
                    codes=[],
                    layout=response_layout,
                    lines=failure_lines,
                    dry_run=False,
                )
            line_results.append(
                PrintAllLineResult(
                    packaging_task_line_id=line_id,
                    product_id=line_product_id,
                    sku_code=sku,
                    product_name=name,
                    quantity=result.quantity,
                    shortage=shortage,
                    codes=result.codes,
                ),
            )
            all_codes.extend(result.codes)
            total_qty += result.quantity
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return PrintAllMarkingCodesResult(
        packaging_task_id=packaging_task_id,
        quantity=total_qty,
        duplicate_copies=duplicate_copies,
        codes=all_codes,
        layout=response_layout,
        lines=line_results,
        dry_run=False,
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


async def _pool_status_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    pool_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, dict[str, int]]:
    stmt = (
        select(
            MarkingCode.pool_id,
            MarkingCode.status,
            func.count(MarkingCode.id),
        )
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.pool_id.is_not(None),
        )
        .group_by(MarkingCode.pool_id, MarkingCode.status)
    )
    if seller_id is not None:
        stmt = stmt.where(MarkingCode.seller_id == seller_id)
    if pool_ids is not None:
        stmt = stmt.where(MarkingCode.pool_id.in_(pool_ids))
    result: dict[uuid.UUID, dict[str, int]] = {}
    for pool_id, status, cnt in (await session.execute(stmt)).all():
        if pool_id is None:
            continue
        bucket = result.setdefault(pool_id, {})
        bucket[status] = int(cnt)
    return result


def _status_count(counts: dict[str, int], status: str) -> int:
    return int(counts.get(status, 0))


CONSUMPTION_LOOKBACK_DAYS = 7
CONSUMPTION_EVENT_TYPES = frozenset({EVENT_PRINTED, EVENT_SHIPPED})


def _pool_loaded_used(pool_counts: dict[str, int]) -> tuple[int, int]:
    loaded = sum(pool_counts.values())
    available = _status_count(pool_counts, STATUS_AVAILABLE)
    reserved = _status_count(pool_counts, STATUS_RESERVED)
    used = max(0, loaded - available - reserved)
    return loaded, used


def compute_forecast_days(available: int, consumption_7d: int) -> float | None:
    if consumption_7d <= 0:
        return None
    avg_per_day = consumption_7d / CONSUMPTION_LOOKBACK_DAYS
    if avg_per_day <= 0:
        return None
    return round(available / avg_per_day, 1)


async def _pool_consumption_7d_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not pool_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=CONSUMPTION_LOOKBACK_DAYS)
    stmt = (
        select(
            MarkingCodeEvent.pool_id,
            func.count(func.distinct(MarkingCodeEvent.code_id)),
        )
        .where(
            MarkingCodeEvent.tenant_id == tenant_id,
            MarkingCodeEvent.pool_id.in_(pool_ids),
            MarkingCodeEvent.event_type.in_(tuple(CONSUMPTION_EVENT_TYPES)),
            MarkingCodeEvent.created_at >= cutoff,
        )
        .group_by(MarkingCodeEvent.pool_id)
    )
    out: dict[uuid.UUID, int] = {}
    for pool_id, total in (await session.execute(stmt)).all():
        if pool_id is not None:
            out[pool_id] = int(total)
    return out


async def set_pool_threshold(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    *,
    low_stock_threshold: int | None,
    forecast_days_threshold: int | None,
) -> MarkingPool:
    pool = await _get_pool_or_error(session, tenant_id, pool_id)
    if low_stock_threshold is not None and low_stock_threshold < 0:
        raise MarkingCodeServiceError("invalid_threshold")
    if forecast_days_threshold is not None and forecast_days_threshold < 0:
        raise MarkingCodeServiceError("invalid_threshold")
    pool.low_stock_threshold = low_stock_threshold
    pool.forecast_days_threshold = forecast_days_threshold
    await session.commit()
    await session.refresh(pool)
    return pool


async def _products_by_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[PoolProductRow]]:
    if not pool_ids:
        return {}
    stmt = (
        select(
            MarkingPoolProduct.pool_id,
            Product.id,
            Product.sku_code,
            Product.name,
        )
        .join(Product, Product.id == MarkingPoolProduct.product_id)
        .where(
            MarkingPoolProduct.tenant_id == tenant_id,
            MarkingPoolProduct.pool_id.in_(pool_ids),
        )
        .order_by(Product.sku_code.asc())
    )
    out: dict[uuid.UUID, list[PoolProductRow]] = {}
    for pool_id, product_id, sku_code, name in (await session.execute(stmt)).all():
        out.setdefault(pool_id, []).append(
            PoolProductRow(id=product_id, sku_code=sku_code, name=name)
        )
    return out


async def list_pools(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
) -> list[PoolListRow]:
    stmt = select(MarkingPool).where(MarkingPool.tenant_id == tenant_id)
    if seller_id is not None:
        stmt = stmt.where(MarkingPool.seller_id == seller_id)
    stmt = stmt.order_by(MarkingPool.title.asc())
    pools = list((await session.execute(stmt)).scalars().all())
    pool_ids = [p.id for p in pools]
    counts = await _pool_status_counts(session, tenant_id, seller_id=seller_id, pool_ids=pool_ids)
    products_map = await _products_by_pool(session, tenant_id, pool_ids)
    consumption_map = await _pool_consumption_7d_batch(session, tenant_id, pool_ids)
    rows: list[PoolListRow] = []
    for pool in pools:
        pool_counts = counts.get(pool.id, {})
        available = _status_count(pool_counts, STATUS_AVAILABLE)
        consumption_7d = consumption_map.get(pool.id, 0)
        loaded, used = _pool_loaded_used(pool_counts)
        linked_products_count, is_shared = _pool_linked_product_flags(products_map, pool.id)
        rows.append(
            PoolListRow(
                id=pool.id,
                title=pool.title,
                gtin=pool.gtin,
                products=products_map.get(pool.id, []),
                linked_products_count=linked_products_count,
                is_shared=is_shared,
                available=available,
                reserved=_status_count(pool_counts, STATUS_RESERVED),
                printed=_status_count(pool_counts, STATUS_PRINTED),
                defective=_status_count(pool_counts, STATUS_DEFECTIVE),
                forecast_days=compute_forecast_days(available, consumption_7d),
                low_stock_threshold=pool.low_stock_threshold,
                forecast_days_threshold=pool.forecast_days_threshold,
                consumption_7d=consumption_7d,
                loaded=loaded,
                used=used,
            )
        )
    return rows


async def get_pool_detail(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
) -> PoolDetailRow:
    pool = await _get_pool_or_error(session, tenant_id, pool_id)
    counts = await _pool_status_counts(
        session, tenant_id, seller_id=None, pool_ids=[pool_id]
    )
    pool_counts = counts.get(pool_id, {})
    available = _status_count(pool_counts, STATUS_AVAILABLE)
    consumption_7d = (
        await _pool_consumption_7d_batch(session, tenant_id, [pool_id])
    ).get(pool_id, 0)
    loaded, used = _pool_loaded_used(pool_counts)

    batch_stmt = (
        select(MarkingCodeImport)
        .join(MarkingCode, MarkingCode.import_batch_id == MarkingCodeImport.id)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.pool_id == pool_id,
            MarkingCodeImport.tenant_id == tenant_id,
        )
        .distinct()
        .order_by(MarkingCodeImport.created_at.desc())
    )
    batches = list((await session.execute(batch_stmt)).scalars().all())
    products_map = await _products_by_pool(session, tenant_id, [pool_id])
    linked_products_count, is_shared = _pool_linked_product_flags(products_map, pool_id)

    return PoolDetailRow(
        id=pool.id,
        seller_id=pool.seller_id,
        title=pool.title,
        gtin=pool.gtin,
        products=products_map.get(pool_id, []),
        linked_products_count=linked_products_count,
        is_shared=is_shared,
        available=available,
        reserved=_status_count(pool_counts, STATUS_RESERVED),
        printed=_status_count(pool_counts, STATUS_PRINTED),
        defective=_status_count(pool_counts, STATUS_DEFECTIVE),
        forecast_days=compute_forecast_days(available, consumption_7d),
        low_stock_threshold=pool.low_stock_threshold,
        forecast_days_threshold=pool.forecast_days_threshold,
        consumption_7d=consumption_7d,
        loaded=loaded,
        used=used,
        import_batches=[
            PoolImportBatchRow(
                import_id=b.id,
                document_number=b.document_number,
                filename=b.filename,
                accepted_count=b.accepted_count,
                created_at=b.created_at,
            )
            for b in batches
        ],
    )


async def list_pool_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pool_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[PoolCodeRow]:
    await _get_pool_or_error(session, tenant_id, pool_id)
    stmt = (
        select(MarkingCode, MarkingCodeImport.document_number, User.email)
        .outerjoin(MarkingCodeImport, MarkingCode.import_batch_id == MarkingCodeImport.id)
        .outerjoin(User, MarkingCode.printed_by_user_id == User.id)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.pool_id == pool_id,
        )
        .order_by(MarkingCode.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(MarkingCode.status == status)
    rows: list[PoolCodeRow] = []
    for code, import_doc, printer_email in (await session.execute(stmt)).all():
        rows.append(
            PoolCodeRow(
                id=code.id,
                cis_masked=mask_cis_code(code.cis_code),
                status=code.status,
                created_at=code.created_at,
                printed_by=printer_email,
                document_number=import_doc,
            )
        )
    return rows


def _ledger_event_row(
    event: MarkingCodeEvent,
    cis: str,
    gtin: str | None,
    pool_title: str | None,
    product_name: str | None,
    product_sku: str | None,
    seller_name: str | None,
    actor_email: str | None,
    *,
    row_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
    aggregated_count: int | None = None,
) -> LedgerEventRow:
    return LedgerEventRow(
        id=row_id or event.id,
        created_at=created_at or event.created_at,
        event_type=event.event_type,
        cis_masked=None if aggregated_count is not None else mask_cis_code(cis),
        pool_title=pool_title,
        gtin=gtin,
        product_name=product_name,
        product_sku=product_sku,
        seller_name=seller_name,
        document_number=event.document_number,
        actor_email=actor_email,
        aggregated_count=aggregated_count,
    )


def _import_ledger_group_key(
    event: MarkingCodeEvent,
    import_batch_id: uuid.UUID | None,
) -> str | uuid.UUID:
    if import_batch_id is not None:
        return import_batch_id
    minute_bucket = event.created_at.replace(second=0, microsecond=0)
    return f"{event.document_number or ''}:{minute_bucket.isoformat()}"


_LedgerRawRow = tuple[
    MarkingCodeEvent,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    uuid.UUID | None,
    datetime | None,
]


def _collapse_ledger_rows(raw_rows: list[_LedgerRawRow]) -> list[LedgerEventRow]:
    non_imported: list[LedgerEventRow] = []
    import_groups: dict[
        str | uuid.UUID,
        list[
            tuple[
                MarkingCodeEvent,
                str,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                uuid.UUID | None,
                datetime | None,
            ]
        ],
    ] = {}

    for (
        event,
        cis,
        gtin,
        pool_title,
        product_name,
        product_sku,
        seller_name,
        actor_email,
        import_batch_id,
        batch_created_at,
    ) in raw_rows:
        if event.event_type != EVENT_IMPORTED:
            non_imported.append(
                _ledger_event_row(
                    event,
                    cis,
                    gtin,
                    pool_title,
                    product_name,
                    product_sku,
                    seller_name,
                    actor_email,
                )
            )
            continue
        key = _import_ledger_group_key(event, import_batch_id)
        import_groups.setdefault(key, []).append(
            (
                event,
                cis,
                gtin,
                pool_title,
                product_name,
                product_sku,
                seller_name,
                actor_email,
                import_batch_id,
                batch_created_at,
            )
        )

    collapsed_imports: list[LedgerEventRow] = []
    for group in import_groups.values():
        head = group[0]
        event = head[0]
        cis = head[1]
        gtin = head[2]
        pool_title = head[3]
        product_name = head[4]
        product_sku = head[5]
        seller_name = head[6]
        actor_email = head[7]
        import_batch_id = head[8]
        batch_created_at = head[9]
        collapsed_imports.append(
            _ledger_event_row(
                event,
                cis,
                gtin,
                pool_title,
                product_name,
                product_sku,
                seller_name,
                actor_email,
                row_id=import_batch_id or event.id,
                created_at=batch_created_at or event.created_at,
                aggregated_count=len(group),
            )
        )

    merged = non_imported + collapsed_imports
    merged.sort(key=lambda row: row.created_at, reverse=True)
    return merged


def _ledger_filtered_stmt(
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    pool_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    document_number: str | None,
    event_type: str | None,
    cis_mask: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select[Any]:
    stmt = (
        select(
            MarkingCodeEvent,
            MarkingCode.cis_code,
            MarkingCode.gtin,
            MarkingPool.title,
            Product.name,
            Product.sku_code,
            Seller.name,
            User.email,
            MarkingCode.import_batch_id,
            MarkingCodeImport.created_at,
        )
        .join(MarkingCode, MarkingCode.id == MarkingCodeEvent.code_id)
        .outerjoin(MarkingCodeImport, MarkingCode.import_batch_id == MarkingCodeImport.id)
        .outerjoin(MarkingPool, MarkingPool.id == MarkingCodeEvent.pool_id)
        .outerjoin(Product, Product.id == MarkingCode.product_id)
        .outerjoin(Seller, Seller.id == MarkingCodeEvent.seller_id)
        .outerjoin(User, User.id == MarkingCodeEvent.actor_user_id)
        .where(MarkingCodeEvent.tenant_id == tenant_id)
    )
    if seller_id is not None:
        stmt = stmt.where(MarkingCodeEvent.seller_id == seller_id)
    if pool_id is not None:
        stmt = stmt.where(MarkingCodeEvent.pool_id == pool_id)
    if product_id is not None:
        pool_for_product = select(MarkingPoolProduct.pool_id).where(
            MarkingPoolProduct.tenant_id == tenant_id,
            MarkingPoolProduct.product_id == product_id,
        )
        stmt = stmt.where(
            or_(
                MarkingCode.product_id == product_id,
                MarkingCodeEvent.pool_id.in_(pool_for_product),
            )
        )
    if document_number:
        stmt = stmt.where(MarkingCodeEvent.document_number == document_number)
    if event_type:
        stmt = stmt.where(MarkingCodeEvent.event_type == event_type)
    if cis_mask:
        needle = normalize_cis_mask_query(cis_mask)
        if needle:
            stmt = stmt.where(MarkingCode.cis_code.contains(needle))
    if date_from is not None:
        stmt = stmt.where(MarkingCodeEvent.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(MarkingCodeEvent.created_at <= date_to)
    return stmt


async def list_ledger(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    pool_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    document_number: str | None,
    event_type: str | None,
    cis_mask: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> LedgerPage:
    base_stmt = _ledger_filtered_stmt(
        tenant_id,
        seller_id=seller_id,
        pool_id=pool_id,
        product_id=product_id,
        document_number=document_number,
        event_type=event_type,
        cis_mask=cis_mask,
        date_from=date_from,
        date_to=date_to,
    )
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    raw_total = int((await session.execute(count_stmt)).scalar_one())
    if raw_total > _LEDGER_EXPORT_MAX:
        raise MarkingCodeServiceError("ledger_too_large")

    stmt = base_stmt.order_by(MarkingCodeEvent.created_at.desc())
    raw_rows = cast(list[_LedgerRawRow], list((await session.execute(stmt)).all()))
    collapsed = _collapse_ledger_rows(raw_rows)
    total = len(collapsed)
    page_rows = collapsed[offset : offset + limit]
    return LedgerPage(rows=page_rows, total=total)


async def export_ledger_csv(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    pool_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    document_number: str | None,
    event_type: str | None,
    cis_mask: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> str:
    stmt = _ledger_filtered_stmt(
        tenant_id,
        seller_id=seller_id,
        pool_id=pool_id,
        product_id=product_id,
        document_number=document_number,
        event_type=event_type,
        cis_mask=cis_mask,
        date_from=date_from,
        date_to=date_to,
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    if total > _LEDGER_EXPORT_MAX:
        raise MarkingCodeServiceError("export_too_large")

    stmt = stmt.order_by(MarkingCodeEvent.created_at.desc()).limit(_LEDGER_EXPORT_MAX)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_LEDGER_CSV_HEADER)
    for raw in (await session.execute(stmt)).all():
        (
            event,
            cis,
            gtin,
            pool_title,
            product_name,
            product_sku,
            seller_name,
            actor_email,
            _import_batch_id,
            _batch_created_at,
        ) = raw
        ledger_row = _ledger_event_row(
            event, cis, gtin, pool_title, product_name, product_sku, seller_name, actor_email
        )
        writer.writerow(
            [
                ledger_row.created_at.isoformat(),
                ledger_row.event_type,
                ledger_row.cis_masked or "",
                ledger_row.pool_title or "",
                ledger_row.gtin or "",
                ledger_row.product_name or "",
                ledger_row.product_sku or "",
                ledger_row.seller_name or "",
                ledger_row.document_number or "",
                ledger_row.actor_email or "",
            ]
        )
    return buffer.getvalue()


async def get_code_history(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code_id: uuid.UUID,
) -> list[CodeHistoryRow]:
    code = await session.get(MarkingCode, code_id)
    if code is None or code.tenant_id != tenant_id:
        raise MarkingCodeServiceError("code_not_found")
    stmt = (
        select(MarkingCodeEvent, User.email)
        .outerjoin(User, User.id == MarkingCodeEvent.actor_user_id)
        .where(
            MarkingCodeEvent.tenant_id == tenant_id,
            MarkingCodeEvent.code_id == code_id,
        )
        .order_by(MarkingCodeEvent.created_at.asc())
    )
    return [
        CodeHistoryRow(
            id=event.id,
            created_at=event.created_at,
            event_type=event.event_type,
            document_number=event.document_number,
            actor_email=actor_email,
            copies=event.copies,
            reason=event.reason,
        )
        for event, actor_email in (await session.execute(stmt)).all()
    ]


@dataclass(frozen=True)
class PrintedCodeRow:
    id: uuid.UUID
    cis_masked: str
    status: str


@dataclass(frozen=True)
class ReprintRequestRow:
    id: uuid.UUID
    code_id: uuid.UUID
    status: str
    reason: str | None
    created_at: datetime
    requested_by_email: str
    product_name: str
    product_sku: str
    cis_masked: str
    document_number: str | None
    packaging_task_id: uuid.UUID
    pool_id: uuid.UUID | None


async def list_printed_codes_for_packaging_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
) -> list[PrintedCodeRow]:
    line = await session.get(PackagingTaskLine, line_id)
    if line is None:
        raise MarkingCodeServiceError("line_not_found")
    task = await session.get(PackagingTask, line.task_id)
    if task is None or task.tenant_id != tenant_id:
        raise MarkingCodeServiceError("line_not_found")

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.packaging_task_line_id == line_id,
            MarkingCode.status == STATUS_PRINTED,
        )
        .order_by(MarkingCode.printed_at.asc(), MarkingCode.created_at.asc())
    )
    codes = list((await session.execute(stmt)).scalars().all())
    return [
        PrintedCodeRow(id=code.id, cis_masked=mask_cis_code(code.cis_code), status=code.status)
        for code in codes
    ]


async def create_defect_reprint_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code_id: uuid.UUID,
    *,
    packaging_task_line_id: uuid.UUID,
    requested_by: uuid.UUID,
    reason: str | None = None,
) -> MarkingReprintRequest:
    code = await session.get(MarkingCode, code_id)
    if code is None or code.tenant_id != tenant_id:
        raise MarkingCodeServiceError("code_not_found")
    if code.status != STATUS_PRINTED:
        raise MarkingCodeServiceError("code_not_printed")
    if code.packaging_task_line_id != packaging_task_line_id:
        raise MarkingCodeServiceError("line_mismatch")

    line = await session.get(PackagingTaskLine, packaging_task_line_id)
    if line is None:
        raise MarkingCodeServiceError("line_not_found")
    task = await session.get(PackagingTask, line.task_id)
    if task is None or task.tenant_id != tenant_id:
        raise MarkingCodeServiceError("line_not_found")

    pending_stmt = select(MarkingReprintRequest.id).where(
        MarkingReprintRequest.tenant_id == tenant_id,
        MarkingReprintRequest.code_id == code_id,
        MarkingReprintRequest.status == REPRINT_STATUS_PENDING,
    )
    if (await session.execute(pending_stmt)).scalar_one_or_none() is not None:
        raise MarkingCodeServiceError("reprint_already_pending")

    req = MarkingReprintRequest(
        tenant_id=tenant_id,
        code_id=code_id,
        packaging_task_line_id=packaging_task_line_id,
        requested_by_user_id=requested_by,
        reason=reason.strip() if reason and reason.strip() else None,
        status=REPRINT_STATUS_PENDING,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def list_pending_reprint_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[ReprintRequestRow]:
    stmt = (
        select(
            MarkingReprintRequest,
            MarkingCode.cis_code,
            MarkingCode.pool_id,
            User.email,
            Product.name,
            Product.sku_code,
            PackagingTask.id,
            PackagingTask.document_number,
        )
        .join(MarkingCode, MarkingCode.id == MarkingReprintRequest.code_id)
        .join(User, User.id == MarkingReprintRequest.requested_by_user_id)
        .join(
            PackagingTaskLine,
            PackagingTaskLine.id == MarkingReprintRequest.packaging_task_line_id,
        )
        .join(Product, Product.id == PackagingTaskLine.product_id)
        .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
        .where(
            MarkingReprintRequest.tenant_id == tenant_id,
            MarkingReprintRequest.status == REPRINT_STATUS_PENDING,
        )
        .order_by(MarkingReprintRequest.created_at.asc())
    )
    rows: list[ReprintRequestRow] = []
    for req, cis, pool_id, email, product_name, sku, task_id, doc_num in (
        await session.execute(stmt)
    ).all():
        rows.append(
            ReprintRequestRow(
                id=req.id,
                code_id=req.code_id,
                status=req.status,
                reason=req.reason,
                created_at=req.created_at,
                requested_by_email=email,
                product_name=product_name,
                product_sku=sku,
                cis_masked=mask_cis_code(cis),
                document_number=doc_num,
                packaging_task_id=task_id,
                pool_id=pool_id,
            )
        )
    return rows


async def _get_pending_reprint_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarkingReprintRequest:
    req = await session.get(MarkingReprintRequest, request_id)
    if req is None or req.tenant_id != tenant_id:
        raise MarkingCodeServiceError("reprint_request_not_found")
    if req.status != REPRINT_STATUS_PENDING:
        raise MarkingCodeServiceError("reprint_request_not_pending")
    return req


@dataclass(frozen=True)
class ReprintResolutionResult:
    request_id: uuid.UUID
    status: str
    code_id: uuid.UUID
    replacement_code_id: uuid.UUID | None = None
    cis_code: str | None = None


async def approve_reprint_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    resolved_by: uuid.UUID,
    copies: int = 1,
) -> ReprintResolutionResult:
    req = await _get_pending_reprint_request(session, tenant_id, request_id)
    code = await session.get(MarkingCode, req.code_id)
    if code is None or code.tenant_id != tenant_id:
        raise MarkingCodeServiceError("code_not_found")
    line = await session.get(PackagingTaskLine, req.packaging_task_line_id)
    if line is None:
        raise MarkingCodeServiceError("line_not_found")
    task = await session.get(PackagingTask, line.task_id)
    if task is None or task.tenant_id != tenant_id:
        raise MarkingCodeServiceError("line_not_found")

    if code.status != STATUS_PRINTED:
        raise MarkingCodeServiceError("code_not_printed")

    await record_event(
        session,
        code=code,
        event_type=EVENT_REPRINTED,
        actor=resolved_by,
        document_number=task.document_number,
        packaging_task=line,
        copies=copies,
        reason=req.reason,
    )
    now = datetime.now(UTC)
    req.status = REPRINT_STATUS_APPROVED
    req.resolved_by_user_id = resolved_by
    req.resolved_at = now
    await session.commit()
    return ReprintResolutionResult(
        request_id=req.id,
        status=req.status,
        code_id=code.id,
        cis_code=code.cis_code,
    )


async def replace_reprint_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    resolved_by: uuid.UUID,
    copies: int = 1,
) -> ReprintResolutionResult:
    req = await _get_pending_reprint_request(session, tenant_id, request_id)
    old_code = await session.get(MarkingCode, req.code_id)
    if old_code is None or old_code.tenant_id != tenant_id:
        raise MarkingCodeServiceError("code_not_found")
    if old_code.status != STATUS_PRINTED:
        raise MarkingCodeServiceError("code_not_printed")
    line = await session.get(PackagingTaskLine, req.packaging_task_line_id)
    if line is None:
        raise MarkingCodeServiceError("line_not_found")
    task = await session.get(PackagingTask, line.task_id)
    if task is None or task.tenant_id != tenant_id:
        raise MarkingCodeServiceError("line_not_found")
    product = await get_product(session, tenant_id, line.product_id)
    if product is None:
        raise MarkingCodeServiceError("product_not_found")

    pool_ids = await _pool_ids_for_product(session, tenant_id, product.id)
    if old_code.pool_id is not None:
        pool_filter = MarkingCode.pool_id == old_code.pool_id
    elif pool_ids:
        pool_filter = MarkingCode.pool_id.in_(pool_ids)
    else:
        pool_filter = MarkingCode.product_id == product.id

    new_stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            MarkingCode.status == STATUS_AVAILABLE,
            pool_filter,
        )
        .order_by(MarkingCode.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    new_code = (await session.execute(new_stmt)).scalar_one_or_none()
    if new_code is None:
        raise MarkingCodeServiceError("no_replacement_code")

    now = datetime.now(UTC)
    old_code.status = STATUS_DEFECTIVE
    old_code.defective_reason = req.reason
    await record_event(
        session,
        code=old_code,
        event_type=EVENT_DEFECTIVE,
        actor=resolved_by,
        document_number=task.document_number,
        packaging_task=line,
        reason=req.reason,
    )

    new_code.status = STATUS_PRINTED
    new_code.product_id = product.id
    new_code.packaging_task_line_id = line.id
    new_code.printed_at = now
    new_code.printed_by_user_id = resolved_by
    old_code.replaced_by_code_id = new_code.id

    await record_event(
        session,
        code=old_code,
        event_type=EVENT_REPLACED,
        actor=resolved_by,
        document_number=task.document_number,
        packaging_task=line,
        reason=req.reason,
    )
    old_code.status = STATUS_REPLACED
    await record_event(
        session,
        code=new_code,
        event_type=EVENT_PRINTED,
        actor=resolved_by,
        document_number=task.document_number,
        packaging_task=line,
        copies=copies,
    )

    req.status = REPRINT_STATUS_APPROVED
    req.resolved_by_user_id = resolved_by
    req.resolved_at = now
    await session.commit()
    return ReprintResolutionResult(
        request_id=req.id,
        status=req.status,
        code_id=old_code.id,
        replacement_code_id=new_code.id,
        cis_code=new_code.cis_code,
    )


async def reject_reprint_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    resolved_by: uuid.UUID,
    reject_reason: str | None = None,
) -> ReprintResolutionResult:
    req = await _get_pending_reprint_request(session, tenant_id, request_id)
    req.status = REPRINT_STATUS_REJECTED
    req.resolved_by_user_id = resolved_by
    req.resolved_at = datetime.now(UTC)
    if reject_reason and reject_reason.strip():
        req.reason = reject_reason.strip()
    await session.commit()
    return ReprintResolutionResult(
        request_id=req.id,
        status=req.status,
        code_id=req.code_id,
    )


@dataclass(frozen=True)
class VerifyPairResult:
    match: bool
    applied: bool
    code_id: uuid.UUID | None = None


async def verify_pair_and_apply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cis_a: str,
    cis_b: str,
    acting_user_id: uuid.UUID,
) -> VerifyPairResult:
    norm_a = normalize_cis(cis_a)
    norm_b = normalize_cis(cis_b)
    if norm_a is None or norm_b is None:
        raise MarkingCodeServiceError("invalid_cis")

    if norm_a != norm_b:
        return VerifyPairResult(match=False, applied=False)

    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.cis_code == norm_a,
        )
        .with_for_update()
    )
    code = (await session.execute(stmt)).scalar_one_or_none()
    if code is None:
        return VerifyPairResult(match=True, applied=False)

    if code.status == STATUS_APPLIED:
        return VerifyPairResult(match=True, applied=False, code_id=code.id)

    if code.status != STATUS_PRINTED:
        return VerifyPairResult(match=True, applied=False, code_id=code.id)

    now = datetime.now(UTC)
    code.status = STATUS_APPLIED
    code.applied_at = now

    line: PackagingTaskLine | None = None
    document_number: str | None = None
    if code.packaging_task_line_id is not None:
        line = await session.get(PackagingTaskLine, code.packaging_task_line_id)
        if line is not None:
            task = await session.get(PackagingTask, line.task_id)
            if task is not None:
                document_number = task.document_number

    await record_event(
        session,
        code=code,
        event_type=EVENT_APPLIED,
        actor=acting_user_id,
        document_number=document_number,
        packaging_task=line,
    )
    await session.commit()
    return VerifyPairResult(match=True, applied=True, code_id=code.id)


@dataclass(frozen=True)
class PendingMarkingRow:
    packaging_task_id: uuid.UUID
    packaging_task_line_id: uuid.UUID
    document_number: str | None
    warehouse_id: uuid.UUID
    seller_id: uuid.UUID | None
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    storage_location_code: str
    qty_need: int
    qty_marking_printed: int
    qty_remaining: int
    marking_available_count: int


async def list_pending_marking_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PendingMarkingRow], int]:
    from app.services.packaging_task_service import qty_need_pack

    qty_need_expr = PackagingTaskLine.qty_total - PackagingTaskLine.qty_confirmed_packed
    base_filters = [
        PackagingTask.tenant_id == tenant_id,
        PackagingTask.status.in_(("draft", "in_progress")),
        Product.requires_honest_sign.is_(True),
        qty_need_expr > 0,
        PackagingTaskLine.qty_marking_printed < qty_need_expr,
    ]
    if warehouse_id is not None:
        base_filters.append(PackagingTask.warehouse_id == warehouse_id)
    if seller_id is not None:
        base_filters.append(Product.seller_id == seller_id)

    count_stmt = (
        select(func.count(PackagingTaskLine.id))
        .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
        .join(Product, Product.id == PackagingTaskLine.product_id)
        .where(*base_filters)
    )
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = (
        select(PackagingTaskLine, PackagingTask, Product, StorageLocation)
        .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
        .join(Product, Product.id == PackagingTaskLine.product_id)
        .join(StorageLocation, StorageLocation.id == PackagingTaskLine.storage_location_id)
        .where(*base_filters)
        .order_by(PackagingTask.created_at.asc(), PackagingTaskLine.id.asc())
        .limit(limit)
        .offset(offset)
    )
    page_rows = (await session.execute(stmt)).all()
    product_ids = {product.id for _line, _task, product, _loc in page_rows}
    available_by_product = await count_available_for_products_batch(
        session,
        tenant_id,
        product_ids,
    )

    rows: list[PendingMarkingRow] = []
    for line, task, product, loc in page_rows:
        qty_need = qty_need_pack(line)
        printed = int(line.qty_marking_printed)
        rows.append(
            PendingMarkingRow(
                packaging_task_id=task.id,
                packaging_task_line_id=line.id,
                document_number=task.document_number,
                warehouse_id=task.warehouse_id,
                seller_id=product.seller_id,
                product_id=product.id,
                sku_code=product.sku_code,
                product_name=product.name,
                storage_location_code=loc.code,
                qty_need=qty_need,
                qty_marking_printed=printed,
                qty_remaining=qty_need - printed,
                marking_available_count=available_by_product.get(product.id, 0),
            )
        )
    return rows, total
