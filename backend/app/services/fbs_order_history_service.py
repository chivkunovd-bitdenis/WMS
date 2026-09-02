"""История заказа FBS: что с ним происходило, по часам.

Зачем. Когда с заказом что-то не так, восстановить картину сейчас нечем: кто его
подобрал, когда упаковали, какие коды маркировки внесли, печатали ли стикер, в
какой поставке уехал и что ответил Wildberries при передаче — всё это лежит в
разных таблицах, и человек собирает историю глазами по базе.

Здесь она собирается за него. Ничего нового не пишется: события берутся из тех
записей, которые система и так ведёт, — подборы, упаковка, маркировки, печатные
документы, журнал документа поставки. Поэтому история доступна и по старым
заказам, а не только по тем, что приедут после выкатки.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_event import DOCUMENT_TYPE_FBS_SUPPLY, DocumentEvent
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.user import User


class FbsOrderHistoryError(ValueError):
    pass


PRINT_KIND_LABELS: dict[str, str] = {
    "order_sticker": "Стикер заказа",
    "supply_qr": "QR поставки",
    "cargo_place_qr": "QR грузоместа",
    "box_qr": "QR короба",
}

MARKING_KIND_LABELS: dict[str, str] = {
    "sgtin": "Честный знак",
    "uin": "УИН",
    "imei": "IMEI",
    "gtin": "GTIN",
}


def _event(
    at: datetime | None,
    kind: str,
    title: str,
    *,
    actor: str | None = None,
    details: str | None = None,
) -> dict[str, Any] | None:
    if at is None:
        return None
    return {
        "at": at.isoformat(),
        "kind": kind,
        "title": title,
        "actor": actor,
        "details": details,
    }


async def _actor_names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = (await session.execute(select(User.id, User.email).where(User.id.in_(ids)))).all()
    return {row[0]: row[1] for row in rows}


async def order_history(
    session: AsyncSession, *, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> dict[str, Any]:
    """Собрать хронологию заказа из уже существующих записей."""
    order = await session.scalar(
        select(FbsOrder).where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
    )
    if order is None:
        raise FbsOrderHistoryError("fbs_order_not_found")

    picks = list(
        (
            await session.scalars(
                select(FbsOrderPick)
                .where(FbsOrderPick.fbs_order_id == order_id)
                .order_by(FbsOrderPick.picked_at)
            )
        ).all()
    )
    packings = list(
        (
            await session.scalars(
                select(FbsPackagingFulfillment)
                .where(FbsPackagingFulfillment.fbs_order_id == order_id)
                .order_by(FbsPackagingFulfillment.fulfilled_at)
            )
        ).all()
    )
    markings = list(
        (
            await session.scalars(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
        ).all()
    )
    prints = list(
        (
            await session.scalars(
                select(FbsPrintAsset).where(FbsPrintAsset.fbs_order_id == order_id)
            )
        ).all()
    )
    supply_events: list[DocumentEvent] = []
    if order.supply_id is not None:
        supply_events = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.tenant_id == tenant_id,
                        DocumentEvent.document_type == DOCUMENT_TYPE_FBS_SUPPLY,
                        DocumentEvent.document_id == order.supply_id,
                    )
                )
            ).all()
        )

    actors = await _actor_names(
        session,
        {pick.picked_by_user_id for pick in picks if pick.picked_by_user_id}
        | {row.fulfilled_by_user_id for row in packings if row.fulfilled_by_user_id}
        | {row.actor_user_id for row in supply_events if row.actor_user_id},
    )

    events: list[dict[str, Any] | None] = [
        _event(order.created_at, "created", "Заказ появился в системе"),
    ]

    for pick in picks:
        where = "с ячейки"
        if pick.source_container_kind:
            where = f"из тары ({pick.source_container_kind})"
        events.append(
            _event(
                pick.picked_at,
                "pick",
                "Товар подобран",
                actor=actors.get(pick.picked_by_user_id) if pick.picked_by_user_id else None,
                details=f"{where}, штрихкод {pick.scanned_product_barcode or '—'}",
            )
        )

    for packing in packings:
        events.append(
            _event(
                packing.fulfilled_at,
                "packed",
                "Заказ упакован",
                actor=(
                    actors.get(packing.fulfilled_by_user_id)
                    if packing.fulfilled_by_user_id
                    else None
                ),
            )
        )
        events.append(
            _event(packing.undone_at, "packed_undone", "Упаковка отменена")
        )

    for marking in markings:
        label = MARKING_KIND_LABELS.get(marking.kind, marking.kind)
        status = marking.meta_status
        events.append(
            _event(
                getattr(marking, "created_at", None),
                "marking",
                f"Внесён код: {label}",
                details=f"{marking.value[:32]}… · статус {status}"
                + (f" · {marking.reason}" if marking.reason else ""),
            )
        )

    for asset in prints:
        label = PRINT_KIND_LABELS.get(asset.kind, asset.kind)
        events.append(
            _event(asset.created_at, "print_requested", f"{label}: запрошен")
        )
        events.append(_event(asset.wb_fetched_at, "print_ready", f"{label}: получен от WB"))
        events.append(_event(asset.applied_at, "print_applied", f"{label}: наклеен"))

    for supply_event in supply_events:
        payload = supply_event.payload_json or {}
        events.append(
            _event(
                supply_event.occurred_at,
                "supply",
                f"Поставка: {supply_event.event_type}",
                actor=(
                    actors.get(supply_event.actor_user_id) if supply_event.actor_user_id else None
                ),
                details=", ".join(f"{key}: {value}" for key, value in payload.items()) or None,
            )
        )

    timeline = [event for event in events if event is not None]
    timeline.sort(key=lambda row: row["at"])
    return {
        "order_id": str(order.id),
        "wb_order_id": order.wb_order_id,
        "status": order.status,
        "wb_status": order.wb_status,
        "supply_id": str(order.supply_id) if order.supply_id else None,
        "events": timeline,
    }
