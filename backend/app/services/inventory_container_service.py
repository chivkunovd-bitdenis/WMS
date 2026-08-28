"""Resolve polymorphic balance containers inside tenant and warehouse bounds."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.pallet import Pallet
from app.models.warehouse_box import WarehouseBox

ContainerKind = Literal["pallet", "box", "cargo_place"]


async def validate_container(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    container_kind: ContainerKind,
    container_id: uuid.UUID,
) -> None:
    if container_kind == "pallet":
        found_id = await session.scalar(
            select(Pallet.id).where(
                Pallet.id == container_id,
                Pallet.tenant_id == tenant_id,
                Pallet.warehouse_id == warehouse_id,
                Pallet.disbanded_at.is_(None),
            )
        )
    elif container_kind == "cargo_place":
        found_id = await session.scalar(
            select(WarehouseBox.id).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.container_kind == "cargo_place",
            )
        )
        if found_id is None:
            found_id = await session.scalar(
                select(InboundIntakeCargoPlace.id)
                .join(
                    InboundIntakeRequest,
                    InboundIntakeRequest.id == InboundIntakeCargoPlace.request_id,
                )
                .where(
                    InboundIntakeCargoPlace.id == container_id,
                    InboundIntakeCargoPlace.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                )
            )
    else:
        found_id = await session.scalar(
            select(WarehouseBox.id).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.container_kind == "box",
            )
        )
        if found_id is None:
            found_id = await session.scalar(
                select(InboundIntakeBox.id)
                .join(
                    InboundIntakeRequest,
                    InboundIntakeRequest.id == InboundIntakeBox.request_id,
                )
                .where(
                    InboundIntakeBox.id == container_id,
                    InboundIntakeBox.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                )
            )
    if found_id is None:
        msg = "container not found"
        raise ValueError(msg)
