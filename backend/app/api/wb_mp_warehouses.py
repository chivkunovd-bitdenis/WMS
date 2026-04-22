from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.user import User
from app.services import wb_mp_warehouse_service as wh_svc

router = APIRouter(prefix="/operations/wb-mp-warehouses", tags=["operations"])


class WbMpWarehouseOut(BaseModel):
    id: str
    wb_warehouse_id: int
    name: str
    address: str | None = None
    work_time: str | None = None
    is_active: bool
    is_transit_active: bool


@router.get("", response_model=list[WbMpWarehouseOut])
async def list_wb_mp_warehouses(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WbMpWarehouseOut]:
    rows = await wh_svc.list_cached_mp_warehouses(session, user.tenant_id)
    return [
        WbMpWarehouseOut(
            id=str(r.id),
            wb_warehouse_id=int(r.wb_warehouse_id),
            name=r.name,
            address=r.address,
            work_time=r.work_time,
            is_active=bool(r.is_active),
            is_transit_active=bool(r.is_transit_active),
        )
        for r in rows
    ]
