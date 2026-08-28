from __future__ import annotations

import uuid
from datetime import time
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.services import inventory_service as inv_svc


class TenantSettingsData(TypedDict):
    address_storage_enabled: bool
    separate_marking_print_enabled: bool
    fbs_shipment_cutoff_time: str | None


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise LookupError("tenant_not_found")
    return tenant


async def is_address_storage_enabled(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> bool:
    """Включено ли адресное хранение у арендатора.

    Читаем одну колонку запросом, а не через объект арендатора. После записи
    сессия сбрасывает загруженные объекты, и обращение к полю у такого объекта
    пытается втихую сходить в базу — в асинхронном коде это падает жалобой на
    контекст, причём далеко от места настоящей причины. Этот флаг спрашивают
    почти из каждого ответа API, поэтому цена ошибки высокая, а запрос дешёвый.
    """
    value = await session.scalar(
        select(Tenant.address_storage_enabled).where(Tenant.id == tenant_id)
    )
    return bool(value)


async def get_tenant_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> TenantSettingsData:
    tenant = await get_tenant(session, tenant_id)
    return {
        "address_storage_enabled": tenant.address_storage_enabled,
        "separate_marking_print_enabled": tenant.separate_marking_print_enabled,
        "fbs_shipment_cutoff_time": (
            tenant.fbs_shipment_cutoff_time.strftime("%H:%M")
            if tenant.fbs_shipment_cutoff_time is not None
            else None
        ),
    }


async def update_tenant_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    address_storage_enabled: bool | None = None,
    separate_marking_print_enabled: bool | None = None,
    fbs_shipment_cutoff_time: time | None = None,
    set_fbs_shipment_cutoff_time: bool = False,
    actor_user_id: uuid.UUID | None,
) -> TenantSettingsData:
    tenant = await get_tenant(session, tenant_id)
    if address_storage_enabled is not None:
        if tenant.address_storage_enabled and not address_storage_enabled:
            await inv_svc.migrate_all_address_balances_to_sorting(
                session,
                tenant_id,
                actor_user_id=actor_user_id,
            )
        tenant.address_storage_enabled = address_storage_enabled
    if separate_marking_print_enabled is not None:
        tenant.separate_marking_print_enabled = separate_marking_print_enabled
    if set_fbs_shipment_cutoff_time:
        tenant.fbs_shipment_cutoff_time = fbs_shipment_cutoff_time
    await session.commit()
    await session.refresh(tenant)
    return {
        "address_storage_enabled": tenant.address_storage_enabled,
        "separate_marking_print_enabled": tenant.separate_marking_print_enabled,
        "fbs_shipment_cutoff_time": (
            tenant.fbs_shipment_cutoff_time.strftime("%H:%M")
            if tenant.fbs_shipment_cutoff_time is not None
            else None
        ),
    }
