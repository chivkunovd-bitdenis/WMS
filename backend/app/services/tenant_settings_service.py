from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.services import inventory_service as inv_svc


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise LookupError("tenant_not_found")
    return tenant


async def is_address_storage_enabled(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> bool:
    tenant = await get_tenant(session, tenant_id)
    return tenant.address_storage_enabled


async def get_tenant_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> dict[str, bool]:
    tenant = await get_tenant(session, tenant_id)
    return {
        "address_storage_enabled": tenant.address_storage_enabled,
        "separate_marking_print_enabled": tenant.separate_marking_print_enabled,
    }


async def update_tenant_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    address_storage_enabled: bool | None = None,
    separate_marking_print_enabled: bool | None = None,
) -> dict[str, bool]:
    tenant = await get_tenant(session, tenant_id)
    if address_storage_enabled is not None:
        if tenant.address_storage_enabled and not address_storage_enabled:
            await inv_svc.migrate_all_address_balances_to_sorting(session, tenant_id)
        tenant.address_storage_enabled = address_storage_enabled
    if separate_marking_print_enabled is not None:
        tenant.separate_marking_print_enabled = separate_marking_print_enabled
    await session.commit()
    await session.refresh(tenant)
    return {
        "address_storage_enabled": tenant.address_storage_enabled,
        "separate_marking_print_enabled": tenant.separate_marking_print_enabled,
    }
