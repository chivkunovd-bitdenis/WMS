from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class MarketplaceAccount(Base):
    """Scoped provider credentials.  S0 addresses the hidden ``primary`` slot only."""

    __tablename__ = "marketplace_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "seller_id", "marketplace", "account_slot",
            name="uq_marketplace_accounts_scope_slot",
        ),
        CheckConstraint("marketplace <> ''", name="ck_marketplace_accounts_marketplace_nonempty"),
        CheckConstraint("account_slot <> ''", name="ck_marketplace_accounts_slot_nonempty"),
        Index(
            "ix_marketplace_accounts_tenant_seller_marketplace_active",
            "tenant_id", "seller_id", "marketplace", "is_active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    account_slot: Mapped[str] = mapped_column(String(64), nullable=False, default="primary")
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_encrypted: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_configured"
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_validation_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credentials_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="marketplace_accounts")
