from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class StorageStatement(Base):
    """Immutable monthly storage document; it contains no money or tariff data."""

    __tablename__ = "storage_statements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "seller_id",
            "warehouse_id",
            "period_start",
            name="uq_storage_statements_tenant_seller_warehouse_period",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_storage_statements_period_end_after_start",
        ),
        Index(
            "ix_storage_statements_scope_status", "tenant_id", "seller_id", "warehouse_id", "status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    document_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
