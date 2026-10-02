"""Read-only access of the WMS-641 dispatcher agent to developer requests."""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_request import DeveloperRequest

MIN_KEY_LENGTH = 32
MAX_PAGE = 200


def key_matches(configured: str | None, presented: str | None) -> bool:
    if not configured or len(configured) < MIN_KEY_LENGTH or not presented:
        return False
    return hmac.compare_digest(configured.encode(), presented.encode())


def access_enabled(configured: str | None) -> bool:
    return bool(configured) and len(configured or "") >= MIN_KEY_LENGTH


async def list_after(
    session: AsyncSession,
    *,
    after_created_at: datetime | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DeveloperRequest]:
    """Oldest first, strictly after the (created_at, id) cursor, across all tenants."""
    query = select(DeveloperRequest)
    if after_created_at is not None:
        newer = DeveloperRequest.created_at > after_created_at
        if after_id is not None:
            newer = or_(
                newer,
                and_(
                    DeveloperRequest.created_at == after_created_at,
                    DeveloperRequest.id > after_id,
                ),
            )
        query = query.where(newer)
    query = query.order_by(DeveloperRequest.created_at, DeveloperRequest.id).limit(
        max(1, min(limit, MAX_PAGE))
    )
    return list(await session.scalars(query))


async def get_one(session: AsyncSession, request_id: uuid.UUID) -> DeveloperRequest | None:
    return await session.get(DeveloperRequest, request_id)
