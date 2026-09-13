"""Sorting labels use the WMS-402 BackgroundJob delivery mechanism."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.print_connection import PrintConnection
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.storage_location import StorageLocation
from app.services.fbs_print_asset_service import FbsPrintAssetError
from app.services.fbs_print_asset_storage import (
    PDF_CONTENT_TYPE,
    operator_document_relative_path,
    save_print_file,
    sha256_checksum,
)
from app.services.fbs_print_job_service import JOB_TYPE_FBS_LABEL_PRINT


def label_pdf(barcode: str, title: str, subtitle: str) -> bytes:
    """58 x 40 mm, Code128 with quiet zones; fit text without clipping the code."""
    import fitz
    import zxingcpp

    if not barcode or not barcode.isascii() or not barcode.isprintable():
        raise FbsPrintAssetError("barcode_missing", message="Нет пригодного штрихкода для печати.")
    code = zxingcpp.create_barcode(barcode, zxingcpp.BarcodeFormat.Code128)
    svg = zxingcpp.write_barcode_to_svg(code, add_quiet_zones=True)
    with fitz.open(stream=svg.encode(), filetype="svg") as graphic:
        drawing = graphic.convert_to_pdf()
    with fitz.open() as pdf, fitz.open(stream=drawing, filetype="pdf") as graphic_pdf:
        page = pdf.new_page(width=58 * 72 / 25.4, height=40 * 72 / 25.4)
        # The standard WMS label uses 58x40 mm. The barcode keeps its entire
        # width, with a white margin; longer labels never crop bars.
        page.show_pdf_page(
            fitz.Rect(5, 34, page.rect.width - 5, 80), graphic_pdf, 0, keep_proportion=False
        )
        page.insert_font(fontname="wms", fontbuffer=fitz.Font("cyrillic").buffer)
        for text, rect, size in (
            (title, fitz.Rect(5, 3, page.rect.width - 5, 31), 9),
            (barcode, fitz.Rect(5, 82, page.rect.width - 5, 95), 8),
            (subtitle, fitz.Rect(5, 97, page.rect.width - 5, 111), 7),
        ):
            while size > 3:
                shape = page.new_shape()
                if shape.insert_textbox(rect, text, fontsize=size, fontname="wms", align=1) >= 0:
                    shape.commit()
                    break
                size -= 0.5
        return bytes(pdf.tobytes(no_new_id=True))


async def resolve_label(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    kind: str,
    object_id: uuid.UUID,
    marketplace: str | None,
) -> tuple[InboundIntakeRequest, str, str, str]:
    request = await session.get(InboundIntakeRequest, request_id)
    if request is None or request.tenant_id != tenant_id:
        raise FbsPrintAssetError("supply_not_found", message="Документ сортировки не найден.")
    if kind == "location":
        location = await session.get(StorageLocation, object_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.warehouse_id != request.warehouse_id
            or location.deleted_at is not None
        ):
            raise FbsPrintAssetError("asset_not_found", message="Ячейка этого склада не найдена.")
        return request, location.barcode, location.code, "Ячейка"
    product = await session.scalar(
        select(Product)
        .join(InboundIntakeLine, InboundIntakeLine.product_id == Product.id)
        .where(
            InboundIntakeLine.request_id == request.id,
            Product.id == object_id,
            Product.tenant_id == tenant_id,
        )
    )
    if product is None or (request.seller_id and product.seller_id != request.seller_id):
        raise FbsPrintAssetError("asset_not_found", message="Товар документа не найден.")
    provider = marketplace or request.marketplace
    if provider not in {"wb", "ozon"}:
        raise FbsPrintAssetError(
            "marketplace_required", message="Выберите WB или Ozon для этикетки."
        )
    link = await session.scalar(
        select(ProductMarketplaceLink).where(
            ProductMarketplaceLink.tenant_id == tenant_id,
            ProductMarketplaceLink.product_id == product.id,
            ProductMarketplaceLink.seller_id == product.seller_id,
            ProductMarketplaceLink.marketplace == provider,
            ProductMarketplaceLink.is_active.is_(True),
        )
    )
    if provider == "ozon":
        barcode = next((str(x).strip() for x in (link.external_barcodes if link else []) if x), "")
    else:
        barcode = (product.wb_barcode or "").strip()
    return request, barcode, product.name, f"{provider.upper()} · {product.sku_code}"


async def create_sorting_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    job_id: uuid.UUID,
    kind: str,
    object_id: uuid.UUID,
    marketplace: str | None,
    copies: int,
    connection_id: uuid.UUID,
) -> BackgroundJob:
    intent: dict[str, Any] = {
        "request_id": str(request_id),
        "kind": kind,
        "object_id": str(object_id),
        "marketplace": marketplace,
        "copies": copies,
        "connection_id": str(connection_id),
        "requested_by_user_id": str(user_id),
    }
    # Serialize by UUID before reading or rendering, including across processes.
    # PostgreSQL transaction lock needs no lock table or attempt journal.
    from sqlalchemy import text

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": job_id.int % (2**63 - 1)}
        )
    existing = await session.get(BackgroundJob, job_id)
    if existing is not None:
        if (
            existing.tenant_id != tenant_id
            or existing.job_type != JOB_TYPE_FBS_LABEL_PRINT
            or (existing.payload_json or {}).get("intent") != intent
        ):
            raise FbsPrintAssetError(
                "print_job_conflict", message="Номер печати занят другим заданием."
            )
        return existing
    request, barcode, title, subtitle = await resolve_label(
        session, tenant_id, request_id, kind=kind, object_id=object_id, marketplace=marketplace
    )
    connection = await session.get(PrintConnection, connection_id)
    if (
        connection is None
        or connection.tenant_id != tenant_id
        or connection.warehouse_id != request.warehouse_id
        or not connection.is_default
    ):
        raise FbsPrintAssetError("print_job_conflict", message="Назначение принтера изменилось.")
    document = label_pdf(barcode, title, subtitle)
    checksum = sha256_checksum(document)
    path = save_print_file(
        operator_document_relative_path(job_id), document, content_type=PDF_CONTENT_TYPE
    )
    job = BackgroundJob(
        id=job_id,
        tenant_id=tenant_id,
        job_type=JOB_TYPE_FBS_LABEL_PRINT,
        status="pending",
        payload_json={
            "intent": intent,
            "request_id": str(request_id),
            "warehouse_id": str(request.warehouse_id),
            "connection_id": str(connection.id),
            "queue_name": connection.queue_name,
            "copies": copies,
            "barcode": barcode,
            "label_title": title,
            "label_subtitle": subtitle,
            "storage_path": path,
            "asset_id": str(job_id),
            "asset_kind": "sorting_label",
            "content_type": PDF_CONTENT_TYPE,
            "checksum": checksum,
            "content_bytes": len(document),
            "width_mm": 58,
            "height_mm": 40,
            "requested_by_user_id": str(user_id),
        },
    )
    session.add(job)
    await session.flush()
    return job
