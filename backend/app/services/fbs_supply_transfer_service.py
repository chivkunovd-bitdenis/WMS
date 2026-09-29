"""Move WB orders without recreating their marking or inventory history."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderProductPick
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBoxItem
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.services.fbs_packaging_integration_service import _decrement_packaging_line_for_product
from app.services.fbs_supply_service import (
    FbsSupplyError,
    _apply_existing_packaging_task_projection,
    _require_marketplace_token,
)
from app.services.fbs_wb_seller_lock_service import wb_seller_lock
from app.services.wildberries_client import (
    WildberriesClientError,
    add_orders_to_marketplace_supply,
    create_marketplace_supply,
)
from app.services.wildberries_fbs_client import (
    fetch_marketplace_supplies_page,
    fetch_marketplace_supply_order_ids,
    split_marketplace_order_id_batches,
)

_KIND = "supply_transfer_orders"
# WMS-581: переносить можно в любую открытую поставку WB — пока её не передали
# в доставку и не закрыли. Тот же набор, что у привязки заказа к поставке WB.
_OPEN_TARGET_STATUSES = ("draft", "assembling", "packed")
# Поиск созданной поставки после потерянного ответа WB: только поставки с тем же
# названием, созданные в окне вокруг нашей попытки и ещё никому не принадлежащие.
_CREATE_CLOCK_SKEW = timedelta(minutes=2)
_CREATE_WINDOW = timedelta(minutes=10)


async def _source(session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID) -> FbsSupply:
    supply = await session.scalar(
        select(FbsSupply)
        .where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.id == supply_id,
        )
        .execution_options(populate_existing=True)
    )
    if supply is None:
        raise FbsSupplyError("supply_not_found", http_status=404)
    if supply.marketplace != "wb":
        raise FbsSupplyError("marketplace_not_supported", http_status=409)
    return supply


def _target_mismatch(
    target: FbsSupply,
    target_orders: Iterable[FbsOrder],
    orders: Iterable[FbsOrder],
) -> str | None:
    """Why WB would not take these orders into the target supply.

    The same attributes the supply validator compares when a supply is created
    from orders: marketplace, seller, WMS warehouse, WB warehouse, B2C/B2B and
    cargo type. The target's own orders are the reference for the last three.
    """
    existing = [order for order in target_orders if order.supply_id == target.id]
    wb_warehouses = {o.wb_warehouse_id for o in existing if o.wb_warehouse_id is not None}
    buyer_types = {bool(o.is_legal) for o in existing}
    cargo_types = {o.cargo_type or "unknown" for o in existing}
    for order in orders:
        if target.marketplace != "wb" or order.marketplace != "wb":
            return "different_marketplace"
        if order.seller_id != target.seller_id:
            return "different_seller"
        if order.warehouse_id != target.warehouse_id:
            return "order_warehouse_mismatch"
        if wb_warehouses and order.wb_warehouse_id not in wb_warehouses:
            return "different_wb_warehouse"
        if buyer_types and bool(order.is_legal) not in buyer_types:
            return "legal_type_mismatch"
        if cargo_types and (order.cargo_type or "unknown") not in cargo_types:
            return "different_cargo_type"
    return None


async def list_transfer_targets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    source_id: uuid.UUID,
    order_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, str]]:
    source = await _source(session, tenant_id, source_id)
    order_filter = (
        FbsOrder.id.in_(order_ids) if order_ids else FbsOrder.supply_id == source.id
    )
    orders = list(
        await session.scalars(
            select(FbsOrder).where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.seller_id == source.seller_id,
                order_filter,
            )
        )
    )
    rows = await session.scalars(
        select(FbsSupply)
        .options(selectinload(FbsSupply.orders))
        .where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == source.seller_id,
            FbsSupply.warehouse_id == source.warehouse_id,
            FbsSupply.marketplace == "wb",
            FbsSupply.status.in_(_OPEN_TARGET_STATUSES),
            FbsSupply.id != source_id,
        )
        .order_by(FbsSupply.created_at.desc(), FbsSupply.id)
    )
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "wb_supply_id": row.wb_supply_id,
            "created_at": (row.created_at_wb or row.created_at).isoformat(),
        }
        for row in rows
        if row.wb_supply_id and _target_mismatch(row, row.orders, orders) is None
    ]


def _result(operation: FbsWbOperation, orders: list[FbsOrder]) -> dict[str, Any]:
    summary = operation.response_summary_json or {}
    request = operation.request_summary_json or {}
    moved = set(summary.get("transferred_order_ids", []))
    failed = set(summary.get("failed_order_ids", [])) - moved
    pending = {str(order.id) for order in orders} - moved - failed
    state = (
        "pending_confirmation"
        if pending
        else "partial"
        if failed and moved
        else "failed"
        if failed
        else "confirmed"
    )
    return {
        "target_supply_id": summary.get("target_supply_id"),
        "target_supply_name": summary.get("target_supply_name"),
        "target_wb_supply_id": summary.get("target_wb_supply_id"),
        "target_created": request.get("target_supply_id") is None,
        "transferred_order_ids": sorted(moved),
        "failed_order_ids": sorted(failed),
        "pending_order_ids": sorted(pending),
        "state": state,
        "message": (
            "Результат WB пока не подтверждён. Повторите проверку переноса."
            if pending
            else "WB отклонил часть выбранных заказов."
            if failed
            else None
        ),
    }


def _create_requested_at(operation: FbsWbOperation) -> datetime:
    raw = (operation.request_summary_json or {}).get("create_requested_at")
    started = datetime.fromisoformat(raw) if isinstance(raw, str) else operation.created_at
    return started if started.tzinfo is not None else started.replace(tzinfo=UTC)


async def _find_created_supply(
    session: AsyncSession,
    client: httpx.AsyncClient,
    token: str,
    operation: FbsWbOperation,
) -> str | None:
    """Find the WB supply our lost create produced, or None when not certain.

    The operator may type a name another supply already has. A candidate must
    have that name, be open, be created by WB within the window of our attempt
    and belong to no local supply or other operation. Anything but exactly one
    candidate stays unknown: no second create and no transfer to a guess.
    """
    name = str((operation.request_summary_json or {})["name"])
    started = _create_requested_at(operation)
    known = set(
        await session.scalars(
            select(FbsSupply.wb_supply_id).where(
                FbsSupply.seller_id == operation.seller_id,
                FbsSupply.marketplace == "wb",
                FbsSupply.wb_supply_id.is_not(None),
            )
        )
    ) | set(
        await session.scalars(
            select(FbsWbOperation.wb_object_id).where(
                FbsWbOperation.seller_id == operation.seller_id,
                FbsWbOperation.id != operation.id,
                FbsWbOperation.wb_object_id.is_not(None),
            )
        )
    )
    cursor = None
    seen: set[int] = set()
    matches: set[str] = set()
    while True:
        page = await fetch_marketplace_supplies_page(client, api_token=token, next_cursor=cursor)
        for sid, (sname, done) in page.supplies.items():
            created = page.created_at.get(sid)
            if (
                sname == name
                and not done
                and sid not in known
                and created is not None
                and started - _CREATE_CLOCK_SKEW <= created <= started + _CREATE_WINDOW
            ):
                matches.add(sid)
        cursor = page.next_cursor
        if not page.supplies or cursor is None or cursor == 0 or cursor in seen:
            break
        seen.add(cursor)
    return next(iter(matches)) if len(matches) == 1 else None


async def _apply_confirmed(
    session: AsyncSession,
    source: FbsSupply,
    target: FbsSupply,
    orders: list[FbsOrder],
) -> None:
    # start-work locks its supply before creating a task. Serialize the local
    # projection with that lock and reload the task/status after WB returns.
    await session.execute(
        select(FbsSupply)
        .where(
            FbsSupply.id.in_([source.id, target.id]),
        )
        .order_by(FbsSupply.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ids = [order.id for order in orders if order.supply_id != target.id]
    if not ids:
        return
    # The physical box stays with the original supply. Order-level packing,
    # KIZ binding, fulfillment and inventory movements remain unchanged. Their
    # task/line references are historical; the existing undo path locks them.
    await session.execute(
        delete(FbsPackingBoxItem).where(
            FbsPackingBoxItem.tenant_id == source.tenant_id,
            FbsPackingBoxItem.fbs_order_id.in_(ids),
        )
    )
    await session.execute(
        update(FbsOrderPick)
        .where(
            FbsOrderPick.tenant_id == source.tenant_id,
            FbsOrderPick.fbs_order_id.in_(ids),
            FbsOrderPick.undone_at.is_(None),
        )
        .values(fbs_supply_id=target.id)
    )
    await session.execute(
        update(FbsOrderProductPick)
        .where(
            FbsOrderProductPick.tenant_id == source.tenant_id,
            FbsOrderProductPick.order_product_id.in_(
                select(FbsOrderProduct.id).where(FbsOrderProduct.order_id.in_(ids))
            ),
            FbsOrderProductPick.undone_at.is_(None),
        )
        .values(fbs_supply_id=target.id)
    )
    fulfilled_ids = set(
        await session.scalars(
            select(FbsPackagingFulfillment.fbs_order_id).where(
                FbsPackagingFulfillment.tenant_id == source.tenant_id,
                FbsPackagingFulfillment.fbs_order_id.in_(ids),
                FbsPackagingFulfillment.undone_at.is_(None),
            )
        )
    )
    for order in orders:
        # Completed work stays on its historical task for billing/undo. Removing
        # its planned unit would consume capacity needed by remaining orders.
        if order.id in ids and order.id not in fulfilled_ids and order.product_id is not None:
            await _decrement_packaging_line_for_product(
                session,
                source.tenant_id,
                source,
                order.product_id,
            )
        order.supply_id = target.id
        order.wb_supply_id = target.wb_supply_id
        order.trbx_id = None
        order.status = "in_supply" if target.status == "draft" else "assembling"
    if target.packaging_task_id is not None:
        await _apply_existing_packaging_task_projection(
            session,
            source.tenant_id,
            target,
            [order for order in orders if order.id in ids],
        )
    await session.flush()


async def transfer_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    source_id: uuid.UUID,
    *,
    order_ids: list[uuid.UUID],
    target_supply_id: uuid.UUID | None,
    idempotency_key: str,
    actor_user_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    name: str | None = None,
) -> dict[str, Any]:
    source = await _source(session, tenant_id, source_id)
    if not order_ids or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise FbsSupplyError("invalid_transfer_request", http_status=422)
    requested = sorted(set(order_ids), key=str)
    request: dict[str, Any] = {
        "source_id": str(source_id),
        "order_ids": list(map(str, requested)),
        "target_supply_id": str(target_supply_id) if target_supply_id else None,
    }
    # WMS-581: the operator's name belongs to the request only for a new supply.
    # An existing target keeps its name in WMS and WB.
    typed_name = (name or "").strip()
    if target_supply_id is None and typed_name:
        request["name"] = typed_name
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    async with wb_seller_lock(session, source.seller_id, wait_timeout_sec=90) as acquired:
        if not acquired:
            raise FbsSupplyError("operation_in_progress", http_status=409, retryable=True)
        source = await _source(session, tenant_id, source_id)
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.tenant_id == tenant_id,
                FbsWbOperation.seller_id == source.seller_id,
                FbsWbOperation.operation_kind == _KIND,
                FbsWbOperation.idempotency_key == idempotency_key,
            )
        )
        if operation is not None and operation.request_hash != digest:
            raise FbsSupplyError("idempotency_key_reused", http_status=409)
        # Recover even if a browser reload generated a different request key.
        if operation is None:
            active = await session.scalars(
                select(FbsWbOperation).where(
                    FbsWbOperation.tenant_id == tenant_id,
                    FbsWbOperation.seller_id == source.seller_id,
                    FbsWbOperation.operation_kind == _KIND,
                    FbsWbOperation.state.in_(["pending", "pending_confirmation"]),
                )
            )
            for previous in active:
                previous_ids = set((previous.request_summary_json or {}).get("order_ids", []))
                if previous_ids.intersection(request["order_ids"] or []):
                    if previous.request_hash != digest:
                        raise FbsSupplyError(
                            "transfer_pending_confirmation",
                            http_status=409,
                            message="Сначала проверьте результат предыдущего переноса.",
                        )
                    operation = previous
                    break
        orders = list(
            await session.scalars(
                select(FbsOrder)
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == source.seller_id,
                    FbsOrder.marketplace == "wb",
                    FbsOrder.id.in_(requested),
                )
                .execution_options(populate_existing=True)
            )
        )
        if len(orders) != len(requested):
            raise FbsSupplyError("order_not_found", http_status=404)
        if operation is not None and operation.state in {"confirmed", "failed"}:
            return _result(operation, orders)
        token = await _require_marketplace_token(session, tenant_id, source.seller_id)
        is_new = operation is None
        target = None
        if is_new:
            if any(order.supply_id != source_id for order in orders):
                raise FbsSupplyError("order_not_in_source_supply", http_status=409)
            if source.status not in {"draft", "assembling", "packed"}:
                raise FbsSupplyError("supply_not_editable", http_status=409)
            if target_supply_id:
                target = await _source(session, tenant_id, target_supply_id)
                if (
                    target.seller_id != source.seller_id
                    or target.id == source.id
                    or target.status not in _OPEN_TARGET_STATUSES
                    or not target.wb_supply_id
                ):
                    raise FbsSupplyError("invalid_transfer_target", http_status=409)
                if target.warehouse_id != source.warehouse_id:
                    raise FbsSupplyError("order_warehouse_mismatch", http_status=409)
                target_orders = await session.scalars(
                    select(FbsOrder).where(FbsOrder.supply_id == target.id)
                )
                if _target_mismatch(target, target_orders, orders) is not None:
                    raise FbsSupplyError(
                        "order_incompatible",
                        message="Заказ нельзя добавить в выбранную поставку.",
                        http_status=409,
                    )
            operation = FbsWbOperation(
                tenant_id=tenant_id,
                seller_id=source.seller_id,
                operation_kind=_KIND,
                idempotency_key=idempotency_key,
                request_hash=digest,
                request_summary_json={
                    **request,
                    "name": typed_name
                    or f"Новая поставка № {secrets.randbelow(90000) + 10000}",
                    "create_requested_at": datetime.now(UTC).isoformat(),
                },
                response_summary_json={"target_supply_id": str(target.id) if target else None},
                local_entity_type="fbs_supply",
                local_entity_id=source_id,
                state="pending",
                created_by_user_id=actor_user_id,
                wb_object_id=target.wb_supply_id if target else None,
            )
            session.add(operation)
            await session.commit()  # durable intent BEFORE any external mutation
        assert operation is not None
        summary = dict(operation.response_summary_json or {})
        if not operation.wb_object_id:
            try:
                if is_new:
                    created = await create_marketplace_supply(
                        http_client,
                        api_token=token,
                        name=str((operation.request_summary_json or {})["name"]),
                    )
                    operation.wb_object_id = str(created.get("id") or "") or None
                else:
                    operation.wb_object_id = await _find_created_supply(
                        session, http_client, token, operation
                    )
            except WildberriesClientError as exc:
                if (
                    is_new
                    and exc.status_code is not None
                    and 400 <= exc.status_code < 500
                    and exc.status_code != 408
                ):
                    operation.state = "failed"
                    operation.response_summary_json = {
                        **summary,
                        "failed_order_ids": [str(o.id) for o in orders],
                    }
                    await session.commit()
                    return _result(operation, orders)
            if not operation.wb_object_id:
                operation.state = "pending_confirmation"
                await session.commit()
                return _result(operation, orders)
            await session.commit()
        if target is None:
            target = await session.scalar(
                select(FbsSupply).where(
                    FbsSupply.tenant_id == tenant_id,
                    FbsSupply.seller_id == source.seller_id,
                    FbsSupply.marketplace == "wb",
                    FbsSupply.wb_supply_id == operation.wb_object_id,
                )
            )
        if target is None:
            target = FbsSupply(
                tenant_id=tenant_id,
                seller_id=source.seller_id,
                warehouse_id=source.warehouse_id,
                marketplace="wb",
                external_supply_id=operation.wb_object_id,
                wb_supply_id=operation.wb_object_id,
                name=str((operation.request_summary_json or {})["name"]),
                status="draft",
                source="wms",
                delivery_type=source.delivery_type,
                cargo_type=source.cargo_type,
                wb_office_id=source.wb_office_id,
                planned_destination_office_id=source.planned_destination_office_id,
                planned_destination_name=source.planned_destination_name,
                planned_destination_zone=source.planned_destination_zone,
            )
            session.add(target)
            await session.flush()
        summary["target_supply_id"] = str(target.id)
        summary["target_supply_name"] = target.name
        summary["target_wb_supply_id"] = target.wb_supply_id
        operation.response_summary_json = summary
        await session.commit()
        # Each batch has its own durable dispatch marker: recovery can send
        # untouched batches, but never replays a request with an unknown outcome.
        dispatched = set(summary.get("dispatched_wb_order_ids", []))
        confirmed: set[int] = set()
        if dispatched:
            try:
                confirmed = set(
                    await fetch_marketplace_supply_order_ids(
                        http_client,
                        api_token=token,
                        supply_id=target.wb_supply_id,
                    )
                )
            except WildberriesClientError:
                operation.state = "pending_confirmation"
                await session.commit()
                return _result(operation, orders)
        unsent = [o.wb_order_id for o in orders if o.wb_order_id not in dispatched | confirmed]
        failed = set(summary.get("failed_order_ids", []))
        for batch in split_marketplace_order_id_batches(unsent):
            dispatched.update(batch)
            summary["dispatched_wb_order_ids"] = sorted(dispatched)
            operation.response_summary_json = dict(summary)
            await session.commit()
            try:
                await add_orders_to_marketplace_supply(
                    http_client,
                    api_token=token,
                    supply_id=target.wb_supply_id,
                    order_ids=batch,
                )
            except WildberriesClientError as exc:
                if (
                    exc.status_code is not None
                    and 400 <= exc.status_code < 500
                    and exc.status_code != 408
                ):
                    failed.update(str(o.id) for o in orders if o.wb_order_id in batch)
            summary["failed_order_ids"] = sorted(failed)
            operation.response_summary_json = dict(summary)
            await session.commit()
        if unsent or not dispatched:
            with suppress(WildberriesClientError):
                confirmed = set(
                    await fetch_marketplace_supply_order_ids(
                        http_client,
                        api_token=token,
                        supply_id=target.wb_supply_id,
                    )
                )
        accepted = [o for o in orders if o.wb_order_id in confirmed]
        await _apply_confirmed(session, source, target, accepted)
        summary["transferred_order_ids"] = sorted(
            set(summary.get("transferred_order_ids", [])) | {str(o.id) for o in accepted}
        )
        operation.response_summary_json = summary
        result = _result(operation, orders)
        operation.state = (
            "pending_confirmation"
            if result["pending_order_ids"]
            else "failed"
            if result["failed_order_ids"]
            else "confirmed"
        )
        await session.commit()
        return result
