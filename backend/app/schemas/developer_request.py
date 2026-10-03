from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class DeveloperRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: uuid.UUID
    type: Literal["bug", "improvement"]
    description: str | None = None
    screen: str | None = None
    problem: str | None = None
    proposal: str | None = None
    page_url: str | None = None

    @field_validator("description", "screen", "problem", "proposal")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("page_url")
    @classmethod
    def pathname_only(cls, value: str | None) -> str | None:
        if not value:
            return None
        path = urlsplit(value).path
        return path if path.startswith("/") else None

    @model_validator(mode="after")
    def validate_active_fields(self) -> Self:
        if self.type == "bug":
            if not self.description:
                raise ValueError("description_required")
            self.screen = self.problem = self.proposal = None
        else:
            for field in ("screen", "problem", "proposal"):
                if not getattr(self, field):
                    raise ValueError(f"{field}_required")
            self.description = None
        return self


class DeveloperRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: Literal["bug", "improvement"]
    title: str
    description: str | None
    screen: str | None
    problem: str | None
    proposal: str | None
    status: Literal["review", "queued", "in_progress", "completed"]
    created_at: datetime
    updated_at: datetime
