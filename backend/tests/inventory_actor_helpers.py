from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def resolve_test_actor_user_id(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    """Return the tenant's real test user, or None when the fixture has no user."""
    return await session.scalar(select(User.id).where(User.tenant_id == tenant_id))
