from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentSequence(Base):
    """Per-tenant daily counter for human-readable document numbers."""

    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "doc_type",
            "date",
            name="uq_document_sequences_tenant_type_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_date: Mapped[date] = mapped_column("date", Date, nullable=False)
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DocumentDisplaySequence(Base):
    """Per-tenant counter for user-facing document numbers."""

    __tablename__ = "document_display_sequences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "doc_type",
            name="uq_document_display_sequences_tenant_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
