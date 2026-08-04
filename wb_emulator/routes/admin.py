"""Admin routes for seeding orders and simulating WB lifecycle events.

Protected by ``WB_EMULATOR_ADMIN_TOKEN`` env and ``X-Admin-Token`` request header.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services.fault_injection import faults_snapshot, set_faults
from wb_emulator.services.orders_store import (
    apply_wb_event,
    count_seeded_orders,
    create_orders_for_seller,
    get_admin_state,
    order_to_api,
    seed_orders_from_templates,
)

admin_router = APIRouter(prefix="/__admin", tags=["admin"])


def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    expected = os.environ.get("WB_EMULATOR_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if (x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class WbEventBody(BaseModel):
    event: str = Field(description="sorted | sold | canceled_by_client")


class FaultBody(BaseModel):
    timeout_ms: int | None = Field(default=None, ge=0)
    supply_conflict_409: bool | None = None
    meta_validation_fail: bool | None = None
    incomplete_stickers: bool | None = None
    delayed_qr_ms: int | None = Field(default=None, ge=0)
    partial_status_ids: list[int] | None = None


@admin_router.post("/seed")
def admin_seed(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    """Load operator seed orders from order_templates.json (idempotent upsert)."""
    before = count_seeded_orders(db)
    counts = seed_orders_from_templates(db)
    after = count_seeded_orders(db)
    return {
        "sellers": len(counts),
        "orders_by_seller": counts,
        "orders_created": max(after - before, 0),
        "orders_skipped": before if after == before and before > 0 else 0,
        "orders_total": after,
    }


@admin_router.post("/faults")
def admin_set_faults(
    body: FaultBody,
    seller: str = Query(min_length=1),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    payload = body.model_dump(exclude_none=True)
    set_faults(seller, payload)
    return faults_snapshot(seller)


@admin_router.get("/faults")
def admin_get_faults(
    seller: str | None = Query(default=None),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return faults_snapshot(seller)


@admin_router.post("/orders")
def admin_create_orders(
    seller: str = Query(min_length=1),
    count: int = Query(default=1, ge=1, le=100),
    warehouse_id: int | None = Query(default=None, ge=1),
    chrt_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        result = create_orders_for_seller(
            db,
            seller,
            count,
            warehouse_id=warehouse_id,
            chrt_id=chrt_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "orders": [order_to_api(order) for order in result.orders],
        "created": result.created,
        "rejected_no_stock": result.rejected_no_stock,
    }


@admin_router.post("/orders/{order_id}/wb-event")
def admin_wb_event(
    order_id: int,
    body: WbEventBody,
    seller: str = Query(min_length=1),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        row = apply_wb_event(db, seller, order_id, body.event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order": order_to_api(row)}


@admin_router.get("/state")
def admin_state(
    seller: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return get_admin_state(db, seller)
