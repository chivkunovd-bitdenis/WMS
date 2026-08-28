"""Free-text note stored on an inbound document independently of containers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeRequest
from app.services.inbound_intake_service import InboundIntakeError


async def update_comment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    comment: str | None,
) -> InboundIntakeRequest:
    request = (
        await session.execute(
            select(InboundIntakeRequest).where(
                InboundIntakeRequest.id == request_id,
                InboundIntakeRequest.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if request is None:
        raise InboundIntakeError("request_not_found")
    request.comment = comment.strip() if comment and comment.strip() else None
    await session.commit()
    await session.refresh(request)
    return request
