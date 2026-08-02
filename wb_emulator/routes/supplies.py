"""Marketplace supplies + trbx routes (/api/v3/supplies)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services import supplies_store as store

router = APIRouter()


class CreateSupplyBody(BaseModel):
    name: str = Field(min_length=1, max_length=512)


class CreateTrbxBody(BaseModel):
    amount: int = Field(ge=1, le=100)


class BindTrbxOrdersBody(BaseModel):
    orderIds: list[int] = Field(min_length=1)


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
    if exc.code == "delivered":
        return HTTPException(status_code=400, detail=exc.message)
    return HTTPException(status_code=422, detail=exc.message)


DbSession = Annotated[Session, Depends(get_db)]


@router.post("")
def create_supply(
    body: CreateSupplyBody,
    request: Request,
    session: DbSession,
) -> dict[str, str]:
    seller_key = _seller_key(request)
    try:
        return store.create_supply(session, seller_key=seller_key, name=body.name)
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc


@router.get("/{supply_id}")
def get_supply(supply_id: str, request: Request, session: DbSession) -> dict[str, object]:
    seller_key = _seller_key(request)
    try:
        view = store.get_supply(session, seller_key=seller_key, supply_id=supply_id)
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return {
        "id": view.id,
        "name": view.name,
        "done": view.status == store.SupplyStatus.DELIVERED,
        "orders": view.order_ids,
        "trbxIds": view.trbx_ids,
    }


@router.patch("/{supply_id}/orders/{order_id}", status_code=204, response_class=Response)
def add_order_to_supply(
    supply_id: str,
    order_id: int,
    request: Request,
    session: DbSession,
) -> Response:
    seller_key = _seller_key(request)
    try:
        store.add_order_to_supply(
            session, seller_key=seller_key, supply_id=supply_id, order_id=order_id
        )
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return Response(status_code=204)


@router.patch("/{supply_id}/deliver", status_code=204, response_class=Response)
def deliver_supply(
    supply_id: str,
    request: Request,
    session: DbSession,
) -> Response:
    seller_key = _seller_key(request)
    try:
        store.deliver_supply(session, seller_key=seller_key, supply_id=supply_id)
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return Response(status_code=204)


@router.post("/{supply_id}/trbx")
def create_trbxes(
    supply_id: str,
    body: CreateTrbxBody,
    request: Request,
    session: DbSession,
) -> dict[str, list[str]]:
    seller_key = _seller_key(request)
    try:
        ids = store.create_trbxes(
            session, seller_key=seller_key, supply_id=supply_id, amount=body.amount
        )
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return {"trbxIds": ids}


@router.patch("/{supply_id}/trbx/{trbx_id}", status_code=204, response_class=Response)
def bind_orders_to_trbx(
    supply_id: str,
    trbx_id: str,
    body: BindTrbxOrdersBody,
    request: Request,
    session: DbSession,
) -> Response:
    seller_key = _seller_key(request)
    try:
        store.bind_orders_to_trbx(
            session,
            seller_key=seller_key,
            supply_id=supply_id,
            trbx_id=trbx_id,
            order_ids=body.orderIds,
        )
    except store.SuppliesStoreError as exc:
        raise _map_store_error(exc) from exc
    return Response(status_code=204)


# barcode + trbx/stickers: real PNG handlers live in media_meta (EMU-040)
