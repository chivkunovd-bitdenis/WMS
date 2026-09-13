from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def normalize_name(value: str) -> str:
    return " ".join(value.split())


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("full_name_required")
        return value

    @field_validator("job_title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return normalize_name(value) or None if value is not None else None


class StaffIdentityCreate(BaseModel):
    email: EmailStr | None = None
    full_name: str = Field(min_length=1, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=128)

    @field_validator("full_name", "job_title")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return normalize_name(value) or None if value is not None else None

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if not self.full_name:
            raise ValueError("full_name_required")
        # Email invitation remains optional; without a delivery address the
        # manager sets the password while creating the named employee.
        if self.email is None and not self.password:
            raise ValueError("full_name_and_password_required")
        return self
