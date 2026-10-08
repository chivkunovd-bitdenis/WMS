"""Boxes and barcode scanning for marketplace unload requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document_event import (
    DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
    EVENT_DATA_CHANGED,
    SOURCE_SYSTEM,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import marketplace_unload_collect_service as collect_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services import warehouse_box_service as wh_box_svc
from app.services import warehouse_map_service
from app.services.document_event_service import record_document_event
from app.services.inventory_container_service import (
    ContainerKind,
    InventoryContainerScanError,
    resolve_container_scan,
    validate_container,
)
from app.services.marketplace_unload_pick_service import (
    MarketplaceUnloadPickError,
    find_location_by_barcode,
)
from app.services.marketplace_unload_status import DELETE_EDITABLE_STATUSES, STATUS_COLLECTING
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

ALLOWED_BOX_PRESETS = frozenset({"60_40_40", "30_20_30"})
MAX_BATCH_BOX_COUNT = 50


class MarketplaceUnloadBoxError(Exception):
    def __init__(self, code: str, detail: dict[str, object] | None = None) -> None:
        self.code = code
        # Структурированный отказ (WMS-686): код плюс сообщение и перечень товаров.
        # Пусто у всех прежних отказов — они по-прежнему отдаются одной строкой кода.
        self.detail = detail
        super().__init__(code)


@dataclass(frozen=True)
class BoxScanResult:
    """TSD scan flow: location (optional) → ready box / product → box line update."""

    kind: Literal["location", "container", "product", "ready_box"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    container_kind: ContainerKind | None = None
    container_id: uuid.UUID | None = None
    container_code: str | None = None
    box_line: MarketplaceUnloadBoxLine | None = None
    picked_qty: int | None = None
    lines_added: int | None = None
    total_qty: int | None = None
    # Product snapshots let a durable mutation receipt replay the response even
    # after the ORM line has changed in a later scan.
    line_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    sku_code: str | None = None
    product_name: str | None = None
    quantity: int | None = None


def _scan_receipt_key(mutation_id: uuid.UUID) -> str:
    return f"marketplace-unload:box-scan:{mutation_id}"


def _scan_request_payload(
    *,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    barcode: str,
    product_id_hint: uuid.UUID | None,
    storage_location_id: uuid.UUID | None,
    quantity: int,
    allow_over_plan: bool,
    container_kind: ContainerKind | None,
    container_id: uuid.UUID | None,
) -> dict[str, object]:
    return {
        "request_id": str(request_id),
        "box_id": str(box_id),
        "barcode": barcode,
        "product_id": str(product_id_hint) if product_id_hint is not None else None,
        "storage_location_id": (
            str(storage_location_id) if storage_location_id is not None else None
        ),
        "quantity": quantity,
        "allow_over_plan": allow_over_plan,
        "container_kind": container_kind,
        "container_id": str(container_id) if container_id is not None else None,
    }


async def _scan_replay(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    request_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    mutation_id: uuid.UUID,
    request_payload: dict[str, object],
) -> BoxScanResult | None:
    event = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _scan_receipt_key(mutation_id),
        )
    )
    if event is None:
        return None
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_MARKETPLACE_UNLOAD
        or event.document_id != request_id
        or event.actor_user_id != actor_user_id
        or payload.get("kind") != "marketplace_unload_box_scan_receipt_v1"
        or payload.get("request") != request_payload
    ):
        raise MarketplaceUnloadBoxError("mutation_payload_mismatch")
    saved = payload.get("result")
    if isinstance(saved, dict):
        return BoxScanResult(
            kind="product",
            storage_location_id=(
                uuid.UUID(str(saved["storage_location_id"]))
                if saved.get("storage_location_id") is not None
                else None
            ),
            picked_qty=int(saved["picked_qty"]),
            line_id=uuid.UUID(str(saved["line_id"])),
            product_id=uuid.UUID(str(saved["product_id"])),
            sku_code=(str(saved["sku_code"]) if saved.get("sku_code") is not None else None),
            product_name=str(saved["product_name"]),
            quantity=int(saved["quantity"]),
        )

    # Compatibility for the tiny crash window after the warehouse commit but
    # before the response snapshot update: the receipt still proves the
    # increment happened, so reconstruct a success without applying it again.
    product_id_raw = request_payload.get("product_id") or event.product_id
    if product_id_raw is None:
        raise MarketplaceUnloadBoxError("mutation_result_missing")
    product_id = uuid.UUID(str(product_id_raw))
    box_id = uuid.UUID(str(request_payload["box_id"]))
    line = await session.scalar(
        select(MarketplaceUnloadBoxLine)
        .where(
            MarketplaceUnloadBoxLine.box_id == box_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
        .options(selectinload(MarketplaceUnloadBoxLine.product))
    )
    if line is None:
        raise MarketplaceUnloadBoxError("mutation_result_missing")
    return BoxScanResult(
        kind="product",
        storage_location_id=(
            uuid.UUID(str(request_payload["storage_location_id"]))
            if request_payload.get("storage_location_id") is not None
            else None
        ),
        picked_qty=await collect_svc.picked_qty_for_product(session, request_id, product_id),
        line_id=line.id,
        product_id=line.product_id,
        sku_code=line.product.sku_code,
        product_name=line.product.name,
        quantity=int(line.quantity),
    )


def _map_collect_err(exc: MarketplaceUnloadPickError) -> MarketplaceUnloadBoxError:
    return MarketplaceUnloadBoxError(exc.code)


async def _barcode_index_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> dict[str, uuid.UUID]:
    rows = await list_seller_wb_catalog_rows(session, tenant_id, seller_id)
    idx: dict[str, uuid.UUID] = {}
    for r in rows:
        for b in r.wb_barcodes:
            key = str(b).strip()
            if key:
                idx[key] = r.product_id
        if r.wb_primary_barcode:
            k = r.wb_primary_barcode.strip()
            if k:
                idx[k] = r.product_id
    return idx


async def _request_for_picking(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> MarketplaceUnloadRequest:
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .options(selectinload(MarketplaceUnloadRequest.lines))
        .execution_options(populate_existing=True)
    )
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    if req.status not in mu_svc.EXECUTION_STATUSES:
        raise MarketplaceUnloadBoxError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")
    return req


async def _open_box_for_request(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    return await collect_svc.get_open_box(session, request_id)


async def create_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    box_preset: str,
) -> MarketplaceUnloadBox:
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    req = await _request_for_picking(session, tenant_id, request_id)
    existing = await _open_box_for_request(session, request_id)
    if existing is not None:
        raise MarketplaceUnloadBoxError("open_box_exists")

    wh_box = await wh_box_svc.create_warehouse_box(
        session,
        tenant_id,
        warehouse_id=req.warehouse_id,
    )
    box = MarketplaceUnloadBox(
        request_id=request_id,
        box_preset=preset,
        warehouse_box_id=wh_box.id,
    )
    session.add(box)
    mu_svc.enter_collecting_if_needed(req)
    await session.flush()
    await mu_svc.record_box_mutation(
        session,
        tenant_id,
        box,
        before=None,
        after=mu_svc.box_audit_fields(box),
    )
    await session.commit()
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == box.id)
        .options(
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def create_boxes_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    count: int,
    box_preset: str,
) -> list[MarketplaceUnloadBox]:
    """Create N empty open boxes with barcodes (batch flow; no open_box_exists gate)."""
    if count < 1 or count > MAX_BATCH_BOX_COUNT:
        raise MarketplaceUnloadBoxError("invalid_batch_count")
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    req = await _request_for_picking(session, tenant_id, request_id)

    created_ids: list[uuid.UUID] = []
    for _ in range(count):
        wh_box = await wh_box_svc.create_warehouse_box(
            session,
            tenant_id,
            warehouse_id=req.warehouse_id,
        )
        box = MarketplaceUnloadBox(
            request_id=request_id,
            box_preset=preset,
            warehouse_box_id=wh_box.id,
            closed_at=None,
        )
        session.add(box)
        await session.flush()
        await mu_svc.record_box_mutation(
            session,
            tenant_id,
            box,
            before=None,
            after=mu_svc.box_audit_fields(box),
        )
        created_ids.append(box.id)

    mu_svc.enter_collecting_if_needed(req)
    await session.commit()
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id.in_(created_ids))
        .options(
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
        .order_by(MarketplaceUnloadBox.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _product_in_shipment(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _finish_box_collection(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> None:
    """Commit only after every requested line passed source and quantity checks.

    WMS-686 D0.3: задание упаковки для FBO — рудимент, его строки здесь не пересчитываются.
    """
    await session.commit()


async def _source_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> uuid.UUID:
    """INB putaway can leave stale metadata; use its sole current stock location."""
    await validate_container(session, tenant_id, warehouse_id, kind, container_id)
    locations = list((await session.scalars(
        select(StorageLocation)
        .join(InventoryBalance, InventoryBalance.storage_location_id == StorageLocation.id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.container_kind == kind,
            InventoryBalance.container_id == container_id,
            InventoryBalance.quantity > 0,
        ).distinct()
    )).all())
    if len(locations) > 1 or any(
        location.tenant_id != tenant_id or location.warehouse_id != warehouse_id
        for location in locations
    ):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    if locations:
        return locations[0].id
    # Empty sources keep their identity; availability still checks this container only.
    return await warehouse_map_service.resolve_container_location(
        session, tenant_id, warehouse_id, kind, container_id
    )


async def _assert_whole_box_fits_plan(
    session: AsyncSession,
    req: MarketplaceUnloadRequest,
    balances: list[InventoryBalance],
) -> None:
    """Перенос короба целиком: по каждому товару «в коробе» не больше «плана минус подобрано».

    Проверка идёт до любого изменения: при нарушении нельзя ни взять часть
    короба, ни оставить полупереложенное. Товар вне плана — тот же отказ с
    «осталось 0». Короб с лишним нужно открыть и подобрать поштучно.
    """
    in_box: dict[uuid.UUID, int] = {}
    for balance in balances:
        in_box[balance.product_id] = in_box.get(balance.product_id, 0) + int(balance.quantity)
    plan = {line.product_id: int(line.quantity) for line in req.lines}
    picked = await collect_svc.picked_qty_by_product(session, req.id)
    over = {
        product_id: (quantity, max(0, plan.get(product_id, 0) - picked.get(product_id, 0)))
        for product_id, quantity in in_box.items()
        if quantity > max(0, plan.get(product_id, 0) - picked.get(product_id, 0))
    }
    if not over:
        return
    names = {
        product_id: name
        for product_id, name in (
            await session.execute(
                select(Product.id, Product.name).where(Product.id.in_(list(over)))
            )
        ).all()
    }
    items = sorted(
        (
            {
                "product_id": str(product_id),
                "product_name": names.get(product_id) or str(product_id),
                "in_box": quantity,
                "remaining": remaining,
            }
            for product_id, (quantity, remaining) in over.items()
        ),
        key=lambda item: (str(item["product_name"]), str(item["product_id"])),
    )
    listed = "; ".join(
        f"{item['product_name']} — в коробе {item['in_box']}, осталось {item['remaining']}"
        for item in items
    )
    raise MarketplaceUnloadBoxError(
        "plan_limit_exceeded",
        {
            "code": "plan_limit_exceeded",
            "message": (
                "Количество товаров в коробе больше, чем осталось подобрать: "
                f"{listed}. Откройте короб и подберите поштучно."
            ),
            "items": items,
        },
    )


@dataclass(frozen=True)
class _WholeBoxSource:
    """Короб-источник целиком: что за тара, откуда её брать и что в ней лежит сейчас."""

    kind: ContainerKind
    container_id: uuid.UUID
    location_id: uuid.UUID
    balances: list[InventoryBalance]


async def _resolve_whole_box_source(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: MarketplaceUnloadRequest,
    barcode: str,
) -> _WholeBoxSource:
    """Только чтение: определить короб по ШК и его текущий состав. Ничего не меняет."""
    try:
        source = await resolve_container_scan(session, tenant_id, req.warehouse_id, barcode)
        location_id = await _source_location(
            session, tenant_id, req.warehouse_id, source.kind, source.id
        )
    except (
        InventoryContainerScanError, ValueError, warehouse_map_service.WarehouseMapError
    ) as exc:
        raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
    if source.kind != "box":
        raise MarketplaceUnloadBoxError("box_barcode_unknown")
    balances = list((await session.scalars(
        select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.container_kind == source.kind,
            InventoryBalance.container_id == source.id,
            InventoryBalance.quantity > 0,
        ).order_by(InventoryBalance.product_id)
    )).all())
    if not balances:
        raise MarketplaceUnloadBoxError("box_empty")
    if any(balance.storage_location_id != location_id for balance in balances):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    return _WholeBoxSource(
        kind=source.kind,
        container_id=source.id,
        location_id=location_id,
        balances=balances,
    )


async def _collect_whole_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: MarketplaceUnloadRequest,
    box_id: uuid.UUID,
    whole: _WholeBoxSource,
    *,
    allow_over_plan: bool,
    actor_user_id: uuid.UUID | None,
) -> tuple[int, int]:
    total = 0
    for balance in whole.balances:
        quantity = int(balance.quantity)
        try:
            await collect_svc.collect_into_box(
                session, tenant_id, req.id,
                box_id=box_id,
                storage_location_id=whole.location_id,
                product_id=balance.product_id,
                quantity=quantity,
                allow_over_plan=allow_over_plan,
                actor_user_id=actor_user_id,
                container_kind=whole.kind,
                container_id=whole.container_id,
            )
        except MarketplaceUnloadPickError as exc:
            raise _map_collect_err(exc) from None
        total += quantity
    return len(whole.balances), total


async def _collect_current_box_contents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: MarketplaceUnloadRequest,
    box_id: uuid.UUID,
    barcode: str,
    *,
    allow_over_plan: bool,
    actor_user_id: uuid.UUID | None,
) -> tuple[int, int]:
    whole = await _resolve_whole_box_source(session, tenant_id, req, barcode)
    if not allow_over_plan:
        await _assert_whole_box_fits_plan(session, req, whole.balances)
    return await _collect_whole_box(
        session, tenant_id, req, box_id, whole,
        allow_over_plan=allow_over_plan, actor_user_id=actor_user_id,
    )


async def collect_ready_box_into_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
) -> BoxScanResult:
    """Explicit whole-box operation: consume only this container's current stock."""
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    req = await _request_for_picking(session, tenant_id, box.request_id)
    lines_added, total_qty = await _collect_current_box_contents(
        session, tenant_id, req, box_id, barcode,
        allow_over_plan=allow_over_plan, actor_user_id=actor_user_id,
    )
    mu_svc.enter_collecting_if_needed(req)
    await _finish_box_collection(session, tenant_id, req.id)
    return BoxScanResult(kind="ready_box", lines_added=lines_added, total_qty=total_qty)


async def scan_barcode_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
    request_id: uuid.UUID | None = None,
    product_id_hint: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None,
    quantity: int = 1,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
    mutation_id: uuid.UUID | None = None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> BoxScanResult:
    """Scan flow for TSD/web: optional location barcode, then product → box line."""
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadBoxError("barcode_empty")
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None or (request_id is not None and box.request_id != request_id):
        raise MarketplaceUnloadBoxError("box_not_found")

    effective_request_id = box.request_id
    request_payload = _scan_request_payload(
        request_id=effective_request_id,
        box_id=box_id,
        barcode=raw,
        product_id_hint=product_id_hint,
        storage_location_id=storage_location_id,
        quantity=quantity,
        allow_over_plan=allow_over_plan,
        container_kind=container_kind,
        container_id=container_id,
    )
    if mutation_id is not None:
        replay = await _scan_replay(
            session,
            tenant_id,
            request_id=effective_request_id,
            actor_user_id=actor_user_id,
            mutation_id=mutation_id,
            request_payload=request_payload,
        )
        if replay is not None:
            return replay

    req = await _request_for_picking(session, tenant_id, effective_request_id)
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")

    address_on = await tenant_settings_svc.is_address_storage_enabled(session, tenant_id)
    if address_on:
        loc = await find_location_by_barcode(session, tenant_id, req.warehouse_id, raw)
        if loc is not None:
            return BoxScanResult(
                kind="location",
                storage_location_id=loc.id,
                location_code=loc.code,
            )

    # A storage container selects the exact source; it does not move its contents.
    try:
        container = await resolve_container_scan(session, tenant_id, req.warehouse_id, raw)
    except InventoryContainerScanError as exc:
        if exc.code != "container_scan_not_found":
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
    else:
        try:
            location_id = await _source_location(
                session, tenant_id, req.warehouse_id, container.kind, container.id
            )
        except (ValueError, warehouse_map_service.WarehouseMapError) as exc:
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
        return BoxScanResult(
            kind="container",
            storage_location_id=location_id,
            container_kind=container.kind,
            container_id=container.id,
            container_code=container.code,
        )

    if product_id_hint is None:
        idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
        product_id = idx.get(raw)
        if product_id is None:
            raise MarketplaceUnloadBoxError("barcode_unknown")
    else:
        product_id = product_id_hint

    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    if mutation_id is not None:
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await session.execute(
                sa.update(DocumentEvent).where(sa.false()).values(idempotency_key=None)
            )
        inserted = await record_document_event(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
            document_id=effective_request_id,
            event_type=EVENT_DATA_CHANGED,
            source=SOURCE_USER if actor_user_id is not None else SOURCE_SYSTEM,
            actor_user_id=actor_user_id,
            product_id=product_id,
            payload_json={
                "kind": "marketplace_unload_box_scan_receipt_v1",
                "request": request_payload,
                "result": None,
            },
            idempotency_key=_scan_receipt_key(mutation_id),
        )
        if not inserted:
            replay = await _scan_replay(
                session,
                tenant_id,
                request_id=effective_request_id,
                actor_user_id=actor_user_id,
                mutation_id=mutation_id,
                request_payload=request_payload,
            )
            assert replay is not None
            return replay

    line = await add_manual_qty_to_box(
        session,
        tenant_id,
        box_id,
        storage_location_id=storage_location_id,
        product_id=product_id,
        quantity=quantity,
        actor_user_id=actor_user_id,
        allow_over_plan=allow_over_plan,
        container_kind=container_kind,
        container_id=container_id,
    )
    result = BoxScanResult(
        kind="product",
        storage_location_id=storage_location_id,
        box_line=line,
        picked_qty=await collect_svc.picked_qty_for_product(session, box.request_id, product_id),
        line_id=line.id,
        product_id=line.product_id,
        sku_code=line.product.sku_code,
        product_name=line.product.name,
        quantity=int(line.quantity),
    )
    if mutation_id is not None:
        receipt = await session.scalar(
            select(DocumentEvent).where(
                DocumentEvent.tenant_id == tenant_id,
                DocumentEvent.idempotency_key == _scan_receipt_key(mutation_id),
            )
        )
        assert receipt is not None
        receipt.payload_json = {
            "kind": "marketplace_unload_box_scan_receipt_v1",
            "request": request_payload,
            "result": {
                "line_id": str(result.line_id),
                "product_id": str(result.product_id),
                "sku_code": result.sku_code,
                "product_name": result.product_name,
                "quantity": result.quantity,
                "picked_qty": result.picked_qty,
                "storage_location_id": (
                    str(result.storage_location_id)
                    if result.storage_location_id is not None
                    else None
                ),
            },
        }
        await session.commit()
    return result


async def boxed_qty_for_product(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Сколько единиц товара уже разложено по коробам этой отгрузки."""
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _packed_picked_not_yet_boxed(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Ready units already picked for this document but not yet placed in a box."""
    picked_stmt = select(
        func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity_packed), 0)
    ).where(
        MarketplaceUnloadPickAllocation.request_id == request_id,
        MarketplaceUnloadPickAllocation.product_id == product_id,
    )
    boxed_stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity_packed), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    picked_packed = int((await session.execute(picked_stmt)).scalar_one() or 0)
    boxed_packed = int((await session.execute(boxed_stmt)).scalar_one() or 0)
    return max(0, picked_packed - boxed_packed)


async def _known_picked_not_yet_boxed(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Known-source picked units which have not yet been put in a box.

    Moving an allocation into a box is not a new pick.  It can carry forward
    source evidence that already exists on the allocation, but cannot create
    it for a historical NULL allocation.
    """
    picked_stmt = select(
        func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity_source_known), 0)
    ).where(
        MarketplaceUnloadPickAllocation.request_id == request_id,
        MarketplaceUnloadPickAllocation.product_id == product_id,
    )
    boxed_stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity_source_known), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    picked_known = int((await session.execute(picked_stmt)).scalar_one() or 0)
    boxed_known = int((await session.execute(boxed_stmt)).scalar_one() or 0)
    return max(0, picked_known - boxed_known)


async def _place_picked_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box: MarketplaceUnloadBox,
    *,
    product_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadBoxLine:
    """Переложить уже подобранный товар в короб.

    Подбор его со склада уже списал и создал аллокацию, поэтому второй раз
    трогать остатки нельзя — иначе одна и та же единица спишется дважды.
    Здесь только строка короба и пересчёт прогресса упаковки.
    """
    packed_quantity = min(
        quantity,
        await _packed_picked_not_yet_boxed(session, box.request_id, product_id),
    )
    source_known = min(
        quantity,
        await _known_picked_not_yet_boxed(session, box.request_id, product_id),
    )
    source_known = max(source_known, packed_quantity)
    stmt = select(MarketplaceUnloadBoxLine).where(
        MarketplaceUnloadBoxLine.box_id == box.id,
        MarketplaceUnloadBoxLine.product_id == product_id,
    )
    line = (await session.execute(stmt)).scalar_one_or_none()
    if line is None:
        line = MarketplaceUnloadBoxLine(
            box_id=box.id,
            product_id=product_id,
            quantity=quantity,
            quantity_packed=packed_quantity,
            quantity_source_known=source_known,
        )
        session.add(line)
    else:
        line.quantity = int(line.quantity) + quantity
        line.quantity_packed = int(line.quantity_packed or 0) + packed_quantity
        if line.quantity_source_known is None:
            line.quantity_source_known = source_known
        else:
            line.quantity_source_known = int(line.quantity_source_known) + source_known

    await session.flush()
    line_id = line.id
    await session.flush()
    # Load the product for serialization; the public operation owns the commit.
    loaded = (
        await session.execute(
            select(MarketplaceUnloadBoxLine)
            .where(MarketplaceUnloadBoxLine.id == line_id)
            .options(selectinload(MarketplaceUnloadBoxLine.product))
        )
    ).scalar_one()
    return loaded


async def add_manual_qty_to_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID | None,
    quantity: int,
    actor_user_id: uuid.UUID | None,
    allow_over_plan: bool = False,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> MarketplaceUnloadBoxLine:
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")

    req = await _request_for_picking(session, tenant_id, box.request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    if (container_kind is None) != (container_id is None):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    if container_kind is not None and container_id is not None:
        try:
            await validate_container(
                session, tenant_id, req.warehouse_id, container_kind, container_id
            )
            source_location_id = await _source_location(
                session, tenant_id, req.warehouse_id, container_kind, container_id
            )
        except (ValueError, warehouse_map_service.WarehouseMapError) as exc:
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
        if storage_location_id is not None and storage_location_id != source_location_id:
            raise MarketplaceUnloadBoxError("invalid_container_reference")
        storage_location_id = source_location_id

    # Serialize placement with collection: two scans cannot spend the same picked unit.
    await session.execute(
        select(MarketplaceUnloadRequest.id)
        .where(MarketplaceUnloadRequest.id == req.id)
        .with_for_update()
    )

    # Упаковка идёт после подбора, и товар к этому моменту уже снят со склада.
    # Раньше любое наполнение короба шло через подбор, а тот отказывал с
    # plan_limit_exceeded, потому что план уже выбран: отгрузка, подобранная
    # россыпью, становилась незавершаемой навсегда. Поэтому сначала кладём в
    # короб то, что уже подобрано и ещё не разложено, и только недостающее
    # добираем со склада обычным подбором.
    picked = await collect_svc.picked_qty_for_product(session, box.request_id, product_id)
    boxed = await boxed_qty_for_product(session, box.request_id, product_id)
    from_picked = max(0, min(quantity, picked - boxed))
    to_collect = quantity - from_picked

    line: MarketplaceUnloadBoxLine | None = None
    if from_picked > 0:
        line = await _place_picked_into_box(
            session, tenant_id, box, product_id=product_id, quantity=from_picked
        )
    if to_collect > 0:
        try:
            result = await collect_svc.collect_into_box(
                session,
                tenant_id,
                box.request_id,
                box_id=box_id,
                storage_location_id=storage_location_id,
                product_id=product_id,
                quantity=to_collect,
                actor_user_id=actor_user_id,
                allow_over_plan=allow_over_plan,
                container_kind=container_kind,
                container_id=container_id,
            )
        except MarketplaceUnloadPickError as exc:
            raise _map_collect_err(exc) from None
        line = result.box_line
    assert line is not None
    await _finish_box_collection(session, tenant_id, req.id)
    return line


async def attach_existing_box_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    box_preset: str = "60_40_40",
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBox:
    """Привязать существующий короб (WHB или приёмочный) и развернуть состав в подбор.

    Короб переносится целиком или не переносится вовсе: пока не доказано, что весь
    состав помещается в оставшийся план, в сессии нет ни одного изменения.
    WMS-686 D1.7: остаток плана проверяется всегда; allow_over_plan из тела запроса
    оставлен в сигнатуре только для совместимости старых клиентов и игнорируется.
    """
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    # Замок документа первым: проверка плана и перенос видят одно и то же состояние,
    # а два одновременных переноса не расходуют один и тот же остаток плана.
    await session.execute(
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    req = await _request_for_picking(session, tenant_id, request_id)

    wh_box, inb_box = await wh_box_svc.resolve_barcode(session, tenant_id, barcode)
    if wh_box is None and inb_box is None:
        raise MarketplaceUnloadBoxError("box_barcode_unknown")

    if wh_box is not None and wh_box.warehouse_id != req.warehouse_id:
        raise MarketplaceUnloadBoxError("warehouse_mismatch")

    # Тот же короб второй раз в той же отгрузке не привязывается — ни складской, ни
    # приёмочный. Проверка до переноса: понятный отказ вместо «короб пуст».
    same_box = (
        MarketplaceUnloadBox.warehouse_box_id == wh_box.id
        if wh_box is not None
        else MarketplaceUnloadBox.inbound_intake_box_id == (inb_box.id if inb_box else None)
    )
    already = await session.scalar(
        select(MarketplaceUnloadBox.id)
        .where(MarketplaceUnloadBox.request_id == request_id, same_box)
        .limit(1)
    )
    if already is not None:
        raise MarketplaceUnloadBoxError("box_already_attached")

    whole = await _resolve_whole_box_source(session, tenant_id, req, barcode)
    await _assert_whole_box_fits_plan(session, req, whole.balances)

    mp_box = MarketplaceUnloadBox(
        request_id=request_id,
        box_preset=preset,
        warehouse_box_id=wh_box.id if wh_box is not None else None,
        inbound_intake_box_id=inb_box.id if inb_box is not None else None,
    )
    session.add(mp_box)
    await session.flush()

    await _collect_whole_box(
        session, tenant_id, req, mp_box.id, whole,
        allow_over_plan=False, actor_user_id=actor_user_id,
    )

    mp_box.closed_at = datetime.now(tz=UTC)
    await mu_svc.record_box_mutation(
        session,
        tenant_id,
        mp_box,
        before=None,
        after=mu_svc.box_audit_fields(mp_box),
    )
    mu_svc.enter_collecting_if_needed(req)
    await _finish_box_collection(session, tenant_id, req.id)
    await session.refresh(
        mp_box, attribute_names=["warehouse_box", "inbound_intake_box", "lines"]
    )
    return mp_box


async def extract_all_from_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    """«Извлечь всё»: очистить состав короба, сам короб остаётся пустым.

    Меняется только состав этого короба. Подобранное (аллокации), КИЗ, остаток и
    расположение не трогаются: штуки остаются подобранными и их можно снова
    разложить. Повторный вызов на пустом коробе ничего не меняет.
    """
    # Замок документа первым: статус читается под замком, а «Завершить» и
    # одновременное наполнение короба не идут параллельно с очисткой.
    await session.execute(
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await _request_for_picking(session, tenant_id, request_id)
    box = await session.get(MarketplaceUnloadBox, box_id, populate_existing=True)
    if box is None or box.request_id != request_id:
        raise MarketplaceUnloadBoxError("box_not_found")

    lines = list(
        (
            await session.scalars(
                select(MarketplaceUnloadBoxLine).where(MarketplaceUnloadBoxLine.box_id == box_id)
            )
        ).all()
    )
    if lines:
        before = mu_svc.box_audit_fields(box)
        before["lines"] = [
            {"product_id": str(line.product_id), "quantity": int(line.quantity)}
            for line in sorted(lines, key=lambda x: str(x.product_id))
        ]
        after = mu_svc.box_audit_fields(box)
        after["lines"] = []
        for line in lines:
            await session.delete(line)
        await mu_svc.record_box_mutation(session, tenant_id, box, before=before, after=after)
        await session.commit()

    res = await session.execute(
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == box_id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
        .execution_options(populate_existing=True)
    )
    return res.scalars().unique().one()


async def close_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await _request_for_picking(session, tenant_id, box.request_id)
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")
    before = mu_svc.box_audit_fields(box)
    box.closed_at = datetime.now(tz=UTC)
    await mu_svc.record_box_mutation(
        session,
        tenant_id,
        box,
        before=before,
        after=mu_svc.box_audit_fields(box),
    )
    await session.commit()
    await session.refresh(box, attribute_names=["warehouse_box", "inbound_intake_box"])
    return box


async def list_boxes_with_lines(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> list[MarketplaceUnloadBox]:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.request_id == request_id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
        .order_by(MarketplaceUnloadBox.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


def _box_total_qty(box: MarketplaceUnloadBox) -> int:
    return sum(int(ln.quantity) for ln in box.lines)


async def remove_box_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int | None = None,
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBoxLine | None:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    # Lock before reading the line: two terminals correcting the same closed box
    # must not both reverse the same pick against a stale line quantity.
    status_stmt = (
        select(MarketplaceUnloadRequest.status)
        .where(
            MarketplaceUnloadRequest.id == box.request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    request_status = (await session.execute(status_stmt)).scalar_one_or_none()
    if request_status is None:
        raise MarketplaceUnloadBoxError("not_found")
    if request_status not in (*DELETE_EDITABLE_STATUSES, STATUS_COLLECTING):
        raise MarketplaceUnloadBoxError("not_draft")
    line = await session.get(MarketplaceUnloadBoxLine, line_id)
    if line is None and quantity is None:
        # The mobile client can retry a full-line correction after losing the
        # first response. There is no stock left to reverse for this line id.
        return None
    if line is None or line.box_id != box_id:
        raise MarketplaceUnloadBoxError("line_not_found")
    try:
        return await collect_svc.remove_from_box(
            session,
            tenant_id,
            box.request_id,
            box_id=box_id,
            line_id=line_id,
            quantity=quantity,
            actor_user_id=actor_user_id,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_collect_err(exc) from None


async def delete_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> None:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await session.refresh(box, attribute_names=["lines"])
    await _request_for_picking(session, tenant_id, box.request_id)
    total_stmt = select(
        func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0)
    ).where(MarketplaceUnloadBoxLine.box_id == box_id)
    total_qty = int((await session.execute(total_stmt)).scalar_one())
    if total_qty > 0:
        raise MarketplaceUnloadBoxError("box_not_empty")
    await mu_svc.record_box_mutation(
        session,
        tenant_id,
        box,
        before=mu_svc.box_audit_fields(box),
        after=None,
    )
    await session.delete(box)
    await session.commit()


async def copy_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBox:
    """Duplicate a closed source box into a new closed box (REV-FIX-015).

    Intentionally closed: copy is a snapshot for shipping labels / repeat shipment,
    not for further manual add (use batch create for open boxes).
    """
    src_stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == box_id)
        .options(
            selectinload(MarketplaceUnloadBox.lines),
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
        .execution_options(populate_existing=True)
    )
    src = (await session.execute(src_stmt)).scalar_one_or_none()
    if src is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await session.refresh(src, attribute_names=["lines"])
    req = await _request_for_picking(session, tenant_id, src.request_id)
    if not src.lines:
        raise MarketplaceUnloadBoxError("box_empty")

    picked = await collect_svc.picked_qty_by_product(session, req.id)
    plan_stmt = select(
        MarketplaceUnloadLine.product_id,
        MarketplaceUnloadLine.quantity,
    ).where(MarketplaceUnloadLine.request_id == req.id)
    plan_by_product = {
        product_id: int(quantity)
        for product_id, quantity in (await session.execute(plan_stmt)).all()
    }
    for ln in src.lines:
        pid = ln.product_id
        add_qty = int(ln.quantity)
        if add_qty < 1:
            continue
        current = picked.get(pid, 0)
        plan_qty = plan_by_product.get(pid, 0)
        if current + add_qty > plan_qty:
            raise MarketplaceUnloadBoxError("plan_limit_exceeded")

    wh_box = await wh_box_svc.create_warehouse_box(
        session,
        tenant_id,
        warehouse_id=req.warehouse_id,
    )
    new_box = MarketplaceUnloadBox(
        request_id=req.id,
        box_preset=src.box_preset,
        warehouse_box_id=wh_box.id,
    )
    session.add(new_box)
    await session.flush()

    for ln in src.lines:
        qty = int(ln.quantity)
        if qty < 1:
            continue
        remaining = qty
        alloc_stmt = (
            select(MarketplaceUnloadPickAllocation)
            .where(
                MarketplaceUnloadPickAllocation.request_id == req.id,
                MarketplaceUnloadPickAllocation.product_id == ln.product_id,
                MarketplaceUnloadPickAllocation.quantity > 0,
            )
            .order_by(MarketplaceUnloadPickAllocation.quantity.desc())
        )
        alloc_res = await session.execute(alloc_stmt)
        allocs = list(alloc_res.scalars().all())
        if not allocs:
            raise MarketplaceUnloadBoxError("insufficient_available")
        for alloc in allocs:
            if remaining < 1:
                break
            chunk = min(int(alloc.quantity), remaining)
            try:
                await collect_svc.collect_into_box(
                    session,
                    tenant_id,
                    req.id,
                    box_id=new_box.id,
                    storage_location_id=alloc.storage_location_id,
                    container_kind=cast(ContainerKind | None, alloc.container_kind),
                    container_id=alloc.container_id,
                    product_id=ln.product_id,
                    quantity=chunk,
                    require_open_box=False,
                    actor_user_id=actor_user_id,
                )
            except MarketplaceUnloadPickError as exc:
                raise _map_collect_err(exc) from None
            remaining -= chunk
        if remaining > 0:
            raise MarketplaceUnloadBoxError("insufficient_available")

    new_box.closed_at = datetime.now(tz=UTC)
    await mu_svc.record_box_mutation(
        session,
        tenant_id,
        new_box,
        before=None,
        after=mu_svc.box_audit_fields(new_box),
    )
    await _finish_box_collection(session, tenant_id, req.id)

    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == new_box.id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadBox.warehouse_box),
            selectinload(MarketplaceUnloadBox.inbound_intake_box),
        )
    )
    res = await session.execute(stmt)
    return res.scalars().unique().one()
