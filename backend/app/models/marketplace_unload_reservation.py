from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.marketplace_unload import MarketplaceUnloadLine
    from app.models.product import Product
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class MarketplaceUnloadReservation(Base):
    """Warehouse-level reserve for a planned MP unload line (submitted/confirmed)."""

    __tablename__ = "marketplace_unload_reservations"
    __table_args__ = (
        UniqueConstraint(
            "marketplace_unload_line_id",
            name="uq_marketplace_unload_reservation_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    marketplace_unload_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_unload_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    unload_line: Mapped[MarketplaceUnloadLine] = relationship(
        "MarketplaceUnloadLine",
        back_populates="reservation",
    )
    product: Mapped[Product] = relationship("Product")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
