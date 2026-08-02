"""SQLAlchemy models for emulator state (extended in later lanes)."""

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for emulator SQLite schema."""


class SchemaVersion(Base):
    """Tracks schema bootstrap so SQLite file is created on startup."""

    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
