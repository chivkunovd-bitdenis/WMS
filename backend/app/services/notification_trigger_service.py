from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.notification import SEVERITY_INFO
from app.services.notification_service import notify_ff_portal


async def notify_ff_inbound_created(
    session: AsyncSession,
    request: InboundIntakeRequest,
) -> None:
    if request.seller_id is None:
        return
    doc = request.document_number or str(request.id)
    await notify_ff_portal(
        session,
        request.tenant_id,
        type="inbound_created",
        severity=SEVERITY_INFO,
        title="Новая приёмка",
        body=f"Селлер создал приёмку {doc}",
        link="/app/ff/reception",
        payload={"request_id": str(request.id), "document_number": doc},
    )


async def notify_ff_marketplace_unload_created(
    session: AsyncSession,
    request: MarketplaceUnloadRequest,
) -> None:
    doc = request.document_number or str(request.id)
    await notify_ff_portal(
        session,
        request.tenant_id,
        type="marketplace_unload_created",
        severity=SEVERITY_INFO,
        title="Новая отгрузка на МП",
        body=f"Создана отгрузка {doc}",
        link="/app/ff/mp-shipments",
        payload={"request_id": str(request.id), "document_number": doc},
    )
