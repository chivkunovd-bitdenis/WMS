"""CRUD for FBS seller WB warehouse → WMS warehouse bindings."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services.catalog_service import get_warehouse

AUTO_FBS_WAREHOUSE_CODE_PREFIX = "fbs-wb"


class FbsWarehouseBindingError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def is_auto_fbs_wms_warehouse(warehouse: Warehouse) -> bool:
    return warehouse.code.startswith(f"{AUTO_FBS_WAREHOUSE_CODE_PREFIX}-") or (
        warehouse.name.startswith("FBS WB ")
    )


async def _seller_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller | None:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    return seller


async def _get_binding_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    *,
    for_update: bool = False,
) -> FbsWarehouseBinding | None:
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _has_active_fbs_reservations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> bool:
    stmt = (
        select(FbsOrderReservation.id)
        .join(FbsOrder, FbsOrderReservation.fbs_order_id == FbsOrder.id)
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id == warehouse_id,
            FbsOrder.seller_id == seller_id,
        )
        .limit(1)
        .with_for_update()
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _assert_wms_not_bound_to_other_wb(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wms_warehouse_id: uuid.UUID,
    *,
    exclude_wb_warehouse_id: int | None,
) -> None:
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.wms_warehouse_id == wms_warehouse_id,
    )
    if exclude_wb_warehouse_id is not None:
        stmt = stmt.where(
            FbsWarehouseBinding.wb_warehouse_id != exclude_wb_warehouse_id
        )
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is not None:
        raise FbsWarehouseBindingError("wms_warehouse_already_bound")


async def list_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[FbsWarehouseBinding]:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    stmt = (
        select(FbsWarehouseBinding)
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
        )
        .order_by(FbsWarehouseBinding.wb_warehouse_id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    if wb_warehouse_id <= 0:
        raise FbsWarehouseBindingError("invalid_wb_warehouse_id")
    row = await _get_binding_row(session, tenant_id, seller_id, wb_warehouse_id)
    if row is None:
        raise FbsWarehouseBindingError("binding_not_found")
    return row


async def upsert_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    *,
    wms_warehouse_id: uuid.UUID,
    stock_sync_enabled: bool,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    if wb_warehouse_id <= 0:
        raise FbsWarehouseBindingError("invalid_wb_warehouse_id")
    if await get_warehouse(session, tenant_id, wms_warehouse_id) is None:
        raise FbsWarehouseBindingError("warehouse_not_found")

    existing = await _get_binding_row(
        session, tenant_id, seller_id, wb_warehouse_id, for_update=True
    )
    if existing is not None:
        old_wms = existing.wms_warehouse_id
        if old_wms != wms_warehouse_id:
            if await _has_active_fbs_reservations(
                session, tenant_id, seller_id, old_wms
            ):
                raise FbsWarehouseBindingError("active_fbs_reservations")
            await _assert_wms_not_bound_to_other_wb(
                session,
                tenant_id,
                seller_id,
                wms_warehouse_id,
                exclude_wb_warehouse_id=wb_warehouse_id,
            )
            existing.wms_warehouse_id = wms_warehouse_id
        existing.stock_sync_enabled = stock_sync_enabled
        existing.is_active = True
        await session.commit()
        await session.refresh(existing)
        return existing

    await _assert_wms_not_bound_to_other_wb(
        session,
        tenant_id,
        seller_id,
        wms_warehouse_id,
        exclude_wb_warehouse_id=None,
    )
    row = FbsWarehouseBinding(
        tenant_id=tenant_id,
        seller_id=seller_id,
        wb_warehouse_id=wb_warehouse_id,
        wms_warehouse_id=wms_warehouse_id,
        stock_sync_enabled=stock_sync_enabled,
        is_active=True,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise FbsWarehouseBindingError("wms_warehouse_already_bound") from exc
    await session.refresh(row)
    return row


async def disable_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    row = await _get_binding_row(
        session, tenant_id, seller_id, wb_warehouse_id, for_update=True
    )
    if row is None:
        raise FbsWarehouseBindingError("binding_not_found")
    if await _has_active_fbs_reservations(
        session, tenant_id, seller_id, row.wms_warehouse_id
    ):
        raise FbsWarehouseBindingError("active_fbs_reservations")
    row.is_active = False
    await session.commit()
    await session.refresh(row)
    return row
