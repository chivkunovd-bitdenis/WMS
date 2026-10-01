from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import PACK_STATUS_PACKED, PICK_STATUS_PICKED, FbsOrder
from app.models.fbs_supply import FbsSupply
from app.services.document_number_service import (
    DOC_TYPE_FBS_ASSEMBLY,
    next_display_number,
)
from app.services.fbs_supply_service import FBS_SUPPLY_ACTIVE_STATUSES
from app.services.fbs_worklist_service import build_worklist_items
from app.services.operation_fact_service import normalize_marketplace


@dataclass
class FbsAssemblyTaskError(Exception):
    code: str
    message: str
    http_status: int = 409
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.code)


def _task_load_options() -> tuple[Any, ...]:
    supply_link = selectinload(FbsAssemblyTask.supply_links).selectinload(
        FbsAssemblyTaskSupply.supply
    )
    return (
        selectinload(FbsAssemblyTask.created_by),
        supply_link.selectinload(FbsSupply.seller),
        selectinload(FbsAssemblyTask.supply_links)
        .selectinload(FbsAssemblyTaskSupply.supply)
        .selectinload(FbsSupply.orders),
    )


async def _task_by_idempotency_key(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    idempotency_key: str,
) -> FbsAssemblyTask | None:
    result = await session.execute(
        select(FbsAssemblyTask).where(
            FbsAssemblyTask.tenant_id == tenant_id,
            FbsAssemblyTask.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _assigned_supply_ids(
    session: AsyncSession,
    supply_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    if not supply_ids:
        return []
    return list(
        (
            await session.scalars(
                select(FbsAssemblyTaskSupply.supply_id).where(
                    FbsAssemblyTaskSupply.supply_id.in_(supply_ids)
                )
            )
        ).all()
    )


async def create_assembly_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    created_by_user_id: uuid.UUID,
    supply_ids: list[uuid.UUID],
    idempotency_key: str,
    seller_id: uuid.UUID | None = None,
) -> uuid.UUID:
    key = idempotency_key.strip()
    if not key:
        raise FbsAssemblyTaskError(
            "idempotency_key_required",
            "Укажите ключ повтора операции.",
            http_status=422,
        )
    unique_supply_ids = list(dict.fromkeys(supply_ids))
    if not unique_supply_ids:
        raise FbsAssemblyTaskError(
            "supply_ids_required",
            "Добавьте хотя бы одну поставку в сборочное задание.",
            http_status=422,
        )

    existing = await _task_by_idempotency_key(session, tenant_id, key)
    if existing is not None:
        return existing.id

    supply_stmt = select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id,
        FbsSupply.id.in_(unique_supply_ids),
    )
    if seller_id is not None:
        supply_stmt = supply_stmt.where(FbsSupply.seller_id == seller_id)
    supplies = list((await session.scalars(supply_stmt)).all())
    if len(supplies) != len(unique_supply_ids):
        raise FbsAssemblyTaskError(
            "supply_scope_conflict",
            "Одна или несколько поставок принадлежат другому клиенту или селлеру.",
        )

    assigned = await _assigned_supply_ids(session, unique_supply_ids)
    if assigned:
        raise FbsAssemblyTaskError(
            "supply_already_in_assembly_task",
            "Одна или несколько поставок уже входят в другое сборочное задание.",
            context={"supply_ids": [str(supply_id) for supply_id in assigned]},
        )

    task_id = uuid.uuid4()
    try:
        async with session.begin_nested():
            task = FbsAssemblyTask(
                id=task_id,
                tenant_id=tenant_id,
                number=await next_display_number(
                    session,
                    tenant_id,
                    DOC_TYPE_FBS_ASSEMBLY,
                ),
                created_by_user_id=created_by_user_id,
                idempotency_key=key,
            )
            session.add(task)
            session.add_all(
                FbsAssemblyTaskSupply(task_id=task_id, supply_id=supply_id)
                for supply_id in unique_supply_ids
            )
            await session.flush()
    except IntegrityError:
        # Both invariants are protected by database constraints. A concurrent
        # replay gets the first task; competing composition gets a stable 409.
        existing = await _task_by_idempotency_key(session, tenant_id, key)
        if existing is not None:
            return existing.id
        assigned = await _assigned_supply_ids(session, unique_supply_ids)
        raise FbsAssemblyTaskError(
            "supply_already_in_assembly_task",
            "Одна или несколько поставок уже входят в другое сборочное задание.",
            context={"supply_ids": [str(supply_id) for supply_id in assigned]},
        ) from None
    return task_id


async def _map_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tasks: list[FbsAssemblyTask],
    *,
    seller_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    visible_supplies_by_task: dict[uuid.UUID, list[FbsSupply]] = {}
    all_orders: list[FbsOrder] = []
    for task in tasks:
        supplies = [
            link.supply
            for link in task.supply_links
            if seller_id is None or link.supply.seller_id == seller_id
        ]
        supplies.sort(key=lambda supply: (supply.created_at, supply.id))
        visible_supplies_by_task[task.id] = supplies
        all_orders.extend(order for supply in supplies for order in supply.orders)

    worklist_items = await build_worklist_items(session, tenant_id, all_orders)
    worklist_by_order_id = {str(item["id"]): item for item in worklist_items}

    payload: list[dict[str, Any]] = []
    for task in tasks:
        supplies_payload: list[dict[str, Any]] = []
        for supply in visible_supplies_by_task[task.id]:
            order_items = [
                worklist_by_order_id[str(order.id)]
                for order in supply.orders
                if str(order.id) in worklist_by_order_id
            ]
            units_count = sum(
                sum(int(position["quantity"]) for position in item["positions"])
                if item["positions"]
                else 1
                for item in order_items
            )
            picked_units_count = sum(
                sum(int(position["picked_quantity"]) for position in item["positions"])
                if item["positions"]
                else int(item["pick"]["status"] == PICK_STATUS_PICKED)
                for item in order_items
            )
            supplies_payload.append(
                {
                    "id": str(supply.id),
                    "marketplace": normalize_marketplace(supply.marketplace),
                    "name": supply.display_number or supply.name,
                    "seller": {
                        "id": str(supply.seller_id),
                        "name": (
                            supply.seller.name if supply.seller else "Селлер не найден"
                        ),
                    },
                    "status": supply.status,
                    "orders_count": len(order_items),
                    "picked_count": sum(
                        item["pick"]["status"] == PICK_STATUS_PICKED
                        for item in order_items
                    ),
                    "units_count": units_count,
                    "picked_units_count": picked_units_count,
                    "packed_count": sum(
                        item["pack"]["status"] == PACK_STATUS_PACKED
                        for item in order_items
                    ),
                }
            )
        payload.append(
            {
                "id": str(task.id),
                "number": task.number,
                "created_at": task.created_at.isoformat(),
                "created_by": {
                    "id": str(task.created_by_user_id) if task.created_by_user_id else None,
                    "name": (
                        task.created_by.display_name
                        if task.created_by is not None
                        else "Пользователь удалён"
                    ),
                },
                "supplies": supplies_payload,
            }
        )
    return payload


async def list_assembly_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    marketplace: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(FbsAssemblyTask)
        .join(FbsAssemblyTask.supply_links)
        .join(FbsAssemblyTaskSupply.supply)
        .options(*_task_load_options())
        .where(
            FbsAssemblyTask.tenant_id == tenant_id,
            FbsSupply.status.in_(FBS_SUPPLY_ACTIVE_STATUSES),
        )
        .order_by(FbsAssemblyTask.created_at.desc(), FbsAssemblyTask.id.desc())
    )
    if seller_id is not None:
        stmt = stmt.where(FbsSupply.seller_id == seller_id)
    if marketplace is not None:
        stmt = stmt.where(FbsSupply.marketplace == marketplace)
    tasks = list((await session.scalars(stmt)).unique().all())
    return await _map_tasks(session, tenant_id, tasks, seller_id=seller_id)


async def get_assembly_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    task = await session.scalar(
        select(FbsAssemblyTask)
        .options(*_task_load_options())
        .where(
            FbsAssemblyTask.id == task_id,
            FbsAssemblyTask.tenant_id == tenant_id,
        )
    )
    if task is None or (
        seller_id is not None
        and not any(link.supply.seller_id == seller_id for link in task.supply_links)
    ):
        raise FbsAssemblyTaskError(
            "assembly_task_not_found",
            "Сборочное задание не найдено.",
            http_status=404,
        )
    return (await _map_tasks(session, tenant_id, [task], seller_id=seller_id))[0]
