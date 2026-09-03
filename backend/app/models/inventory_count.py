from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse


class InventoryCount(Base):
    """Документ, фиксирующий системный и фактический остаток товаров."""

    __tablename__ = "inventory_counts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    seller: Mapped[Seller | None] = relationship("Seller")
    created_by: Mapped[User] = relationship("User", foreign_keys=[created_by_user_id])
    posted_by: Mapped[User | None] = relationship("User", foreign_keys=[posted_by_user_id])
    lines: Mapped[list[InventoryCountLine]] = relationship(
        "InventoryCountLine",
        back_populates="count",
        cascade="all, delete-orphan",
        order_by="InventoryCountLine.id",
    )


class InventoryCountLine(Base):
    """Одна пересчитываемая позиция шага 1: товар в ячейке."""

    __tablename__ = "inventory_count_lines"
    __table_args__ = (
        Index(
            "uq_inventory_count_line_scope",
            "count_id",
            text("COALESCE(storage_location_id, '00000000-0000-0000-0000-000000000000')"),
            text("COALESCE(container_kind, '')"),
            text("COALESCE(container_id, '00000000-0000-0000-0000-000000000000')"),
            "product_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    count_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    container_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    container_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    count: Mapped[InventoryCount] = relationship("InventoryCount", back_populates="lines")
    product: Mapped[Product] = relationship("Product")
    storage_location: Mapped[StorageLocation | None] = relationship("StorageLocation")
    movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="inventory_count_line",
    )


class InventoryCountFoundScan(Base):
    """Один скан находки — чтобы повтор не превращался в лишнюю штуку.

    Кладовщик сканирует по складскому вайфаю, который рвётся. Ответ не доехал,
    экран показал ошибку, а сервер уже записал. Человек сканирует ещё раз —
    и на сервере становится две штуки вместо одной. Излишек на ровном месте, и
    найти его потом нечем: в документе просто стоит цифра.

    Клиент присылает идентификатор скана, мы его запоминаем и на повтор
    отвечаем тем же результатом, ничего не прибавляя.
    """

    __tablename__ = "inventory_count_found_scans"
    __table_args__ = (
        UniqueConstraint("count_id", "scan_id", name="uq_inventory_found_scan"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    count_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_count_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    scan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class InventoryCountCreatedContainer(Base):
    """Тара, заведённая прямо в документе пересчёта — исключение из прунинга.

    Карта склада отдаёт всю тару склада, и `_prune_empty_containers` в
    `app/api/inventory_counts.py` выбрасывает из дерева документа ту, в
    которой по документу ничего не лежит — иначе документ распухает сотнями
    строк «0 из 0» чужой тары (см. докстринг там же). Но короб, который
    оператор только что создал прямо в ЭТОМ документе, пуст по определению —
    и общее правило вышвыривало его сразу же, хотя человеку нужно видеть,
    куда класть товар. Эта таблица — точечный список исключений на пару
    (документ, тара), а не отключение прунинга.
    """

    __tablename__ = "inventory_count_created_containers"
    __table_args__ = (
        UniqueConstraint(
            "count_id",
            "container_kind",
            "container_id",
            name="uq_inventory_count_created_container",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    count_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    container_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    container_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
