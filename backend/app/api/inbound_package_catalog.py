from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_catalog_cells_read_access
from app.db.session import get_db
from app.models.user import User
from app.services import inbound_package_catalog_service as catalog_svc

router = APIRouter(prefix="/operations/inbound-packages", tags=["operations"])


class InboundPackageCatalogLineOut(BaseModel):
    product_id: str
    remaining_qty: int
    name: str
    sku_code: str
    wb_vendor_code: str | None = None
    wb_barcode: str | None = None
    wb_size: str | None = None
    seller_name: str | None = None


class PackageSourceDocumentOut(BaseModel):
    kind: str
    id: str
    number: str | None = None
    date: datetime


class InboundPackageCatalogItemOut(BaseModel):
    id: str
    kind: Literal["box", "cargo_place"]
    number: int
    internal_barcode: str
    request_id: str
    request_display_number: str | None = None
    warehouse_name: str | None = None
    intake_status: str
    composition_tracked: bool
    fully_distributed: bool
    remaining_qty: int | None = None
    lines: list[InboundPackageCatalogLineOut] = Field(default_factory=list)
    source_document: PackageSourceDocumentOut


def _item_out(item: catalog_svc.InboundPackageCatalogItem) -> InboundPackageCatalogItemOut:
    return InboundPackageCatalogItemOut(
        id=str(item.id),
        kind=item.kind,
        number=item.number,
        internal_barcode=item.internal_barcode,
        request_id=str(item.request_id),
        request_display_number=item.request_display_number,
        warehouse_name=item.warehouse_name,
        intake_status=item.intake_status,
        composition_tracked=item.composition_tracked,
        fully_distributed=item.fully_distributed,
        remaining_qty=item.remaining_qty,
        lines=[
            InboundPackageCatalogLineOut(
                product_id=str(line.product_id),
                remaining_qty=line.remaining_qty,
                name=line.name,
                sku_code=line.sku_code,
                wb_vendor_code=line.wb_vendor_code,
                wb_barcode=line.wb_barcode,
                wb_size=line.wb_size,
                seller_name=line.seller_name,
            )
            for line in item.lines
        ],
        source_document=PackageSourceDocumentOut(
            kind=item.source_document.kind,
            id=str(item.source_document.id),
            number=item.source_document.number,
            date=item.source_document.date,
        ),
    )


@router.get("", response_model=list[InboundPackageCatalogItemOut])
async def get_inbound_packages(
    user: Annotated[User, Depends(require_catalog_cells_read_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InboundPackageCatalogItemOut]:
    items = await catalog_svc.list_current_packages(session, user.tenant_id)
    return [_item_out(item) for item in items]


@router.get("/lookup", response_model=InboundPackageCatalogItemOut)
async def lookup_inbound_package(
    barcode: Annotated[str, Query(min_length=1, max_length=64)],
    user: Annotated[User, Depends(require_catalog_cells_read_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundPackageCatalogItemOut:
    item = await catalog_svc.lookup_package_by_barcode(session, user.tenant_id, barcode)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package_not_found")
    return _item_out(item)
