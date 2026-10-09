"""ORM mapping for the deployed ``marking_print_batches`` table.

Migration ``20260710_0061`` created this table, but no service ever came to
read or write it: label printing went through
``fbs_print_asset_service.request_supply_print_batch`` instead, which never
persists a row here. The table is still part of every deployed schema
(production, staging, any fresh ``alembic upgrade head``) and is reachable
from ``warehouses`` through ``packaging_task_lines`` -> ``packaging_tasks``.

``physical_warehouse_repair_service._tables()`` and
``physical_warehouse_guard.physical_graph`` both need every table that is
structurally reachable from ``warehouses`` to be mapped here, or the repair
service's own schema self-check rejects the migrated database as an
"unrecognised physical descendant" before it reads any data (WMS-516 review
P0-1). Mapping it makes it a known, harmless leaf: it carries no warehouse
identity of its own, so repair never needs to rewrite it, but it is still
covered by the maintenance-window table lock like every other descendant.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarkingPrintBatch(Base):
    __tablename__ = "marking_print_batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    packaging_task_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_task_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    printed_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    layout_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
