from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse


OPERATION_SOURCE_USER = "user"
OPERATION_SOURCE_SYSTEM = "system"
OPERATION_SOURCES = frozenset({OPERATION_SOURCE_USER, OPERATION_SOURCE_SYSTEM})


class OperationFactCutover(Base):
    __tablename__ = "operation_fact_cutover"
    __table_args__ = (CheckConstraint("id = 1", name="ck_operation_fact_cutover_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OperationFact(Base):
    __tablename__ = "operation_facts"
    __table_args__ = (
        Index(
            "uq_operation_facts_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_operation_facts_source_operation",
            "tenant_id",
            "source_kind",
            "source_event_id",
            "operation_code",
            unique=True,
        ),
        Index("ix_operation_facts_seller_occurred", "tenant_id", "seller_id", "occurred_at", "id"),
        Index(
            "ix_operation_facts_actor_occurred", "tenant_id", "actor_user_id", "occurred_at", "id"
        ),
        Index(
            "ix_operation_facts_operation_occurred",
            "tenant_id",
            "operation_code",
            "occurred_at",
            "id",
        ),
        CheckConstraint("operation_code <> ''", name="ck_operation_facts_operation_code"),
        CheckConstraint("source_kind <> ''", name="ck_operation_facts_source_kind"),
        CheckConstraint("item_quantity >= 0", name="ck_operation_facts_item_quantity_nonnegative"),
        CheckConstraint("source IN ('user', 'system')", name="ck_operation_facts_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    operation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    billable_service_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="SET NULL"), nullable=True
    )
    seller_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    marketplace: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    item_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("operation_facts.id", ondelete="RESTRICT"), nullable=True
    )
    integrity_status: Mapped[str] = mapped_column(String(64), nullable=False, default="complete")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller | None] = relationship("Seller")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    actor: Mapped[User | None] = relationship("User")
    reversal_of: Mapped[OperationFact | None] = relationship("OperationFact", remote_side=[id])
    lines: Mapped[list[OperationFactLine]] = relationship(
        "OperationFactLine", back_populates="operation_fact", cascade="all, delete-orphan"
    )


class OperationFactLine(Base):
    __tablename__ = "operation_fact_lines"
    __table_args__ = (
        Index("ix_operation_fact_lines_fact", "operation_fact_id"),
        CheckConstraint(
            "item_quantity >= 0", name="ck_operation_fact_lines_item_quantity_nonnegative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_fact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("operation_facts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    sku_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    operation_fact: Mapped[OperationFact] = relationship("OperationFact", back_populates="lines")
    product: Mapped[Product | None] = relationship("Product")
