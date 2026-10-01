from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.developer_request import DeveloperRequest
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.developer_request import DeveloperRequestCreate
from app.services.developer_request_content import (
    TRELLO_DESCRIPTION_MAX_LENGTH,
    card_description,
    description_length,
)


class IdempotencyConflict(Exception):
    pass


class DescriptionTooLong(Exception):
    def __init__(self, actual_length: int) -> None:
        self.actual_length = actual_length
        super().__init__("developer_request_description_too_long")


async def create_request(
    session: AsyncSession,
    user: User,
    seller_id: uuid.UUID | None,
    body: DeveloperRequestCreate,
) -> DeveloperRequest:
    values = body.model_dump(exclude={"idempotency_key"})
    # Seller context is part of intent, although the caller cannot supply it in the body.
    canonical = {**values, "seller_id": str(seller_id) if seller_id else None}
    payload_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    query = select(DeveloperRequest).where(
        DeveloperRequest.tenant_id == user.tenant_id,
        DeveloperRequest.created_by_user_id == user.id,
        DeveloperRequest.idempotency_key == body.idempotency_key,
    )
    row = await session.scalar(query)
    if row is None:
        tenant = await session.get(Tenant, user.tenant_id)
        seller = await session.get(Seller, seller_id) if seller_id else None
        client_name = tenant.name if tenant else str(user.tenant_id)
        if seller is not None and seller.tenant_id == user.tenant_id:
            client_name += f" / {seller.name}"
        created_at = datetime.now(UTC)
        row = DeveloperRequest(
            id=uuid.uuid4(),
            created_at=created_at,
            updated_at=created_at,
            tenant_id=user.tenant_id,
            created_by_user_id=user.id,
            seller_id=seller_id,
            client_name=client_name,
            idempotency_key=body.idempotency_key,
            payload_hash=payload_hash,
            title=" ".join((body.description or body.screen or "").split())[:160],
            **values,
        )
        actual_length = description_length(card_description(row))
        if actual_length > TRELLO_DESCRIPTION_MAX_LENGTH:
            raise DescriptionTooLong(actual_length)
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError:
            # The concurrent winner commits before its unique-key conflict is returned.
            existing = await session.scalar(query)
            if existing is None:
                raise
            row = existing
    if row.payload_hash != payload_hash:
        raise IdempotencyConflict
    return row


async def list_requests(session: AsyncSession, user: User) -> list[DeveloperRequest]:
    result = await session.scalars(
        select(DeveloperRequest)
        .where(
            DeveloperRequest.tenant_id == user.tenant_id,
            DeveloperRequest.created_by_user_id == user.id,
        )
        .order_by(DeveloperRequest.created_at.desc(), DeveloperRequest.id.desc())
    )
    return list(result)


async def get_request(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
) -> DeveloperRequest | None:
    result = await session.execute(
        select(DeveloperRequest).where(
            DeveloperRequest.id == request_id,
            DeveloperRequest.tenant_id == user.tenant_id,
            DeveloperRequest.created_by_user_id == user.id,
        )
    )
    return result.scalar_one_or_none()
