from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_barcode import ProductBarcode


@dataclass(frozen=True)
class BarcodeWriteResult:
    added: int
    existing: int
    conflicts: tuple[tuple[str, uuid.UUID], ...]


def normalize_barcodes(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            normalized
            for value in values
            if isinstance(value, str)
            and (normalized := value.strip())
            and len(normalized) <= 64
        )
    )


async def add_barcodes_to_product(
    session: AsyncSession,
    product: Product,
    barcodes: tuple[str, ...],
) -> BarcodeWriteResult:
    """Stage new aliases without committing; any ownership conflict stages nothing."""
    if product.seller_id is None:
        raise ValueError("product_seller_required")
    normalized = normalize_barcodes(barcodes)
    if not normalized:
        return BarcodeWriteResult(added=0, existing=0, conflicts=())

    rows = list(
        (
            await session.execute(
                select(ProductBarcode).where(
                    ProductBarcode.tenant_id == product.tenant_id,
                    ProductBarcode.seller_id == product.seller_id,
                    ProductBarcode.barcode.in_(normalized),
                )
            )
        )
        .scalars()
        .all()
    )
    conflicts = tuple(
        (row.barcode, row.product_id) for row in rows if row.product_id != product.id
    )
    if conflicts:
        return BarcodeWriteResult(added=0, existing=0, conflicts=conflicts)

    present = {row.barcode for row in rows}
    missing = [barcode for barcode in normalized if barcode not in present]
    session.add_all(
        ProductBarcode(
            tenant_id=product.tenant_id,
            seller_id=product.seller_id,
            product_id=product.id,
            barcode=barcode,
            source="wb",
        )
        for barcode in missing
    )
    return BarcodeWriteResult(
        added=len(missing),
        existing=len(normalized) - len(missing),
        conflicts=(),
    )


async def load_barcodes_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: set[uuid.UUID],
) -> dict[uuid.UUID, tuple[str, ...]]:
    if not product_ids:
        return {}
    rows = (
        await session.execute(
            select(ProductBarcode.product_id, ProductBarcode.barcode)
            .where(
                ProductBarcode.tenant_id == tenant_id,
                ProductBarcode.product_id.in_(product_ids),
                ProductBarcode.source == "wb",
            )
            .order_by(ProductBarcode.barcode, ProductBarcode.id)
        )
    ).all()
    grouped: dict[uuid.UUID, list[str]] = {}
    for product_id, barcode in rows:
        grouped.setdefault(product_id, []).append(barcode)
    return {product_id: tuple(dict.fromkeys(values)) for product_id, values in grouped.items()}
