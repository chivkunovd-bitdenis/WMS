"""WMS-650 · «назад» на экране раскладки: отмена одного действия по его квитанциям.

Решение Д2: отмена — обратное действие на сервере, а не перерисовка экрана.
Что вернуть, сервер берёт из квитанций самого действия, которые уже пишутся в
существующие записи: движения остатка с ``transfer_group_id`` = operation_id
действия и строка журнала карты склада с ``id`` = operation_id (подписи
«откуда» и «куда» в ней — место или палета тары). Новых таблиц, журналов и
статусов нет.

Отмена сама пишет такие же квитанции: обратные движения и строку журнала с
идентификатором, производным от отменяемого действия. Поэтому повтор той же
отмены (потерян ответ) и вторая отмена того же действия (двойной клик, дошедший
до сервера) ничего не меняют (R13, R17).

Отказы (ничего не меняется, R13 / Д4 / Д5):
- ``undo_target_not_found`` — такого подтверждённого действия раскладки в этом
  документе нет (отклонённое действие в историю не попадает);
- ``undo_target_moved`` — то, что действие переместило, уже переместили ещё раз
  (или действие иначе отменить нельзя);
- ``undo_document_posted`` — действие оприходовало документ; «назад» не
  переоткрывает его и не трогает начисление (Д5).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeDistributionLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.models.pallet import Pallet
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import inbound_intake_service as intake
from app.services import inventory_service
from app.services import warehouse_map_service as warehouse_map
from app.services.defect_warehouse_service import defect_service_write
from app.services.inventory_container_service import ContainerKind
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    SORTING_LOCATION_LABEL,
    UNASSIGNED_LABEL,
    get_or_create_sorting_location,
)

WarehouseMapError = warehouse_map.WarehouseMapError

# Квитанция отмены выводится из отменяемого действия, а не из идентификатора
# нажатия: отменить одно действие можно только один раз.
_UNDO_RECEIPT_NAME = "wms650-sorting-undo"

BalanceKey = tuple[uuid.UUID, str | None, uuid.UUID | None, uuid.UUID]
Holder = tuple[str, uuid.UUID | None, uuid.UUID]  # (вид, id палеты, место)


def undo_receipt_id(target_operation_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(target_operation_id, _UNDO_RECEIPT_NAME)


def _key(row: InventoryMovement | InventoryBalance) -> BalanceKey:
    return (row.storage_location_id, row.container_kind, row.container_id, row.product_id)


def _mirror_type(movement_type: str) -> str:
    if movement_type == MOVEMENT_TYPE_STOCK_TRANSFER_OUT:
        return MOVEMENT_TYPE_STOCK_TRANSFER_IN
    if movement_type == MOVEMENT_TYPE_STOCK_TRANSFER_IN:
        return MOVEMENT_TYPE_STOCK_TRANSFER_OUT
    return movement_type


async def _balance_quantity(session: AsyncSession, tenant_id: uuid.UUID, key: BalanceKey) -> int:
    location_id, container_kind, container_id, product_id = key
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.storage_location_id == location_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.container_kind.is_(None)
                if container_kind is None
                else InventoryBalance.container_kind == container_kind,
                InventoryBalance.container_id.is_(None)
                if container_id is None
                else InventoryBalance.container_id == container_id,
            )
        )
        or 0
    )


async def _container_titles(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    owned: set[tuple[str, uuid.UUID]],
) -> dict[str, tuple[ContainerKind, uuid.UUID]]:
    """Название тары документа → тара: так журнал называет тару в квитанции."""
    titles: dict[str, tuple[ContainerKind, uuid.UUID]] = {}
    for kind, container_id in owned:
        container_kind = cast(ContainerKind, kind)
        try:
            code = await warehouse_map._container_code(
                session, tenant_id, warehouse_id, container_kind, container_id
            )
        except WarehouseMapError:
            continue
        titles[warehouse_map._container_title(container_kind, code)] = (
            container_kind,
            container_id,
        )
    return titles


async def _resolve_holder(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    sorting_location_id: uuid.UUID,
    label: str,
) -> Holder | None:
    """Подпись журнала «откуда/куда» тары → палета или место; None — не найти."""
    if label in {UNASSIGNED_LABEL, SORTING_LOCATION_LABEL}:
        return ("sorting", None, sorting_location_id)
    cell_prefix = "Ячейка "
    if label.startswith(cell_prefix):
        location = await session.scalar(
            select(StorageLocation).where(
                StorageLocation.tenant_id == tenant_id,
                StorageLocation.warehouse_id == warehouse_id,
                StorageLocation.code == label[len(cell_prefix):],
                StorageLocation.deleted_at.is_(None),
            )
        )
        if location is None or location.code == SORTING_LOCATION_CODE:
            return None
        return ("cell", None, location.id)
    pallet_prefix = warehouse_map._container_title("pallet", "")
    if label.startswith(pallet_prefix):
        pallet = await session.scalar(
            select(Pallet).where(
                Pallet.tenant_id == tenant_id,
                Pallet.warehouse_id == warehouse_id,
                Pallet.code == label[len(pallet_prefix):],
                Pallet.disbanded_at.is_(None),
            )
        )
        if pallet is None:
            return None
        location_id = await warehouse_map._container_location_id(
            session, tenant_id, warehouse_id, "pallet", pallet.id
        )
        return ("pallet", pallet.id, location_id)
    return None


async def _subtree(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> set[tuple[str, uuid.UUID]]:
    """Тара и всё, что сейчас стоит на ней (короба и грузоместа на палете)."""
    refs: set[tuple[str, uuid.UUID]] = {(kind, container_id)}
    if kind != "pallet":
        return refs
    generic = await session.execute(
        select(WarehouseBox.container_kind, WarehouseBox.id).where(
            WarehouseBox.tenant_id == tenant_id,
            WarehouseBox.warehouse_id == warehouse_id,
            WarehouseBox.pallet_id == container_id,
        )
    )
    refs.update((row_kind, row_id) for row_kind, row_id in generic.all())
    boxes = await session.scalars(
        select(InboundIntakeBox.id).where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeBox.pallet_id == container_id,
        )
    )
    refs.update(("box", row_id) for row_id in boxes.all())
    cargos = await session.scalars(
        select(InboundIntakeCargoPlace.id).where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeCargoPlace.pallet_id == container_id,
        )
    )
    refs.update(("cargo_place", row_id) for row_id in cargos.all())
    return refs


@defect_service_write
async def _reverse_movements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    movements: list[InventoryMovement],
    receipt_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Обратные движения: каждая штука — туда, откуда действие её взяло.

    Сначала забираем то, что действие положило (так недостача обнаружится до
    любой записи), затем возвращаем на исходные места. Тип движения зеркальный:
    в отчётах это то же перемещение внутри фулфилмента, не приход и не расход.
    Брак возвращается из зоны брака той же служебной записью, что его туда
    положила, поэтому вызов идёт с правом записи в зону брака.
    """
    ordered = sorted(movements, key=lambda row: row.quantity_delta < 0)
    for row in ordered:
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=row.product_id,
            storage_location_id=row.storage_location_id,
            quantity_delta=-row.quantity_delta,
            _exact_source=row.quantity_delta > 0,
            movement_type=_mirror_type(row.movement_type),
            transfer_group_id=receipt_id,
            inbound_intake_line_id=row.inbound_intake_line_id,
            container_kind=cast(ContainerKind | None, row.container_kind),
            container_id=row.container_id,
            actor_user_id=actor_user_id,
        )


async def undo_sorting_action(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    inbound_request_id: uuid.UUID,
    operation_id: uuid.UUID,
    target_operation_id: uuid.UUID,
) -> dict[str, Any]:
    """Отменить одно подтверждённое действие раскладки документа (R12, R13)."""
    request = await intake.get_request(session, tenant_id, inbound_request_id, for_update=True)
    if request is None or request.warehouse_id != warehouse_id:
        raise WarehouseMapError("inbound_request_not_found")
    answer = {"id": str(operation_id), "target_operation_id": str(target_operation_id)}
    receipt_id = undo_receipt_id(target_operation_id)
    done = await session.get(WarehouseMapEvent, receipt_id)
    if done is not None:
        if done.tenant_id != tenant_id or done.warehouse_id != warehouse_id:
            raise WarehouseMapError("undo_target_not_found")
        return answer
    target = await session.get(WarehouseMapEvent, target_operation_id)
    if target is None or target.tenant_id != tenant_id or target.warehouse_id != warehouse_id:
        raise WarehouseMapError("undo_target_not_found")
    movements = list(
        (
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.transfer_group_id == target_operation_id,
                )
            )
        ).all()
    )
    # Товары блокируем в одном порядке на всех путях (как _container_balances),
    # чтобы две одновременные операции не ждали друг друга по кругу.
    for product_id in sorted({row.product_id for row in movements}, key=str):
        await inventory_service.lock_stock_product(session, tenant_id, product_id)
    lines = {line.id: line for line in request.lines}
    owned = await warehouse_map.sorting_document_containers(
        session, tenant_id, warehouse_id, inbound_request_id
    )
    titles = await _container_titles(session, tenant_id, warehouse_id, owned)
    moved_container = titles.get(target.subject)
    if any(
        row.inbound_intake_line_id is not None and row.inbound_intake_line_id not in lines
        for row in movements
    ):
        raise WarehouseMapError("undo_target_not_found")
    if moved_container is None:
        products = {line.product_id for line in request.lines}
        if not movements or any(
            row.product_id not in products
            or (
                row.container_kind is not None
                and (row.container_kind, row.container_id) not in owned
            )
            for row in movements
        ):
            raise WarehouseMapError("undo_target_not_found")

    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)

    # Прогресс раскладки, который изменило действие: штуки документа, ушедшие
    # из «Сортировки» (разложено +) или вернувшиеся в неё (разложено -).
    inbound_contents: dict[tuple[uuid.UUID, uuid.UUID], InboundIntakeBoxLine
                           | InboundIntakeCargoPlaceLine] = {}
    for box in request.boxes:
        for content in box.lines:
            inbound_contents[(box.id, content.product_id)] = content
    for cargo in request.cargo_places:
        for cargo_content in cargo.lines:
            inbound_contents[(cargo.id, cargo_content.product_id)] = cargo_content
    line_change: dict[uuid.UUID, int] = defaultdict(int)
    content_change: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for row in movements:
        if row.inbound_intake_line_id is None or row.storage_location_id != sorting.id:
            continue
        line_change[row.inbound_intake_line_id] -= row.quantity_delta
        if row.container_id is not None and (row.container_id, row.product_id) in inbound_contents:
            content_change[(row.container_id, row.product_id)] -= row.quantity_delta
    changes_progress = any(line_change.values()) or any(content_change.values())
    if changes_progress and request.status != intake.STATUS_SORTING:
        raise WarehouseMapError("undo_document_posted")
    for line_id, change in line_change.items():
        line = lines[line_id]
        if not 0 <= line.posted_qty - change <= intake._accepted_qty_for_line(line):
            raise WarehouseMapError("undo_target_moved")

    # То, что действие положило, должно лежать там же.
    net: dict[BalanceKey, int] = defaultdict(int)
    for row in movements:
        net[_key(row)] += row.quantity_delta
    for balance_key, quantity in net.items():
        if quantity > 0 and await _balance_quantity(session, tenant_id, balance_key) < quantity:
            raise WarehouseMapError("undo_target_moved")

    subtree: set[tuple[str, uuid.UUID]] = set()
    from_holder: Holder | None = None
    if moved_container is not None:
        kind, container_id = moved_container
        to_holder = await _resolve_holder(
            session, tenant_id=tenant_id, warehouse_id=warehouse_id,
            sorting_location_id=sorting.id, label=target.to_label,
        )
        from_holder = await _resolve_holder(
            session, tenant_id=tenant_id, warehouse_id=warehouse_id,
            sorting_location_id=sorting.id, label=target.from_label,
        )
        if to_holder is None or from_holder is None:
            raise WarehouseMapError("undo_target_moved")
        try:
            current_location = await warehouse_map._container_location_id(
                session, tenant_id, warehouse_id, kind, container_id
            )
        except ValueError as exc:
            raise WarehouseMapError("undo_target_moved") from exc
        current_pallet = await warehouse_map.container_pallet_id(
            session, tenant_id, warehouse_id, kind, container_id
        )
        if current_pallet != to_holder[1] or current_location != to_holder[2]:
            raise WarehouseMapError("undo_target_moved")
        subtree = await _subtree(session, tenant_id, warehouse_id, kind, container_id)
        from_location = from_holder[2]
        # Всё, что сейчас в таре не на исходном месте, ровно то, что действие
        # привезло: иначе отмена разорвала бы тару и её содержимое.
        balances = list(
            (
                await session.scalars(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.quantity > 0,
                        InventoryBalance.container_id.in_([ref[1] for ref in subtree]),
                    )
                )
            ).all()
        )
        for balance in balances:
            if (balance.container_kind, balance.container_id) not in subtree:
                continue
            if balance.storage_location_id == from_location:
                continue
            if net.get(_key(balance), 0) != balance.quantity:
                raise WarehouseMapError("undo_target_moved")
        if any(
            quantity < 0
            and (balance_key[1], balance_key[2]) in subtree
            and balance_key[0] != from_location
            for balance_key, quantity in net.items()
        ):
            raise WarehouseMapError("undo_target_moved")

    # Товар, вынутый из тары, возвращается в ту же тару — она должна стоять там же.
    for (source_location, source_kind, source_id, _product), quantity in net.items():
        if quantity >= 0 or source_kind is None or source_id is None:
            continue
        if (source_kind, source_id) in subtree:
            continue
        try:
            where = await warehouse_map._container_location_id(
                session, tenant_id, warehouse_id, cast(ContainerKind, source_kind), source_id
            )
        except ValueError as exc:
            raise WarehouseMapError("undo_target_moved") from exc
        if where != source_location:
            raise WarehouseMapError("undo_target_moved")

    try:
        await _reverse_movements(
            session,
            tenant_id,
            movements=movements,
            receipt_id=receipt_id,
            actor_user_id=actor_user_id,
        )
    except ValueError as exc:
        # Штук там, куда их положило действие, уже нет — их кто-то сдвинул
        # между проверкой и записью. Отменять нечего, а не «ошибка сервера».
        if str(exc) == "insufficient stock":
            raise WarehouseMapError("undo_target_moved") from exc
        raise
    if moved_container is not None and from_holder is not None:
        kind, container_id = moved_container
        holder_kind, pallet_id, location_id = from_holder
        await warehouse_map._place_container(
            session,
            tenant_id,
            warehouse_id,
            kind,
            container_id,
            cast(warehouse_map.DestinationKind, holder_kind),
            pallet_id,
            location_id,
        )

    for line_id, change in line_change.items():
        lines[line_id].posted_qty -= change
    for content_key, change in content_change.items():
        # «Разложено» короба — в пределах самого короба, как и при снятии: в
        # короб могли доложить сканом штуки сверх его состава.
        content_row = inbound_contents[content_key]
        content_row.posted_qty = max(
            0, min(int(content_row.quantity), int(content_row.posted_qty) - change)
        )
    await _restore_distribution(
        session,
        request=request,
        movements=movements,
        line_change=line_change,
        sorting_location_id=sorting.id,
        target_operation_id=target_operation_id,
        receipt_id=receipt_id,
    )
    session.add(
        WarehouseMapEvent(
            id=receipt_id,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            actor_user_id=actor_user_id,
            subject=target.subject,
            quantity=target.quantity,
            from_label=target.to_label,
            to_label=target.from_label,
        )
    )
    await warehouse_map.rebalance_distribution(session, request)
    await session.commit()
    return answer


async def _restore_distribution(
    session: AsyncSession,
    *,
    request: InboundIntakeRequest,
    movements: list[InventoryMovement],
    line_change: dict[uuid.UUID, int],
    sorting_location_id: uuid.UUID,
    target_operation_id: uuid.UUID,
    receipt_id: uuid.UUID,
) -> None:
    """Строки распределения документа (квитанции раскладки, Д2) — как до действия.

    Строки делятся по коробу приёмки (или «без короба»), как их делит само
    распределение: сумма по коробу и по товару должна совпадать с «разложено».
    Отмена постановки снимает строки того же набора (квитанция действия —
    первой, без отбора по месту: брак мог уйти в зону брака, а строка записана
    на ячейку скана). Отмена снятия возвращает ровно снятое количество туда,
    где штуки снова стоят.
    """
    changed_lines = {line_id for line_id, change in line_change.items() if change}
    lines = {line.id: line for line in request.lines}
    for row in movements:
        if row.inbound_intake_line_id not in changed_lines:
            continue
        line = lines[row.inbound_intake_line_id]
        box_id = warehouse_map.distribution_box_id(request, row.container_kind, row.container_id)
        if row.storage_location_id == sorting_location_id and row.quantity_delta < 0:
            # Действие разложило эти штуки из «Сортировки» — снимаем их строки.
            placed_at = next(
                (
                    one.storage_location_id for one in movements
                    if one.quantity_delta > 0
                    and one.product_id == row.product_id
                    and one.storage_location_id != sorting_location_id
                ),
                None,
            )
            await warehouse_map.release_distribution(
                session,
                request_id=request.id,
                product_id=line.product_id,
                quantity=-row.quantity_delta,
                box_id=box_id,
                prefer_location_id=placed_at,
                prefer_id=target_operation_id,
            )
        elif row.storage_location_id != sorting_location_id and row.quantity_delta < 0:
            # Действие сняло эти штуки с места — возвращаем строки туда же:
            # в строки короба не больше, чем в нём помещается (снятие брало их
            # первыми), остальное — строкой без короба, как было при скане.
            quantity = -row.quantity_delta
            in_box = 0
            if box_id is not None:
                await session.flush()
                capacity = next(
                    (
                        content.quantity
                        for box in request.boxes
                        if box.id == box_id
                        for content in box.lines
                        if content.product_id == line.product_id
                    ),
                    0,
                )
                used = int(
                    await session.scalar(
                        select(func.coalesce(func.sum(InboundIntakeDistributionLine.quantity), 0))
                        .where(
                            InboundIntakeDistributionLine.request_id == request.id,
                            InboundIntakeDistributionLine.product_id == line.product_id,
                            InboundIntakeDistributionLine.box_id == box_id,
                        )
                    )
                    or 0
                )
                in_box = max(0, min(quantity, int(capacity) - used))
            for part, part_box, name in (
                (in_box, box_id, "box"),
                (quantity - in_box, None, "loose"),
            ):
                if part <= 0:
                    continue
                session.add(
                    InboundIntakeDistributionLine(
                        id=uuid.uuid5(receipt_id, f"{row.id}:{name}"),
                        request_id=request.id,
                        product_id=line.product_id,
                        storage_location_id=row.storage_location_id,
                        quantity=part,
                        box_id=part_box,
                    )
                )
