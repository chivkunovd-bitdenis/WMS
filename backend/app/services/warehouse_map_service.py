from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC
from typing import Any, Literal, cast

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import (
    inbound_container_putaway_service,
    inventory_service,
    pallet_service,
    warehouse_box_service,
)
from app.services.inventory_container_service import ContainerKind, validate_container
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    UNASSIGNED_LABEL,
    get_or_create_sorting_location,
)
from app.services.tenant_settings_service import is_address_storage_enabled
from app.services.wb_card_enrichment import first_photo_url_from_card, subject_name_from_card

ObjectKind = Literal["product", "pallet", "box", "cargo_place"]
DestinationKind = Literal["cell", "unassigned", "sorting", "pallet", "box", "cargo_place"]
MOVEMENT_TYPE_WAREHOUSE_MAP = "warehouse_map_move"


@dataclass(frozen=True)
class PendingInboundContent:
    kind: Literal["box", "cargo_place"]
    container_id: uuid.UUID
    line_id: uuid.UUID
    product: Product
    seller: Seller | None
    quantity: int


class WarehouseMapError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WarehouseContainerPathItem:
    kind: ContainerKind
    id: uuid.UUID
    code: str
    label: str


def _container_title(kind: str, code: str) -> str:
    title = {"pallet": "Палета", "box": "Короб", "cargo_place": "Грузоместо"}[kind]
    return f"{title} {code}"


def _container_path_item(
    kind: ContainerKind,
    container_id: uuid.UUID,
    code: str,
) -> WarehouseContainerPathItem:
    return WarehouseContainerPathItem(
        kind=kind,
        id=container_id,
        code=code,
        label=_container_title(kind, code),
    )


async def resolve_container_paths(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    container_refs: set[tuple[ContainerKind, uuid.UUID]],
) -> dict[tuple[ContainerKind, uuid.UUID], tuple[WarehouseContainerPathItem, ...]]:
    """Return map-compatible human container paths within one tenant warehouse."""
    if not container_refs:
        return {}
    await _assert_warehouse(session, tenant_id, warehouse_id)
    pallets = list(
        (
            await session.scalars(
                select(Pallet).where(
                    Pallet.tenant_id == tenant_id,
                    Pallet.warehouse_id == warehouse_id,
                    Pallet.disbanded_at.is_(None),
                )
            )
        ).all()
    )
    warehouse_boxes, inbound_boxes, cargo_places = await _load_boxes(
        session, tenant_id, warehouse_id
    )
    pallet_by_id = {pallet.id: pallet for pallet in pallets}
    warehouse_box_by_key: dict[tuple[ContainerKind, uuid.UUID], WarehouseBox] = {
        (box.container_kind, box.id): box for box in warehouse_boxes
    }
    inbound_box_by_id = {box.id: box for box in inbound_boxes}
    cargo_place_by_id = {place.id: place for place in cargo_places}

    paths: dict[
        tuple[ContainerKind, uuid.UUID], tuple[WarehouseContainerPathItem, ...]
    ] = {}
    for ref in container_refs:
        kind, container_id = ref
        if kind == "pallet":
            pallet = pallet_by_id.get(container_id)
            if pallet is None:
                raise WarehouseMapError("container_not_found")
            paths[ref] = (_container_path_item("pallet", pallet.id, pallet.code),)
            continue

        code: str
        parent_pallet_id: uuid.UUID | None
        warehouse_box = warehouse_box_by_key.get(ref)
        if warehouse_box is not None:
            code = warehouse_box.internal_barcode
            parent_pallet_id = warehouse_box.pallet_id
        elif kind == "box" and container_id in inbound_box_by_id:
            inbound_box = inbound_box_by_id[container_id]
            code = f"КР-{inbound_box.box_number:06d}"
            parent_pallet_id = inbound_box.pallet_id
        elif kind == "cargo_place" and container_id in cargo_place_by_id:
            cargo_place = cargo_place_by_id[container_id]
            code = f"ГМ-{cargo_place.place_number:06d}"
            parent_pallet_id = cargo_place.pallet_id
        else:
            raise WarehouseMapError("container_not_found")

        path: list[WarehouseContainerPathItem] = []
        if parent_pallet_id is not None:
            parent = pallet_by_id.get(parent_pallet_id)
            if parent is None:
                raise WarehouseMapError("container_not_found")
            path.append(_container_path_item("pallet", parent.id, parent.code))
        path.append(_container_path_item(kind, container_id, code))
        paths[ref] = tuple(path)
    return paths


def _card_data(card: SellerWildberriesImportedCard | None) -> tuple[str | None, str | None]:
    raw = card.raw_json if card is not None else None
    if not isinstance(raw, dict):
        return None, None
    return subject_name_from_card(raw), first_photo_url_from_card(raw)


async def _assert_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise WarehouseMapError("warehouse_not_found")
    return warehouse


async def _load_boxes(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> tuple[list[WarehouseBox], list[InboundIntakeBox], list[InboundIntakeCargoPlace]]:
    warehouse_boxes = list(
        (
            await session.scalars(
                select(WarehouseBox).where(
                    WarehouseBox.tenant_id == tenant_id,
                    WarehouseBox.warehouse_id == warehouse_id,
                )
            )
        ).all()
    )
    inbound_boxes = list(
        (
            await session.scalars(
                select(InboundIntakeBox)
                .join(InboundIntakeRequest)
                .outerjoin(
                    StorageLocation,
                    StorageLocation.id == InboundIntakeBox.storage_location_id,
                )
                .where(
                    InboundIntakeBox.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    or_(
                        StorageLocation.warehouse_id == warehouse_id,
                        and_(
                            InboundIntakeBox.storage_location_id.is_(None),
                            InboundIntakeRequest.warehouse_id == warehouse_id,
                        ),
                    ),
                )
            )
        ).all()
    )
    cargo_places = list(
        (
            await session.scalars(
                select(InboundIntakeCargoPlace)
                .join(InboundIntakeRequest)
                .outerjoin(
                    StorageLocation,
                    StorageLocation.id
                    == InboundIntakeCargoPlace.storage_location_id,
                )
                .where(
                    InboundIntakeCargoPlace.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    or_(
                        StorageLocation.warehouse_id == warehouse_id,
                        and_(
                            InboundIntakeCargoPlace.storage_location_id.is_(None),
                            InboundIntakeRequest.warehouse_id == warehouse_id,
                        ),
                    ),
                )
            )
        ).all()
    )
    return warehouse_boxes, inbound_boxes, cargo_places


async def _load_map_rows(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> tuple[
    list[tuple[InventoryBalance, StorageLocation, Product, Seller | None]],
    list[StorageLocation],
    list[Pallet],
    list[WarehouseBox],
    list[InboundIntakeBox],
    list[InboundIntakeCargoPlace],
    list[PendingInboundContent],
    dict[uuid.UUID, str | None],
    dict[tuple[uuid.UUID, int], SellerWildberriesImportedCard],
]:
    rows = cast(
        list[tuple[InventoryBalance, StorageLocation, Product, Seller | None]],
        list(
            (
                await session.execute(
                    select(InventoryBalance, StorageLocation, Product, Seller)
                    .join(
                        StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id
                    )
                    .join(Product, Product.id == InventoryBalance.product_id)
                    .outerjoin(Seller, Seller.id == Product.seller_id)
                    .where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.quantity > 0,
                        StorageLocation.tenant_id == tenant_id,
                        StorageLocation.warehouse_id == warehouse_id,
                        Product.tenant_id == tenant_id,
                    )
                )
            ).all()
        ),
    )
    locations = list(
        (
            await session.scalars(
                select(StorageLocation)
                .where(
                    StorageLocation.tenant_id == tenant_id,
                    StorageLocation.warehouse_id == warehouse_id,
                    StorageLocation.deleted_at.is_(None),
                )
                .order_by(StorageLocation.code)
            )
        ).all()
    )
    pallets = list(
        (
            await session.scalars(
                select(Pallet)
                .where(
                    Pallet.tenant_id == tenant_id,
                    Pallet.warehouse_id == warehouse_id,
                    Pallet.disbanded_at.is_(None),
                )
                .order_by(Pallet.code)
            )
        ).all()
    )
    warehouse_boxes, inbound_boxes, cargo_places = await _load_boxes(
        session, tenant_id, warehouse_id
    )
    pending_contents: list[PendingInboundContent] = []
    box_line_rows = await session.execute(
        select(InboundIntakeBoxLine, InboundIntakeBox, Product, Seller)
        .join(InboundIntakeBox, InboundIntakeBox.id == InboundIntakeBoxLine.box_id)
        .join(
            InboundIntakeRequest,
            InboundIntakeRequest.id == InboundIntakeBox.request_id,
        )
        .outerjoin(
            StorageLocation,
            StorageLocation.id == InboundIntakeBox.storage_location_id,
        )
        .join(Product, Product.id == InboundIntakeBoxLine.product_id)
        .outerjoin(Seller, Seller.id == Product.seller_id)
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            or_(
                StorageLocation.warehouse_id == warehouse_id,
                and_(
                    InboundIntakeBox.storage_location_id.is_(None),
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                ),
            ),
            InboundIntakeBoxLine.quantity > InboundIntakeBoxLine.posted_qty,
            ~exists(
                select(InventoryBalance.id).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.container_kind == "box",
                    InventoryBalance.container_id == InboundIntakeBox.id,
                    InventoryBalance.product_id == InboundIntakeBoxLine.product_id,
                )
            ),
        )
    )
    pending_contents.extend(
        PendingInboundContent(
            kind="box",
            container_id=box.id,
            line_id=line.id,
            product=product,
            seller=seller,
            quantity=max(0, int(line.quantity) - int(line.posted_qty)),
        )
        for line, box, product, seller in box_line_rows.all()
    )
    cargo_line_rows = await session.execute(
        select(
            InboundIntakeCargoPlaceLine,
            InboundIntakeCargoPlace,
            Product,
            Seller,
        )
        .join(
            InboundIntakeCargoPlace,
            InboundIntakeCargoPlace.id
            == InboundIntakeCargoPlaceLine.cargo_place_id,
        )
        .join(
            InboundIntakeRequest,
            InboundIntakeRequest.id == InboundIntakeCargoPlace.request_id,
        )
        .outerjoin(
            StorageLocation,
            StorageLocation.id == InboundIntakeCargoPlace.storage_location_id,
        )
        .join(Product, Product.id == InboundIntakeCargoPlaceLine.product_id)
        .outerjoin(Seller, Seller.id == Product.seller_id)
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            or_(
                StorageLocation.warehouse_id == warehouse_id,
                and_(
                    InboundIntakeCargoPlace.storage_location_id.is_(None),
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                ),
            ),
            InboundIntakeCargoPlaceLine.quantity
            > InboundIntakeCargoPlaceLine.posted_qty,
            ~exists(
                select(InventoryBalance.id).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.container_kind == "cargo_place",
                    InventoryBalance.container_id == InboundIntakeCargoPlace.id,
                    InventoryBalance.product_id
                    == InboundIntakeCargoPlaceLine.product_id,
                )
            ),
        )
    )
    pending_contents.extend(
        PendingInboundContent(
            kind="cargo_place",
            container_id=place.id,
            line_id=line.id,
            product=product,
            seller=seller,
            quantity=max(0, int(line.quantity) - int(line.posted_qty)),
        )
        for line, place, product, seller in cargo_line_rows.all()
    )
    request_ids = {
        *(box.request_id for box in inbound_boxes),
        *(place.request_id for place in cargo_places),
        *(
            pallet.inbound_request_id
            for pallet in pallets
            if pallet.inbound_request_id is not None
        ),
        *(
            box.inbound_request_id
            for box in warehouse_boxes
            if box.inbound_request_id is not None
        ),
    }
    request_numbers: dict[uuid.UUID, str | None] = {}
    if request_ids:
        request_rows = await session.execute(
            select(
                InboundIntakeRequest.id,
                InboundIntakeRequest.display_number,
                InboundIntakeRequest.document_number,
            ).where(
                InboundIntakeRequest.id.in_(request_ids),
                InboundIntakeRequest.tenant_id == tenant_id,
            )
        )
        request_numbers = {
            request_id: display_number or document_number
            for request_id, display_number, document_number in request_rows.all()
        }
    pairs = {
        (product.seller_id, product.wb_nm_id)
        for _balance, _location, product, _seller in rows
        if product.seller_id is not None and product.wb_nm_id is not None
    }
    pairs.update(
        (row.product.seller_id, row.product.wb_nm_id)
        for row in pending_contents
        if row.product.seller_id is not None and row.product.wb_nm_id is not None
    )
    cards: dict[tuple[uuid.UUID, int], SellerWildberriesImportedCard] = {}
    if pairs:
        seller_ids = {pair[0] for pair in pairs}
        nm_ids = {pair[1] for pair in pairs}
        card_rows = await session.scalars(
            select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.tenant_id == tenant_id,
                SellerWildberriesImportedCard.seller_id.in_(seller_ids),
                SellerWildberriesImportedCard.nm_id.in_(nm_ids),
            )
        )
        cards = {(card.seller_id, int(card.nm_id)): card for card in card_rows.all()}
    return (
        rows,
        locations,
        pallets,
        warehouse_boxes,
        inbound_boxes,
        cargo_places,
        pending_contents,
        request_numbers,
        cards,
    )


def _normalize_container(node: dict[str, Any]) -> dict[str, Any]:
    children = [
        _normalize_container(child) if child["kind"] != "product" else child
        for child in node["children"]
    ]
    sellers: set[str] = set()

    def collect(child: dict[str, Any]) -> None:
        if child["kind"] == "product":
            if child["seller_name"]:
                sellers.add(child["seller_name"])
            return
        for nested in child["children"]:
            collect(nested)

    for child in children:
        collect(child)
    return {
        **node,
        "children": children,
        "qty": sum(int(child["qty"]) for child in children),
        "seller_name": next(iter(sellers)) if len(sellers) == 1 else None,
    }


async def get_warehouse_map(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> dict[str, Any]:
    await _assert_warehouse(session, tenant_id, warehouse_id)
    address_enabled = await is_address_storage_enabled(session, tenant_id)
    (
        rows,
        locations,
        pallets,
        warehouse_boxes,
        inbound_boxes,
        cargo_places,
        pending_contents,
        request_numbers,
        cards,
    ) = await _load_map_rows(session, tenant_id, warehouse_id)

    location_by_id = {location.id: location for location in locations}
    balance_location: dict[tuple[str, uuid.UUID], uuid.UUID] = {}
    for balance, location, _product, _seller in rows:
        if balance.container_kind and balance.container_id:
            balance_location.setdefault((balance.container_kind, balance.container_id), location.id)

    nodes: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    holders: dict[tuple[str, uuid.UUID], tuple[str, uuid.UUID] | uuid.UUID | None] = {}

    def source_document_number(request_id: uuid.UUID | None) -> str | None:
        return request_numbers.get(request_id) if request_id is not None else None

    pallet_ids = {pallet.id for pallet in pallets}
    for pallet in pallets:
        key = ("pallet", pallet.id)
        nodes[key] = {
            "kind": "pallet",
            "id": str(pallet.id),
            "code": pallet.code,
            "barcode": pallet.barcode,
            "seller_name": None,
            "qty": 0,
            "source_document_number": source_document_number(
                pallet.inbound_request_id
            ),
            "children": [],
        }
        holders[key] = pallet.storage_location_id
    for box in warehouse_boxes:
        key = (box.container_kind, box.id)
        nodes[key] = {
            "kind": box.container_kind,
            "id": str(box.id),
            "code": box.internal_barcode,
            "barcode": box.internal_barcode,
            "seller_name": None,
            "qty": 0,
            "source_document_number": source_document_number(box.inbound_request_id),
            "children": [],
        }
        holders[key] = (
            ("pallet", box.pallet_id)
            if box.pallet_id in pallet_ids
            else box.storage_location_id or balance_location.get(key)
        )
    for inbound_box in inbound_boxes:
        key = ("box", inbound_box.id)
        nodes[key] = {
            "kind": "box",
            "id": str(inbound_box.id),
            "code": f"КР-{inbound_box.box_number:06d}",
            "barcode": inbound_box.internal_barcode,
            "seller_name": None,
            "qty": 0,
            "source_document_number": request_numbers.get(inbound_box.request_id),
            "children": [],
        }
        holders[key] = (
            ("pallet", inbound_box.pallet_id)
            if inbound_box.pallet_id in pallet_ids
            else inbound_box.storage_location_id or balance_location.get(key)
        )
    for place in cargo_places:
        key = ("cargo_place", place.id)
        nodes[key] = {
            "kind": "cargo_place",
            "id": str(place.id),
            "code": f"ГМ-{place.place_number:06d}",
            "barcode": place.internal_barcode,
            "seller_name": None,
            "qty": 0,
            "source_document_number": request_numbers.get(place.request_id),
            "children": [],
        }
        holders[key] = (
            ("pallet", place.pallet_id)
            if place.pallet_id in pallet_ids
            else place.storage_location_id or balance_location.get(key)
        )

    loose_by_location: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    current_container_qty: dict[tuple[str, uuid.UUID, uuid.UUID], int] = defaultdict(int)
    sellers: set[str] = set()
    categories: set[str] = set()
    for balance, location, product, seller in rows:
        card = (
            cards.get((product.seller_id, product.wb_nm_id))
            if (product.seller_id is not None and product.wb_nm_id is not None)
            else None
        )
        category, photo_url = _card_data(card)
        seller_name = seller.name if seller is not None else None
        if seller_name:
            sellers.add(seller_name)
        if category:
            categories.add(category)
        product_node = {
            "kind": "product",
            "id": str(balance.id),
            "product_id": str(product.id),
            "name": product.name,
            "seller_name": seller_name,
            "category": category,
            "barcode": product.wb_barcode,
            "seller_article": product.wb_vendor_code,
            "photo_url": photo_url,
            "qty": int(balance.quantity),
        }
        container_key = (
            (balance.container_kind, balance.container_id)
            if balance.container_kind and balance.container_id
            else None
        )
        if container_key in nodes:
            assert container_key is not None
            nodes[container_key]["children"].append(product_node)
            current_container_qty[
                (container_key[0], container_key[1], product.id)
            ] += int(balance.quantity)
        else:
            loose_by_location[location.id].append(product_node)

    for pending in pending_contents:
        container_key = (pending.kind, pending.container_id)
        if container_key not in nodes:
            continue
        pending_quantity = max(
            0,
            pending.quantity
            - current_container_qty.get(
                (pending.kind, pending.container_id, pending.product.id), 0
            ),
        )
        if pending_quantity == 0:
            continue
        product = pending.product
        card = (
            cards.get((product.seller_id, product.wb_nm_id))
            if (product.seller_id is not None and product.wb_nm_id is not None)
            else None
        )
        category, photo_url = _card_data(card)
        seller_name = pending.seller.name if pending.seller is not None else None
        if seller_name:
            sellers.add(seller_name)
        if category:
            categories.add(category)
        nodes[container_key]["children"].append(
            {
                "kind": "product",
                "id": str(pending.line_id),
                "product_id": str(product.id),
                "name": product.name,
                "seller_name": seller_name,
                "category": category,
                "barcode": product.wb_barcode,
                "seller_article": product.wb_vendor_code,
                "photo_url": photo_url,
                "qty": pending_quantity,
            }
        )

    root_by_location: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    unassigned: list[dict[str, Any]] = []
    for key, node in nodes.items():
        holder = holders.get(key)
        if isinstance(holder, tuple) and holder in nodes:
            nodes[holder]["children"].append(node)
            continue
        root_location = location_by_id.get(holder) if isinstance(holder, uuid.UUID) else None
        if (
            address_enabled
            and root_location is not None
            and root_location.code != SORTING_LOCATION_CODE
        ):
            root_by_location[root_location.id].append(node)
        else:
            unassigned.append(node)

    cells: list[dict[str, Any]] = []
    if address_enabled:
        for location in locations:
            if location.code == SORTING_LOCATION_CODE:
                unassigned.extend(loose_by_location.pop(location.id, []))
                continue
            children = [
                *root_by_location.get(location.id, []),
                *loose_by_location.pop(location.id, []),
            ]
            normalized = [
                _normalize_container(child) if child["kind"] != "product" else child
                for child in children
            ]
            cells.append(
                {
                    "id": str(location.id),
                    "code": location.code,
                    "barcode": location.barcode,
                    "qty": sum(int(child["qty"]) for child in normalized),
                    "children": normalized,
                }
            )
    else:
        for loose in loose_by_location.values():
            unassigned.extend(loose)
    normalized_unassigned = [
        _normalize_container(node) if node["kind"] != "product" else node for node in unassigned
    ]

    warehouses = list(
        (
            await session.scalars(
                select(Warehouse)
                .where(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.is_operational.is_(True),
                )
                .order_by(Warehouse.name)
            )
        ).all()
    )
    event_rows = list(
        (
            await session.execute(
                select(WarehouseMapEvent, User)
                .outerjoin(User, User.id == WarehouseMapEvent.actor_user_id)
                .where(
                    WarehouseMapEvent.tenant_id == tenant_id,
                    WarehouseMapEvent.warehouse_id == warehouse_id,
                )
                .order_by(WarehouseMapEvent.created_at.desc(), WarehouseMapEvent.id.desc())
                .limit(100)
            )
        ).all()
    )
    journal = [
        {
            "id": str(event.id),
            "at": event.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "actor_name": actor.email if actor is not None else "Система",
            "subject": event.subject,
            "qty": event.quantity,
            "from_label": event.from_label,
            "to_label": event.to_label,
        }
        for event, actor in event_rows
    ]
    return {
        "warehouses": [{"id": str(row.id), "name": row.name} for row in warehouses],
        "sellers": sorted(sellers),
        "categories": sorted(categories),
        "cells": cells,
        "unassigned": normalized_unassigned,
        "journal": journal,
    }


async def _container_location_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> uuid.UUID:
    await validate_container(session, tenant_id, warehouse_id, kind, container_id)
    if kind == "pallet":
        pallet = await session.get(Pallet, container_id)
        assert pallet is not None
        if pallet.storage_location_id is not None:
            return pallet.storage_location_id
    if kind == "box":
        box = await session.get(WarehouseBox, container_id)
        if (
            box is not None
            and box.tenant_id == tenant_id
            and box.warehouse_id == warehouse_id
            and box.container_kind == kind
        ):
            if box.pallet_id is not None:
                pallet = await session.get(Pallet, box.pallet_id)
                if pallet is not None and pallet.storage_location_id is not None:
                    return pallet.storage_location_id
            if box.storage_location_id is not None:
                return box.storage_location_id
        inbound_box = await session.get(InboundIntakeBox, container_id)
        if inbound_box is not None and inbound_box.tenant_id == tenant_id:
            if inbound_box.pallet_id is not None:
                pallet = await session.get(Pallet, inbound_box.pallet_id)
                if pallet is not None and pallet.storage_location_id is not None:
                    return pallet.storage_location_id
            if inbound_box.storage_location_id is not None:
                return inbound_box.storage_location_id
    if kind == "cargo_place":
        cargo_place = await session.get(WarehouseBox, container_id)
        if (
            cargo_place is not None
            and cargo_place.tenant_id == tenant_id
            and cargo_place.warehouse_id == warehouse_id
            and cargo_place.container_kind == kind
        ):
            if cargo_place.pallet_id is not None:
                pallet = await session.get(Pallet, cargo_place.pallet_id)
                if pallet is not None and pallet.storage_location_id is not None:
                    return pallet.storage_location_id
            if cargo_place.storage_location_id is not None:
                return cargo_place.storage_location_id
        inbound_cargo = await session.get(InboundIntakeCargoPlace, container_id)
        if inbound_cargo is not None and inbound_cargo.tenant_id == tenant_id:
            if inbound_cargo.pallet_id is not None:
                pallet = await session.get(Pallet, inbound_cargo.pallet_id)
                if pallet is not None and pallet.storage_location_id is not None:
                    return pallet.storage_location_id
            if inbound_cargo.storage_location_id is not None:
                return inbound_cargo.storage_location_id
    balance_location = await session.scalar(
        select(InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.container_kind == kind,
            InventoryBalance.container_id == container_id,
            InventoryBalance.quantity > 0,
        )
        .limit(1)
    )
    if balance_location is not None:
        location = await session.get(StorageLocation, balance_location)
        if location is not None and location.warehouse_id == warehouse_id:
            return balance_location
    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
    return sorting.id


async def resolve_container_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> uuid.UUID:
    """Return the persisted root location for a pick-source container."""
    return await _container_location_id(
        session,
        tenant_id,
        warehouse_id,
        kind,
        container_id,
    )


async def _destination(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    to_kind: DestinationKind,
    to_id: uuid.UUID | None,
) -> tuple[uuid.UUID, ContainerKind | None, uuid.UUID | None, str]:
    if to_kind == "cell":
        if not await is_address_storage_enabled(session, tenant_id):
            raise WarehouseMapError("address_storage_disabled")
        if to_id is None:
            raise WarehouseMapError("destination_required")
        location = await session.get(StorageLocation, to_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.warehouse_id != warehouse_id
            or location.deleted_at is not None
            or location.code == SORTING_LOCATION_CODE
        ):
            raise WarehouseMapError("cell_not_found")
        return location.id, None, None, f"Ячейка {location.code}"
    if to_kind in {"unassigned", "sorting"}:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        return sorting.id, None, None, UNASSIGNED_LABEL
    if to_id is None:
        raise WarehouseMapError("destination_required")
    container_kind = cast(ContainerKind, to_kind)
    try:
        location_id = await _container_location_id(
            session, tenant_id, warehouse_id, container_kind, to_id
        )
    except ValueError as exc:
        raise WarehouseMapError("destination_not_found") from exc
    code = await _container_code(session, tenant_id, warehouse_id, container_kind, to_id)
    return location_id, container_kind, to_id, _container_title(container_kind, code)


async def _container_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> str:
    if kind == "pallet":
        row = await session.get(Pallet, container_id)
        if row is not None and row.tenant_id == tenant_id and row.warehouse_id == warehouse_id:
            return row.code
    elif kind == "box":
        warehouse_box = await session.get(WarehouseBox, container_id)
        if (
            warehouse_box is not None
            and warehouse_box.tenant_id == tenant_id
            and warehouse_box.warehouse_id == warehouse_id
            and warehouse_box.container_kind == "box"
        ):
            return warehouse_box.internal_barcode
        inbound = await session.get(InboundIntakeBox, container_id)
        if inbound is not None and inbound.tenant_id == tenant_id:
            try:
                await validate_container(
                    session, tenant_id, warehouse_id, "box", container_id
                )
            except ValueError:
                pass
            else:
                return f"КР-{inbound.box_number:06d}"
    else:
        warehouse_cargo_place = await session.get(WarehouseBox, container_id)
        if (
            warehouse_cargo_place is not None
            and warehouse_cargo_place.tenant_id == tenant_id
            and warehouse_cargo_place.warehouse_id == warehouse_id
            and warehouse_cargo_place.container_kind == "cargo_place"
        ):
            return warehouse_cargo_place.internal_barcode
        cargo = await session.get(InboundIntakeCargoPlace, container_id)
        if cargo is not None and cargo.tenant_id == tenant_id:
            try:
                await validate_container(
                    session, tenant_id, warehouse_id, "cargo_place", container_id
                )
            except ValueError:
                pass
            else:
                return f"ГМ-{cargo.place_number:06d}"
    raise WarehouseMapError("object_not_found")


async def _location_label(session: AsyncSession, location_id: uuid.UUID) -> str:
    location = await session.get(StorageLocation, location_id)
    if location is None or location.code == SORTING_LOCATION_CODE:
        return UNASSIGNED_LABEL
    return f"Ячейка {location.code}"


async def _transfer_balance(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    balance: InventoryBalance,
    quantity: int,
    destination_location_id: uuid.UUID,
    destination_container_kind: ContainerKind | None,
    destination_container_id: uuid.UUID | None,
    transfer_group_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    source_kind = cast(ContainerKind | None, balance.container_kind)
    await inventory_service.record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=balance.product_id,
        storage_location_id=balance.storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_WAREHOUSE_MAP,
        transfer_group_id=transfer_group_id,
        container_kind=source_kind,
        container_id=balance.container_id,
        actor_user_id=actor_user_id,
    )
    await inventory_service.record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=balance.product_id,
        storage_location_id=destination_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_WAREHOUSE_MAP,
        transfer_group_id=transfer_group_id,
        container_kind=destination_container_kind,
        container_id=destination_container_id,
        actor_user_id=actor_user_id,
    )


async def _container_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> list[InventoryBalance]:
    refs: list[tuple[str, uuid.UUID]] = [(kind, container_id)]
    if kind == "pallet":
        warehouse_boxes, inbound_boxes, cargo_places = await _load_boxes(
            session, tenant_id, warehouse_id
        )
        refs.extend(
            (row.container_kind, row.id)
            for row in warehouse_boxes
            if row.pallet_id == container_id
        )
        refs.extend(("box", row.id) for row in inbound_boxes if row.pallet_id == container_id)
        refs.extend(
            ("cargo_place", row.id) for row in cargo_places if row.pallet_id == container_id
        )
    predicates = [
        (InventoryBalance.container_kind == ref_kind) & (InventoryBalance.container_id == ref_id)
        for ref_kind, ref_id in refs
    ]
    rows = list(
        (
            await session.scalars(
                select(InventoryBalance)
                .join(StorageLocation)
                .where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.quantity > 0,
                    StorageLocation.warehouse_id == warehouse_id,
                    or_(*predicates),
                )
                .with_for_update()
            )
        ).all()
    )
    return rows


async def _place_container(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
    to_kind: DestinationKind,
    to_id: uuid.UUID | None,
    destination_location_id: uuid.UUID,
) -> None:
    if kind == "pallet":
        if to_kind not in {"cell", "unassigned", "sorting"}:
            raise WarehouseMapError("invalid_container_destination")
        pallet = await session.get(Pallet, container_id)
        if (
            pallet is None
            or pallet.tenant_id != tenant_id
            or pallet.warehouse_id != warehouse_id
            or pallet.disbanded_at is not None
        ):
            raise WarehouseMapError("object_not_found")
        pallet.storage_location_id = destination_location_id if to_kind == "cell" else None
        return
    if to_kind not in {"cell", "unassigned", "sorting", "pallet"}:
        raise WarehouseMapError("invalid_container_destination")
    pallet_id = to_id if to_kind == "pallet" else None
    if pallet_id == container_id:
        raise WarehouseMapError("container_cycle")
    if kind == "box":
        warehouse_box = await session.get(WarehouseBox, container_id)
        if (
            warehouse_box is not None
            and warehouse_box.tenant_id == tenant_id
            and warehouse_box.warehouse_id == warehouse_id
            and warehouse_box.container_kind == "box"
        ):
            warehouse_box.pallet_id = pallet_id
            warehouse_box.storage_location_id = (
                destination_location_id if to_kind == "cell" else None
            )
            return
        inbound = await session.get(InboundIntakeBox, container_id)
        if inbound is None or inbound.tenant_id != tenant_id:
            raise WarehouseMapError("object_not_found")
        try:
            await validate_container(session, tenant_id, warehouse_id, "box", container_id)
        except ValueError as exc:
            raise WarehouseMapError("object_not_found") from exc
        inbound.pallet_id = pallet_id
        inbound.storage_location_id = destination_location_id
        return
    warehouse_cargo_place = await session.get(WarehouseBox, container_id)
    if (
        warehouse_cargo_place is not None
        and warehouse_cargo_place.tenant_id == tenant_id
        and warehouse_cargo_place.warehouse_id == warehouse_id
        and warehouse_cargo_place.container_kind == "cargo_place"
    ):
        warehouse_cargo_place.pallet_id = pallet_id
        warehouse_cargo_place.storage_location_id = (
            destination_location_id if to_kind == "cell" else None
        )
        return
    cargo = await session.get(InboundIntakeCargoPlace, container_id)
    if cargo is None or cargo.tenant_id != tenant_id:
        raise WarehouseMapError("object_not_found")
    try:
        await validate_container(
            session, tenant_id, warehouse_id, "cargo_place", container_id
        )
    except ValueError as exc:
        raise WarehouseMapError("object_not_found") from exc
    cargo.pallet_id = pallet_id
    cargo.storage_location_id = destination_location_id


async def move_object(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    kind: ObjectKind,
    object_id: uuid.UUID,
    to_kind: DestinationKind,
    to_id: uuid.UUID | None,
    quantity: int | None,
) -> dict[str, Any]:
    await _assert_warehouse(session, tenant_id, warehouse_id)
    # Количество имеет смысл только для товара: тара всегда переезжает целиком
    # вместе с содержимым (контракт карты склада, раздел 3.1).
    if kind == "product" and (quantity is None or quantity <= 0):
        raise WarehouseMapError("quantity_must_be_positive")
    if kind == "pallet" and to_kind == "pallet" and object_id == to_id:
        raise WarehouseMapError("container_cycle")
    destination_location_id, destination_kind, destination_id, to_label = await _destination(
        session, tenant_id, warehouse_id, to_kind, to_id
    )
    transfer_group_id = uuid.uuid4()

    if kind == "product":
        balance = await session.scalar(
            select(InventoryBalance)
            .join(StorageLocation)
            .where(
                InventoryBalance.id == object_id,
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.quantity > 0,
                StorageLocation.warehouse_id == warehouse_id,
            )
            .with_for_update()
        )
        if balance is None:
            raise WarehouseMapError("object_not_found")
        # Проверка выше уже гарантировала число для товара; сообщаем это типам.
        assert quantity is not None
        if quantity > balance.quantity:
            raise WarehouseMapError("insufficient_stock")
        product = await session.get(Product, balance.product_id)
        assert product is not None
        from_label = await _location_label(session, balance.storage_location_id)
        if balance.container_kind and balance.container_id:
            code = await _container_code(
                session,
                tenant_id,
                warehouse_id,
                cast(ContainerKind, balance.container_kind),
                balance.container_id,
            )
            from_label = _container_title(balance.container_kind, code)
        await _transfer_balance(
            session,
            tenant_id=tenant_id,
            balance=balance,
            quantity=quantity,
            destination_location_id=destination_location_id,
            destination_container_kind=destination_kind,
            destination_container_id=destination_id,
            transfer_group_id=transfer_group_id,
            actor_user_id=actor_user_id,
        )
        subject = product.name
        moved_quantity: int | None = quantity
    else:
        container_kind: ContainerKind = kind
        try:
            await validate_container(session, tenant_id, warehouse_id, container_kind, object_id)
        except ValueError as exc:
            raise WarehouseMapError("object_not_found") from exc
        if to_kind in {"box", "cargo_place"}:
            raise WarehouseMapError("invalid_container_destination")
        source_location_id = await _container_location_id(
            session, tenant_id, warehouse_id, container_kind, object_id
        )
        from_label = await _location_label(session, source_location_id)
        balances = await _container_balances(
            session, tenant_id, warehouse_id, container_kind, object_id
        )
        if (
            balances
            and source_location_id == destination_location_id
            and to_kind in {"cell", "sorting", "unassigned"}
        ):
            raise WarehouseMapError("nothing_to_move")
        moved_total = sum(int(row.quantity) for row in balances)
        pending_moved: int | None = None
        try:
            pending_moved = (
                await inbound_container_putaway_service.putaway_pending_container(
                    session,
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    actor_user_id=actor_user_id,
                    kind=container_kind,
                    container_id=object_id,
                    destination_location_id=destination_location_id,
                    destination_is_cell=to_kind == "cell",
                )
            )
        except inbound_container_putaway_service.InboundContainerPutawayError as exc:
            # A container with current balance can be moved again after its
            # original intake has already been posted. The canonical intake
            # bridge is required only while that intake still has pending qty.
            if not balances or exc.code != "nothing_to_move":
                raise WarehouseMapError(exc.code) from exc
        if pending_moved is not None:
            moved_total = pending_moved
        else:
            for balance in balances:
                await _transfer_balance(
                    session,
                    tenant_id=tenant_id,
                    balance=balance,
                    quantity=int(balance.quantity),
                    destination_location_id=destination_location_id,
                    destination_container_kind=cast(ContainerKind, balance.container_kind),
                    destination_container_id=balance.container_id,
                    transfer_group_id=transfer_group_id,
                    actor_user_id=actor_user_id,
                )
        await _place_container(
            session,
            tenant_id,
            warehouse_id,
            container_kind,
            object_id,
            to_kind,
            to_id,
            destination_location_id,
        )
        code = await _container_code(session, tenant_id, warehouse_id, container_kind, object_id)
        subject = _container_title(container_kind, code)
        moved_quantity = moved_total or None

    event = WarehouseMapEvent(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        subject=subject,
        quantity=moved_quantity,
        from_label=from_label,
        to_label=to_label,
    )
    session.add(event)
    await session.commit()
    return {"id": str(event.id), "moved_qty": moved_quantity}


async def create_sorting_object(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    kind: Literal["pallet", "box", "cargo_place"],
    inbound_request_id: uuid.UUID | None = None,
) -> dict[str, str | None]:
    await _assert_warehouse(session, tenant_id, warehouse_id)
    if inbound_request_id is not None:
        request = await session.get(InboundIntakeRequest, inbound_request_id)
        if (
            request is None
            or request.tenant_id != tenant_id
            or request.warehouse_id != warehouse_id
        ):
            raise WarehouseMapError("inbound_request_not_found")
    if kind == "pallet":
        try:
            pallet = await pallet_service.create_pallet(
                session,
                tenant_id,
                warehouse_id=warehouse_id,
                inbound_request_id=inbound_request_id,
            )
        except pallet_service.PalletServiceError as exc:
            raise WarehouseMapError(exc.code) from exc
        return {
            "id": str(pallet.id),
            "kind": kind,
            "code": pallet.code,
            "barcode": pallet.barcode,
            "holder": None,
        }

    try:
        container = await warehouse_box_service.create_warehouse_box(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            inbound_request_id=inbound_request_id,
            container_kind=kind,
        )
        await session.commit()
        await session.refresh(container)
    except warehouse_box_service.WarehouseBoxError as exc:
        await session.rollback()
        raise WarehouseMapError(exc.code) from exc
    return {
        "id": str(container.id),
        "kind": kind,
        "code": container.internal_barcode,
        "barcode": container.internal_barcode,
        "holder": None,
    }


async def disband_pallet(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    pallet_id: uuid.UUID,
) -> dict[str, Any]:
    await _assert_warehouse(session, tenant_id, warehouse_id)
    pallet = await session.get(Pallet, pallet_id)
    if (
        pallet is None
        or pallet.tenant_id != tenant_id
        or pallet.warehouse_id != warehouse_id
        or pallet.disbanded_at is not None
    ):
        raise WarehouseMapError("pallet_not_found")
    from_label = (
        await _location_label(session, pallet.storage_location_id)
        if pallet.storage_location_id is not None
        else UNASSIGNED_LABEL
    )
    code = pallet.code
    try:
        await pallet_service.disband_pallet(session, tenant_id, pallet_id)
    except pallet_service.PalletServiceError as exc:
        raise WarehouseMapError(exc.code) from exc
    event = WarehouseMapEvent(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        subject=_container_title("pallet", code),
        quantity=None,
        from_label=from_label,
        to_label=UNASSIGNED_LABEL,
    )
    session.add(event)
    await session.commit()
    return {"id": str(pallet_id), "disbanded": True}


def _sorting_tree_rows(
    nodes: list[dict[str, Any]],
    *,
    holder: str | None,
    objects: list[dict[str, Any]],
    lines: list[dict[str, Any]],
) -> None:
    for node in nodes:
        if node["kind"] == "product":
            lines.append(
                {
                    "id": node["id"],
                    "productId": node["product_id"],
                    "qty": node["qty"],
                    "holder": holder,
                }
            )
            continue
        object_holder = f"obj:{node['id']}"
        objects.append(
            {
                "id": node["id"],
                "kind": node["kind"],
                "code": node["code"],
                "barcode": node["barcode"] or "",
                "holder": holder,
            }
        )
        _sorting_tree_rows(node["children"], holder=object_holder, objects=objects, lines=lines)


async def _filter_sorting_map_by_inbound_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    inbound_request_id: uuid.UUID,
    data: dict[str, Any],
) -> dict[str, Any]:
    request = await session.get(InboundIntakeRequest, inbound_request_id)
    if (
        request is None
        or request.tenant_id != tenant_id
        or request.warehouse_id != warehouse_id
    ):
        raise WarehouseMapError("inbound_request_not_found")

    accepted_rows = list(
        (
            await session.execute(
                select(InboundIntakeLine.product_id, InboundIntakeLine.actual_qty).where(
                    InboundIntakeLine.request_id == inbound_request_id,
                )
            )
        ).all()
    )
    remaining_by_product = {
        str(product_id): max(0, int(actual_qty or 0))
        for product_id, actual_qty in accepted_rows
    }

    box_rows = list(
        (
            await session.execute(
                select(InboundIntakeBox.id, InboundIntakeBox.pallet_id).where(
                    InboundIntakeBox.request_id == inbound_request_id,
                    InboundIntakeBox.tenant_id == tenant_id,
                )
            )
        ).all()
    )
    cargo_place_rows = list(
        (
            await session.execute(
                select(
                    InboundIntakeCargoPlace.id,
                    InboundIntakeCargoPlace.pallet_id,
                ).where(
                    InboundIntakeCargoPlace.request_id == inbound_request_id,
                    InboundIntakeCargoPlace.tenant_id == tenant_id,
                )
            )
        ).all()
    )
    allowed_containers = {
        *(('box', str(container_id)) for container_id, _pallet_id in box_rows),
        *(
            ('cargo_place', str(container_id))
            for container_id, _pallet_id in cargo_place_rows
        ),
        *(
            ('pallet', str(pallet_id))
            for _container_id, pallet_id in [*box_rows, *cargo_place_rows]
            if pallet_id is not None
        ),
    }
    generic_pallet_ids = list(
        (
            await session.scalars(
                select(Pallet.id).where(
                    Pallet.tenant_id == tenant_id,
                    Pallet.warehouse_id == warehouse_id,
                    Pallet.inbound_request_id == inbound_request_id,
                    Pallet.disbanded_at.is_(None),
                )
            )
        ).all()
    )
    generic_box_rows = list(
        (
            await session.execute(
                select(WarehouseBox.id, WarehouseBox.container_kind).where(
                    WarehouseBox.tenant_id == tenant_id,
                    WarehouseBox.warehouse_id == warehouse_id,
                    WarehouseBox.inbound_request_id == inbound_request_id,
                )
            )
        ).all()
    )
    allowed_containers.update(
        ("pallet", str(pallet_id)) for pallet_id in generic_pallet_ids
    )
    allowed_containers.update(
        (container_kind, str(container_id))
        for container_id, container_kind in generic_box_rows
    )

    def filter_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for node in nodes:
            if node["kind"] == "product":
                product_id = node["product_id"]
                remaining = remaining_by_product.get(product_id, 0)
                quantity = min(int(node["qty"]), remaining)
                if quantity > 0:
                    filtered.append({**node, "qty": quantity})
                    remaining_by_product[product_id] = remaining - quantity
                continue

            children = filter_nodes(node["children"])
            if (node["kind"], node["id"]) not in allowed_containers:
                # Тара другого документа не должна становиться владельцем товара
                # выбранной приёмки: относящиеся к документу строки поднимаем выше.
                filtered.extend(children)
                continue
            filtered.append(
                _normalize_container(
                    {
                        **node,
                        "children": children,
                    }
                )
            )
        return filtered

    # Сначала расходуем документное количество в зоне сортировки. Это сохраняет
    # только что принятую приёмку в «осталось поставить», даже если тот же SKU уже
    # лежит в ячейках от прежних документов.
    filtered_unassigned = filter_nodes(data["unassigned"])
    filtered_cells = [
        {
            **cell,
            "children": filter_nodes(cell["children"]),
        }
        for cell in data["cells"]
    ]
    return {
        **data,
        "unassigned": filtered_unassigned,
        "cells": filtered_cells,
    }


async def get_sorting_objects(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    inbound_request_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    data = await get_warehouse_map(session, tenant_id, warehouse_id)
    if inbound_request_id is not None:
        data = await _filter_sorting_map_by_inbound_request(
            session,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            inbound_request_id=inbound_request_id,
            data=data,
        )
    objects: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    _sorting_tree_rows(data["unassigned"], holder=None, objects=objects, lines=lines)
    cells: list[dict[str, Any]] = []
    for row in data["cells"]:
        cell_objects: list[dict[str, Any]] = []
        cell_lines: list[dict[str, Any]] = []
        _sorting_tree_rows(
            row["children"],
            holder=f"cell:{row['id']}",
            objects=cell_objects,
            lines=cell_lines,
        )
        objects.extend(cell_objects)
        lines.extend(cell_lines)
        cells.append(
            {
                "id": row["id"],
                "code": row["code"],
                "barcode": row["barcode"],
                "objects": cell_objects,
                "lines": cell_lines,
            }
        )
    product_ids = {uuid.UUID(row["productId"]) for row in lines}
    products = (
        list(
            (
                await session.execute(
                    select(Product, Seller)
                    .outerjoin(Seller, Seller.id == Product.seller_id)
                    .where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
                )
            ).all()
        )
        if product_ids
        else []
    )
    location_rows = (
        list(
            (
                await session.execute(
                    select(
                        InventoryBalance.product_id,
                        StorageLocation,
                        func.sum(InventoryBalance.quantity),
                    )
                    .join(StorageLocation)
                    .where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id.in_(product_ids),
                        InventoryBalance.quantity > 0,
                        StorageLocation.warehouse_id == warehouse_id,
                        StorageLocation.code != SORTING_LOCATION_CODE,
                        StorageLocation.deleted_at.is_(None),
                    )
                    .group_by(InventoryBalance.product_id, StorageLocation.id)
                )
            ).all()
        )
        if product_ids
        else []
    )
    already: dict[uuid.UUID, dict[uuid.UUID, tuple[str, int]]] = defaultdict(dict)
    for product_id, location, quantity in location_rows:
        already[product_id][location.id] = (location.code, int(quantity or 0))

    product_nodes: dict[str, dict[str, Any]] = {}

    def collect_product_nodes(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if node["kind"] == "product":
                product_nodes[node["product_id"]] = node
            else:
                collect_product_nodes(node["children"])

    for cell in data["cells"]:
        collect_product_nodes(cell["children"])
    collect_product_nodes(data["unassigned"])
    product_data = [
        {
            "id": str(product.id),
            "name": product.name,
            "sku": product.sku_code,
            "seller": seller.name if seller is not None else "",
            "barcode": product.wb_barcode or "",
            "photo": product_nodes.get(str(product.id), {}).get("photo_url") or "",
            "size": product.wb_size,
            "alreadyAt": [
                {"cellId": str(cell_id), "code": code, "qty": qty}
                for cell_id, (code, qty) in already.get(product.id, {}).items()
            ],
        }
        for product, seller in products
    ]
    return {
        "objects": objects,
        "lines": lines,
        "products": product_data,
        "cells": cells,
    }


async def _sorting_destination_kind(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    container_id: uuid.UUID,
) -> ContainerKind:
    found: list[ContainerKind] = []
    candidates: tuple[ContainerKind, ...] = ("pallet", "box", "cargo_place")
    for candidate in candidates:
        try:
            await validate_container(
                session,
                tenant_id,
                warehouse_id,
                candidate,
                container_id,
            )
        except ValueError:
            continue
        found.append(candidate)
    if len(found) != 1:
        raise WarehouseMapError("destination_not_found")
    return found[0]


async def place_sorting_object(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    kind: ObjectKind,
    object_id: uuid.UUID,
    cell_id: uuid.UUID | None,
    to_id: uuid.UUID | None,
    quantity: int | None,
) -> dict[str, Any]:
    if cell_id is not None and to_id is not None:
        raise WarehouseMapError("destination_conflict")
    if cell_id is not None:
        destination_kind: DestinationKind = "cell"
        destination_id = cell_id
    elif to_id is not None:
        destination_kind = await _sorting_destination_kind(
            session,
            tenant_id,
            warehouse_id,
            to_id,
        )
        destination_id = to_id
    else:
        destination_kind = "unassigned"
        destination_id = None
    return await move_object(
        session,
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        kind=kind,
        object_id=object_id,
        to_kind=destination_kind,
        to_id=destination_id,
        quantity=quantity,
    )
