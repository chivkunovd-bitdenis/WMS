from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.settings import settings


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    seller_id: uuid.UUID | None = None,
) -> str:
    now = datetime.now(tz=UTC)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
        "iat": now,
    }
    if seller_id is not None:
        payload["seller_id"] = str(seller_id)
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
