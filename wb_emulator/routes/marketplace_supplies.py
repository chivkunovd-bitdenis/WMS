"""Marketplace batch supply routes (/api/marketplace/v3/supplies)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services import supplies_store as store
from wb_emulator.services.fault_injection import get_faults

router = APIRouter()


class BatchAddOrdersBody(BaseModel):
    orders: list[int] = Field(min_length=1, max_length=100)


def _seller_key(request: Request) -> str:
    seller_key = getattr(request.state, "seller_key", None)
    if not seller_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(seller_key)


def _map_store_error(exc: store.SuppliesStoreError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(status_code=404, detail=exc.message)
    if exc.code == "conflict":
        return HTTPException(status_code=409, detail=exc.message)
    return HTTPException(status_code=422, detail=exc.message)


DbSession = Annotated[Session, Depends(get_db)]


@router.patch("/{supply_id}/orders", status_code=204, response_class=Response)
def batch_add_orders_to_supply(
    supply_id: str,
    body: BatchAddOrdersBody,
    request: Request,
    session: DbSession,
) -> Response:
    """PATCH /api/marketplace/v3/supplies/{supplyId}/orders — batch add (≤100)."""
    seller_key = _seller_key(request)
    if get_faults(seller_key).supply_conflict_409:
        raise HTTPException(status_code=409, detail="emulator_fault: supply_conflict")
    try:
        for order_id in body.orders:
            store.add_order_to_supply(
                session,
                seller_key=seller_key,
                supply_id=supply_id,
                order_id=order_id,
            )
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return Response(status_code=204)


@router.get("/{supply_id}/order-ids")
def get_supply_order_ids(
    supply_id: str,
    request: Request,
    session: DbSession,
) -> dict[str, list[int]]:
    """GET /api/marketplace/v3/supplies/{supplyId}/order-ids."""
    seller_key = _seller_key(request)
    try:
        view = store.get_supply(session, seller_key=seller_key, supply_id=supply_id)
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return {"orderIds": list(view.order_ids)}
