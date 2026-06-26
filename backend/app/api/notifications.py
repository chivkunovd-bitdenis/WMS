from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_effective_seller_id, require_ff_or_seller
from app.db.session import get_db
from app.models.notification import (
    FF_PORTAL_RECIPIENT_ID,
    RECIPIENT_TYPE_FF_ROLE,
    RECIPIENT_TYPE_SELLER,
    RECIPIENT_TYPE_USER,
    SEVERITY_INFO,
    Notification,
)
from app.models.user import User
from app.services import notification_service as notify_svc

_E2E_SCHEMA = os.environ.get("WMS_AUTO_CREATE_SCHEMA") == "1"

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


if _E2E_SCHEMA:

    class E2eSeedNotificationIn(BaseModel):
        recipient_type: str = Field(default=RECIPIENT_TYPE_FF_ROLE)
        recipient_id: str | None = None
        type: str = "e2e_test"
        severity: str = SEVERITY_INFO
        title: str
        body: str = "e2e body"
        link: str | None = None

    class E2eSeedNotificationOut(BaseModel):
        id: str

    @router.post("/_e2e/seed", response_model=E2eSeedNotificationOut)
    async def e2e_seed_notification(
        body: E2eSeedNotificationIn,
        user: Annotated[User, Depends(require_ff_or_seller)],
        session: Annotated[AsyncSession, Depends(get_db)],
        effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    ) -> E2eSeedNotificationOut:
        if body.recipient_type == RECIPIENT_TYPE_USER:
            recipient_id = body.recipient_id or str(user.id)
        elif body.recipient_type == RECIPIENT_TYPE_SELLER:
            if effective_seller_id is None and body.recipient_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="seller_id_required",
                )
            recipient_id = body.recipient_id or str(effective_seller_id)
        elif body.recipient_type == RECIPIENT_TYPE_FF_ROLE:
            recipient_id = body.recipient_id or FF_PORTAL_RECIPIENT_ID
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_recipient_type",
            )
        row = await notify_svc.notify(
            session,
            user.tenant_id,
            notify_svc.NotificationRecipient(body.recipient_type, recipient_id),
            type=body.type,
            severity=body.severity,
            title=body.title,
            body=body.body,
            link=body.link,
        )
        await session.commit()
        return E2eSeedNotificationOut(id=str(row.id))
