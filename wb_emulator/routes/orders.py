"""WB Marketplace orders API routes (/api/v3/orders/*)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services import orders_store
from wb_emulator.services.fault_injection import get_faults

router = APIRouter()


class OrdersStatusRequest(BaseModel):
    orders: list[int] = Field(default_factory=list)


@router.get("/new")
def get_orders_new(request: Request, db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    seller_key: str = request.state.seller_key
    orders = orders_store.list_new_orders(db, seller_key)
    return {"orders": [orders_store.order_to_api(order) for order in orders]}


@router.get("")
def get_orders(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=1000),
    next: int | None = Query(default=None),
) -> dict[str, object]:
    seller_key: str = request.state.seller_key
    page, next_token = orders_store.list_orders_page(db, seller_key, limit=limit, next_cursor=next)
    return {
        "orders": [orders_store.order_to_api(order) for order in page],
        "next": next_token,
    }


@router.post("/status")
def post_orders_status(
    request: Request,
    body: OrdersStatusRequest,
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object]]]:
    seller_key: str = request.state.seller_key
    faults = get_faults(seller_key)
    rows = orders_store.get_statuses(
        db,
        seller_key,
        body.orders,
        omit_ids=faults.partial_status_ids,
    )
    return {"orders": rows}


@router.patch("/{order_id}/cancel")
def patch_cancel_order(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
) -> Response:
    seller_key: str = request.state.seller_key
    orders_store.cancel_order(db, seller_key, order_id)
    return Response(status_code=204)
