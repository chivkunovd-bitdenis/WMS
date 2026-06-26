from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.packaging_task import PackagingTaskLine
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User

STATUS_AVAILABLE = "available"
STATUS_RESERVED = "reserved"
STATUS_PRINTED = "printed"
STATUS_APPLIED = "applied"
STATUS_INTRODUCED = "introduced"
STATUS_SHIPPED = "shipped"
STATUS_TRANSFERRED = "transferred"
STATUS_DEFECTIVE = "defective"
STATUS_REPLACED = "replaced"
STATUS_VOID = "void"

MARKING_CODE_STATUSES = frozenset(
    {
        STATUS_AVAILABLE,
        STATUS_RESERVED,
        STATUS_PRINTED,
        STATUS_APPLIED,
        STATUS_INTRODUCED,
        STATUS_SHIPPED,
        STATUS_TRANSFERRED,
        STATUS_DEFECTIVE,
        STATUS_REPLACED,
        STATUS_VOID,
    }
)

EVENT_IMPORTED = "imported"
EVENT_PRINTED = "printed"
EVENT_REPRINTED = "reprinted"
EVENT_APPLIED = "applied"
EVENT_INTRODUCED = "introduced"
EVENT_SHIPPED = "shipped"
EVENT_TRANSFERRED = "transferred"
EVENT_DEFECTIVE = "defective"
EVENT_REPLACED = "replaced"
EVENT_VOIDED = "voided"

MARKING_CODE_EVENT_TYPES = frozenset(
    {
        EVENT_IMPORTED,
        EVENT_PRINTED,
        EVENT_REPRINTED,
        EVENT_APPLIED,
        EVENT_INTRODUCED,
        EVENT_SHIPPED,
        EVENT_TRANSFERRED,
        EVENT_DEFECTIVE,
        EVENT_REPLACED,
        EVENT_VOIDED,
    }
)


class MarkingPool(Base):
    __tablename__ = "marking_pools"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    gtin: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    pool_products: Mapped[list[MarkingPoolProduct]] = relationship(
        "MarkingPoolProduct",
        back_populates="pool",
        cascade="all, delete-orphan",
    )
    codes: Mapped[list[MarkingCode]] = relationship(
        "MarkingCode",
        back_populates="pool",
    )


class MarkingPoolProduct(Base):
    __tablename__ = "marking_pool_products"
    __table_args__ = (
        UniqueConstraint("pool_id", "product_id", name="uq_marking_pool_products_pool_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_pools.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    pool: Mapped[MarkingPool] = relationship("MarkingPool", back_populates="pool_products")
    product: Mapped[Product] = relationship("Product")


class MarkingCodeImport(Base):
    __tablename__ = "marking_code_imports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    accepted_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skip_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    codes: Mapped[list[MarkingCode]] = relationship(
        "MarkingCode",
        back_populates="import_batch",
    )


class MarkingCode(Base):
    __tablename__ = "marking_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cis_code", name="uq_marking_codes_tenant_cis"),
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
    pool_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_pools.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_code_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    packaging_task_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_task_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cis_code: Mapped[str] = mapped_column(String(512), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    crypto_tail: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_AVAILABLE)
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    printed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reserved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    introduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    defective_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    replaced_by_code_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    pool: Mapped[MarkingPool | None] = relationship("MarkingPool", back_populates="codes")
    product: Mapped[Product | None] = relationship("Product")
    import_batch: Mapped[MarkingCodeImport | None] = relationship(
        "MarkingCodeImport",
        back_populates="codes",
    )
    packaging_task_line: Mapped[PackagingTaskLine | None] = relationship(
        "PackagingTaskLine",
        back_populates="marking_codes",
    )
    reserved_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[reserved_by_user_id],
    )
    replaced_by_code: Mapped[MarkingCode | None] = relationship(
        "MarkingCode",
        remote_side=[id],
        foreign_keys=[replaced_by_code_id],
    )
    events: Mapped[list[MarkingCodeEvent]] = relationship(
        "MarkingCodeEvent",
        back_populates="code",
    )


class MarkingCodeEvent(Base):
    __tablename__ = "marking_code_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    code_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_codes.id", ondelete="CASCADE"),
        index=True,
    )
    pool_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_pools.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    packaging_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    packaging_task_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_task_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    code: Mapped[MarkingCode] = relationship("MarkingCode", back_populates="events")
    pool: Mapped[MarkingPool | None] = relationship("MarkingPool")
