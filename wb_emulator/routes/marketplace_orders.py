"""Marketplace batch order routes (/api/marketplace/v3/orders)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from wb_emulator.services.fault_injection import get_faults
from wb_emulator.services.marking_meta import get_meta

router = APIRouter()


class OrdersMetaBody(BaseModel):
    orders: list[int] = Field(min_length=1, max_length=100)


def _seller_key(request: Request) -> str:
    seller_key = getattr(request.state, "seller_key", None)
    if not seller_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(seller_key)


@router.post("/meta")
def get_orders_meta_batch(body: OrdersMetaBody, request: Request) -> dict[str, Any]:
    """POST /api/marketplace/v3/orders/meta — batch metadata for up to 100 orders.

    Заменяет устаревший GET /api/v3/orders/{orderId}/meta. Возвращает по каждому
    заказу его `meta` (те же множественные ключи sgtins/uins/imeis/gtins, что и
    старый одиночный роут) и `metaDetails` — обратную связь валидации WB.
    """
    seller_key = _seller_key(request)
    if get_faults(seller_key).meta_validation_fail:
        raise HTTPException(
            status_code=409,
            detail={"code": "MetaValidationFail", "message": "emulator_fault: meta rejected"},
        )
    orders: list[dict[str, Any]] = []
    for order_id in body.orders:
        orders.append(
            {
                "id": order_id,
                "meta": get_meta(seller_key, order_id),
                # WB отдаёт metaDetails только когда есть вердикт проверки;
                # эмулятор держит статусы в meta.checkStatus, поэтому здесь пусто.
                "metaDetails": [],
            }
        )
    return {"orders": orders}
