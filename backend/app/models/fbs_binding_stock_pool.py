from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.product import Product


class FbsBindingStockPool(Base):
    """Правило товара для одной привязки внешнего склада к складу ФФ."""

    __tablename__ = "fbs_binding_stock_pools"
    __table_args__ = (
        UniqueConstraint(
            "binding_id",
            "product_id",
            name="uq_fbs_binding_stock_pools_binding_product",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="ck_fbs_binding_stock_pools_quantity_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_warehouse_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Only an explicit key in an operator-saved units rule proves zero intent.
    units_configured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # WMS-469: одно сохранённое значение на пару товар x привязка. Если percent
    # задан, действует процентный режим; если NULL — ручной потолок quantity.
    # Рассчитанное к публикации число нигде рядом не сохраняется.
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL означает старую строку до WMS-469: для неё выключатель и режим ещё
    # читаются из legacy-полей Product. После первого сохранения блока значение
    # становится явным и независимо от других привязок этого товара.
    publish_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    binding: Mapped[FbsWarehouseBinding] = relationship("FbsWarehouseBinding")
    product: Mapped[Product] = relationship("Product")
