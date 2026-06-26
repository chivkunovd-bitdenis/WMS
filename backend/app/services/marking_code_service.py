from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marking_code import (
    EVENT_IMPORTED,
    EVENT_PRINTED,
    EVENT_REPRINTED,
    STATUS_AVAILABLE,
    STATUS_DEFECTIVE,
    STATUS_PRINTED,
    STATUS_RESERVED,
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.user import User
from app.services.catalog_service import get_product
from app.services.document_number_service import (
    DOC_TYPE_MARKING_IMPORT,
    assign_document_number_if_missing,
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


@dataclass(frozen=True)
class PoolProductRow:
    id: uuid.UUID
    sku_code: str
    name: str


@dataclass(frozen=True)
class PoolProductsResult:
    pool_id: uuid.UUID
    products: list[PoolProductRow]


@dataclass(frozen=True)
class PoolListRow:
    id: uuid.UUID
    title: str
    gtin: str
    products: list[PoolProductRow]
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None


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
    title: str
    gtin: str
    products: list[PoolProductRow]
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None
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
    cis_masked: str
    pool_title: str | None
    gtin: str | None
    product_name: str | None
    product_sku: str | None
    seller_name: str | None
    document_number: str | None
    actor_email: str | None


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
        MarkingCode.pool_id.is_(None),
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


def _group_cis_codes_from_rows(
    parsed_rows: list[dict[str, str]],
) -> tuple[dict[str, list[str]], int, int]:
    seen_in_upload: set[str] = set()
    by_gtin: dict[str, list[str]] = {}
    invalid_count = 0
    duplicate_count = 0
    for row in parsed_rows:
        cis = normalize_cis(row.get("cis", ""))
        if cis is None:
            invalid_count += 1
            continue
        if cis in seen_in_upload:
            duplicate_count += 1
            continue
        seen_in_upload.add(cis)
        gtin = (row.get("gtin") or "").strip() or extract_gtin_from_cis(cis)
        if not gtin:
            invalid_count += 1
            continue
        by_gtin.setdefault(gtin, []).append(cis)
    return by_gtin, invalid_count, duplicate_count


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

    parsed_rows: list[dict[str, str]] = []
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

    by_gtin, invalid_count, duplicates_in_file = _group_cis_codes_from_rows(parsed_rows)
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

    parsed_rows: list[dict[str, str]] = []
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

    by_gtin, invalid_count, duplicate_count = _group_cis_codes_from_rows(parsed_rows)

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
            existing = await session.execute(
                select(MarkingCode.id).where(
                    MarkingCode.tenant_id == tenant_id,
                    MarkingCode.cis_code == cis,
                )
            )
            if existing.scalar_one_or_none() is not None:
                pool_duplicates += 1
                continue
            code = MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
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
    if seller_id is not None:
        await relink_unlinked_marking_codes(session, tenant_id, seller_id)

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
    for pool_id, product_id in pool_links:
        if pool_id in available_by_pool:
            available_by_product[product_id] = (
                available_by_product.get(product_id, 0) + available_by_pool[pool_id]
            )
        if pool_id in printed_by_pool:
            printed_by_product[product_id] = (
                printed_by_product.get(product_id, 0) + printed_by_pool[pool_id]
            )

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
    product = await get_product(session, tenant_id, product_id)
    if product is None:
        return 0
    pool_ids = await _pool_ids_for_product(session, tenant_id, product_id)
    filters = [MarkingCode.product_id == product_id]
    if pool_ids:
        filters.append(MarkingCode.pool_id.in_(pool_ids))
    stmt = select(func.count(MarkingCode.id)).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.seller_id == product.seller_id,
        MarkingCode.status == STATUS_AVAILABLE,
        or_(*filters),
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

    pool_ids = await _pool_ids_for_product(session, tenant_id, product.id)
    code_filters = [MarkingCode.product_id == product.id]
    if pool_ids:
        code_filters.append(MarkingCode.pool_id.in_(pool_ids))
    stmt = (
        select(MarkingCode)
        .where(
            MarkingCode.tenant_id == tenant_id,
            MarkingCode.seller_id == product.seller_id,
            MarkingCode.status == STATUS_AVAILABLE,
            or_(*code_filters),
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
    rows: list[PoolListRow] = []
    for pool in pools:
        pool_counts = counts.get(pool.id, {})
        rows.append(
            PoolListRow(
                id=pool.id,
                title=pool.title,
                gtin=pool.gtin,
                products=products_map.get(pool.id, []),
                available=_status_count(pool_counts, STATUS_AVAILABLE),
                reserved=_status_count(pool_counts, STATUS_RESERVED),
                printed=_status_count(pool_counts, STATUS_PRINTED),
                defective=_status_count(pool_counts, STATUS_DEFECTIVE),
                forecast_days=None,
                low_stock_threshold=pool.low_stock_threshold,
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
    products_map = await _products_by_pool(session, tenant_id, [pool_id])

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

    return PoolDetailRow(
        id=pool.id,
        title=pool.title,
        gtin=pool.gtin,
        products=products_map.get(pool_id, []),
        available=_status_count(pool_counts, STATUS_AVAILABLE),
        reserved=_status_count(pool_counts, STATUS_RESERVED),
        printed=_status_count(pool_counts, STATUS_PRINTED),
        defective=_status_count(pool_counts, STATUS_DEFECTIVE),
        forecast_days=None,
        low_stock_threshold=pool.low_stock_threshold,
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


async def list_ledger(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    pool_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    document_number: str | None,
    event_type: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> LedgerPage:
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
        )
        .join(MarkingCode, MarkingCode.id == MarkingCodeEvent.code_id)
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
    if date_from is not None:
        stmt = stmt.where(MarkingCodeEvent.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(MarkingCodeEvent.created_at <= date_to)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = stmt.order_by(MarkingCodeEvent.created_at.desc()).limit(limit).offset(offset)
    rows: list[LedgerEventRow] = []
    for event, cis, gtin, pool_title, product_name, product_sku, seller_name, actor_email in (
        await session.execute(stmt)
    ).all():
        rows.append(
            LedgerEventRow(
                id=event.id,
                created_at=event.created_at,
                event_type=event.event_type,
                cis_masked=mask_cis_code(cis),
                pool_title=pool_title,
                gtin=gtin,
                product_name=product_name,
                product_sku=product_sku,
                seller_name=seller_name,
                document_number=event.document_number,
                actor_email=actor_email,
            )
        )
    return LedgerPage(rows=rows, total=total)


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
