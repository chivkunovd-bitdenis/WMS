from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg_async://postgres:postgres@localhost:5432/wms",
        description="Async SQLAlchemy URL (use postgresql+psycopg_async:// for PostgreSQL).",
    )
    jwt_secret_key: str = Field(
        default="change-me-in-production-use-long-random-secret",
        min_length=16,
    )
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60 * 24)

    @property
    def database_url_sync(self) -> str:
        """Alembic and sync scripts use psycopg (sync) driver."""
        if self.database_url.startswith("postgresql+psycopg_async://"):
            return self.database_url.replace(
                "postgresql+psycopg_async://", "postgresql+psycopg://", 1
            )
        return self.database_url


settings = Settings()
