"""Chat REST endpoints — WMS-397/WMS-399.

Routes:

* ``GET /operations/chat/conversations`` — visible conversations for user
* ``GET /operations/chat/conversations/main?seller_id=`` — main chat for a
  seller; auto-creates on first read (idempotent)
* ``POST /operations/chat/conversations/extra`` — FF admin creates an extra
  chat with initial participants
* ``GET /operations/chat/conversations/{id}`` — meta only
* ``GET /operations/chat/conversations/{id}/participants``
* ``POST /operations/chat/conversations/{id}/participants``
* ``GET /operations/chat/conversations/{id}/messages``
* ``POST /operations/chat/conversations/{id}/messages``
* ``PATCH /operations/chat/messages/{id}``
* ``POST /operations/chat/conversations/{id}/attachments`` — multipart upload
* ``GET /operations/chat/attachments/{id}/content`` — proxy download

Authorization uses the existing ``require_ff_or_seller`` guard plus
``chat_service.can_read_conversation`` for per-conversation access.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_effective_seller_id,
    require_ff_or_seller,
    require_fulfillment_admin,
)
from app.db.session import get_db
from app.models.chat import (
    CHAT_KIND_EXTRA,
    CHAT_KIND_MAIN,
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    ChatParticipant,
)
from app.models.user import User
from app.services import chat_service
from app.services.chat_attachment_storage import (
    MAX_ATTACHMENT_BYTES,
    MAX_MESSAGE_ATTACHMENTS,
    build_storage_key,
    get_bytes,
    is_image_content_type,
    put_bytes,
)

router = APIRouter(prefix="/operations/chat", tags=["operations", "chat"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConversationOut(BaseModel):
    id: str
    tenant_id: str
    seller_id: str
    kind: str
    title: str | None
    created_at: str
    updated_at: str


class ConversationListOut(BaseModel):
    items: list[ConversationOut]


class ExtraChatIn(BaseModel):
    seller_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    participant_user_ids: list[uuid.UUID] = Field(default_factory=list)


class ParticipantOut(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    added_at: str


class ParticipantListOut(BaseModel):
    items: list[ParticipantOut]


class ParticipantIn(BaseModel):
    user_id: uuid.UUID


class AttachedDocumentIn(BaseModel):
    kind: str
    id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    seller_id: uuid.UUID
    seller_name: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_valid(cls, value: str) -> str:
        if value not in chat_service.ALLOWED_ATTACHED_DOCUMENT_KINDS:
            raise ValueError("kind_not_allowed")
        return value


class MessageIn(BaseModel):
    client_message_id: str = Field(..., min_length=1, max_length=64)
    text: str = ""
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    attached_document: AttachedDocumentIn | None = None


class MessageEditIn(BaseModel):
    text: str = Field(..., min_length=1)


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    is_image: bool
    created_at: str


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    author_user_id: str
    client_message_id: str
    text: str
    attached_document: dict[str, Any] | None
    attachments: list[AttachmentOut]
    edited_at: str | None
    deleted_at: str | None
    created_at: str


class MessageListOut(BaseModel):
    items: list[MessageOut]


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _conversation_out(conv: ChatConversation) -> ConversationOut:
    return ConversationOut(
        id=str(conv.id),
        tenant_id=str(conv.tenant_id),
        seller_id=str(conv.seller_id),
        kind=conv.kind,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
    )


def _participant_out(row: ChatParticipant) -> ParticipantOut:
    return ParticipantOut(
        id=str(row.id),
        conversation_id=str(row.conversation_id),
        user_id=str(row.user_id),
        added_at=row.added_at.isoformat(),
    )


def _attachment_out(row: ChatAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=str(row.id),
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        is_image=row.is_image,
        created_at=row.created_at.isoformat(),
    )


def _message_out(
    msg: ChatMessage, attachments: list[ChatAttachment] | None = None
) -> MessageOut:
    return MessageOut(
        id=str(msg.id),
        conversation_id=str(msg.conversation_id),
        author_user_id=str(msg.author_user_id),
        client_message_id=msg.client_message_id,
        text=msg.text,
        attached_document=msg.attached_document,
        attachments=[_attachment_out(a) for a in (attachments or [])],
        edited_at=msg.edited_at.isoformat() if msg.edited_at else None,
        deleted_at=msg.deleted_at.isoformat() if msg.deleted_at else None,
        created_at=msg.created_at.isoformat(),
    )


def _raise_chat_error(exc: chat_service.ChatError) -> None:
    code = exc.code
    if code == "forbidden":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=code)
    if code in {"empty_message", "empty_file", "title_required"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)
    if code in {
        "attachment_not_owned",
        "document_seller_mismatch",
        "bad_document_kind",
        "cross_tenant",
        "client_message_id_required",
        "client_message_id_too_long",
    }:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)
    if code == "deleted":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=code)
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=code)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ConversationListOut:
    convs = await chat_service.list_conversations_for_user(
        session, user, effective_seller_id=effective_seller_id
    )
    return ConversationListOut(items=[_conversation_out(c) for c in convs])


@router.get("/conversations/main", response_model=ConversationOut)
async def get_main_chat(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: uuid.UUID | None = Query(default=None),
) -> ConversationOut:
    """Return the seller's main chat, creating it on first call."""
    resolved_seller_id = seller_id or effective_seller_id
    if resolved_seller_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="seller_id_required"
        )
    # A seller may only ask for their own seller_id.
    if effective_seller_id is not None and resolved_seller_id != effective_seller_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    seller = await chat_service.resolve_seller(
        session, user.tenant_id, resolved_seller_id
    )
    if seller is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    conv = await chat_service.ensure_main_chat(
        session,
        tenant_id=user.tenant_id,
        seller_id=resolved_seller_id,
        created_by=user,
    )
    await session.commit()
    await session.refresh(conv)
    return _conversation_out(conv)


@router.post(
    "/conversations/extra",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_extra_chat(
    payload: ExtraChatIn,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    seller = await chat_service.resolve_seller(
        session, admin.tenant_id, payload.seller_id
    )
    if seller is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    # Validate participants live in the same tenant.
    if payload.participant_user_ids:
        stmt = select(User).where(
            User.id.in_(payload.participant_user_ids),
            User.tenant_id == admin.tenant_id,
        )
        users = list((await session.execute(stmt)).scalars())
        if len(users) != len(set(payload.participant_user_ids)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_participants"
            )
    try:
        conv = await chat_service.create_extra_chat(
            session,
            tenant_id=admin.tenant_id,
            seller_id=payload.seller_id,
            title=payload.title,
            created_by=admin,
            participant_user_ids=payload.participant_user_ids,
        )
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
    await session.commit()
    await session.refresh(conv)
    return _conversation_out(conv)


async def _require_readable_conversation(
    conversation_id: uuid.UUID,
    user: User,
    session: AsyncSession,
    effective_seller_id: uuid.UUID | None,
) -> ChatConversation:
    conv = await chat_service.load_conversation(
        session, user.tenant_id, conversation_id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    if not await chat_service.can_read_conversation(
        session, user, conv, effective_seller_id=effective_seller_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ConversationOut:
    conv = await _require_readable_conversation(
        conversation_id, user, session, effective_seller_id
    )
    return _conversation_out(conv)


@router.get(
    "/conversations/{conversation_id}/participants",
    response_model=ParticipantListOut,
)
async def list_participants(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ParticipantListOut:
    conv = await _require_readable_conversation(
        conversation_id, user, session, effective_seller_id
    )
    items = await chat_service.load_participants(session, conv)
    return ParticipantListOut(items=[_participant_out(p) for p in items])


@router.post(
    "/conversations/{conversation_id}/participants",
    response_model=ParticipantOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_participant(
    conversation_id: uuid.UUID,
    payload: ParticipantIn,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ParticipantOut:
    conv = await chat_service.load_conversation(
        session, admin.tenant_id, conversation_id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    stmt = select(User).where(
        User.id == payload.user_id, User.tenant_id == admin.tenant_id
    )
    user_to_add = (await session.execute(stmt)).scalar_one_or_none()
    if user_to_add is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    try:
        row = await chat_service.add_participant(
            session, conv, user_to_add, added_by=admin
        )
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
    await session.commit()
    return _participant_out(row)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListOut,
)
async def list_messages(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    limit: int = Query(default=200, ge=1, le=500),
) -> MessageListOut:
    conv = await _require_readable_conversation(
        conversation_id, user, session, effective_seller_id
    )
    msgs = await chat_service.list_messages(session, conv, limit=limit)
    attachments_by_msg: dict[uuid.UUID, list[ChatAttachment]] = {}
    if msgs:
        rows = await chat_service.list_attachments_for_messages(
            session, conv, [m.id for m in msgs]
        )
        for att in rows:
            if att.message_id is None:
                continue
            attachments_by_msg.setdefault(att.message_id, []).append(att)
    return MessageListOut(
        items=[_message_out(m, attachments_by_msg.get(m.id, [])) for m in msgs]
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MessageOut:
    conv = await _require_readable_conversation(
        conversation_id, user, session, effective_seller_id
    )
    if len(payload.attachment_ids) > MAX_MESSAGE_ATTACHMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="too_many_attachments"
        )
    attached_doc: chat_service.AttachedDocument | None = None
    if payload.attached_document is not None:
        # For a document, verify seller matches the conversation seller.
        if payload.attached_document.seller_id != conv.seller_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="document_seller_mismatch"
            )
        attached_doc = chat_service.AttachedDocument(
            kind=payload.attached_document.kind,
            id=payload.attached_document.id,
            title=payload.attached_document.title,
            seller_id=payload.attached_document.seller_id,
            seller_name=payload.attached_document.seller_name,
        )
    try:
        msg = await chat_service.post_message(
            session,
            conv,
            user,
            client_message_id=payload.client_message_id,
            text=payload.text,
            attachment_ids=payload.attachment_ids,
            attached_document=attached_doc,
        )
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
    await session.commit()
    await session.refresh(msg)
    attachments = await chat_service.list_attachments_for_messages(
        session, conv, [msg.id]
    )
    return _message_out(msg, attachments)


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: uuid.UUID,
    payload: MessageEditIn,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MessageOut:
    stmt = select(ChatMessage).where(
        ChatMessage.id == message_id, ChatMessage.tenant_id == user.tenant_id
    )
    msg = (await session.execute(stmt)).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="message_not_found")
    conv = await chat_service.load_conversation(
        session, user.tenant_id, msg.conversation_id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    if not await chat_service.can_read_conversation(
        session, user, conv, effective_seller_id=effective_seller_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        msg = await chat_service.edit_message(session, msg, user, new_text=payload.text)
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
    await session.commit()
    await session.refresh(msg)
    attachments = await chat_service.list_attachments_for_messages(
        session, conv, [msg.id]
    )
    return _message_out(msg, attachments)


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    conversation_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    is_image: Annotated[bool | None, Form()] = None,
) -> AttachmentOut:
    conv = await _require_readable_conversation(
        conversation_id, user, session, effective_seller_id
    )
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_file")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large"
        )
    content_type = (file.content_type or "application/octet-stream").strip()
    filename = (file.filename or "file").strip() or "file"
    detected_image = is_image_content_type(content_type)
    resolved_image = detected_image if is_image is None else bool(is_image)
    attachment_id = uuid.uuid4()
    storage_key = build_storage_key(user.tenant_id, attachment_id, filename)
    try:
        put_bytes(storage_key, raw, content_type=content_type)
    except Exception as exc:  # pragma: no cover — depends on backend
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"storage_unavailable:{type(exc).__name__}",
        ) from exc
    # Instantiate the ORM row with a caller-chosen id so it matches storage.
    row = ChatAttachment(
        id=attachment_id,
        tenant_id=conv.tenant_id,
        uploader_user_id=user.id,
        conversation_id=conv.id,
        message_id=None,
        filename=filename,
        content_type=content_type,
        size_bytes=len(raw),
        is_image=resolved_image,
        storage_key=storage_key,
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return _attachment_out(row)


@router.get("/attachments/{attachment_id}/content")
async def download_attachment(
    attachment_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> Response:
    row = await chat_service.load_attachment(session, user.tenant_id, attachment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="attachment_not_found")
    conv = await chat_service.load_conversation(
        session, user.tenant_id, row.conversation_id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    # Uploader can always fetch their own upload (needed for drafts before
    # the message is created); everyone else needs read access to the chat.
    if row.uploader_user_id != user.id and not await chat_service.can_read_conversation(
        session, user, conv, effective_seller_id=effective_seller_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        content = get_bytes(row.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="content_not_found") from None
    headers = {
        "Content-Disposition": f'inline; filename="{row.filename}"',
    }
    return Response(
        content=content,
        media_type=row.content_type,
        headers=headers,
    )


__all__ = [
    "router",
    # Re-exported for tests to avoid touching internals.
    "ConversationOut",
    "MessageOut",
    "MessageIn",
]


# Silence unused-import warnings for imports that stay in the annotations.
_ = (CHAT_KIND_MAIN, CHAT_KIND_EXTRA, get_current_user, datetime)
