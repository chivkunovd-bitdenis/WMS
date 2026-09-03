from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.document_event import DocumentEvent
from app.models.user import User
from app.services.document_event_service import list_document_events

router = APIRouter(prefix="/operations/document-events", tags=["document-events"])


class DocumentEventActorOut(BaseModel):
    id: uuid.UUID
    name: str


class DocumentEventProductOut(BaseModel):
    id: uuid.UUID
    name: str


class DocumentEventOut(BaseModel):
    id: uuid.UUID
    document_type: str
    document_id: uuid.UUID
    event_type: str
    actor: DocumentEventActorOut | None
    source: str
    occurred_at: datetime
    qty: int | None
    product: DocumentEventProductOut | None
    payload: dict[str, Any]


def _event_out(event: DocumentEvent) -> DocumentEventOut:
    actor = (
        DocumentEventActorOut(id=event.actor.id, name=event.actor.email)
        if event.actor is not None
        else None
    )
    product = (
        DocumentEventProductOut(id=event.product.id, name=event.product.name)
        if event.product is not None
        else None
    )
    return DocumentEventOut(
        id=event.id,
        document_type=event.document_type,
        document_id=event.document_id,
        event_type=event.event_type,
        actor=actor,
        source=event.source,
        occurred_at=event.occurred_at,
        qty=event.qty,
        product=product,
        payload=event.payload_json,
    )


@router.get("", response_model=list[DocumentEventOut])
async def get_document_events(
    # `fbs_order` сервис пишет, а ручка его не принимала: историю FBS-заказа
    # через этот эндпоинт было не запросить вовсе.
    document_type: Literal["inbound_intake", "fbs_supply", "marketplace_unload", "fbs_order"],
    document_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentEventOut]:
    events = await list_document_events(
        session,
        tenant_id=user.tenant_id,
        document_type=document_type,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return [_event_out(event) for event in events]
