from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
    from app.models.tenant import Tenant
    from app.models.user import User


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="sellers")
    users: Mapped[list[User]] = relationship("User", back_populates="seller")
    products: Mapped[list[Product]] = relationship("Product", back_populates="seller")
    wildberries_credentials: Mapped[SellerWildberriesCredentials | None] = relationship(
        "SellerWildberriesCredentials",
        back_populates="seller",
        uselist=False,
        cascade="all, delete-orphan",
    )
