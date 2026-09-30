from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.settings import settings
from app.services.tokens import create_access_token, decode_access_token


@pytest.fixture(autouse=True)
def use_test_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret_key", "test-only-signing-secret-with-enough-length")


def test_access_token_has_no_expiration() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role="fulfillment_seller",
        seller_id=seller_id,
    )

    claims = decode_access_token(token)

    assert claims["sub"] == str(user_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert claims["seller_id"] == str(seller_id)
    assert claims["role"] == "fulfillment_seller"
    assert "iat" in claims
    assert "exp" not in claims


def test_expired_access_tokens_are_rejected() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=settings.access_token_expire_minutes + 1)
    payload = {"sub": str(uuid.uuid4()), "iat": issued}
    payload["exp"] = issued + timedelta(minutes=settings.access_token_expire_minutes)
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


@pytest.mark.parametrize("age_days", [0, 3650])
def test_signed_session_without_expiration_remains_valid(age_days: int) -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": datetime.now(UTC) - timedelta(days=age_days)},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token)["sub"]


def test_access_token_still_rejects_a_foreign_signature() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "fulfillment_admin",
        },
        "a-different-secret-with-enough-length",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)
