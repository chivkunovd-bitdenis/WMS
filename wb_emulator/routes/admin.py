"""Admin routes for seeding orders and simulating WB lifecycle events.

Protected by ``WB_EMULATOR_ADMIN_TOKEN`` env and ``X-Admin-Token`` request header.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.seed.orders_store import (
    apply_wb_event,
    create_orders_for_seller,
    get_admin_state,
    list_new_orders,
    order_to_api,
)

admin_router = APIRouter(prefix="/__admin", tags=["admin"])
orders_read_router = APIRouter(tags=["orders"])


def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    expected = os.environ.get("WB_EMULATOR_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if (x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class WbEventBody(BaseModel):
    event: str = Field(description="sorted | sold | canceled_by_client")


@orders_read_router.get("/new")
def get_orders_new(request: Request, db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    seller_key: str = request.state.seller_key
    orders = list_new_orders(db, seller_key)
    return {"orders": [order_to_api(order) for order in orders]}


@admin_router.get("/orders")
def admin_create_orders(
    seller: str = Query(min_length=1),
    count: int = Query(default=1, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> dict[str, list[dict[str, object]]]:
    created = create_orders_for_seller(db, seller, count)
    return {"orders": [order_to_api(order) for order in created]}


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
