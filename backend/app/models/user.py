from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, case, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import SQLColumnExpression

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ff_staff_permissions import FfStaffPermissions
    from app.models.seller import Seller
    from app.models.seller_shop_delegation import SellerShopDelegation
    from app.models.seller_staff_permissions import SellerStaffPermissions
    from app.models.tenant import Tenant


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ix_users_ff_email", "email", unique=True,
            postgresql_where=text("role <> 'fulfillment_seller' AND email IS NOT NULL"),
            sqlite_where=text("role <> 'fulfillment_seller' AND email IS NOT NULL"),
        ),
        Index(
            "ix_users_seller_email", "email", unique=True,
            postgresql_where=text("role = 'fulfillment_seller' AND email IS NOT NULL"),
            sqlite_where=text("role = 'fulfillment_seller' AND email IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @hybrid_property
    def display_name(self) -> str:
        return (self.full_name or "").strip() or "ФИО не указано"

    @display_name.inplace.expression
    @classmethod
    def _display_name_expression(cls) -> SQLColumnExpression[str]:
        return case(
            (cls.id.is_(None), None),
            else_=func.coalesce(func.nullif(func.trim(cls.full_name), ""), "ФИО не указано"),
        )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_set_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    can_manage_seller_shops: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    packaging_rate_kopecks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")
    seller: Mapped[Seller | None] = relationship("Seller", back_populates="users")
    ff_staff_permissions: Mapped[FfStaffPermissions | None] = relationship(
        "FfStaffPermissions",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    seller_staff_permissions: Mapped[SellerStaffPermissions | None] = relationship(
        "SellerStaffPermissions",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    shop_delegations: Mapped[list[SellerShopDelegation]] = relationship(
        "SellerShopDelegation",
        back_populates="user",
        cascade="all, delete-orphan",
    )
