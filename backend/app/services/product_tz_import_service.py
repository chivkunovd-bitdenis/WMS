# ruff: noqa: RUF001
"""Parse FF TZ template xlsx and create/update catalog products."""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.seller import Seller
from app.services.catalog_service import CatalogError, create_product, update_packaging_instructions
from app.services.wb_card_enrichment import WbSizeVariant, sku_code_for_wb_variant

TZ_SHEET_PREFIX = "ТЗ Шаблон"
_BARCODE_RE = re.compile(r"^\d{8,32}$")

HEADER_ALIASES: dict[str, str] = {
    "артикул продавца": "vendor_article",
    "размер": "size",
    "штрихкод": "barcode",
    "информация для этикетки": "label_barcode",
    "пожелания/инструкция по обработке, упаковке и фасовке": "tz",
    "пожелания/инструкция по обработке упаковке и фасовке": "tz",
}

_EXPAND_FIELDS = ("vendor_article", "size", "barcode", "label_barcode", "tz")


class ProductTzImportError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass(frozen=True)
class ProductTzRowError:
    row: int
    barcode: str | None
    code: str
    message: str


@dataclass(frozen=True)
class ProductTzRowPreview:
    row: int
    vendor_article: str | None
    size: str | None
    barcode: str | None
    name: str
    sku_code: str
    packaging_instructions: str | None
    action: Literal["create", "update", "skip", "error"]
    product_id: uuid.UUID | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class ProductTzPreviewSummary:
    total: int
    create_count: int
    update_count: int
    skip_count: int
    error_count: int


@dataclass(frozen=True)
class ProductTzPreviewResult:
    rows: tuple[ProductTzRowPreview, ...]
    errors: tuple[ProductTzRowError, ...]
    summary: ProductTzPreviewSummary
    sheet_name: str


@dataclass(frozen=True)
class ProductTzApplyResult:
    created_count: int
    updated_count: int
    skipped_count: int
    product_ids: tuple[uuid.UUID, ...]
    summary: ProductTzPreviewSummary
    errors: tuple[ProductTzRowError, ...]


def _norm_header(value: object) -> str:
    text = str(value or "").strip().lower().replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def _cell_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text or text.startswith("="):
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _as_barcode(value: object) -> str | None:
    text = _cell_str(value)
    if text is None:
        return None
    compact = re.sub(r"\s+", "", text)
    if _BARCODE_RE.match(compact):
        return compact
    return None


def _pick_tz_sheet(sheetnames: list[str]) -> str:
    for name in sheetnames:
        if name.strip().startswith(TZ_SHEET_PREFIX):
            return name
    raise ProductTzImportError(
        "missing_sheet",
        f"Не найден лист, имя которого начинается с «{TZ_SHEET_PREFIX}».",
    )


def _find_header_row(ws: Worksheet) -> tuple[int, dict[str, int]]:
    max_scan = min(ws.max_row or 1, 30)
    for r in range(1, max_scan + 1):
        mapping: dict[str, int] = {}
        for c in range(1, (ws.max_column or 1) + 1):
            key = HEADER_ALIASES.get(_norm_header(ws.cell(r, c).value))
            if key and key not in mapping:
                mapping[key] = c
        if "vendor_article" in mapping and ("barcode" in mapping or "label_barcode" in mapping):
            return r, mapping
    raise ProductTzImportError(
        "missing_column",
        "В файле нет обязательных колонок: «Артикул продавца» и штрихкод/этикетка.",
    )


def _merged_values_by_row(
    ws: Worksheet, col: int, header_row: int
) -> dict[int, str]:
    """Expand Excel merged cells for one column onto every covered data row."""
    out: dict[int, str] = {}
    covered: set[int] = set()
    for mr in ws.merged_cells.ranges:
        if not (mr.min_col <= col <= mr.max_col):
            continue
        text = _cell_str(ws.cell(mr.min_row, col).value)
        if not text:
            continue
        for r in range(mr.min_row, mr.max_row + 1):
            if r <= header_row:
                continue
            out[r] = text
            covered.add(r)
    max_row = ws.max_row or header_row
    for r in range(header_row + 1, max_row + 1):
        if r in covered:
            continue
        text = _cell_str(ws.cell(r, col).value)
        if text:
            out[r] = text
    return out


def _resolve_barcode(*, barcode_raw: str | None, label_raw: str | None) -> str | None:
    """Prefer «Штрихкод», then digit-looking «Информация для этикетки»."""
    for candidate in (barcode_raw, label_raw):
        parsed = _as_barcode(candidate)
        if parsed:
            return parsed
    return None


def _sku_for_row(*, vendor: str, size: str | None, barcode: str) -> str:
    variant = WbSizeVariant(chrt_id=None, size_label=size, barcode=barcode)
    return sku_code_for_wb_variant(vendor, None, variant, multi_variant=True)


def _display_name(vendor: str, size: str | None) -> str:
    if size:
        return f"{vendor} {size}"[:255]
    return vendor[:255]


def parse_product_tz_xlsx(content: bytes, *, filename: str) -> tuple[str, list[dict[str, Any]]]:
    lower = filename.lower()
    if not lower.endswith(".xlsx"):
        raise ProductTzImportError(
            "unsupported_file_type",
            "Поддерживаются только файлы Excel (.xlsx).",
        )
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise ProductTzImportError(
            "unsupported_file_type", "Не удалось прочитать Excel."
        ) from exc

    try:
        sheet_name = _pick_tz_sheet(list(wb.sheetnames))
        ws = wb[sheet_name]
        header_row, cols = _find_header_row(ws)
        expanded: dict[str, dict[int, str]] = {}
        for field in _EXPAND_FIELDS:
            col = cols.get(field)
            if col is not None:
                expanded[field] = _merged_values_by_row(ws, col, header_row)

        rows: list[dict[str, Any]] = []
        max_row = ws.max_row or header_row
        for r in range(header_row + 1, max_row + 1):
            vendor = expanded.get("vendor_article", {}).get(r)
            size = expanded.get("size", {}).get(r)
            barcode_raw = expanded.get("barcode", {}).get(r)
            label_raw = expanded.get("label_barcode", {}).get(r)
            tz = expanded.get("tz", {}).get(r)
            # Skip completely empty trailing rows.
            if not any((vendor, size, barcode_raw, label_raw, tz)):
                continue
            barcode = _resolve_barcode(barcode_raw=barcode_raw, label_raw=label_raw)
            rows.append(
                {
                    "row": r,
                    "vendor_article": vendor,
                    "size": size,
                    "barcode": barcode,
                    "packaging_instructions": tz,
                }
            )
        if not rows:
            raise ProductTzImportError(
                "empty_file", "Файл пустой — нет строк с артикулами."
            )
        return sheet_name, rows
    finally:
        wb.close()


async def _find_by_barcode_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    barcode: str,
) -> Product | None:
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.seller_id == seller_id,
        Product.wb_barcode == barcode,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _find_by_barcode_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    barcode: str,
) -> Product | None:
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.wb_barcode == barcode,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _find_by_sku(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sku_code: str,
) -> Product | None:
    stmt = select(Product).where(
        Product.tenant_id == tenant_id, Product.sku_code == sku_code
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


def _error_preview(
    *,
    row_no: int,
    vendor: str | None,
    size: str | None,
    barcode: str | None,
    name: str,
    sku: str,
    tz: str | None,
    code: str,
    msg: str,
) -> ProductTzRowPreview:
    return ProductTzRowPreview(
        row=row_no,
        vendor_article=vendor,
        size=size,
        barcode=barcode,
        name=name,
        sku_code=sku,
        packaging_instructions=tz,
        action="error",
        product_id=None,
        error_code=code,
        error_message=msg,
    )


async def build_product_tz_preview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID,
    content: bytes,
    filename: str,
) -> ProductTzPreviewResult:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        raise ProductTzImportError("seller_not_found", "Селлер не найден.")

    sheet_name, raw_rows = parse_product_tz_xlsx(content, filename=filename)
    previews: list[ProductTzRowPreview] = []
    errors: list[ProductTzRowError] = []
    create_count = update_count = skip_count = error_count = 0
    seen_barcodes: set[str] = set()

    for raw in raw_rows:
        row_no = int(raw["row"])
        vendor = raw["vendor_article"] if isinstance(raw["vendor_article"], str) else None
        size = raw["size"] if isinstance(raw["size"], str) else None
        barcode = raw["barcode"] if isinstance(raw["barcode"], str) else None
        raw_tz = raw["packaging_instructions"]
        tz = raw_tz if isinstance(raw_tz, str) else None
        name = _display_name(vendor or "Товар", size)

        if not vendor:
            error_count += 1
            msg = "Нет артикула продавца (проверьте объединённые ячейки)."
            errors.append(
                ProductTzRowError(row=row_no, barcode=barcode, code="missing_vendor", message=msg)
            )
            previews.append(
                _error_preview(
                    row_no=row_no,
                    vendor=vendor,
                    size=size,
                    barcode=barcode,
                    name=name,
                    sku="",
                    tz=tz,
                    code="missing_vendor",
                    msg=msg,
                )
            )
            continue

        if not barcode:
            error_count += 1
            msg = "Нет штрихкода (нужны цифры в «Штрихкод» или «Информация для этикетки»)."
            errors.append(
                ProductTzRowError(
                    row=row_no, barcode=None, code="missing_barcode", message=msg
                )
            )
            previews.append(
                _error_preview(
                    row_no=row_no,
                    vendor=vendor,
                    size=size,
                    barcode=None,
                    name=name,
                    sku="",
                    tz=tz,
                    code="missing_barcode",
                    msg=msg,
                )
            )
            continue

        if barcode in seen_barcodes:
            error_count += 1
            msg = "Дубликат штрихкода в файле."
            errors.append(
                ProductTzRowError(
                    row=row_no,
                    barcode=barcode,
                    code="duplicate_barcode_in_file",
                    message=msg,
                )
            )
            previews.append(
                _error_preview(
                    row_no=row_no,
                    vendor=vendor,
                    size=size,
                    barcode=barcode,
                    name=name,
                    sku="",
                    tz=tz,
                    code="duplicate_barcode_in_file",
                    msg=msg,
                )
            )
            continue
        seen_barcodes.add(barcode)

        sku = _sku_for_row(vendor=vendor, size=size, barcode=barcode)
        existing = await _find_by_barcode_seller(session, tenant_id, seller_id, barcode)
        if existing is not None:
            update_count += 1
            previews.append(
                ProductTzRowPreview(
                    row=row_no,
                    vendor_article=vendor,
                    size=size,
                    barcode=barcode,
                    name=existing.name,
                    sku_code=existing.sku_code,
                    packaging_instructions=tz,
                    action="update",
                    product_id=existing.id,
                    error_code=None,
                    error_message=None,
                )
            )
            continue

        other = await _find_by_barcode_tenant(session, tenant_id, barcode)
        if other is not None:
            error_count += 1
            msg = "Штрихкод уже занят другим селлером в этом ФФ."
            errors.append(
                ProductTzRowError(
                    row=row_no,
                    barcode=barcode,
                    code="barcode_taken_other_seller",
                    message=msg,
                )
            )
            previews.append(
                _error_preview(
                    row_no=row_no,
                    vendor=vendor,
                    size=size,
                    barcode=barcode,
                    name=name,
                    sku=sku,
                    tz=tz,
                    code="barcode_taken_other_seller",
                    msg=msg,
                )
            )
            continue

        by_sku = await _find_by_sku(session, tenant_id, sku)
        if by_sku is not None and (by_sku.wb_barcode or "").strip() != barcode:
            sku_alt = _sku_for_row(vendor=vendor, size=None, barcode=barcode)
            by_sku_alt = await _find_by_sku(session, tenant_id, sku_alt)
            if by_sku_alt is not None and (by_sku_alt.wb_barcode or "").strip() != barcode:
                error_count += 1
                msg = "Артикул уже занят другим товаром."
                errors.append(
                    ProductTzRowError(
                        row=row_no, barcode=barcode, code="sku_taken", message=msg
                    )
                )
                previews.append(
                    _error_preview(
                        row_no=row_no,
                        vendor=vendor,
                        size=size,
                        barcode=barcode,
                        name=name,
                        sku=sku,
                        tz=tz,
                        code="sku_taken",
                        msg=msg,
                    )
                )
                continue
            sku = sku_alt

        create_count += 1
        previews.append(
            ProductTzRowPreview(
                row=row_no,
                vendor_article=vendor,
                size=size,
                barcode=barcode,
                name=name,
                sku_code=sku,
                packaging_instructions=tz,
                action="create",
                product_id=None,
                error_code=None,
                error_message=None,
            )
        )

    summary = ProductTzPreviewSummary(
        total=len(previews),
        create_count=create_count,
        update_count=update_count,
        skip_count=skip_count,
        error_count=error_count,
    )
    return ProductTzPreviewResult(
        rows=tuple(previews),
        errors=tuple(errors),
        summary=summary,
        sheet_name=sheet_name,
    )


async def apply_product_tz_import(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID,
    content: bytes,
    filename: str,
    ignore_errors: bool = False,
) -> ProductTzApplyResult:
    preview = await build_product_tz_preview(
        session,
        tenant_id,
        seller_id=seller_id,
        content=content,
        filename=filename,
    )
    if preview.summary.error_count and not ignore_errors:
        raise ProductTzImportError(
            "row_errors",
            f"В файле есть ошибки строк ({preview.summary.error_count}).",
        )

    created = 0
    updated = 0
    skipped = 0
    product_ids: list[uuid.UUID] = []

    try:
        for row in preview.rows:
            if row.action == "error":
                skipped += 1
                continue
            if row.action == "update":
                assert row.product_id is not None
                async with session.begin_nested():
                    existing = await session.get(Product, row.product_id)
                    if existing is None:
                        skipped += 1
                        continue
                    if row.size:
                        existing.wb_size = row.size
                    if row.vendor_article:
                        existing.wb_vendor_code = row.vendor_article
                    if row.packaging_instructions is not None:
                        await update_packaging_instructions(
                            session,
                            tenant_id,
                            existing.id,
                            packaging_instructions=row.packaging_instructions,
                            commit=False,
                        )
                    else:
                        await session.flush()
                    product_ids.append(existing.id)
                    updated += 1
                continue
            if row.action == "create":
                if not row.barcode:
                    skipped += 1
                    continue
                try:
                    async with session.begin_nested():
                        p = await create_product(
                            session,
                            tenant_id,
                            name=row.name,
                            sku_code=row.sku_code,
                            length_mm=None,
                            width_mm=None,
                            height_mm=None,
                            seller_id=seller_id,
                            wb_barcode=row.barcode,
                            wb_size=row.size,
                            wb_vendor_code=row.vendor_article,
                            packaging_instructions=row.packaging_instructions,
                            commit=False,
                        )
                        product_ids.append(p.id)
                        created += 1
                except IntegrityError as exc:
                    err = str(getattr(exc, "orig", exc)).lower()
                    code = (
                        "barcode_taken"
                        if "wb_barcode" in err or "uq_products_tenant_wb_barcode" in err
                        else "sku_taken"
                    )
                    if ignore_errors:
                        skipped += 1
                        continue
                    raise ProductTzImportError(
                        code, "Конфликт уникальности при создании."
                    ) from exc
                except CatalogError as exc:
                    if ignore_errors and exc.code in {
                        "sku_taken",
                        "barcode_taken",
                    }:
                        skipped += 1
                        continue
                    raise ProductTzImportError(exc.code, str(exc)) from exc
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return ProductTzApplyResult(
        created_count=created,
        updated_count=updated,
        skipped_count=skipped,
        product_ids=tuple(product_ids),
        summary=preview.summary,
        errors=preview.errors,
    )
