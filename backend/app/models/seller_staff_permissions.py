from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SellerStaffPermissions(Base):
    __tablename__ = "seller_staff_permissions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_products: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_honest_sign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_settings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship("User", back_populates="seller_staff_permissions")
