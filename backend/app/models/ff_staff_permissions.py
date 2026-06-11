from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class FfStaffPermissions(Base):
    __tablename__ = "ff_staff_permissions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_settings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_mp_shipments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_reception: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_cells: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_inventory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_packaging: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship("User", back_populates="ff_staff_permissions")
