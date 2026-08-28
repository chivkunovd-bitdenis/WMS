from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_stock_sync_item import FbsStockSyncItem
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class FbsWarehouseBinding(Base):
    """Maps one seller WB virtual warehouse to one WMS FBS physical warehouse."""

    __tablename__ = "fbs_warehouse_bindings"
    __table_args__ = (
        UniqueConstraint(
            "seller_id",
            "wb_warehouse_id",
            name="uq_fbs_warehouse_bindings_seller_wb_warehouse",
        ),
        UniqueConstraint(
            "seller_id",
            "marketplace",
            "external_warehouse_id",
            name="uq_fbs_warehouse_bindings_seller_marketplace_external",
        ),
        # No uniqueness on (seller_id, wms_warehouse_id): one physical WMS
        # warehouse now feeds every WB warehouse address for a seller
        # (pool 1, item 5 of docs/agent-orders/HANDOFF-POLISH.md).
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
    marketplace: Mapped[str] = mapped_column(
        String(32), nullable=False, default="wb", server_default="wb", index=True
    )
    external_warehouse_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    wb_warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    wms_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    stock_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Обслуживаем ли мы этот склад продавца. Галочка ставится один раз в карточке
    # продавца и решает сразу две вещи: какие заказы FBS наши и по каким складам
    # раздаётся остаток.
    served: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    wms_warehouse: Mapped[Warehouse] = relationship("Warehouse")
    sync_items: Mapped[list[FbsStockSyncItem]] = relationship(
        "FbsStockSyncItem",
        back_populates="binding",
        cascade="all, delete-orphan",
    )
