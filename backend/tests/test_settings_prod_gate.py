from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings

_FERNET_KEY = "dGVzdC1mZXJuZXQta2V5LXRlc3Qta2V5LXRlc3Qta2V5dGVzdA=="
_SAFE_JWT = "production-jwt-secret-not-default-value"


def test_prod_requires_fernet_key() -> None:
    with pytest.raises(ValidationError, match="wms_secrets_fernet_key must be set"):
        Settings(
            app_env="production",
            jwt_secret_key=_SAFE_JWT,
            wms_secrets_fernet_key=None,
        )


def test_prod_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="jwt_secret_key must be overridden"):
        Settings(
            app_env="production",
            jwt_secret_key="change-me-in-production-use-long-random-secret",
            wms_secrets_fernet_key=_FERNET_KEY,
        )


def test_prod_accepts_explicit_secrets() -> None:
    cfg = Settings(
        app_env="production",
        jwt_secret_key=_SAFE_JWT,
        wms_secrets_fernet_key=_FERNET_KEY,
    )
    assert cfg.app_env == "production"
    assert cfg.wms_secrets_fernet_key == _FERNET_KEY


def test_development_allows_missing_fernet_key() -> None:
    cfg = Settings(app_env="development", wms_secrets_fernet_key=None)
    assert cfg.wms_secrets_fernet_key is None
