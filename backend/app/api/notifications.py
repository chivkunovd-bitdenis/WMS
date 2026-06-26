from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_effective_seller_id, require_ff_or_seller
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.services import notification_service as notify_svc

router = APIRouter(
    prefix="/operations/notifications",
    tags=["operations"],
)


class NotificationOut(BaseModel):
    id: str
    type: str
    severity: str
    title: str
    body: str
    link: str | None
    payload_json: dict[str, Any] | None
    read_at: str | None
    created_at: str


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int


def _notification_out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=str(row.id),
        type=row.type,
        severity=row.severity,
        title=row.title,
        body=row.body,
        link=row.link,
        payload_json=row.payload_json,
        read_at=row.read_at.isoformat() if row.read_at else None,
        created_at=row.created_at.isoformat(),
    )


def _scopes_for(
    user: User,
    effective_seller_id: uuid.UUID | None,
) -> list[notify_svc.NotificationRecipient]:
    return notify_svc.recipient_scope_for_user(
        user, effective_seller_id=effective_seller_id
    )


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    unread: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> NotificationListOut:
    scopes = _scopes_for(user, effective_seller_id)
    items = await notify_svc.list_notifications(
        session,
        user.tenant_id,
        scopes,
        unread=unread,
        limit=limit,
    )
    unread_count = await notify_svc.count_unread(session, user.tenant_id, scopes)
    return NotificationListOut(
        items=[_notification_out(row) for row in items],
        unread_count=unread_count,
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> NotificationOut:
    scopes = _scopes_for(user, effective_seller_id)
    row = await notify_svc.mark_read(
        session, user.tenant_id, notification_id, scopes
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notification_not_found",
        )
    await session.commit()
    return _notification_out(row)


@router.post("/read-all")
async def mark_all_notifications_read(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> dict[str, int]:
    scopes = _scopes_for(user, effective_seller_id)
    marked = await notify_svc.mark_all_read(session, user.tenant_id, scopes)
    await session.commit()
    return {"marked": marked}
