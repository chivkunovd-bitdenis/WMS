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
from typing import Annotated, Any, NoReturn
from urllib.parse import quote

import fitz
from fastapi import (
    APIRouter,
    Depends,
    File,
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
    get_effective_seller_id,
    require_ff_or_seller,
    require_fulfillment_admin,
)
from app.core.roles import FF_PORTAL_ROLES, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.chat import (
    CHAT_KIND_EXTRA,
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    ChatParticipant,
)
from app.models.seller import Seller
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
from app.services.chat_document_service import (
    DocumentKey,
    read_document,
    read_document_cards,
    readable_document_kinds,
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
    text: str = Field(default="", max_length=20000)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    attached_document: AttachedDocumentIn | None = None


class MessageEditIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


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
    author_label: str = "Участник"
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


def _message_out(msg: ChatMessage, attachments: list[ChatAttachment] | None = None) -> MessageOut:
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


def _raise_chat_error(exc: chat_service.ChatError) -> NoReturn:
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
    if code == "main_participants_implicit":
        raise HTTPException(422, detail=code)
    if code == "document_not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=code)
    if code in {"message_files_too_large", "draft_upload_budget_exceeded"}:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=code)
    if code in {"deleted", "client_message_id_conflict"}:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=code)
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=code)


async def _visible_messages_out(
    session: AsyncSession,
    user: User,
    effective_seller_id: uuid.UUID | None,
    messages: list[ChatMessage],
    attachments: dict[uuid.UUID, list[ChatAttachment]],
) -> list[MessageOut]:
    keys: dict[uuid.UUID, DocumentKey] = {}
    for msg in messages:
        if msg.attached_document:
            try:
                doc = msg.attached_document
                keys[msg.id] = (doc["kind"], uuid.UUID(doc["id"]), uuid.UUID(doc["seller_id"]))
            except (KeyError, ValueError, TypeError):
                pass
    cards = await read_document_cards(
        session, user, keys.values(), effective_seller_id=effective_seller_id
    )
    authors = (
        {
            author.id: author.email
            for author in (
                await session.execute(
                    select(User).where(
                        User.tenant_id == user.tenant_id,
                        User.id.in_({m.author_user_id for m in messages}),
                    )
                )
            ).scalars()
        }
        if messages
        else {}
    )
    result = []
    for msg in messages:
        row = _message_out(msg, attachments.get(msg.id, []))
        row.author_label = authors.get(msg.author_user_id, "Участник")
        row.attached_document = cards.get(keys[msg.id]) if msg.id in keys else None
        result.append(row)
    return result


async def _visible_message_out(
    session: AsyncSession,
    user: User,
    effective_seller_id: uuid.UUID | None,
    msg: ChatMessage,
    attachments: list[ChatAttachment],
) -> MessageOut:
    return (
        await _visible_messages_out(
            session, user, effective_seller_id, [msg], {msg.id: attachments}
        )
    )[0]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ConversationListOut:
    await chat_service.ensure_visible_main_chats(
        session, user, effective_seller_id=effective_seller_id
    )
    await session.commit()
    convs = await chat_service.list_conversations_for_user(
        session, user, effective_seller_id=effective_seller_id
    )
    return ConversationListOut(items=[_conversation_out(c) for c in convs])


@router.get("/conversations/main", response_model=ConversationOut)
async def get_main_chat(
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ConversationOut:
    """Return the seller's main chat, creating it on first call."""
    resolved_seller_id = seller_id or effective_seller_id
    if resolved_seller_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="seller_id_required")
    # A seller may only ask for their own seller_id.
    if user.role == FULFILLMENT_SELLER and resolved_seller_id != effective_seller_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    seller = await chat_service.resolve_seller(session, user.tenant_id, resolved_seller_id)
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
    seller = await chat_service.resolve_seller(session, admin.tenant_id, payload.seller_id)
    if seller is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    # Validate participants live in the same tenant.
    if payload.participant_user_ids:
        stmt = select(User).where(
            User.id.in_(payload.participant_user_ids),
            User.tenant_id == admin.tenant_id,
        )
        users = list((await session.execute(stmt)).scalars())
        if len(users) != len(set(payload.participant_user_ids)) or any(
            not _eligible_participant(u, payload.seller_id) for u in users
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_participants")
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
    conv = await chat_service.load_conversation(session, user.tenant_id, conversation_id)
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
    conv = await _require_readable_conversation(conversation_id, user, session, effective_seller_id)
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
    conv = await _require_readable_conversation(conversation_id, user, session, effective_seller_id)
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
    conv = await chat_service.load_conversation(session, admin.tenant_id, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    if conv.kind != CHAT_KIND_EXTRA:
        raise HTTPException(422, detail="main_participants_implicit")
    stmt = select(User).where(User.id == payload.user_id, User.tenant_id == admin.tenant_id)
    user_to_add = (await session.execute(stmt)).scalar_one_or_none()
    if user_to_add is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if not _eligible_participant(user_to_add, conv.seller_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="bad_participants")
    if not await chat_service.can_read_conversation(session, admin, conv, effective_seller_id=None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        row = await chat_service.add_participant(session, conv, user_to_add, added_by=admin)
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
    before: uuid.UUID | None = None,
) -> MessageListOut:
    conv = await _require_readable_conversation(conversation_id, user, session, effective_seller_id)
    msgs = await chat_service.list_messages(session, conv, limit=limit, before=before)
    attachments_by_msg: dict[uuid.UUID, list[ChatAttachment]] = {}
    if msgs:
        rows = await chat_service.list_attachments_for_messages(session, conv, [m.id for m in msgs])
        for att in rows:
            if att.message_id is None:
                continue
            attachments_by_msg.setdefault(att.message_id, []).append(att)
    return MessageListOut(
        items=await _visible_messages_out(
            session, user, effective_seller_id, msgs, attachments_by_msg
        )
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
    conv = await _require_readable_conversation(conversation_id, user, session, effective_seller_id)
    if len(payload.attachment_ids) > MAX_MESSAGE_ATTACHMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="too_many_attachments")
    attached_doc: chat_service.AttachedDocument | None = None
    if payload.attached_document is not None:
        # For a document, verify seller matches the conversation seller.
        if payload.attached_document.seller_id != conv.seller_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="document_seller_mismatch"
            )
        try:
            actual = await read_document(
                session,
                user,
                kind=payload.attached_document.kind,
                document_id=payload.attached_document.id,
                seller_id=conv.seller_id,
                effective_seller_id=effective_seller_id,
            )
        except chat_service.ChatError as exc:
            _raise_chat_error(exc)
        attached_doc = chat_service.AttachedDocument(
            kind=actual["document"]["kind"],
            id=uuid.UUID(actual["document"]["id"]),
            title=actual["document"]["title"],
            seller_id=conv.seller_id,
            seller_name=actual["document"].get("seller_name"),
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
    attachments = await chat_service.list_attachments_for_messages(session, conv, [msg.id])
    return await _visible_message_out(session, user, effective_seller_id, msg, attachments)


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
    conv = await chat_service.load_conversation(session, user.tenant_id, msg.conversation_id)
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
    attachments = await chat_service.list_attachments_for_messages(session, conv, [msg.id])
    return await _visible_message_out(session, user, effective_seller_id, msg, attachments)


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
) -> AttachmentOut:
    conv = await _require_readable_conversation(conversation_id, user, session, effective_seller_id)
    raw = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_file")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="file_too_large")
    raw_content_type = file.content_type or "application/octet-stream"
    if len(raw_content_type) > 128 or any(ord(c) < 32 or ord(c) > 126 for c in raw_content_type):
        raise HTTPException(422, detail="invalid_content_type")
    content_type = raw_content_type.strip() or "application/octet-stream"
    filename = (file.filename or "file").replace("\r", "").replace("\n", "").strip()[:255] or "file"
    detected_image = is_image_content_type(content_type)
    resolved_image = detected_image
    if detected_image:
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif raw.startswith((b"GIF87a", b"GIF89a")):
            content_type = "image/gif"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            content_type = "image/webp"
        elif raw.startswith(b"BM"):
            content_type = "image/bmp"
        else:
            raise HTTPException(422, detail="invalid_image")
        try:
            with fitz.open(stream=raw) as image:
                if image.metadata.get("format") != "Image" or image.page_count < 1:
                    raise ValueError("invalid_image")
                if image[0].rect.width * image[0].rect.height > 40_000_000:
                    raise ValueError("image_too_large")
        except (RuntimeError, ValueError):
            raise HTTPException(422, detail="invalid_image") from None
    try:
        await chat_service.require_draft_upload_budget(session, user, len(raw))
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
    attachment_id = uuid.uuid4()
    storage_key = build_storage_key(user.tenant_id, attachment_id, filename)
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
    # Reject database constraints before writing an object. Storage and SQL do
    # not share a transaction; a later commit failure still needs an explicit
    # reconciliation contract, not automatic deletion of user files here.
    await session.flush()
    try:
        put_bytes(storage_key, raw, content_type=content_type)
    except Exception as exc:  # pragma: no cover — depends on backend
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"storage_unavailable:{type(exc).__name__}",
        ) from exc
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
    conv = await chat_service.load_conversation(session, user.tenant_id, row.conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found")
    # Draft uploads belong to their uploader. Every download also requires
    # current chat access, including downloads by a removed uploader.
    if (
        row.message_id is None and row.uploader_user_id != user.id
    ) or not await chat_service.can_read_conversation(
        session, user, conv, effective_seller_id=effective_seller_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        content = get_bytes(row.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="content_not_found") from None
    disposition = "inline" if row.is_image else "attachment"
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(row.filename, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, no-store",
    }
    return Response(
        content=content,
        media_type=row.content_type,
        headers=headers,
    )


# Re-exported for tests to avoid touching internals.
__all__ = [
    "ConversationOut",
    "MessageIn",
    "MessageOut",
    "router",
]


def _eligible_participant(user: User, seller_id: uuid.UUID) -> bool:
    return user.role in FF_PORTAL_ROLES or (
        user.role == FULFILLMENT_SELLER and user.seller_id == seller_id
    )


@router.get("/participant-options")
async def participant_options(
    seller_id: uuid.UUID,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, str]]:
    if await chat_service.resolve_seller(session, admin.tenant_id, seller_id) is None:
        raise HTTPException(404, detail="seller_not_found")
    users = (await session.execute(select(User).where(User.tenant_id == admin.tenant_id))).scalars()
    return [
        {"id": str(u.id), "email": u.email, "role": u.role}
        for u in users
        if _eligible_participant(u, seller_id)
    ]


@router.get("/documents/{kind}/{document_id}")
async def get_document(
    kind: str,
    document_id: uuid.UUID,
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> dict[str, Any]:
    try:
        return await read_document(
            session,
            user,
            kind=kind,
            document_id=document_id,
            seller_id=seller_id,
            effective_seller_id=effective_seller_id,
        )
    except chat_service.ChatError as exc:
        _raise_chat_error(exc)
        raise AssertionError("unreachable") from exc


@router.get("/document-options/{kind}/{document_id}")
async def document_options(
    kind: str,
    document_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[dict[str, Any]]:
    if kind not in chat_service.ALLOWED_ATTACHED_DOCUMENT_KINDS:
        raise HTTPException(422, detail="bad_document_kind")
    if kind not in await readable_document_kinds(session, user):
        raise HTTPException(403, detail="forbidden")
    stmt = select(Seller.id).where(Seller.tenant_id == user.tenant_id)
    if user.role == FULFILLMENT_SELLER:
        stmt = stmt.where(Seller.id == effective_seller_id)
    seller_ids = (await session.execute(stmt.order_by(Seller.id))).scalars().all()
    cards = await read_document_cards(
        session,
        user,
        [(kind, document_id, sid) for sid in seller_ids],
        effective_seller_id=effective_seller_id,
    )
    return [
        cards[(kind, document_id, sid)] for sid in seller_ids if (kind, document_id, sid) in cards
    ]
