from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_supply import FbsSupply
    from app.models.tenant import Tenant
    from app.models.user import User


class FbsAssemblyTask(Base):
    __tablename__ = "fbs_assembly_tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "number",
            name="uq_fbs_assembly_tasks_tenant_number",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_fbs_assembly_tasks_tenant_idempotency",
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
    number: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    created_by: Mapped[User | None] = relationship("User")
    supply_links: Mapped[list[FbsAssemblyTaskSupply]] = relationship(
        "FbsAssemblyTaskSupply",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class FbsAssemblyTaskSupply(Base):
    __tablename__ = "fbs_assembly_task_supplies"
    __table_args__ = (
        UniqueConstraint(
            "supply_id",
            name="uq_fbs_assembly_task_supplies_supply_id",
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_assembly_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="CASCADE"),
        primary_key=True,
    )

    task: Mapped[FbsAssemblyTask] = relationship(
        "FbsAssemblyTask",
        back_populates="supply_links",
    )
    supply: Mapped[FbsSupply] = relationship("FbsSupply")
