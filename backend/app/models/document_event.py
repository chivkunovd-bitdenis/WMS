from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.tenant import Tenant
    from app.models.user import User


DOCUMENT_TYPE_INBOUND_INTAKE = "inbound_intake"
DOCUMENT_TYPE_FBS_SUPPLY = "fbs_supply"
DOCUMENT_TYPE_MARKETPLACE_UNLOAD = "marketplace_unload"
# Заказ FBS — тоже документ склада: по нему надо восстанавливать картину по часам.
DOCUMENT_TYPE_FBS_ORDER = "fbs_order"
DOCUMENT_TYPES = frozenset(
    {
        DOCUMENT_TYPE_INBOUND_INTAKE,
        DOCUMENT_TYPE_FBS_SUPPLY,
        DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
        DOCUMENT_TYPE_FBS_ORDER,
    }
)

EVENT_STATUS_CHANGED = "status_changed"
EVENT_LINE_ADDED = "line_added"
EVENT_LINE_REMOVED = "line_removed"
EVENT_LINE_QTY_CHANGED = "line_qty_changed"
EVENT_WAREHOUSE_CHANGED = "warehouse_changed"
EVENT_PLANNED_DATE_CHANGED = "planned_date_changed"
EVENT_DEFECT_QTY_CHANGED = "defect_qty_changed"
DOCUMENT_EVENT_TYPES = frozenset(
    {
        EVENT_STATUS_CHANGED,
        EVENT_LINE_ADDED,
        EVENT_LINE_REMOVED,
        EVENT_LINE_QTY_CHANGED,
        EVENT_WAREHOUSE_CHANGED,
        EVENT_PLANNED_DATE_CHANGED,
        EVENT_DEFECT_QTY_CHANGED,
    }
)

SOURCE_USER = "user"
SOURCE_SYSTEM = "system"
DOCUMENT_EVENT_SOURCES = frozenset({SOURCE_USER, SOURCE_SYSTEM})


class DocumentEvent(Base):
    """Append-only document status and data change."""

    __tablename__ = "document_event"
    __table_args__ = (
        Index(
            "ix_document_event_document_occurred",
            "tenant_id",
            "document_type",
            "document_id",
            "occurred_at",
        ),
        Index(
            "ix_document_event_actor_occurred",
            "tenant_id",
            "actor_user_id",
            "occurred_at",
        ),
        Index(
            "uq_document_event_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    actor: Mapped[User | None] = relationship("User")
    product: Mapped[Product | None] = relationship("Product")
