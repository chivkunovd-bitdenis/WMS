"""Append-only tenant cache of FBW warehouses and its historical fallback."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.services import wildberries_client as wb_client
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller

logger = logging.getLogger(__name__)


class WbMpWarehousesMethodDisabled(Exception):
    """WB explicitly disabled the FBW method, independently of a seller key."""


@dataclass
class _DailySweep:
    method_disabled: bool = False


def wb_mp_warehouse_tokens_to_try(
    content_token: str | None,
    supplies_token: str | None,
) -> list[str]:
    """Content key first, then supplies; skip empty and duplicate values."""
    out: list[str] = []
    for raw in (content_token, supplies_token):
        token = (raw or "").strip()
        if token and token not in out:
            out.append(token)
    return out


def _usable_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if isinstance(row, dict)
            and isinstance(row.get("ID"), int) and not isinstance(row.get("ID"), bool)
            and isinstance(row.get("name"), str) and str(row["name"]).strip()]


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
    """Retain the existing entry point, but only insert missing warehouse numbers.

    The tenant row serializes the read/insert transaction across daily, lazy and
    background writers, including SQLite. It changes no tenant fields and avoids
    a unique migration that would require deleting historical duplicates.
    """
    rows = _usable_rows(rows)
    if not rows:
        return
    try:
        await session.execute(update(Tenant).where(Tenant.id == tenant_id).values(id=Tenant.id))
        existing = set(await session.scalars(select(TenantWbMpWarehouse.wb_warehouse_id).where(
            TenantWbMpWarehouse.tenant_id == tenant_id,
        )))
        now = datetime.now(tz=UTC)
        for raw in rows:
            wid = int(str(raw["ID"]))
            if wid in existing:
                continue
            existing.add(wid)
            addr, wt = raw.get("address"), raw.get("workTime")
            date = raw.get("fetched_at")
            session.add(TenantWbMpWarehouse(
                tenant_id=tenant_id, wb_warehouse_id=wid,
                name=str(raw["name"]).strip()[:512],
                address=str(addr) if addr is not None else None,
                work_time=str(wt)[:128] if wt is not None else None,
                is_active=bool(raw.get("isActive")),
                is_transit_active=bool(raw.get("isTransitActive")),
                fetched_at=date if isinstance(date, datetime) else now,
            ))
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def fetch_mp_warehouses_try_tokens(
    content_token: str | None,
    supplies_token: str | None,
    *,
    tried_tokens: set[str] | None = None,
) -> list[dict[str, object]]:
    """Stop on a usable FBW reply or explicit method disablement, not any 404."""
    tried = tried_tokens if tried_tokens is not None else set()
    async with httpx.AsyncClient() as client:
        for token in wb_mp_warehouse_tokens_to_try(content_token, supplies_token):
            if token in tried:
                continue
            tried.add(token)
            try:
                data = await wb_client.fetch_mp_warehouses_list(client, api_token=token)
            except WildberriesClientError as exc:
                if "this method is temporarily disabled" in (exc.response_body or "").casefold():
                    logger.warning("wb mp warehouses: FBW method temporarily disabled")
                    raise WbMpWarehousesMethodDisabled from exc
                logger.warning("wb mp warehouses fetch failed: %s http=%s",
                               exc.code, exc.status_code)
                continue
            except (httpx.HTTPError, ValueError):
                logger.warning("wb mp warehouses: transport or invalid response")
                continue
            usable = _usable_rows(data)
            if usable:
                return usable
    return []


async def _copy_known_fbw_warehouses(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    # This canonical table has one writer: the successful FBW loader. FBS,
    # seller warehouse bindings and Ozon data have their own separate tables.
    known = await session.scalars(select(TenantWbMpWarehouse).order_by(
        TenantWbMpWarehouse.fetched_at.desc(), TenantWbMpWarehouse.tenant_id.asc(),
        TenantWbMpWarehouse.id.asc(),
    ))
    rows: dict[int, dict[str, object]] = {}
    for row in known:
        if row.wb_warehouse_id not in rows and row.name.strip():
            rows[row.wb_warehouse_id] = {
                "ID": row.wb_warehouse_id, "name": row.name, "address": row.address,
                "workTime": row.work_time, "isActive": row.is_active,
                "isTransitActive": row.is_transit_active, "fetched_at": row.fetched_at,
            }
    if rows:
        await replace_tenant_mp_warehouses(session, tenant_id, list(rows.values()))


async def sync_tenant_mp_warehouses_from_seller_tokens(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    content_token: str | None,
    supplies_token: str | None,
) -> int:
    if not wb_mp_warehouse_tokens_to_try(content_token, supplies_token):
        return await count_tenant_mp_warehouses(session, tenant_id)
    try:
        data = await fetch_mp_warehouses_try_tokens(content_token, supplies_token)
    except WbMpWarehousesMethodDisabled:
        await _copy_known_fbw_warehouses(session, tenant_id)
    else:
        if data:
            await replace_tenant_mp_warehouses(session, tenant_id, data)
    return await count_tenant_mp_warehouses(session, tenant_id)


async def sync_tenant_mp_warehouses_if_empty_from_seller_tokens(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    content_token: str | None,
    supplies_token: str | None,
) -> int:
    n_existing = await count_tenant_mp_warehouses(session, tenant_id)
    if n_existing:
        return n_existing
    return await sync_tenant_mp_warehouses_from_seller_tokens(
        session, tenant_id, content_token=content_token, supplies_token=supplies_token,
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


async def _sync_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, sweep: _DailySweep,
) -> None:
    seller_ids = list(await session.scalars(select(Seller.id).where(Seller.tenant_id == tenant_id)
                                           .order_by(Seller.created_at.asc(), Seller.id.asc())))
    tried: set[str] = set()
    for seller_id in seller_ids:
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if pair is None or not wb_mp_warehouse_tokens_to_try(*pair):
            continue
        if not sweep.method_disabled:
            try:
                data = await fetch_mp_warehouses_try_tokens(*pair, tried_tokens=tried)
            except WbMpWarehousesMethodDisabled:
                sweep.method_disabled = True
            else:
                if data:
                    await replace_tenant_mp_warehouses(session, tenant_id, data)
                    return
        if sweep.method_disabled:
            await _copy_known_fbw_warehouses(session, tenant_id)
            return


async def run_wb_mp_warehouses_sync_task(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> None:
    """Initial background fill; search only sellers belonging to this tenant."""
    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != tenant_id:
            return
        if not await count_tenant_mp_warehouses(session, tenant_id):
            await _sync_tenant(session, tenant_id, _DailySweep())


async def run_daily_wb_mp_warehouses_sync_for_tenant(
    tenant_id: uuid.UUID, *, _sweep: _DailySweep | None = None,
) -> None:
    async with SessionLocal() as session:
        await _sync_tenant(session, tenant_id, _sweep if _sweep is not None else _DailySweep())


async def run_daily_wb_mp_warehouses_sync_all_tenants() -> None:
    async with SessionLocal() as session:
        tenant_ids = list(await session.scalars(select(Seller.tenant_id).distinct()
                                                .order_by(Seller.tenant_id)))
    sweep = _DailySweep()
    for tenant_id in tenant_ids:
        try:
            await run_daily_wb_mp_warehouses_sync_for_tenant(tenant_id, _sweep=sweep)
        except Exception as exc:
            # Do not log exception messages or SQL parameters containing secrets.
            logger.warning("wb mp warehouses tenant %s failed: %s", tenant_id, type(exc).__name__)


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
    session: AsyncSession, tenant_id: uuid.UUID,
) -> list[TenantWbMpWarehouse]:
    rows = await list_cached_mp_warehouses(session, tenant_id)
    if rows:
        return rows
    await _sync_tenant(session, tenant_id, _DailySweep())
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
