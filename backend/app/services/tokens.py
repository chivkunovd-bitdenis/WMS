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
    payload: dict[str, object] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if seller_id is not None:
        payload["seller_id"] = str(seller_id)
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["iat"]},
    )
    # Existing signed sessions use the same finite lifetime from their issue time.
    # This prevents legacy tokens without exp from remaining valid indefinitely.
    if "exp" not in payload:
        issued_at = payload["iat"]
        if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
            raise jwt.InvalidIssuedAtError("invalid iat")
        expires_at = issued_at + settings.access_token_expire_minutes * 60
        if datetime.now(UTC).timestamp() >= expires_at:
            raise jwt.ExpiredSignatureError("Signature has expired")
    return payload
