from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller
    from app.models.tenant import Tenant

WB_OPERATION_STATE_PENDING = "pending"
WB_OPERATION_STATE_CONFIRMED = "confirmed"
WB_OPERATION_STATE_FAILED = "failed"
WB_OPERATION_STATE_PENDING_CONFIRMATION = "pending_confirmation"
FBS_WB_OPERATION_STATES = frozenset(
    {
        WB_OPERATION_STATE_PENDING,
        WB_OPERATION_STATE_CONFIRMED,
        WB_OPERATION_STATE_FAILED,
        WB_OPERATION_STATE_PENDING_CONFIRMATION,
    }
)


class FbsWbOperation(Base):
    """Journal of external Wildberries operations with idempotency."""

    __tablename__ = "fbs_wb_operations"
    __table_args__ = (
        UniqueConstraint(
            "seller_id",
            "operation_kind",
            "idempotency_key",
            name="uq_fbs_wb_operations_seller_kind_idempotency",
        ),
        Index("ix_fbs_wb_operations_tenant_seller_state", "tenant_id", "seller_id", "state"),
        Index(
            "ix_fbs_wb_operations_local_entity",
            "local_entity_type",
            "local_entity_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    operation_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wb_object_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wb_object_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    local_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    local_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WB_OPERATION_STATE_PENDING,
        server_default=WB_OPERATION_STATE_PENDING,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    request_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
