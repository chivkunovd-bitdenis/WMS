from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller

SIGNING_FF_KEP_MCHD = "ff_kep_mchd"
SIGNING_SELLER_CLOUD = "seller_cloud"
SIGNING_MANUAL = "manual"

SIGNING_METHODS = frozenset({SIGNING_FF_KEP_MCHD, SIGNING_SELLER_CLOUD, SIGNING_MANUAL})

EDO_LIGHT_ROAMING_DIADOC = "edo_light_roaming_diadoc"
EDO_DIADOC_DIRECT = "diadoc_direct"

EDO_ROUTES = frozenset({EDO_LIGHT_ROAMING_DIADOC, EDO_DIADOC_DIRECT})

MARKETPLACE_WILDBERRIES = "wildberries"
MARKETPLACE_OZON = "ozon"

MARKETPLACES = frozenset({MARKETPLACE_WILDBERRIES, MARKETPLACE_OZON})


class SellerMarkingCredentials(Base):
    """Per-seller marking integration tokens and signing configuration (encrypted at rest)."""

    __tablename__ = "seller_marking_credentials"

    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cz_token_enc: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    suz_oms_token_enc: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    marketplace: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mp_api_key_enc: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    mchd_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mchd_valid_until: Mapped[date | None] = mapped_column(Date(), nullable=True)
    signing_method: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=SIGNING_MANUAL
    )
    edo_route: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=EDO_LIGHT_ROAMING_DIADOC
    )
    auto_introduce: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default="false")
    auto_emit_limit: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="marking_credentials")
