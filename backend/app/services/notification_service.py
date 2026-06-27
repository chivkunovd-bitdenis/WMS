from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FF_PORTAL_ROLES, FULFILLMENT_SELLER
from app.models.notification import (
    FF_PORTAL_RECIPIENT_ID,
    RECIPIENT_TYPE_FF_ROLE,
    RECIPIENT_TYPE_SELLER,
    RECIPIENT_TYPE_USER,
    RECIPIENT_TYPES,
    SEVERITIES,
    Notification,
)
from app.models.user import User


@dataclass(frozen=True)
class NotificationRecipient:
    recipient_type: str
    recipient_id: str


def _validate_recipient(recipient: NotificationRecipient) -> None:
    if recipient.recipient_type not in RECIPIENT_TYPES:
        raise ValueError(f"invalid_recipient_type:{recipient.recipient_type}")


def _validate_severity(severity: str) -> None:
    if severity not in SEVERITIES:
        raise ValueError(f"invalid_severity:{severity}")


def recipient_scope_for_user(
    user: User,
    *,
    effective_seller_id: uuid.UUID | None,
) -> list[NotificationRecipient]:
    """Recipient keys visible to the authenticated user."""
    scopes: list[NotificationRecipient] = [
        NotificationRecipient(RECIPIENT_TYPE_USER, str(user.id)),
    ]
    if user.role == FULFILLMENT_SELLER and effective_seller_id is not None:
        scopes.append(
            NotificationRecipient(RECIPIENT_TYPE_SELLER, str(effective_seller_id))
        )
    if user.role in FF_PORTAL_ROLES:
        scopes.append(NotificationRecipient(RECIPIENT_TYPE_FF_ROLE, user.role))
        scopes.append(
            NotificationRecipient(RECIPIENT_TYPE_FF_ROLE, FF_PORTAL_RECIPIENT_ID)
        )
    return scopes


def _scope_filter(
    tenant_id: uuid.UUID,
    scopes: list[NotificationRecipient],
) -> Any:
    return or_(
        *[
            and_(
                Notification.tenant_id == tenant_id,
                Notification.recipient_type == scope.recipient_type,
                Notification.recipient_id == scope.recipient_id,
            )
            for scope in scopes
        ]
    )


async def notify(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    recipient: NotificationRecipient,
    *,
    type: str,
    severity: str,
    title: str,
    body: str,
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    _validate_recipient(recipient)
    _validate_severity(severity)
    row = Notification(
        tenant_id=tenant_id,
        recipient_type=recipient.recipient_type,
        recipient_id=recipient.recipient_id,
        type=type,
        severity=severity,
        title=title,
        body=body,
        link=link,
        payload_json=payload,
    )
    session.add(row)
    await session.flush()
    return row


async def notify_ff_portal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    type: str,
    severity: str,
    title: str,
    body: str,
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    return await notify(
        session,
        tenant_id,
        NotificationRecipient(RECIPIENT_TYPE_FF_ROLE, FF_PORTAL_RECIPIENT_ID),
        type=type,
        severity=severity,
        title=title,
        body=body,
        link=link,
        payload=payload,
    )


def _list_query(
    tenant_id: uuid.UUID,
    scopes: list[NotificationRecipient],
    *,
    unread: bool | None,
) -> Select[tuple[Notification]]:
    stmt = (
        select(Notification)
        .where(_scope_filter(tenant_id, scopes))
        .order_by(Notification.created_at.desc())
    )
    if unread is True:
        stmt = stmt.where(Notification.read_at.is_(None))
    elif unread is False:
        stmt = stmt.where(Notification.read_at.is_not(None))
    return stmt


async def list_notifications(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    scopes: list[NotificationRecipient],
    *,
    unread: bool | None = None,
    limit: int = 50,
) -> list[Notification]:
    stmt = _list_query(tenant_id, scopes, unread=unread).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_unread(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    scopes: list[NotificationRecipient],
) -> int:
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(_scope_filter(tenant_id, scopes))
        .where(Notification.read_at.is_(None))
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_notification_for_scope(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    notification_id: uuid.UUID,
    scopes: list[NotificationRecipient],
) -> Notification | None:
    stmt = select(Notification).where(
        Notification.id == notification_id,
        _scope_filter(tenant_id, scopes),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def mark_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    notification_id: uuid.UUID,
    scopes: list[NotificationRecipient],
) -> Notification | None:
    row = await get_notification_for_scope(
        session, tenant_id, notification_id, scopes
    )
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await session.flush()
    return row


async def mark_all_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    scopes: list[NotificationRecipient],
) -> int:
    stmt = select(Notification).where(
        _scope_filter(tenant_id, scopes),
        Notification.read_at.is_(None),
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    if rows:
        await session.flush()
    return len(rows)
