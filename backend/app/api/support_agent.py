"""WMS-639: read-only machine access of the dispatcher agent to developer requests.

Only GET. Authenticated by a separate server secret (settings.support_agent_key), never by a
user JWT, and it opens none of the user endpoints of developer-requests (WMS-624 R10).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import get_db
from app.schemas.support_agent import SupportAgentRequestOut
from app.services import support_agent_service as service

router = APIRouter(prefix="/support-agent", tags=["support-agent"])


def require_agent_key(
    x_support_agent_key: Annotated[str | None, Header()] = None,
) -> None:
    if not service.access_enabled(settings.support_agent_key):
        # Switched off: indistinguishable from a route that does not exist.
        raise HTTPException(status_code=404, detail="Not Found")
    if not service.key_matches(settings.support_agent_key, x_support_agent_key):
        raise HTTPException(status_code=401, detail="support_agent_key_invalid")


@router.get(
    "/developer-requests",
    response_model=list[SupportAgentRequestOut],
    dependencies=[Depends(require_agent_key)],
)
async def list_developer_requests(
    session: Annotated[AsyncSession, Depends(get_db)],
    after_created_at: datetime | None = None,
    after_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE)] = 50,
) -> list[SupportAgentRequestOut]:
    rows = await service.list_after(
        session, after_created_at=after_created_at, after_id=after_id, limit=limit
    )
    return [SupportAgentRequestOut.model_validate(row) for row in rows]


@router.get(
    "/developer-requests/{request_id}",
    response_model=SupportAgentRequestOut,
    dependencies=[Depends(require_agent_key)],
)
async def get_developer_request(
    request_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SupportAgentRequestOut:
    row = await service.get_one(session, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="developer_request_not_found")
    return SupportAgentRequestOut.model_validate(row)
