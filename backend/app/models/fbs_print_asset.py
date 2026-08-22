from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_trbx import FbsTrbx
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User

PRINT_ASSET_KIND_ORDER_STICKER = "order_sticker"
PRINT_ASSET_KIND_CARGO_PLACE_QR = "cargo_place_qr"
PRINT_ASSET_KIND_SUPPLY_QR = "supply_qr"
PRINT_ASSET_KIND_LABEL_TAPE = "label_tape"
FBS_PRINT_ASSET_KINDS = frozenset(
    {
        PRINT_ASSET_KIND_ORDER_STICKER,
        PRINT_ASSET_KIND_CARGO_PLACE_QR,
        PRINT_ASSET_KIND_SUPPLY_QR,
        PRINT_ASSET_KIND_LABEL_TAPE,
    }
)

PRINT_ASSET_STATUS_REQUESTING = "requesting"
PRINT_ASSET_STATUS_READY = "ready"
PRINT_ASSET_STATUS_ERROR = "error"
FBS_PRINT_ASSET_STATUSES = frozenset(
    {
        PRINT_ASSET_STATUS_REQUESTING,
        PRINT_ASSET_STATUS_READY,
        PRINT_ASSET_STATUS_ERROR,
    }
)


class FbsPrintAsset(Base):
    """Binary print asset; storage_path is internal-only (never exposed in API)."""

    __tablename__ = "fbs_print_assets"
    __table_args__ = (
        Index(
            "uq_fbs_print_assets_ready_order_sticker",
            "fbs_order_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status = 'ready' AND kind = 'order_sticker' AND fbs_order_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_fbs_print_assets_ready_supply_qr",
            "fbs_supply_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status = 'ready' AND kind = 'supply_qr' AND fbs_supply_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_fbs_print_assets_ready_cargo_qr",
            "fbs_trbx_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status = 'ready' AND kind = 'cargo_place_qr' AND fbs_trbx_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_fbs_print_assets_tenant_seller_kind_status",
            "tenant_id",
            "seller_id",
            "kind",
            "status",
        ),
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
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PRINT_ASSET_STATUS_REQUESTING,
        server_default=PRINT_ASSET_STATUS_REQUESTING,
    )
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wb_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fbs_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    fbs_supply_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    fbs_trbx_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_trbxes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    print_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    order: Mapped[FbsOrder | None] = relationship("FbsOrder", back_populates="print_assets")
    supply: Mapped[FbsSupply | None] = relationship(
        "FbsSupply",
        back_populates="print_assets",
        foreign_keys=[fbs_supply_id],
    )
    trbx: Mapped[FbsTrbx | None] = relationship(
        "FbsTrbx",
        back_populates="qr_asset_ref",
        foreign_keys=[fbs_trbx_id],
    )
    applied_by_user: Mapped[User | None] = relationship("User")
