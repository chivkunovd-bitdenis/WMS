from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.seller import Seller


class SellerWildberriesCredentials(Base):
    """Per-seller WB API tokens (encrypted). One row per seller when configured."""

    __tablename__ = "seller_wildberries_credentials"

    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_token_encrypted: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    supplies_token_encrypted: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="wildberries_credentials")
