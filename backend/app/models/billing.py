from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse


class BillingProfile(Base):
    """The single set of invoice requisites for a tenant or one of its sellers."""

    __tablename__ = "billing_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "seller_id", name="uq_billing_profiles_tenant_seller"),
        Index(
            "uq_billing_profiles_tenant_ff",
            "tenant_id",
            unique=True,
            postgresql_where=text("seller_id IS NULL"),
            sqlite_where=text("seller_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), nullable=False)
    kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bik: Mapped[str | None] = mapped_column(String(9), nullable=True)
    settlement_account: Mapped[str | None] = mapped_column(String(20), nullable=True)
    correspondent_account: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller | None] = relationship("Seller")


class BillingTariffVersion(Base):
    __tablename__ = "billing_tariff_versions"
    __table_args__ = (
        Index(
            "uq_billing_tariff_version_global_seller",
            "tenant_id",
            "seller_id",
            "service_code",
            "unit",
            "valid_from",
            unique=True,
            postgresql_where=text("seller_id IS NOT NULL AND warehouse_id IS NULL"),
            sqlite_where=text("seller_id IS NOT NULL AND warehouse_id IS NULL"),
        ),
        Index(
            "uq_billing_tariff_version_global_common",
            "tenant_id",
            "service_code",
            "unit",
            "valid_from",
            unique=True,
            postgresql_where=text("seller_id IS NULL AND warehouse_id IS NULL"),
            sqlite_where=text("seller_id IS NULL AND warehouse_id IS NULL"),
        ),
        Index(
            "uq_billing_tariff_version_warehouse_seller",
            "tenant_id",
            "warehouse_id",
            "seller_id",
            "service_code",
            "unit",
            "valid_from",
            unique=True,
            postgresql_where=text("seller_id IS NOT NULL AND warehouse_id IS NOT NULL"),
            sqlite_where=text("seller_id IS NOT NULL AND warehouse_id IS NOT NULL"),
        ),
        Index(
            "uq_billing_tariff_version_warehouse_common",
            "tenant_id",
            "warehouse_id",
            "service_code",
            "unit",
            "valid_from",
            unique=True,
            postgresql_where=text("seller_id IS NULL AND warehouse_id IS NOT NULL"),
            sqlite_where=text("seller_id IS NULL AND warehouse_id IS NOT NULL"),
        ),
        CheckConstraint("unit IN ('document', 'item', 'liter_day')", name="ck_billing_tariff_unit"),
        CheckConstraint("amount >= 0", name="ck_billing_tariff_amount_nonnegative"),
        CheckConstraint(
            "(service_code = 'storage_liter_day' AND warehouse_id IS NOT NULL) OR "
            "(service_code <> 'storage_liter_day' AND warehouse_id IS NULL)",
            name="ck_billing_tariff_warehouse_scope",
        ),
        Index("ix_billing_tariffs_tenant_service", "tenant_id", "service_code", "valid_from"),
        Index(
            "ix_billing_tariffs_scope_lookup",
            "tenant_id",
            "service_code",
            "warehouse_id",
            "seller_id",
            "valid_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    # Monetary values are integer kopecks at every billing-core boundary.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller | None] = relationship("Seller")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")


class BillingTariffMatrixConfig(Base):
    """Explicit per-tenant matrix state; absence is a configuration error."""

    __tablename__ = "billing_tariff_matrix_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_billing_tariff_matrix_config_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    service_states: Mapped[list[BillingTariffServiceState]] = relationship(
        "BillingTariffServiceState", cascade="all, delete-orphan", back_populates="config"
    )


class BillingTariffServiceState(Base):
    __tablename__ = "billing_tariff_service_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_code", name="uq_billing_tariff_service_state"),
        CheckConstraint(
            "service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return')",
            name="ck_billing_tariff_service_state_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_tariff_matrix_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)

    config: Mapped[BillingTariffMatrixConfig] = relationship(
        "BillingTariffMatrixConfig", back_populates="service_states"
    )


class BillingTariffVersionV2(Base):
    __tablename__ = "billing_tariff_versions_v2"
    __table_args__ = (
        CheckConstraint("unit IN ('document', 'item')", name="ck_billing_tariff_v2_unit"),
        CheckConstraint("rate >= 0", name="ck_billing_tariff_v2_rate_nonnegative"),
        CheckConstraint(
            "valid_to_at IS NULL OR valid_to_at > valid_from_at",
            name="ck_billing_tariff_v2_interval",
        ),
        CheckConstraint(
            "("
            "employee_user_id IS NOT NULL "
            "AND seller_id IS NULL "
            "AND product_id IS NULL "
            "AND unit = 'item' "
            "AND service_code IN ('inbound', 'picking', 'marketplace_outbound', 'return')"
            ") OR ("
            "employee_user_id IS NULL "
            "AND service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return') "
            "AND (product_id IS NULL OR (seller_id IS NOT NULL AND unit = 'item'))"
            ")",
            name="ck_billing_tariff_v2_scope",
        ),
        Index(
            "uq_billing_tariff_v2_common_start",
            "tenant_id",
            "service_code",
            "valid_from_at",
            unique=True,
            postgresql_where=text(
                "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NULL"
            ),
            sqlite_where=text(
                "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NULL"
            ),
        ),
        Index(
            "uq_billing_tariff_v2_seller_start",
            "tenant_id",
            "seller_id",
            "service_code",
            "valid_from_at",
            unique=True,
            postgresql_where=text(
                "seller_id IS NOT NULL AND product_id IS NULL AND employee_user_id IS NULL"
            ),
            sqlite_where=text(
                "seller_id IS NOT NULL AND product_id IS NULL AND employee_user_id IS NULL"
            ),
        ),
        Index(
            "uq_billing_tariff_v2_product_start",
            "tenant_id",
            "seller_id",
            "product_id",
            "service_code",
            "valid_from_at",
            unique=True,
            postgresql_where=text(
                "seller_id IS NOT NULL AND product_id IS NOT NULL AND employee_user_id IS NULL"
            ),
            sqlite_where=text(
                "seller_id IS NOT NULL AND product_id IS NOT NULL AND employee_user_id IS NULL"
            ),
        ),
        Index(
            "uq_billing_tariff_v2_employee_start",
            "tenant_id",
            "employee_user_id",
            "service_code",
            "valid_from_at",
            unique=True,
            postgresql_where=text(
                "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NOT NULL"
            ),
            sqlite_where=text(
                "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NOT NULL"
            ),
        ),
        UniqueConstraint("tenant_id", "id", name="uq_billing_tariff_v2_tenant_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    employee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    rate: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BillingLedgerEntry(Base):
    """Immutable billing event; a reversal points to, but never edits, its charge."""

    __tablename__ = "billing_ledger_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_billing_ledger_entries_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "service_code",
            "source_type",
            "source_id",
            "event_kind",
            name="uq_billing_ledger_source_event",
        ),
        Index(
            "uq_billing_ledger_reversal_of",
            "reversal_of_id",
            unique=True,
            postgresql_where=text("reversal_of_id IS NOT NULL"),
            sqlite_where=text("reversal_of_id IS NOT NULL"),
        ),
        CheckConstraint(
            "entry_type IN ('charge', 'reversal')", name="ck_billing_ledger_entry_type"
        ),
        CheckConstraint("unit IN ('document', 'item', 'liter_day')", name="ck_billing_ledger_unit"),
        CheckConstraint("service_code <> ''", name="ck_billing_ledger_service_code"),
        Index("ix_billing_ledger_tenant_occurred", "tenant_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    tariff_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_tariff_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    tariff_version_v2_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_tariff_versions_v2.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_ledger_entries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    performer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False, default="charge")
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="completed")
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller | None] = relationship("Seller")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    tariff_version: Mapped[BillingTariffVersion | None] = relationship("BillingTariffVersion")
    tariff_version_v2: Mapped[BillingTariffVersionV2 | None] = relationship(
        "BillingTariffVersionV2"
    )
    lines: Mapped[list[BillingLedgerLine]] = relationship(
        "BillingLedgerLine",
        cascade="all, delete-orphan",
        back_populates="ledger_entry",
        foreign_keys="BillingLedgerLine.ledger_entry_id",
    )
    reversal_of: Mapped[BillingLedgerEntry | None] = relationship(
        "BillingLedgerEntry", remote_side=[id]
    )
    performer: Mapped[User | None] = relationship("User")


class BillingLedgerLine(Base):
    __tablename__ = "billing_ledger_lines"
    __table_args__ = (
        CheckConstraint("billing_unit IN ('document', 'item')", name="ck_billing_ledger_line_unit"),
        CheckConstraint(
            "amount IS NULL OR rate IS NOT NULL", name="ck_billing_ledger_line_amount_rate"
        ),
        Index("ix_billing_ledger_lines_tenant_entry", "tenant_id", "ledger_entry_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ledger_entry_id"],
            ["billing_ledger_entries.tenant_id", "billing_ledger_entries.id"],
            name="fk_billing_ledger_lines_tenant_entry",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "operation_fact_line_id"],
            ["operation_fact_lines.tenant_id", "operation_fact_lines.id"],
            name="fk_billing_ledger_lines_tenant_fact_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_billing_ledger_lines_tenant_product",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tariff_version_v2_id"],
            ["billing_tariff_versions_v2.tenant_id", "billing_tariff_versions_v2.id"],
            name="fk_billing_ledger_lines_tenant_tariff_v2",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ledger_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_ledger_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_fact_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("operation_fact_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    physical_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    billing_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    billing_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    tariff_version_v2_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_tariff_versions_v2.id", ondelete="SET NULL"),
        nullable=True,
    )
    tariff_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ledger_entry: Mapped[BillingLedgerEntry] = relationship(
        "BillingLedgerEntry", back_populates="lines", foreign_keys=[ledger_entry_id]
    )


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "seller_id", "period", name="uq_billing_invoice_period"),
        UniqueConstraint("tenant_id", "number", name="uq_billing_invoice_tenant_number"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="issued")
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    ff_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    seller_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class BillingRunIssue(Base):
    __tablename__ = "billing_run_issues"
    __table_args__ = (
        UniqueConstraint("tenant_id", "seller_id", "period", "reason", name="uq_billing_run_issue"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
