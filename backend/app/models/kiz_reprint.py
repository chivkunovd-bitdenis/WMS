from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User


class KizReprint(Base):
    """Append-only FF history for scanned KIZ reprints.

    This deliberately does not reference ``MarkingCode`` or a marking pool:
    scanning a label to print it again is not a pool allocation or a warehouse
    lifecycle transition.
    """

    __tablename__ = "kiz_reprints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "seller_id",
            "idempotency_key",
            name="uq_kiz_reprints_tenant_seller_idempotency",
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
    # Full normalized scanner payload, including GS (0x1D) separators.
    kiz: Mapped[str] = mapped_column(String(512), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # A scan becomes successful only after the browser has actually started the
    # print dialog.  The claim serializes that one automatic launch across a
    # repeated delivery of the same scan request.
    print_claim_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    print_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    created_by_user: Mapped[User | None] = relationship("User")
