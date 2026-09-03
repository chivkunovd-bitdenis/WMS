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
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_event import (
    DOCUMENT_TYPE_FBS_ORDER,
    DOCUMENT_TYPE_FBS_SUPPLY,
    DocumentEvent,
)
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBox
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.user import User


class FbsOrderHistoryError(ValueError):
    pass


PRINT_KIND_LABELS: dict[str, str] = {
    "order_sticker": "Стикер заказа",
    "supply_qr": "QR поставки",
    "cargo_place_qr": "QR грузоместа",
    "box_qr": "QR короба",
}

SUPPLY_EVENT_LABELS: dict[str, str] = {
    "line_added": "Заказ добавлен в поставку",
    "line_removed": "Заказ убран из поставки",
    "status_changed": "Статус поставки изменён",
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
    # Смены статуса самого заказа журнал ведёт с 03.09.2026 — по заказам старше
    # этой даты их просто нет, и это честнее, чем достраивать задним числом.
    order_events = list(
        (
            await session.scalars(
                select(DocumentEvent).where(
                    DocumentEvent.tenant_id == tenant_id,
                    DocumentEvent.document_type == DOCUMENT_TYPE_FBS_ORDER,
                    DocumentEvent.document_id == order_id,
                )
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
        | {row.actor_user_id for row in supply_events if row.actor_user_id}
        | {row.actor_user_id for row in order_events if row.actor_user_id},
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

    for order_event in order_events:
        payload = order_event.payload_json or {}
        before = payload.get("status_before") or "—"
        after = payload.get("status_after") or "—"
        events.append(
            _event(
                order_event.occurred_at,
                "status",
                f"Статус: {before} → {after}",
                actor=(
                    actors.get(order_event.actor_user_id) if order_event.actor_user_id else None
                ),
                details=f"статус в WB: {payload.get('wb_status') or '—'}",
            )
        )

    for supply_event in supply_events:
        payload = supply_event.payload_json or {}
        # Строчные события поставки касаются конкретного заказа. Пока ссылки на
        # заказ в них не было, историю одного заказа засыпало добавлениями всех
        # соседей по поставке — по таким записям ничего не восстановишь. Чужие
        # и неатрибутированные строки пропускаем, а не выдаём за свои.
        if supply_event.event_type in {"line_added", "line_removed"} and payload.get(
            "fbs_order_id"
        ) != str(order_id):
            continue
        title = SUPPLY_EVENT_LABELS.get(supply_event.event_type, supply_event.event_type)
        details = None
        if supply_event.event_type == "status_changed":
            details = f"{payload.get('from') or '—'} → {payload.get('to') or '—'}"
        events.append(
            _event(
                supply_event.occurred_at,
                "supply",
                title,
                actor=(
                    actors.get(supply_event.actor_user_id) if supply_event.actor_user_id else None
                ),
                details=details,
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


SUPPLY_STATUS_LABELS: dict[str, str] = {
    "draft": "черновик",
    "assembling": "сборка",
    "packed": "упакована",
    "in_delivery": "передана в доставку",
    "done": "принята Wildberries",
}

PRINT_TITLES: dict[str, tuple[str, str]] = {
    "order_sticker": ("Стикеры заказов запрошены", "Стикеры заказов получены от WB"),
    "supply_qr": ("QR поставки запрошен", "QR поставки получен от WB"),
    "cargo_place_qr": ("QR грузомест запрошены", "QR грузомест получены от WB"),
    "box_qr": ("QR коробов запрошены", "QR коробов получены от WB"),
}


def _bucket(moment: datetime) -> str:
    """Ключ склейки: одно действие оператора рождает пачку записей в одну секунду."""
    return moment.replace(microsecond=0).isoformat()


def _grouped_event(
    at: datetime,
    kind: str,
    title: str,
    items: list[str],
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Одна строка вместо пачки одинаковых: подробности прячутся внутрь строки."""
    return {
        "at": at.isoformat(),
        "kind": kind,
        "title": title if len(items) <= 1 else f"{title} ({len(items)})",
        "actor": actor,
        "details": items[0] if len(items) == 1 else None,
        "items": items if len(items) > 1 else [],
    }


async def supply_history(
    session: AsyncSession, *, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> dict[str, Any]:
    """Хронология поставки: что с ней и её заказами происходило, по часам.

    История операционная, а не денежная: по ней восстанавливают, кто собрал,
    что печатал, какие короба завёл и когда поставка уехала. Однотипные записи
    склеиваются в одну строку — иначе печать сорока стикеров превращает историю
    в сорок одинаковых строк, по которым ничего не найдёшь.
    """
    supply = await session.scalar(
        select(FbsSupply).where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
    )
    if supply is None:
        raise FbsOrderHistoryError("fbs_supply_not_found")

    orders = list(
        (await session.scalars(select(FbsOrder).where(FbsOrder.supply_id == supply_id))).all()
    )
    order_ids = [order.id for order in orders]
    numbers = {order.id: str(order.wb_order_id) for order in orders}

    picks = (
        list(
            (
                await session.scalars(
                    select(FbsOrderPick).where(FbsOrderPick.fbs_order_id.in_(order_ids))
                )
            ).all()
        )
        if order_ids
        else []
    )
    packings = (
        list(
            (
                await session.scalars(
                    select(FbsPackagingFulfillment).where(
                        FbsPackagingFulfillment.fbs_order_id.in_(order_ids)
                    )
                )
            ).all()
        )
        if order_ids
        else []
    )
    markings = (
        list(
            (
                await session.scalars(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id.in_(order_ids))
                )
            ).all()
        )
        if order_ids
        else []
    )
    prints = list(
        (
            await session.scalars(
                select(FbsPrintAsset).where(
                    (FbsPrintAsset.fbs_supply_id == supply_id)
                    | (FbsPrintAsset.fbs_order_id.in_(order_ids) if order_ids else false())
                )
            )
        ).all()
    )
    boxes = list(
        (
            await session.scalars(
                select(FbsPackingBox).where(FbsPackingBox.supply_id == supply_id)
            )
        ).all()
    )
    supply_events = list(
        (
            await session.scalars(
                select(DocumentEvent).where(
                    DocumentEvent.tenant_id == tenant_id,
                    DocumentEvent.document_type == DOCUMENT_TYPE_FBS_SUPPLY,
                    DocumentEvent.document_id == supply_id,
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

    events: list[dict[str, Any]] = []
    created = _event(supply.created_at, "created", "Поставка создана")
    if created is not None:
        events.append({**created, "items": []})

    # Заказы в поставке: добавление, снятие, отмена.
    for event in supply_events:
        payload = event.payload_json or {}
        if event.event_type in {"line_added", "line_removed"}:
            order_uuid = payload.get("fbs_order_id")
            number = numbers.get(uuid.UUID(order_uuid)) if order_uuid else None
            title = "Заказ добавлен в поставку" if event.event_type == "line_added" else (
                "Заказ убран из поставки"
            )
            events.append(
                {
                    "at": event.occurred_at.isoformat(),
                    "kind": "order",
                    "title": title if number is None else f"{title}: {number}",
                    "actor": actors.get(event.actor_user_id) if event.actor_user_id else None,
                    "details": None,
                    "items": [],
                }
            )
        elif event.event_type == "status_changed":
            before = SUPPLY_STATUS_LABELS.get(str(payload.get("from")), payload.get("from") or "—")
            after = SUPPLY_STATUS_LABELS.get(str(payload.get("to")), payload.get("to") or "—")
            events.append(
                {
                    "at": event.occurred_at.isoformat(),
                    "kind": "status",
                    "title": f"Поставка: {before} → {after}",
                    "actor": actors.get(event.actor_user_id) if event.actor_user_id else None,
                    "details": None,
                    "items": [],
                }
            )

    for order in orders:
        if order.status == "cancelled":
            row = _event(order.updated_at, "cancelled", f"Заказ отменён: {numbers[order.id]}")
            if row is not None:
                events.append({**row, "items": []})

    # Подбор: важна тара, из которой взяли товар.
    picked: dict[tuple[str, str | None, str | None], list[str]] = defaultdict(list)
    for pick in picks:
        if pick.picked_at is None:
            continue
        actor = actors.get(pick.picked_by_user_id) if pick.picked_by_user_id else None
        where = (
            f"из тары {pick.source_container_kind}"
            if pick.source_container_kind
            else "с ячейки"
        )
        picked[(_bucket(pick.picked_at), actor, where)].append(
            numbers.get(pick.fbs_order_id, "—")
        )
    for (pick_moment, pick_actor, pick_where), pick_items in picked.items():
        events.append(
            _grouped_event(
                datetime.fromisoformat(pick_moment),
                "pick",
                f"Товар подобран {pick_where}",
                pick_items,
                actor=pick_actor,
            )
        )

    packed: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for packing in packings:
        if packing.fulfilled_at is None:
            continue
        actor = (
            actors.get(packing.fulfilled_by_user_id) if packing.fulfilled_by_user_id else None
        )
        packed[(_bucket(packing.fulfilled_at), actor)].append(
            numbers.get(packing.fbs_order_id, "—")
        )
    for (pack_moment, pack_actor), pack_items in packed.items():
        events.append(
            _grouped_event(
                datetime.fromisoformat(pack_moment),
                "packed",
                "Заказ упакован",
                pack_items,
                actor=pack_actor,
            )
        )

    # Честные знаки: номера прячем внутрь строки, иначе их сотни.
    marked: dict[tuple[str, str], list[str]] = defaultdict(list)
    for marking in markings:
        mark_at = getattr(marking, "created_at", None)
        if mark_at is None:
            continue
        marked[(_bucket(mark_at), MARKING_KIND_LABELS.get(marking.kind, marking.kind))].append(
            marking.value
        )
    for (mark_moment, mark_label), mark_items in marked.items():
        events.append(
            _grouped_event(
                datetime.fromisoformat(mark_moment),
                "marking",
                f"Внесены коды: {mark_label}",
                mark_items,
            )
        )

    printed: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for asset in prints:
        titles = PRINT_TITLES.get(asset.kind)
        if titles is None:
            continue
        label = numbers.get(asset.fbs_order_id, "") if asset.fbs_order_id else ""
        if asset.created_at is not None:
            printed[(_bucket(asset.created_at), asset.kind, "requested")].append(label)
        if asset.wb_fetched_at is not None:
            printed[(_bucket(asset.wb_fetched_at), asset.kind, "ready")].append(label)
    for (print_moment, print_kind, stage), print_items in printed.items():
        requested, ready = PRINT_TITLES[print_kind]
        events.append(
            _grouped_event(
                datetime.fromisoformat(print_moment),
                "print",
                requested if stage == "requested" else ready,
                [item for item in print_items if item],
            )
        )

    boxed: dict[str, list[str]] = defaultdict(list)
    for box in boxes:
        boxed[_bucket(box.created_at)].append(f"№{box.box_number}")
    for box_moment, box_items in boxed.items():
        events.append(
            _grouped_event(
                datetime.fromisoformat(box_moment), "box", "Короб добавлен", box_items
            )
        )

    events.sort(key=lambda row: row["at"])
    return {
        "supply_id": str(supply.id),
        "supply_number": supply.display_number or supply.wb_supply_id or supply.name,
        "status": supply.status,
        "order_count": len(orders),
        "events": events,
    }
