"""Tenant cache for WB marketplace warehouses (GET /api/v1/warehouses)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.services import wildberries_client as wb_client
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller

logger = logging.getLogger(__name__)


async def count_tenant_mp_warehouses(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(TenantWbMpWarehouse).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def replace_tenant_mp_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, object]],
) -> None:
    await session.execute(
        delete(TenantWbMpWarehouse).where(TenantWbMpWarehouse.tenant_id == tenant_id),
    )
    now = datetime.now(tz=UTC)
    for raw in rows:
        wid = raw.get("ID")
        name = raw.get("name")
        if not isinstance(wid, int) or not isinstance(name, str) or not name.strip():
            continue
        addr = raw.get("address")
        wt = raw.get("workTime")
        session.add(
            TenantWbMpWarehouse(
                tenant_id=tenant_id,
                wb_warehouse_id=wid,
                name=name.strip()[:512],
                address=str(addr) if addr is not None else None,
                work_time=str(wt)[:128] if wt is not None else None,
                is_active=bool(raw.get("isActive")),
                is_transit_active=bool(raw.get("isTransitActive")),
                fetched_at=now,
            ),
        )
    await session.commit()


async def sync_tenant_mp_warehouses_if_empty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    supplies_api_token: str,
) -> int:
    """Если для тенанта ещё нет кэша — один раз тянем склады WB. Возвращает число записей."""
    n_existing = await count_tenant_mp_warehouses(session, tenant_id)
    if n_existing > 0:
        return n_existing
    token = supplies_api_token.strip()
    if not token:
        return 0
    try:
        async with httpx.AsyncClient() as client:
            data = await wb_client.fetch_mp_warehouses_list(client, api_token=token)
    except WildberriesClientError as exc:
        logger.warning("wb mp warehouses fetch failed: %s", exc.code)
        return 0
    except httpx.HTTPError:
        logger.warning("wb mp warehouses transport error")
        return 0
    if not data:
        return 0
    await replace_tenant_mp_warehouses(session, tenant_id, data)
    return await count_tenant_mp_warehouses(session, tenant_id)


async def run_wb_mp_warehouses_sync_task(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> None:
    """Фон: если кэш пуст — взять supplies-токен этого селлера и заполнить склады WB."""
    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != tenant_id:
            return
        if await count_tenant_mp_warehouses(session, tenant_id) > 0:
            return
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if pair is None:
            return
        _c, supplies = pair
        if not supplies:
            return
        await sync_tenant_mp_warehouses_if_empty(session, tenant_id, supplies_api_token=supplies)


async def list_cached_mp_warehouses(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[TenantWbMpWarehouse]:
    stmt = (
        select(TenantWbMpWarehouse)
        .where(TenantWbMpWarehouse.tenant_id == tenant_id)
        .order_by(TenantWbMpWarehouse.name.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_cached_mp_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, wb_warehouse_id: int
) -> TenantWbMpWarehouse | None:
    stmt = select(TenantWbMpWarehouse).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
        TenantWbMpWarehouse.wb_warehouse_id == wb_warehouse_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
