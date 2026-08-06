"""Application settings: SQLite path and seller token map."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """WB emulator configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(
        default=Path("/data/wb_emulator.sqlite"),
        validation_alias="WB_EMULATOR_DB_PATH",
    )
    token_map: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="WB_EMULATOR_TOKEN_MAP",
    )
    token_map_file: Path | None = Field(
        default=None,
        validation_alias="WB_EMULATOR_TOKEN_MAP_FILE",
    )
    allow_dynamic_test_tokens: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "WB_EMULATOR_ALLOW_DYNAMIC_TEST_TOKENS",
            "allow_dynamic_test_tokens",
        ),
    )

    @field_validator("token_map", mode="before")
    @classmethod
    def parse_token_map(cls, value: Any) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(token): str(seller_key) for token, seller_key in value.items()}
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise TypeError("WB_EMULATOR_TOKEN_MAP must be a JSON object")
            return {str(token): str(seller_key) for token, seller_key in parsed.items()}
        raise TypeError("WB_EMULATOR_TOKEN_MAP must be a JSON object")

    def resolved_token_map(self) -> dict[str, str]:
        """Merge token map from env and optional JSON file (file overrides env)."""
        merged = dict(self.token_map)
        if self.token_map_file is not None:
            path = self.token_map_file.expanduser()
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"{path} must contain a JSON object TOKEN -> seller_key")
            merged.update({str(token): str(seller_key) for token, seller_key in raw.items()})
        return merged

    def seller_key_for_token(self, token: str) -> str | None:
        if not token:
            return None
        mapped = self.resolved_token_map().get(token)
        if mapped is not None:
            return mapped
        if self.allow_dynamic_test_tokens and token.startswith("wms-test-"):
            return token
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
