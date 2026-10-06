"""One scanner intent places one accepted unit, using existing movement receipts."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeDistributionLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.pallet import Pallet
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.warehouse_box import WarehouseBox
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import inbound_intake_service as intake
from app.services import inventory_service as inventory
from app.services import warehouse_map_service as warehouse_map
from app.services.catalog_service import ID_IN_BATCH_SIZE, chunked
from app.services.defect_warehouse_service import get_or_create_defect_location
from app.services.inventory_container_service import ContainerKind
from app.services.sorting_location_service import get_or_create_sorting_location


async def _wb_card_variant_scan_lines(
    session: AsyncSession, req: InboundIntakeRequest, barcode: str,
) -> list[InboundIntakeLine]:
    """Legacy fallback: the WB card's declared per-size ``skus``, matched by chrtId.

    A card can declare an alternative barcode for one specific size (chrtId)
    of a multi-size nm_id before that alternative is persisted into
    ``product_barcodes`` (WMS-535's backfill/import is what does that
    normally) -- ``matching_scan_lines``'s document-scoped index below finds
    it once it is. Until then, this is the only place that still knows about
    it, so it stays as a fallback and keeps its original chrtId scoping: a
    size sibling of the same nm_id that is *not* the document's own chrtId
    must keep failing (a different size was never accepted onto this line).
    """
    keys = {(row.product.seller_id, row.product.wb_nm_id) for row in req.lines
            if row.product.seller_id is not None and row.product.wb_nm_id is not None}
    if not keys:
        return []
    card_type = SellerWildberriesImportedCard
    variants: set[tuple[uuid.UUID, int, str]] = set()
    for batch in chunked(list(keys), min(ID_IN_BATCH_SIZE, 500)):
        cards = await session.scalars(select(card_type).where(
            card_type.tenant_id == req.tenant_id,
            tuple_(card_type.seller_id, card_type.nm_id).in_(batch),
        ))
        for card in cards:
            raw = card.raw_json if isinstance(card.raw_json, dict) else {}
            for size in raw.get("sizes") or []:
                if not isinstance(size, dict) or size.get("chrtID") is None:
                    continue
                if barcode in (size.get("skus") or []):
                    variants.add((card.seller_id, card.nm_id, str(size["chrtID"])))
    return [row for row in req.lines if (
        row.product.seller_id, row.product.wb_nm_id, str(row.product.wb_chrt_id)
    ) in variants]


async def matching_scan_lines(
    session: AsyncSession, req: InboundIntakeRequest, barcode: str,
) -> list[InboundIntakeLine]:
    """Resolve a scan the same way receiving does, scoped to this document's lines.

    WMS-578 review (P2-4): sorting used to check only ``product.wb_barcode``
    (exact case) and the WB card's declared per-size ``skus``. It missed
    everything else receiving's own barcode index already accepts for the
    same document -- extra WB barcodes from ``product_barcodes`` (WMS-535),
    Ozon barcodes, the WMS article, all case-insensitively -- and a product
    sold only on Ozon (no ``wb_barcode``/``wb_nm_id``) could never match at
    all, since the old check compared exclusively against a WB-only field.

    Two tiers, same as receiving:

    1. A direct, unconditional check against each line's own
       ``wb_barcode``/``sku_code`` (case-insensitive) -- this does not depend
       on the document having a resolved ``seller_id`` yet, unlike the index
       below, so it keeps working exactly like the old code did for a
       just-created line whose product only got its seller assigned later.
    2. ``inbound_intake_service._request_barcode_index``/``_index_lookup`` --
       the exact index receiving's own ``resolve_scanned_product_id`` uses,
       scoped to this document's lines (``include_seller_catalog=False``),
       covering everything tier 1 does not: extra WB barcodes, Ozon barcodes.

    The same barcode aliasing two different products of this document is
    ambiguous, exactly as receiving's own equivalent case raises
    ``barcode_ambiguous`` -- here as ``ambiguous_product``, scan_product's own
    established code for it.

    Only when neither tier resolves anything does this fall back to the
    legacy WB-card-variant match below, for a card-declared alternative not
    yet persisted into ``product_barcodes``.
    """
    if not barcode:
        return []
    upper = barcode.upper()
    direct_ids = {
        row.product_id for row in req.lines
        for alias in ((row.product.wb_barcode or "").upper(), (row.product.sku_code or "").upper())
        if alias and alias == upper
    }
    idx = await intake._request_barcode_index(
        session, req.tenant_id, req, include_seller_catalog=False,
    )
    indexed_id, known = intake._index_lookup(idx, barcode)
    if known and indexed_id is None:
        raise warehouse_map.WarehouseMapError("ambiguous_product")
    matched_ids = set(direct_ids)
    if indexed_id is not None:
        matched_ids.add(indexed_id)
    if len(matched_ids) > 1:
        raise warehouse_map.WarehouseMapError("ambiguous_product")
    if matched_ids:
        product_id = next(iter(matched_ids))
        return [row for row in req.lines if row.product_id == product_id]
    return await _wb_card_variant_scan_lines(session, req, barcode)


async def _scan_target_labels(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    cell_id: uuid.UUID,
    to_id: uuid.UUID | None,
) -> set[str]:
    """Как журнал скана называет цель: ячейка или открытая тара."""
    try:
        _, _, _, label = await warehouse_map._destination(
            session, tenant_id, warehouse_id, "cell", cell_id
        )
        if to_id is None:
            return {label}
        kind = await warehouse_map._sorting_destination_kind(
            session, tenant_id, warehouse_id, to_id
        )
        _, _, _, label = await warehouse_map._destination(
            session, tenant_id, warehouse_id, kind, to_id
        )
        return {label}
    except warehouse_map.WarehouseMapError:
        return set()


async def scan_product(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    inbound_request_id: uuid.UUID,
    operation_id: uuid.UUID,
    barcode: str,
    cell_id: uuid.UUID,
    to_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    error = warehouse_map.WarehouseMapError
    barcode = barcode.strip()
    req = await intake.get_request(session, tenant_id, inbound_request_id, for_update=True)
    if req is None or req.warehouse_id != warehouse_id:
        raise error("inbound_request_not_found")
    # WMS-650 Д2: movements of one scan carry the scanner's operation id, the
    # receipt «назад» reverses. Scans recorded before that release used a group
    # derived from the whole intent; their replays are still recognised.
    group_id = operation_id
    legacy_group_id = uuid.uuid5(
        operation_id, f"sorting-scan:{inbound_request_id}:{barcode}:{cell_id}:{to_id}"
    )
    prior = await session.get(InboundIntakeDistributionLine, operation_id)
    event = await session.get(WarehouseMapEvent, operation_id)
    if prior is not None and prior.request_id != req.id:
        raise error("operation_conflict")
    if prior is not None and await session.scalar(select(InventoryMovement.id).where(
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.transfer_group_id == legacy_group_id,
    ).limit(1)) is not None:
        return {"id": str(operation_id), "moved_qty": 1, "reload": True}
    if prior is not None or event is not None:
        # Повтор узнаётся по квитанциям скана: строке журнала карты и движениям
        # группы operation_id. Строка распределения могла уйти при выравнивании
        # наборов (WMS-650), поэтому она — не обязательный признак.
        evidence = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.transfer_group_id == group_id,
        ))).all())
        line_ids = {row.id for row in req.lines}
        placed = [row for row in evidence
                  if row.quantity_delta > 0 and row.storage_location_id == cell_id]
        replayed_lines = await matching_scan_lines(session, req, barcode)
        products = {row.product_id for row in evidence}
        same_cell = (
            prior.storage_location_id == cell_id
            if prior is not None
            else bool(placed) or (
                event is not None
                and event.to_label in await _scan_target_labels(
                    session, tenant_id, warehouse_id, cell_id, to_id
                )
            )
        )
        if (
            not evidence
            or (event is not None and (
                event.tenant_id != tenant_id or event.warehouse_id != warehouse_id
            ))
            or any(row.inbound_intake_line_id not in line_ids for row in evidence)
            or len(products) != 1
            or not same_cell
            or any(row.container_id != to_id for row in placed)
            or [row.product_id for row in replayed_lines] != list(products)
        ):
            raise error("operation_conflict")
        return {"id": str(operation_id), "moved_qty": 1, "reload": True}
    matches = await matching_scan_lines(session, req, barcode)
    if not matches:
        raise error("product_not_on_request")
    if len(matches) != 1:
        raise error("ambiguous_product")
    line = matches[0]
    await inventory.lock_stock_product(session, tenant_id, line.product_id)
    _, _, _, cell_label = await warehouse_map._destination(
        session, tenant_id, warehouse_id, "cell", cell_id
    )
    target_kind: ContainerKind | None = None
    target_label = cell_label
    if to_id is not None:
        target_kind = await warehouse_map._sorting_destination_kind(
            session, tenant_id, warehouse_id, to_id
        )
        location, _, _, target_label = await warehouse_map._destination(
            session, tenant_id, warehouse_id, target_kind, to_id
        )
        if location != cell_id:
            raise error("container_cell_mismatch")
        owned_containers: list[InboundIntakeBox | InboundIntakeCargoPlace] = [
            *req.boxes, *req.cargo_places,
        ]
        belongs_to_request = any(container.id == to_id for container in owned_containers)
        if target_kind == "pallet":
            pallet = await session.get(Pallet, to_id)
            belongs_to_request = (
                pallet is not None and pallet.inbound_request_id == req.id
            ) or any(container.pallet_id == to_id for container in owned_containers)
        elif not belongs_to_request:
            generic = await session.get(WarehouseBox, to_id)
            belongs_to_request = generic is not None and generic.inbound_request_id == req.id
        if not belongs_to_request:
            raise error("destination_not_found")

    async def no_remaining_source() -> None:
        if to_id is not None and await session.scalar(select(InventoryBalance.id).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == line.product_id,
            InventoryBalance.container_id == to_id,
            InventoryBalance.storage_location_id == cell_id,
            InventoryBalance.quantity > 0,
        ).limit(1)) is not None:
            raise error("already_in_target")
        raise error("nothing_to_move")

    if (
        req.status != intake.STATUS_SORTING
        or line.posted_qty >= intake._accepted_qty_for_line(line)
    ):
        await no_remaining_source()

    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
    balances = list((await session.scalars(select(InventoryBalance).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == line.product_id,
        InventoryBalance.storage_location_id == sorting.id,
        InventoryBalance.quantity > 0,
    ).with_for_update())).all())
    physical = {(row.container_kind, row.container_id): row for row in balances}
    candidates: list[tuple[InventoryBalance | None, Any | None]] = []
    pending = 0
    for kind, containers in (("box", req.boxes), ("cargo_place", req.cargo_places)):
        for container in containers:
            for content in container.lines:
                if content.product_id != line.product_id:
                    continue
                remaining = max(0, content.quantity - content.posted_qty)
                pending += remaining
                if remaining and container.id != to_id:
                    candidates.append((physical.get((kind, container.id)), content))
    generic_qty = 0
    for balance in balances:
        owner: Pallet | WarehouseBox | None = None
        if balance.container_kind == "pallet":
            owner = await session.get(Pallet, balance.container_id)
        elif balance.container_id is not None:
            owner = await session.get(WarehouseBox, balance.container_id)
        if owner is not None and owner.inbound_request_id == req.id:
            if balance.container_id == to_id:
                continue
            candidates.append((balance, None))
            generic_qty += balance.quantity
    loose_remaining = intake._accepted_qty_for_line(line) - line.posted_qty - pending - generic_qty
    if loose_remaining > 0:
        candidates.append((physical.get((None, None)), None))
    if not candidates:
        await no_remaining_source()
    if len(candidates) > 1:
        raise error("ambiguous_source")
    source_balance, source_content = candidates[0]
    if source_balance is None:
        raise error("container_stock_missing")
    source_kind = cast(ContainerKind | None, source_balance.container_kind)
    from_label = "Сортировка"
    if source_kind is not None and source_balance.container_id is not None:
        code = await warehouse_map._container_code(
            session, tenant_id, warehouse_id, source_kind, source_balance.container_id
        )
        from_label = warehouse_map._container_title(source_kind, code)
    good_total = max(0, intake._accepted_qty_for_line(line) - line.defective_qty)
    try:
        if line.posted_qty < good_total:
            await inventory.apply_putaway_from_sorting(
                session, tenant_id, from_storage_location_id=sorting.id,
                to_storage_location_id=cell_id, product_id=line.product_id, quantity=1,
                inbound_intake_line_id=line.id, actor_user_id=actor_user_id,
                from_container_kind=source_kind, from_container_id=source_balance.container_id,
                to_container_kind=target_kind, to_container_id=to_id,
                transfer_group_id=group_id,
            )
        else:
            defect = await get_or_create_defect_location(session, tenant_id)
            await inventory.apply_return_defect_putaway(
                session, tenant_id, from_storage_location_id=sorting.id,
                to_storage_location_id=defect.id, product_id=line.product_id, quantity=1,
                inbound_intake_line_id=line.id, actor_user_id=actor_user_id,
                from_container_kind=source_kind, from_container_id=source_balance.container_id,
                transfer_group_id=group_id,
            )
    except ValueError as exc:
        if str(exc) == "insufficient stock":
            raise error("insufficient_sorting_stock") from exc
        raise
    line.posted_qty += 1
    if source_content is not None:
        source_content.posted_qty += 1
    session.add(InboundIntakeDistributionLine(
        id=operation_id, request_id=req.id, product_id=line.product_id,
        storage_location_id=cell_id, quantity=1,
        box_id=(source_balance.container_id
                if source_kind == "box" and source_content is not None else None),
    ))
    session.add(WarehouseMapEvent(
        id=operation_id, tenant_id=tenant_id, warehouse_id=warehouse_id,
        actor_user_id=actor_user_id, subject=line.product.name, quantity=1,
        from_label=from_label, to_label=target_label,
    ))
    intake._maybe_set_distribution_completed(req)
    intake._maybe_complete_request(req)
    await intake._record_charge_if_done(session, req, performer_id=actor_user_id)
    result: dict[str, Any] = {"id": str(operation_id), "moved_qty": 1, "reload": True}
    result["remaining_qty"] = sum(
        max(0, intake._accepted_qty_for_line(row) - row.posted_qty) for row in req.lines
    )
    if line.posted_qty <= good_total:
        target = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == line.product_id,
            InventoryBalance.storage_location_id == cell_id,
            InventoryBalance.container_kind == target_kind,
            InventoryBalance.container_id == to_id,
        ))
        if target is not None:
            result.update(
                reload=False, source_id=str(source_balance.id),
                target_id=str(target.id), product_id=str(line.product_id),
                target_holder=f"obj:{to_id}" if to_id else f"cell:{cell_id}",
            )
    # WMS-650: строки распределения по наборам (короб / россыпь) — как «разложено».
    await warehouse_map.rebalance_distribution(session, req)
    await session.commit()
    return result
