"""Marketplace FBS stocks routes (/api/v3/stocks)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wb_emulator.db import get_db
from wb_emulator.services import stocks_store as store

router = APIRouter(tags=["stocks"])


class StockPutItem(BaseModel):
    chrtId: int
    amount: int = Field(ge=0)


class PutStocksBody(BaseModel):
    stocks: list[StockPutItem] = Field(min_length=1, max_length=1000)


class PostStocksBody(BaseModel):
    chrtIds: list[int] = Field(default_factory=list)


def _seller_key(request: Request) -> str:
    seller_key = getattr(request.state, "seller_key", None)
    if not seller_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(seller_key)


DbSession = Annotated[Session, Depends(get_db)]


@router.put("/stocks/{warehouse_id}", status_code=204, response_class=Response)
def put_stocks(
    warehouse_id: int,
    body: PutStocksBody,
    request: Request,
    session: DbSession,
) -> Response:
    seller_key = _seller_key(request)
    store.upsert_stocks(
        session,
        seller_key=seller_key,
        warehouse_id=warehouse_id,
        stocks=[store.StockItem(chrt_id=item.chrtId, amount=item.amount) for item in body.stocks],
    )
    return Response(status_code=204)


@router.post("/stocks/{warehouse_id}")
def post_stocks(
    warehouse_id: int,
    body: PostStocksBody,
    request: Request,
    session: DbSession,
) -> dict[str, list[dict[str, int]]]:
    seller_key = _seller_key(request)
    items = store.get_stocks_by_chrt_ids(
        session,
        seller_key=seller_key,
        warehouse_id=warehouse_id,
        chrt_ids=body.chrtIds,
    )
    return {
        "stocks": [{"chrtId": item.chrt_id, "amount": item.amount} for item in items],
    }
