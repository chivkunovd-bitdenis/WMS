"""Shared API models and helpers for xlsx box import routes."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.services import box_import_service as box_svc

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class BoxImportLinePreviewOut(BaseModel):
    barcode: str
    product_id: str | None = None
    sku_code: str | None = None
    product_name: str | None = None
    quantity: int


class BoxImportBoxPreviewOut(BaseModel):
    address: str
    lines: list[BoxImportLinePreviewOut]
    total_qty: int


class BoxImportRowErrorOut(BaseModel):
    row: int
    barcode: str | None = None
    code: str
    message: str


class BoxImportPreviewSummaryOut(BaseModel):
    boxes_count: int
    positions: int
    total_units: int
    error_count: int


class BoxImportPreviewOut(BaseModel):
    boxes: list[BoxImportBoxPreviewOut]
    errors: list[BoxImportRowErrorOut]
    summary: BoxImportPreviewSummaryOut


class BoxImportApplyOut(BaseModel):
    boxes_created: int
    box_ids: list[str] = Field(default_factory=list)
    summary: BoxImportPreviewSummaryOut
    errors: list[BoxImportRowErrorOut] = Field(default_factory=list)


def preview_result_out(result: box_svc.BoxImportPreviewResult) -> BoxImportPreviewOut:
    return BoxImportPreviewOut(
        boxes=[
            BoxImportBoxPreviewOut(
                address=box.address,
                lines=[
                    BoxImportLinePreviewOut(
                        barcode=line.barcode,
                        product_id=str(line.product_id) if line.product_id else None,
                        sku_code=line.sku_code,
                        product_name=line.product_name,
                        quantity=line.quantity,
                    )
                    for line in box.lines
                ],
                total_qty=box.total_qty,
            )
            for box in result.boxes
        ],
        errors=[
            BoxImportRowErrorOut(
                row=err.row,
                barcode=err.barcode,
                code=err.code,
                message=err.message,
            )
            for err in result.errors
        ],
        summary=BoxImportPreviewSummaryOut(
            boxes_count=result.summary.boxes_count,
            positions=result.summary.positions,
            total_units=result.summary.total_units,
            error_count=result.summary.error_count,
        ),
    )


async def read_xlsx_upload(upload: UploadFile) -> tuple[str, bytes]:
    filename = (upload.filename or "upload").strip() or "upload"
    content = await upload.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="file_too_large",
        )
    return filename, content


def http_from_box_import_error(exc: box_svc.BoxImportError) -> HTTPException:
    code = exc.code
    if code in {"unsupported_file_type", "empty_file", "missing_column"}:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": code, "message": exc.message},
        )
    if code == "row_errors":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": exc.message},
    )
