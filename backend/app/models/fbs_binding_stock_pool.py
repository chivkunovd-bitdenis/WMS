from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    """Доля FBS по складу WB и наследуемое абсолютное количество."""

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
    # Сколько штук оператор выделил на этот склад WB в режиме «остаток по штукам».
    # Это НЕ счётчик: заказы его не уменьшают. Сколько от квоты осталось, считается
    # выводом из журнала ``fbs_stock_pool_debits`` — см.
    # ``fbs_stock_units_service.remaining_units_by_binding``. Счётчик, который
    # уменьшают событиями, однажды разъезжается с реальностью навсегда: старый пул
    # уменьшался при импорте заказа и не восстанавливался при отмене.
    #
    # Момент, с которого считается расход. Оператор переписал числа — отметка
    # сдвигается на «сейчас», и всё, что съедено до этого, перестаёт учитываться:
    # он вводит числа, глядя на сегодняшний остаток.
    allocated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Доля свободного остатка для этого склада WB, когда у товара доли разные.
    # NULL — «отдельная доля не задана», и это не то же самое, что ноль: ноль
    # означает осознанное «на этот склад не публикуем».
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
