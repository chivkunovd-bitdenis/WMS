from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_print_asset import FbsPrintAsset
    from app.models.fbs_supply import FbsSupply
    from app.models.user import User
    from app.models.warehouse_box import WarehouseBox


class FbsTrbx(Base):
    __tablename__ = "fbs_trbxes"
    __table_args__ = (
        Index("ix_fbs_trbxes_packaging_box_id", "packaging_box_id"),
        Index("uq_fbs_trbxes_packaging_box_id", "packaging_box_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wb_trbx_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    packaging_box_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "warehouse_boxes.id",
            name="fk_fbs_trbxes_packaging_box_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sticker_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # Mirrors the named 0069 migration FK.  Deferring this edge breaks the
        # metadata-only FBS print-asset cycle for PostgreSQL drop_all().
        ForeignKey(
            "fbs_print_assets.id",
            name="fk_fbs_trbxes_qr_asset_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )
    qr_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qr_applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supply: Mapped[FbsSupply] = relationship("FbsSupply", back_populates="trbxes")
    orders: Mapped[list[FbsOrder]] = relationship("FbsOrder", back_populates="trbx")
    qr_asset: Mapped[FbsPrintAsset | None] = relationship(
        "FbsPrintAsset",
        foreign_keys=[qr_asset_id],
    )
    qr_asset_ref: Mapped[FbsPrintAsset | None] = relationship(
        "FbsPrintAsset",
        back_populates="trbx",
        foreign_keys="FbsPrintAsset.fbs_trbx_id",
    )
    qr_applied_by_user: Mapped[User | None] = relationship("User")
    packaging_box: Mapped[WarehouseBox | None] = relationship("WarehouseBox")
