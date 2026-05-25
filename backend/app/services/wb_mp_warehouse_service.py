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


async def sync_tenant_mp_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    supplies_api_token: str,
) -> int:
    """Pull WB warehouses and replace tenant cache. Returns row count."""
    token = supplies_api_token.strip()
    if not token:
        return await count_tenant_mp_warehouses(session, tenant_id)
    try:
        async with httpx.AsyncClient() as client:
            data = await wb_client.fetch_mp_warehouses_list(client, api_token=token)
    except WildberriesClientError as exc:
        logger.warning("wb mp warehouses fetch failed: %s", exc.code)
        return await count_tenant_mp_warehouses(session, tenant_id)
    except httpx.HTTPError:
        logger.warning("wb mp warehouses transport error")
        return await count_tenant_mp_warehouses(session, tenant_id)
    if not data:
        return await count_tenant_mp_warehouses(session, tenant_id)
    await replace_tenant_mp_warehouses(session, tenant_id, data)
    return await count_tenant_mp_warehouses(session, tenant_id)


async def sync_tenant_mp_warehouses_if_empty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    supplies_api_token: str,
) -> int:
    """Если для тенанта ещё нет кэша — один раз тянем склады WB."""
    n_existing = await count_tenant_mp_warehouses(session, tenant_id)
    if n_existing > 0:
        return n_existing
    return await sync_tenant_mp_warehouses(
        session, tenant_id, supplies_api_token=supplies_api_token
    )


async def get_first_tenant_seller_id(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = (
        select(Seller.id)
        .where(Seller.tenant_id == tenant_id)
        .order_by(Seller.created_at.asc())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


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


async def run_daily_wb_mp_warehouses_sync_for_tenant(tenant_id: uuid.UUID) -> None:
    """Daily: sync WB MP warehouses using first registered seller's supplies token."""
    async with SessionLocal() as session:
        first_seller_id = await get_first_tenant_seller_id(session, tenant_id)
        if first_seller_id is None:
            return
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, first_seller_id)
        if pair is None:
            return
        _c, supplies = pair
        if not supplies:
            return
        await sync_tenant_mp_warehouses(session, tenant_id, supplies_api_token=supplies)


async def run_daily_wb_mp_warehouses_sync_all_tenants() -> None:
    async with SessionLocal() as session:
        stmt = select(Seller.tenant_id).distinct()
        res = await session.execute(stmt)
        tenant_ids = [row[0] for row in res.all()]
    for tid in tenant_ids:
        await run_daily_wb_mp_warehouses_sync_for_tenant(tid)


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


async def list_mp_warehouses_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[TenantWbMpWarehouse]:
    """Return cached WB MP warehouses; lazy-fill from first seller supplies token if empty."""
    rows = await list_cached_mp_warehouses(session, tenant_id)
    if rows:
        return rows
    first_seller_id = await get_first_tenant_seller_id(session, tenant_id)
    if first_seller_id is None:
        return []
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, first_seller_id)
    if pair is None:
        return []
    _c, supplies = pair
    if not supplies:
        return []
    await sync_tenant_mp_warehouses_if_empty(
        session, tenant_id, supplies_api_token=supplies
    )
    return await list_cached_mp_warehouses(session, tenant_id)


async def get_cached_mp_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, wb_warehouse_id: int
) -> TenantWbMpWarehouse | None:
    stmt = select(TenantWbMpWarehouse).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
        TenantWbMpWarehouse.wb_warehouse_id == wb_warehouse_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
