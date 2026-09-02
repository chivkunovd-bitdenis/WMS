"""Media, stickers, and order marking meta routes (EMU-040)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services import supplies_store as store
from wb_emulator.services.fault_injection import get_faults, maybe_delay
from wb_emulator.services.marking_meta import (
    META_KINDS,
    get_meta,
    parse_put_values,
    upsert_meta,
)
from wb_emulator.services.stickers import (
    build_order_stickers,
    build_trbx_stickers,
    generate_qr_png_bytes,
)

router = APIRouter(tags=["media-meta"])

DbSession = Annotated[Session, Depends(get_db)]


class OrderStickersRequest(BaseModel):
    orders: list[int] = Field(default_factory=list)


class TrbxStickersRequest(BaseModel):
    trbxIds: list[str] = Field(default_factory=list)


def _seller_key(request: Request) -> str:
    seller = getattr(request.state, "seller_key", None)
    if not isinstance(seller, str) or not seller:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return seller


@router.post("/orders/stickers")
async def post_order_stickers(
    request: Request,
    body: OrderStickersRequest,
    type: str = Query(default="png"),
    width: int = Query(default=58, ge=1),
    height: int = Query(default=40, ge=1),
) -> dict[str, list[dict[str, Any]]]:
    """POST /api/v3/orders/stickers — complete WB 58x40 order sticker PNGs."""
    seller_key = _seller_key(request)
    await maybe_delay(seller_key)
    if type.lower() != "png":
        raise HTTPException(status_code=400, detail="unsupported sticker type")
    order_ids = list(body.orders)
    if get_faults(seller_key).incomplete_stickers and len(order_ids) > 1:
        order_ids = order_ids[:1]
    stickers = build_order_stickers(order_ids, width_mm=width, height_mm=height)
    return {"stickers": stickers}


@router.get("/supplies/{supply_id}/barcode")
async def get_supply_barcode(
    request: Request,
    supply_id: str,
    session: DbSession,
    type: str = Query(default="png"),
) -> Response:
    """GET /api/v3/supplies/{supply_id}/barcode — QR after confirmed delivery."""
    seller_key = _seller_key(request)
    await maybe_delay(seller_key, qr=True)
    if type.lower() != "png":
        raise HTTPException(status_code=400, detail="unsupported barcode type")
    try:
        supply = store.get_supply(session, seller_key=seller_key, supply_id=supply_id)
    except store.SuppliesStoreError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if supply.status != store.SupplyStatus.DELIVERED:
        raise HTTPException(status_code=409, detail="Supply is not delivered")
    png_bytes = generate_qr_png_bytes(f"SUPPLY:{supply_id}")
    return Response(content=png_bytes, media_type="image/png")


@router.post("/supplies/{supply_id}/trbx/stickers")
def post_trbx_stickers(
    request: Request,
    supply_id: str,
    body: TrbxStickersRequest,
    type: str = Query(default="png"),
) -> dict[str, list[dict[str, Any]]]:
    """POST /api/v3/supplies/{supply_id}/trbx/stickers — batch trbx QR stickers."""
    _seller_key(request)
    if type.lower() != "png":
        raise HTTPException(status_code=400, detail="unsupported sticker type")
    _ = supply_id
    stickers = build_trbx_stickers(body.trbxIds)
    return {"stickers": stickers}


@router.get("/orders/{order_id}/meta")
def get_order_meta(request: Request, order_id: int) -> dict[str, Any]:
    """GET /api/v3/orders/{order_id}/meta — marking identifiers and check statuses."""
    seller_key = _seller_key(request)
    return get_meta(seller_key, order_id)


@router.put("/orders/{order_id}/meta/{kind}")
def put_order_meta(
    request: Request,
    order_id: int,
    kind: str,
    body: dict[str, Any],
) -> dict[str, str]:
    """PUT /api/v3/orders/{order_id}/meta/{kind} — attach KIZ/UIN/IMEI/GTIN."""
    seller_key = _seller_key(request)
    if get_faults(seller_key).meta_validation_fail:
        raise HTTPException(
            status_code=409,
            detail={"code": "MetaValidationFail", "message": "emulator_fault: meta rejected"},
        )
    if kind not in META_KINDS:
        raise HTTPException(status_code=400, detail="invalid_meta_kind")
    try:
        values = parse_put_values(kind, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not values:
        raise HTTPException(status_code=400, detail="empty_meta_value")
    for value in values:
        upsert_meta(seller_key, order_id, kind, value)
    return {"status": "ok"}
