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


def test_plain_postgresql_database_url_is_normalized() -> None:
    cfg = Settings(
        app_env="development",
        database_url="postgresql://postgres:postgres@localhost:5432/wms",
        wms_secrets_fernet_key=None,
    )
    assert cfg.database_url == "postgresql+psycopg_async://postgres:postgres@localhost:5432/wms"


def test_async_postgresql_database_url_stays_unchanged() -> None:
    url = "postgresql+psycopg_async://postgres:postgres@localhost:5432/wms"
    cfg = Settings(
        app_env="development",
        database_url=url,
        wms_secrets_fernet_key=None,
    )
    assert cfg.database_url == url


def test_cors_origins_adds_staging_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WMS_CORS_ORIGINS", "https://staging.example.com, https://admin.example.com")
    cfg = Settings(
        app_env="development",
        database_url="sqlite+aiosqlite:///:memory:",
        wms_secrets_fernet_key=None,
    )
    assert cfg.cors_allow_origins[:2] == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert "https://staging.example.com" in cfg.cors_allow_origins
    assert "https://admin.example.com" in cfg.cors_allow_origins
