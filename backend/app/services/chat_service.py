"""Chat service — WMS-397/WMS-399.

Business rules implemented here:

* ``ensure_main_chat`` is idempotent: exactly one row per (tenant, seller).
  Concurrent callers can race on INSERT because the unique index
  ``uq_chat_conversations_main`` provides the last-write ordering; on
  integrity error we re-read.
* ``can_read_conversation`` uses the existing user/tenant/role machinery.
  Fulfillment admins and staff always read the main chat of any seller in
  their tenant. Sellers read their own main chat and any extra chat they
  are an explicit participant of. Extra chats require explicit
  ``ChatParticipant`` rows for both sides, including the creator.
* Messages are stored with an author-scoped unique ``client_message_id``;
  a retry sends the same value and returns the existing row instead of
  duplicating.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import (
    FF_PORTAL_ROLES,
    FULFILLMENT_ADMIN,
    FULFILLMENT_SELLER,
)
from app.models.chat import (
    CHAT_KIND_EXTRA,
    CHAT_KIND_MAIN,
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    ChatParticipant,
)
from app.models.seller import Seller
from app.models.user import User


class ChatError(Exception):
    """Raised on domain-level chat errors. API layer converts to HTTPException."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


ALLOWED_ATTACHED_DOCUMENT_KINDS = frozenset(
    {
        "fbs_order",
        "fbs_supply",
        "inbound_intake",
        "marketplace_unload",
        "outbound_shipment",
    }
)


@dataclass(frozen=True)
class AttachedDocument:
    kind: str
    id: uuid.UUID
    title: str
    seller_id: uuid.UUID
    seller_name: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "id": str(self.id),
            "title": self.title,
            "seller_id": str(self.seller_id),
        }
        if self.seller_name is not None:
            payload["seller_name"] = self.seller_name
        return payload


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


async def ensure_main_chat(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    created_by: User | None = None,
) -> ChatConversation:
    """Return the main chat for the seller, creating it on first access."""
    existing = await _load_main_chat(session, tenant_id, seller_id)
    if existing is not None:
        return existing
    conv = ChatConversation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        kind=CHAT_KIND_MAIN,
        title=None,
        created_by_user_id=created_by.id if created_by is not None else None,
    )
    try:
        async with session.begin_nested():
            session.add(conv)
            await session.flush()
    except IntegrityError:
        existing = await _load_main_chat(session, tenant_id, seller_id)
        if existing is None:
            raise
        return existing
    return conv


async def _load_main_chat(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> ChatConversation | None:
    stmt = select(ChatConversation).where(
        ChatConversation.tenant_id == tenant_id,
        ChatConversation.seller_id == seller_id,
        ChatConversation.kind == CHAT_KIND_MAIN,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_extra_chat(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    title: str,
    created_by: User,
    participant_user_ids: Iterable[uuid.UUID] = (),
) -> ChatConversation:
    if created_by.role != FULFILLMENT_ADMIN:
        raise ChatError("forbidden", "only fulfillment admin creates extra chats")
    clean_title = title.strip()
    if not clean_title:
        raise ChatError("title_required")
    conv = ChatConversation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        kind=CHAT_KIND_EXTRA,
        title=clean_title,
        created_by_user_id=created_by.id,
    )
    session.add(conv)
    await session.flush()
    seen: set[uuid.UUID] = set()
    for user_id in [created_by.id, *participant_user_ids]:
        if user_id in seen:
            continue
        seen.add(user_id)
        session.add(
            ChatParticipant(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                user_id=user_id,
                added_by_user_id=created_by.id,
            )
        )
    await session.flush()
    return conv


async def load_conversation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> ChatConversation | None:
    stmt = select(ChatConversation).where(
        ChatConversation.id == conversation_id,
        ChatConversation.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_conversations_for_user(
    session: AsyncSession,
    user: User,
    *,
    effective_seller_id: uuid.UUID | None,
) -> list[ChatConversation]:
    """List conversations the user can read.

    * FF admins/staff: main chats and extra chats they participate in.
    * Sellers: main chat of their effective seller plus every extra chat they
      are a participant of.
    """
    stmt = select(ChatConversation).where(ChatConversation.tenant_id == user.tenant_id)
    participant_ids_stmt = select(ChatParticipant.conversation_id).where(
        ChatParticipant.tenant_id == user.tenant_id,
        ChatParticipant.user_id == user.id,
    )
    if user.role in FF_PORTAL_ROLES:
        stmt = stmt.where(
            or_(
                ChatConversation.kind == CHAT_KIND_MAIN,
                ChatConversation.id.in_(participant_ids_stmt),
            )
        ).order_by(ChatConversation.kind.desc(), ChatConversation.updated_at.desc())
        return list((await session.execute(stmt)).scalars())
    if user.role == FULFILLMENT_SELLER:
        seller_id = effective_seller_id
        if seller_id is None:
            return []
        participant_ids_stmt = select(ChatParticipant.conversation_id).where(
            ChatParticipant.tenant_id == user.tenant_id,
            ChatParticipant.user_id == user.id,
        )
        stmt = stmt.where(
            and_(
                ChatConversation.seller_id == seller_id,
                or_(
                    ChatConversation.kind == CHAT_KIND_MAIN,
                    ChatConversation.id.in_(participant_ids_stmt),
                ),
            )
        ).order_by(ChatConversation.kind.desc(), ChatConversation.updated_at.desc())
        return list((await session.execute(stmt)).scalars())
    return []


async def can_read_conversation(
    session: AsyncSession,
    user: User,
    conv: ChatConversation,
    *,
    effective_seller_id: uuid.UUID | None,
) -> bool:
    if user.tenant_id != conv.tenant_id:
        return False
    if user.role not in FF_PORTAL_ROLES and user.role != FULFILLMENT_SELLER:
        return False
    if user.role == FULFILLMENT_SELLER and conv.seller_id != effective_seller_id:
        return False
    if conv.kind == CHAT_KIND_MAIN:
        return True
    # extra: participation required
    stmt = select(ChatParticipant.id).where(
        ChatParticipant.tenant_id == user.tenant_id,
        ChatParticipant.conversation_id == conv.id,
        ChatParticipant.user_id == user.id,
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def load_participants(
    session: AsyncSession,
    conv: ChatConversation,
) -> list[ChatParticipant]:
    stmt = select(ChatParticipant).where(
        ChatParticipant.conversation_id == conv.id,
        ChatParticipant.tenant_id == conv.tenant_id,
    )
    return list((await session.execute(stmt)).scalars())


async def add_participant(
    session: AsyncSession,
    conv: ChatConversation,
    user_to_add: User,
    *,
    added_by: User,
) -> ChatParticipant:
    if conv.kind != CHAT_KIND_EXTRA:
        raise ChatError("main_participants_implicit")
    if added_by.role != FULFILLMENT_ADMIN:
        raise ChatError("forbidden", "only fulfillment admin manages members")
    if user_to_add.tenant_id != conv.tenant_id:
        raise ChatError("cross_tenant")
    existing = await session.execute(
        select(ChatParticipant).where(
            ChatParticipant.conversation_id == conv.id,
            ChatParticipant.user_id == user_to_add.id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row
    row = ChatParticipant(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        user_id=user_to_add.id,
        added_by_user_id=added_by.id,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        row = (
            await session.execute(
                select(ChatParticipant).where(
                    ChatParticipant.conversation_id == conv.id,
                    ChatParticipant.user_id == user_to_add.id,
                )
            )
        ).scalar_one()
    return row


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def list_messages(
    session: AsyncSession,
    conv: ChatConversation,
    *,
    limit: int = 200,
    before: uuid.UUID | None = None,
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.tenant_id == conv.tenant_id,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    if before is not None:
        cursor = (
            await session.execute(
                select(ChatMessage).where(
                    ChatMessage.id == before,
                    ChatMessage.conversation_id == conv.id,
                    ChatMessage.tenant_id == conv.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if cursor is None:
            return []
        stmt = stmt.where(
            or_(
                ChatMessage.created_at < cursor.created_at,
                and_(
                    ChatMessage.created_at == cursor.created_at,
                    ChatMessage.id < cursor.id,
                ),
            )
        )
    return list(reversed(list((await session.execute(stmt)).scalars())))


async def post_message(
    session: AsyncSession,
    conv: ChatConversation,
    author: User,
    *,
    client_message_id: str,
    text: str,
    attachment_ids: Iterable[uuid.UUID] = (),
    attached_document: AttachedDocument | None = None,
) -> ChatMessage:
    """Idempotent message insert keyed by (author, client_message_id)."""
    clean_client_id = client_message_id.strip()
    if not clean_client_id:
        raise ChatError("client_message_id_required")
    if len(clean_client_id) > 64:
        raise ChatError("client_message_id_too_long")
    clean_text = text or ""
    attach_list = [uuid.UUID(str(a)) if not isinstance(a, uuid.UUID) else a for a in attachment_ids]
    if not clean_text.strip() and not attach_list:
        raise ChatError("empty_message")
    if attached_document is not None:
        if attached_document.kind not in ALLOWED_ATTACHED_DOCUMENT_KINDS:
            raise ChatError("bad_document_kind")
        if attached_document.seller_id != conv.seller_id:
            raise ChatError("document_seller_mismatch")

    existing_stmt = select(ChatMessage).where(
        ChatMessage.author_user_id == author.id,
        ChatMessage.client_message_id == clean_client_id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        if existing.conversation_id != conv.id or existing.tenant_id != conv.tenant_id:
            raise ChatError("client_message_id_conflict")
        return existing

    msg = ChatMessage(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        author_user_id=author.id,
        client_message_id=clean_client_id,
        text=clean_text,
        created_at=datetime.now(UTC),
        attached_document=(attached_document.to_json() if attached_document is not None else None),
    )
    try:
        async with session.begin_nested():
            session.add(msg)
            await session.flush()
            if attach_list:
                await _attach_uploads_to_message(session, conv, author, msg, attach_list)
    except IntegrityError:
        row = (await session.execute(existing_stmt)).scalar_one_or_none()
        if row is None:
            raise
        if row.conversation_id != conv.id or row.tenant_id != conv.tenant_id:
            raise ChatError("client_message_id_conflict") from None
        return row

    # Refresh conversation updated_at.
    conv.updated_at = datetime.now(UTC)
    await session.flush()
    return msg


async def edit_message(
    session: AsyncSession,
    msg: ChatMessage,
    author: User,
    *,
    new_text: str,
) -> ChatMessage:
    if msg.author_user_id != author.id:
        raise ChatError("forbidden", "only author can edit")
    if msg.deleted_at is not None:
        raise ChatError("deleted")
    text = new_text or ""
    if not text.strip():
        raise ChatError("empty_message")
    msg.text = text
    msg.edited_at = datetime.now(UTC)
    await session.flush()
    return msg


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


async def load_attachment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> ChatAttachment | None:
    stmt = select(ChatAttachment).where(
        ChatAttachment.id == attachment_id,
        ChatAttachment.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_attachments_for_messages(
    session: AsyncSession,
    conv: ChatConversation,
    message_ids: Iterable[uuid.UUID],
) -> list[ChatAttachment]:
    ids = list(message_ids)
    if not ids:
        return []
    stmt = select(ChatAttachment).where(
        ChatAttachment.tenant_id == conv.tenant_id,
        ChatAttachment.conversation_id == conv.id,
        ChatAttachment.message_id.in_(ids),
    )
    return list((await session.execute(stmt)).scalars())


async def _attach_uploads_to_message(
    session: AsyncSession,
    conv: ChatConversation,
    uploader: User,
    msg: ChatMessage,
    attachment_ids: list[uuid.UUID],
) -> None:
    stmt = (
        select(ChatAttachment)
        .where(
            ChatAttachment.id.in_(attachment_ids),
            ChatAttachment.tenant_id == conv.tenant_id,
            ChatAttachment.uploader_user_id == uploader.id,
            ChatAttachment.conversation_id == conv.id,
            ChatAttachment.message_id.is_(None),
        )
        .order_by(ChatAttachment.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    rows = list((await session.execute(stmt)).scalars())
    if len(rows) != len(attachment_ids):
        raise ChatError("attachment_not_owned")
    from app.services.chat_attachment_storage import MAX_MESSAGE_TOTAL_BYTES

    if sum(row.size_bytes for row in rows) > MAX_MESSAGE_TOTAL_BYTES:
        raise ChatError("message_files_too_large")
    for row in rows:
        row.message_id = msg.id
    await session.flush()


# ---------------------------------------------------------------------------
# Helpers used by the API layer
# ---------------------------------------------------------------------------


async def resolve_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> Seller | None:
    stmt = select(Seller).where(
        Seller.id == seller_id,
        Seller.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_visible_main_chats(
    session: AsyncSession,
    user: User,
    *,
    effective_seller_id: uuid.UUID | None,
) -> None:
    """One missing-seller query, bounded bulk inserts, no per-seller reads."""
    missing = (
        select(Seller.id)
        .where(
            Seller.tenant_id == user.tenant_id,
            ~select(ChatConversation.id)
            .where(
                ChatConversation.tenant_id == user.tenant_id,
                ChatConversation.seller_id == Seller.id,
                ChatConversation.kind == CHAT_KIND_MAIN,
            )
            .exists(),
        )
        .order_by(Seller.id)
    )
    if user.role == FULFILLMENT_SELLER:
        missing = missing.where(Seller.id == effective_seller_id)
    seller_ids = list((await session.execute(missing)).scalars())
    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    for start in range(0, len(seller_ids), 100):
        statement = (
            insert(ChatConversation)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": user.tenant_id,
                        "seller_id": sid,
                        "kind": CHAT_KIND_MAIN,
                        "created_by_user_id": user.id,
                    }
                    for sid in seller_ids[start : start + 100]
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[ChatConversation.tenant_id, ChatConversation.seller_id],
                index_where=ChatConversation.kind == CHAT_KIND_MAIN,
            )
        )
        await session.execute(statement)


async def require_draft_upload_budget(
    session: AsyncSession,
    uploader: User,
    size_bytes: int,
) -> None:
    """Bound unpublished bytes/rows across ALL chats from existing attachments.

    The existing user row serializes simultaneous uploads on PostgreSQL. No
    counter or expiry marker is stored, and nothing is automatically deleted.
    Posting a message frees its uploads from this derived draft budget.
    """
    from app.services.chat_attachment_storage import (
        MAX_MESSAGE_ATTACHMENTS,
        MAX_MESSAGE_TOTAL_BYTES,
    )

    await session.execute(
        select(User.id)
        .where(
            User.id == uploader.id,
            User.tenant_id == uploader.tenant_id,
        )
        .with_for_update()
    )
    used_bytes, used_files = (
        await session.execute(
            select(
                func.coalesce(func.sum(ChatAttachment.size_bytes), 0),
                func.count(ChatAttachment.id),
            ).where(
                ChatAttachment.tenant_id == uploader.tenant_id,
                ChatAttachment.uploader_user_id == uploader.id,
                ChatAttachment.message_id.is_(None),
            )
        )
    ).one()
    if used_bytes + size_bytes > MAX_MESSAGE_TOTAL_BYTES or used_files >= MAX_MESSAGE_ATTACHMENTS:
        raise ChatError("draft_upload_budget_exceeded")
