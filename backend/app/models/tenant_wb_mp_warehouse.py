from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TenantWbMpWarehouse(Base):
    """Кэш складов WB (GET /api/v1/warehouses) на тенанта — один раз при первом supplies-токене."""

    __tablename__ = "tenant_wb_mp_warehouses"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # WMS-423. bigint: сюда приходят и номера складов Ozon из поля заказа
    # (1020005029603630), которые в int4 не помещаются и роняли запрос.
    wb_warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_time: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_transit_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[object] = relationship("Tenant")
