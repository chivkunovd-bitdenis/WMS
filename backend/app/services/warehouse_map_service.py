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
from app.services.box_barcode_service import inbound_box_display_code
from app.services.catalog_service import load_ozon_primary_image_urls
from app.services.inventory_container_service import ContainerKind, validate_container
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    SORTING_LOCATION_LABEL,
    UNASSIGNED_LABEL,
    get_or_create_sorting_location,
)
from app.services.tenant_settings_service import is_address_storage_enabled
from app.services.wb_card_enrichment import first_photo_url_from_card, subject_name_from_card

ObjectKind = Literal["product", "pallet", "box", "cargo_place"]
DestinationKind = Literal["cell", "unassigned", "sorting", "pallet", "box", "cargo_place"]
MOVEMENT_TYPE_WAREHOUSE_MAP = "warehouse_map_move"


def _inbound_box_display_code(box: InboundIntakeBox) -> str:
    """WMS-564/565: «КР-00000N» только у «Империи ФФ» для системного кода;
    остальным — сам код короба (WMS-551)."""
    return inbound_box_display_code(box.tenant_id, box.box_number, box.internal_barcode)


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
            code = _inbound_box_display_code(inbound_box)
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
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
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
    # WMS-490 D1: с ``product_id`` в дерево попадают только строки остатка и
    # незавершённых приёмок этого товара — контейнеры и локации по-прежнему
    # читаются целиком (их список не тяжелее без фильтра), а лишние продуктовые
    # строки убираются пустыми контейнерами в ``get_warehouse_map``.
    balance_filters = [
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.quantity > 0,
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.warehouse_id == warehouse_id,
        Product.tenant_id == tenant_id,
    ]
    if product_id is not None:
        balance_filters.append(InventoryBalance.product_id == product_id)
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
                    .where(*balance_filters)
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
    box_line_filters = [
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
    ]
    if product_id is not None:
        box_line_filters.append(InboundIntakeBoxLine.product_id == product_id)
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
        .where(*box_line_filters)
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
    cargo_line_filters = [
        InboundIntakeCargoPlace.tenant_id == tenant_id,
        InboundIntakeRequest.tenant_id == tenant_id,
        or_(
            StorageLocation.warehouse_id == warehouse_id,
            and_(
                InboundIntakeCargoPlace.storage_location_id.is_(None),
                InboundIntakeRequest.warehouse_id == warehouse_id,
            ),
        ),
        InboundIntakeCargoPlaceLine.quantity > InboundIntakeCargoPlaceLine.posted_qty,
        ~exists(
            select(InventoryBalance.id).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.container_kind == "cargo_place",
                InventoryBalance.container_id == InboundIntakeCargoPlace.id,
                InventoryBalance.product_id == InboundIntakeCargoPlaceLine.product_id,
            )
        ),
    ]
    if product_id is not None:
        cargo_line_filters.append(InboundIntakeCargoPlaceLine.product_id == product_id)
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
        .where(*cargo_line_filters)
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


def _drop_empty_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove containers left with no row of the filtered product (WMS-490 D1).

    ``_load_map_rows`` with ``product_id`` never attaches any other товар as a
    child, so a container's normalized ``qty`` is already 0 exactly when this
    drops it — the kept siblings' quantities do not change.
    """
    kept: list[dict[str, Any]] = []
    for node in nodes:
        if node["kind"] == "product":
            kept.append(node)
            continue
        children = _drop_empty_nodes(node["children"])
        if not children:
            continue
        kept.append({**node, "children": children})
    return kept


async def get_warehouse_map(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
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
    ) = await _load_map_rows(session, tenant_id, warehouse_id, product_id=product_id)
    # У озоновского товара снапшота карточки WB нет — фото лежит в привязке Ozon.
    ozon_photos = await load_ozon_primary_image_urls(
        session,
        tenant_id,
        {product.id for _balance, _location, product, _seller in rows}
        | {row.product.id for row in pending_contents},
    )

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
            "code": _inbound_box_display_code(inbound_box),
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
        photo_url = photo_url or ozon_photos.get(product.id)
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
        photo_url = photo_url or ozon_photos.get(product.id)
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

    # WMS-490 D1: без ``product_id`` ответ не меняется байт в байт — контейнеры
    # и ячейки без строк отфильтрованного товара убираются только при фильтре.
    if product_id is not None:
        normalized_unassigned = _drop_empty_nodes(normalized_unassigned)
        filtered_cells: list[dict[str, Any]] = []
        for cell in cells:
            cell_children = _drop_empty_nodes(cell["children"])
            if not cell_children:
                continue
            filtered_cells.append({**cell, "children": cell_children})
        cells = filtered_cells

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
            "actor_name": actor.display_name if actor is not None else "Система",
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


async def list_product_location_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> list[dict[str, str]]:
    """Operational warehouses where this product's filtered map is not empty.

    WMS-490 D1: карточка товара («Расположение») переключает склады тем же
    фильтром, что и сама карта — иначе список складов карточки разошёлся бы с
    тем, что показывает дерево. Складов у тенанта обычно немного, поэтому
    строим карту по каждому и смотрим, осталось ли в ней что-нибудь после
    фильтра — отдельного лёгкого запроса ради этого не заводим (R17: не
    считать то же самое вторым способом).
    """
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
    result: list[dict[str, str]] = []
    for warehouse in warehouses:
        data = await get_warehouse_map(session, tenant_id, warehouse.id, product_id=product_id)
        if data["cells"] or data["unassigned"]:
            result.append({"id": str(warehouse.id), "name": warehouse.name})
    return result


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
                return _inbound_box_display_code(inbound)
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
    inbound_request_id: uuid.UUID | None = None,
) -> None:
    from app.services.inbound_intake_service import InboundIntakeError
    from app.services.inbound_sorting_service import apply_received_balance_putaway

    try:
        if await apply_received_balance_putaway(
            session, tenant_id=tenant_id, balance_id=balance.id,
            destination_location_id=destination_location_id,
            destination_container_kind=destination_container_kind,
            destination_container_id=destination_container_id, quantity=quantity,
            performer_id=actor_user_id, request_id=inbound_request_id,
            transfer_group_id=transfer_group_id,
        ):
            return
    except InboundIntakeError as exc:
        raise WarehouseMapError(exc.code) from exc
    inbound_line_id = None
    if inbound_request_id is not None:
        from app.models.inventory_movement import InventoryMovement

        line = await session.scalar(select(InboundIntakeLine).where(
            InboundIntakeLine.request_id == inbound_request_id,
            InboundIntakeLine.product_id == balance.product_id,
        ))
        source = await session.get(StorageLocation, balance.storage_location_id)
        if source is not None and source.code != SORTING_LOCATION_CODE:
            proven = 0 if line is None else int(await session.scalar(select(
                func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)
            ).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.inbound_intake_line_id == line.id,
                InventoryMovement.storage_location_id == balance.storage_location_id,
            )) or 0)
            if proven < quantity:
                raise WarehouseMapError("qty_exceeds_accepted")
            assert line is not None
            inbound_line_id = line.id
    source_kind = cast(ContainerKind | None, balance.container_kind)
    await inventory_service.record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=balance.product_id,
        storage_location_id=balance.storage_location_id,
        quantity_delta=-quantity,
        _exact_source=True,
        movement_type=MOVEMENT_TYPE_WAREHOUSE_MAP,
        transfer_group_id=transfer_group_id,
        inbound_intake_line_id=inbound_line_id,
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
        inbound_intake_line_id=inbound_line_id,
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
    product_ids = (await session.scalars(select(InventoryBalance.product_id).where(
        InventoryBalance.tenant_id == tenant_id, or_(*predicates),
    ).distinct())).all()
    for product_id in sorted(product_ids, key=str):
        await inventory_service.lock_stock_product(session, tenant_id, product_id)
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


async def _lock_object_intakes(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
    kind: ObjectKind, object_id: uuid.UUID, request_id: uuid.UUID | None,
) -> None:
    """Take document locks before product/balance locks on every putaway route."""
    from app.services import inbound_intake_service as intake

    request_ids = {request_id} if request_id is not None else set()
    source_kind: str | None = kind
    source_id: uuid.UUID | None = object_id
    if kind == "product":
        balance = await session.get(InventoryBalance, object_id)
        if balance is not None and balance.tenant_id == tenant_id:
            source_kind, source_id = balance.container_kind, balance.container_id
    warehouse_boxes, boxes, cargos = await _load_boxes(session, tenant_id, warehouse_id)
    for box in boxes:
        if (source_kind == "box" and box.id == source_id) or (
            source_kind == "pallet" and box.pallet_id == source_id
        ):
            request_ids.add(box.request_id)
    for cargo in cargos:
        if (source_kind == "cargo_place" and cargo.id == source_id) or (
            source_kind == "pallet" and cargo.pallet_id == source_id
        ):
            request_ids.add(cargo.request_id)
    for generic in warehouse_boxes:
        if generic.inbound_request_id is not None and (
            generic.id == source_id or (source_kind == "pallet" and generic.pallet_id == source_id)
        ):
            request_ids.add(generic.inbound_request_id)
    if source_kind == "pallet" and source_id is not None:
        pallet = await session.get(Pallet, source_id)
        if pallet is not None and pallet.tenant_id == tenant_id and pallet.inbound_request_id:
            request_ids.add(pallet.inbound_request_id)
    for intake_id in sorted(request_ids, key=str):
        await intake.get_request(session, tenant_id, intake_id, for_update=True)


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
    commit: bool = True,
    inbound_request_id: uuid.UUID | None = None,
    transfer_group_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    from_label: str | None = None,
) -> dict[str, Any]:
    await _assert_warehouse(session, tenant_id, warehouse_id)
    await _lock_object_intakes(
        session, tenant_id, warehouse_id, kind, object_id, inbound_request_id
    )
    # Количество имеет смысл только для товара: тара всегда переезжает целиком
    # вместе с содержимым (контракт карты склада, раздел 3.1).
    if kind == "product" and (quantity is None or quantity <= 0):
        raise WarehouseMapError("quantity_must_be_positive")
    if kind == "pallet" and to_kind == "pallet" and object_id == to_id:
        raise WarehouseMapError("container_cycle")
    destination_location_id, destination_kind, destination_id, to_label = await _destination(
        session, tenant_id, warehouse_id, to_kind, to_id
    )
    transfer_group_id = transfer_group_id or uuid.uuid4()

    if kind == "product":
        initial_balance = await session.get(InventoryBalance, object_id)
        if initial_balance is not None and initial_balance.tenant_id == tenant_id:
            await inventory_service.lock_stock_product(
                session, tenant_id, initial_balance.product_id
            )
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
        source_label = await _location_label(session, balance.storage_location_id)
        if balance.container_kind and balance.container_id:
            code = await _container_code(
                session,
                tenant_id,
                warehouse_id,
                cast(ContainerKind, balance.container_kind),
                balance.container_id,
            )
            source_label = _container_title(balance.container_kind, code)
        await _transfer_balance(
            session,
            tenant_id=tenant_id,
            balance=balance,
            quantity=quantity,
            destination_location_id=destination_location_id,
            destination_container_kind=destination_kind,
            destination_container_id=destination_id,
            transfer_group_id=transfer_group_id,
            inbound_request_id=inbound_request_id,
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
        source_label = await _location_label(session, source_location_id)
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
                    transfer_group_id=transfer_group_id,
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
                    inbound_request_id=inbound_request_id,
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
        id=event_id or uuid.uuid4(),
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        subject=subject,
        quantity=moved_quantity,
        from_label=from_label or source_label,
        to_label=to_label,
    )
    session.add(event)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return {"id": str(event.id), "moved_qty": moved_quantity}


async def create_sorting_object(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    kind: Literal["pallet", "box", "cargo_place"],
    inbound_request_id: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None = None,
    commit: bool = True,
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
    if storage_location_id is not None:
        # WMS-153: тара должна попадать сразу в выбранную ячейку, а не в общий
        # склад. Проверяем, что ячейка принадлежит тому же складу и тенанту —
        # иначе оператор случайно создаст тару чужого склада.
        location = await session.get(StorageLocation, storage_location_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.warehouse_id != warehouse_id
            or location.deleted_at is not None
        ):
            raise WarehouseMapError("storage_location_not_found")
    if kind == "pallet":
        try:
            pallet = await pallet_service.create_pallet(
                session,
                tenant_id,
                warehouse_id=warehouse_id,
                storage_location_id=storage_location_id,
                inbound_request_id=inbound_request_id,
                commit=commit,
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
            storage_location_id=storage_location_id,
            inbound_request_id=inbound_request_id,
            container_kind=kind,
        )
        if commit:
            await session.commit()
            await session.refresh(container)
    except warehouse_box_service.WarehouseBoxError as exc:
        if commit:
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
                select(
                    InboundIntakeLine.product_id, InboundIntakeLine.actual_qty,
                    InboundIntakeLine.posted_qty,
                ).where(
                    InboundIntakeLine.request_id == inbound_request_id,
                )
            )
        ).all()
    )
    remaining_by_product = {
        str(product_id): max(0, int(actual_qty or 0) - int(posted_qty))
        for product_id, actual_qty, posted_qty in accepted_rows
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

    from app.models.inventory_movement import InventoryMovement

    placed_rows = (await session.execute(select(
        InventoryMovement.storage_location_id, InventoryMovement.product_id,
        func.sum(InventoryMovement.quantity_delta),
    ).join(InboundIntakeLine, InboundIntakeLine.id == InventoryMovement.inbound_intake_line_id)
        .where(InboundIntakeLine.request_id == inbound_request_id,
               InventoryMovement.tenant_id == tenant_id)
        .group_by(InventoryMovement.storage_location_id, InventoryMovement.product_id))).all()
    placed_by_cell: dict[str, dict[str, int]] = defaultdict(dict)
    for location_id, product_id, qty in placed_rows:
        placed_by_cell[str(location_id)][str(product_id)] = max(0, int(qty))

    contained: dict[str, int] = defaultdict(int)

    def count_owned(nodes: list[dict[str, Any]], *, owned: bool = False) -> None:
        for node in nodes:
            if node["kind"] == "product":
                if owned:
                    contained[node["product_id"]] += int(node["qty"])
            elif (node["kind"], node["id"]) in allowed_containers:
                count_owned(node["children"], owned=True)

    count_owned(data["unassigned"])
    loose_remaining = {
        product_id: max(0, qty - contained[product_id])
        for product_id, qty in remaining_by_product.items()
    }

    def filter_nodes(
        nodes: list[dict[str, Any]], *, in_container: bool = False, in_sorting: bool = True,
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for node in nodes:
            if node["kind"] == "product":
                product_id = node["product_id"]
                remaining = remaining_by_product.get(product_id, 0)
                if in_sorting and not in_container:
                    remaining = min(remaining, loose_remaining.get(product_id, 0))
                quantity = min(int(node["qty"]), remaining)
                if quantity > 0:
                    filtered.append({**node, "qty": quantity})
                    remaining_by_product[product_id] -= quantity
                    if in_sorting and not in_container:
                        loose_remaining[product_id] -= quantity
                continue
            if (node["kind"], node["id"]) not in allowed_containers:
                continue
            children = filter_nodes(node["children"], in_container=True, in_sorting=in_sorting)
            filtered.append(_normalize_container({**node, "children": children}))
        return filtered

    filtered_unassigned = filter_nodes(data["unassigned"])
    filtered_cells = []
    for cell in data["cells"]:
        remaining_by_product = placed_by_cell.get(cell["id"], {}).copy()
        filtered_cells.append({
            **cell, "children": filter_nodes(cell["children"], in_sorting=False),
        })

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


async def _replayed_sorting_cargo_putaway(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    inbound_request_id: uuid.UUID,
    cargo_place_id: uuid.UUID,
    destination_location_id: uuid.UUID,
    operation_id: uuid.UUID,
) -> int | None:
    """Return a prior cargo placement only when this exact sorting intent owns it."""
    from app.models.inventory_movement import InventoryMovement

    cargo = await session.get(InboundIntakeCargoPlace, cargo_place_id)
    if cargo is None or cargo.tenant_id != tenant_id or cargo.request_id != inbound_request_id:
        raise WarehouseMapError("object_not_found")
    rows = list((await session.scalars(select(InventoryMovement).where(
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.transfer_group_id == operation_id,
    ))).all())
    if not rows:
        return None
    outgoing = [row for row in rows if row.quantity_delta < 0]
    if not outgoing or any(
        row.container_kind != "cargo_place" or row.container_id != cargo_place_id
        for row in outgoing
    ):
        raise WarehouseMapError("operation_conflict")
    # The existing warehouse-map event is the one-per-container receipt for the
    # requested cell. Inventory movements can rightly point only to the defect
    # zone, so they cannot tell a defect-only replay which cell the operator chose.
    event = await session.get(WarehouseMapEvent, operation_id)
    expected_label = await _location_label(session, destination_location_id)
    if event is None or event.to_label != expected_label:
        raise WarehouseMapError("operation_conflict")
    return sum(-int(row.quantity_delta) for row in outgoing)


async def _pending_sorting_cargo_quantity(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    inbound_request_id: uuid.UUID,
    cargo_place_id: uuid.UUID,
) -> int:
    cargo = await session.get(InboundIntakeCargoPlace, cargo_place_id)
    if cargo is None or cargo.tenant_id != tenant_id or cargo.request_id != inbound_request_id:
        raise WarehouseMapError("object_not_found")
    lines = list((await session.scalars(
        select(InboundIntakeCargoPlaceLine).where(
            InboundIntakeCargoPlaceLine.cargo_place_id == cargo_place_id,
            InboundIntakeCargoPlaceLine.tenant_id == tenant_id,
        ).with_for_update()
    )).all())
    return sum(int(line.quantity) - int(line.posted_qty) for line in lines)


# ── WMS-650: раскладка внутри документа приёмки ─────────────────────────────
#
# Каждое действие экрана раскладки пишет квитанции в уже существующие записи
# (решение Д2): движения остатка с transfer_group_id = operation_id экрана и
# строку журнала карты склада с id = operation_id. По ним сервер узнаёт повтор
# того же запроса (R17) и по ним же «назад» восстанавливает состояние до
# действия (sorting_undo_service). Новых таблиц и статусов нет.


async def container_pallet_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> uuid.UUID | None:
    """Палета, на которой стоит короб или грузоместо (у палеты — никогда)."""
    if kind == "pallet":
        return None
    generic = await session.get(WarehouseBox, container_id)
    if (
        generic is not None
        and generic.tenant_id == tenant_id
        and generic.warehouse_id == warehouse_id
        and generic.container_kind == kind
    ):
        return generic.pallet_id
    if kind == "box":
        inbound = await session.get(InboundIntakeBox, container_id)
        if inbound is not None and inbound.tenant_id == tenant_id:
            return inbound.pallet_id
        return None
    cargo = await session.get(InboundIntakeCargoPlace, container_id)
    if cargo is not None and cargo.tenant_id == tenant_id:
        return cargo.pallet_id
    return None


async def sorting_holder_label(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> str:
    """Где стоит тара: палета («Палета П-…») или место («Ячейка …», «Без ячеек»).

    Подпись «откуда» в журнале — квитанция действия: по ней «назад» вернёт тару
    на ту же палету или в то же место (WMS-650 Д2). Для тары не на палете она
    совпадает с прежней подписью места.
    """
    pallet_id = await container_pallet_id(session, tenant_id, warehouse_id, kind, container_id)
    if pallet_id is not None:
        pallet = await session.get(Pallet, pallet_id)
        if pallet is not None and pallet.disbanded_at is None:
            return _container_title("pallet", pallet.code)
    location_id = await _container_location_id(
        session, tenant_id, warehouse_id, kind, container_id
    )
    return await _location_label(session, location_id)


async def sorting_document_containers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    request_id: uuid.UUID,
) -> set[tuple[str, uuid.UUID]]:
    """Тара документа приёмки — та же, что экран показывает в его составе.

    Ручки экрана раскладки двигают только её (R18): чужой короб, даже того же
    селлера, ручкой документа A не сдвинуть.
    """
    owned: set[tuple[str, uuid.UUID]] = set()
    pallets: set[uuid.UUID] = set()
    for container_id, pallet_id in (
        await session.execute(
            select(InboundIntakeBox.id, InboundIntakeBox.pallet_id).where(
                InboundIntakeBox.tenant_id == tenant_id,
                InboundIntakeBox.request_id == request_id,
            )
        )
    ).all():
        owned.add(("box", container_id))
        if pallet_id is not None:
            pallets.add(pallet_id)
    for container_id, pallet_id in (
        await session.execute(
            select(InboundIntakeCargoPlace.id, InboundIntakeCargoPlace.pallet_id).where(
                InboundIntakeCargoPlace.tenant_id == tenant_id,
                InboundIntakeCargoPlace.request_id == request_id,
            )
        )
    ).all():
        owned.add(("cargo_place", container_id))
        if pallet_id is not None:
            pallets.add(pallet_id)
    for container_id, container_kind, pallet_id in (
        await session.execute(
            select(WarehouseBox.id, WarehouseBox.container_kind, WarehouseBox.pallet_id).where(
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.inbound_request_id == request_id,
            )
        )
    ).all():
        owned.add((container_kind, container_id))
        if pallet_id is not None:
            pallets.add(pallet_id)
    pallets.update(
        (
            await session.scalars(
                select(Pallet.id).where(
                    Pallet.tenant_id == tenant_id,
                    Pallet.warehouse_id == warehouse_id,
                    Pallet.inbound_request_id == request_id,
                )
            )
        ).all()
    )
    owned.update(("pallet", pallet_id) for pallet_id in pallets)
    return owned


async def _expected_destination_labels(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    destination_kind: DestinationKind,
    destination_id: uuid.UUID | None,
) -> set[str] | None:
    """Подписи «куда», которыми могло записаться это действие; None — не узнать."""
    if destination_kind in {"unassigned", "sorting"}:
        return {UNASSIGNED_LABEL, SORTING_LOCATION_LABEL}
    if destination_id is None:
        return None
    if destination_kind == "cell":
        location = await session.get(StorageLocation, destination_id)
        if location is None or location.tenant_id != tenant_id:
            return None
        # Россыпь, разложенная по документу, пишет в журнал голый код ячейки.
        return {f"Ячейка {location.code}", location.code}
    try:
        code = await _container_code(
            session, tenant_id, warehouse_id, cast(ContainerKind, destination_kind), destination_id
        )
    except WarehouseMapError:
        return None
    return {_container_title(destination_kind, code)}


async def _replayed_sorting_action(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    operation_id: uuid.UUID,
    kind: ObjectKind,
    object_id: uuid.UUID,
    destination_kind: DestinationKind,
    destination_id: uuid.UUID | None,
) -> dict[str, Any] | None:
    """Повтор того же действия (потерян ответ, очередь после обновления): ответ без изменений.

    Повтор — это тот же объект в то же место. Тот же operation_id для другого
    объекта или другого места — ошибка клиента: ``operation_conflict``.
    """
    event = await session.get(WarehouseMapEvent, operation_id)
    if event is None:
        return None
    if event.tenant_id != tenant_id or event.warehouse_id != warehouse_id:
        raise WarehouseMapError("operation_conflict")
    if event.subject != await _sorting_subject(session, tenant_id, warehouse_id, kind, object_id):
        raise WarehouseMapError("operation_conflict")
    expected = await _expected_destination_labels(
        session, tenant_id, warehouse_id, destination_kind, destination_id
    )
    if expected is not None and event.to_label not in expected:
        raise WarehouseMapError("operation_conflict")
    return {"id": str(operation_id), "moved_qty": event.quantity}


async def _sorting_subject(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ObjectKind,
    object_id: uuid.UUID,
) -> str | None:
    """Как журнал называет объект действия: товар — по названию, тара — по номеру."""
    if kind == "product":
        balance = await session.get(InventoryBalance, object_id)
        if balance is None or balance.tenant_id != tenant_id:
            return None
        product = await session.get(Product, balance.product_id)
        return product.name if product is not None else None
    try:
        code = await _container_code(session, tenant_id, warehouse_id, kind, object_id)
    except WarehouseMapError:
        return None
    return _container_title(kind, code)


async def linked_location_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    inbound_line_id: uuid.UUID,
    location_id: uuid.UUID,
    container_kind: str | None,
    container_id: uuid.UUID | None,
) -> int:
    """Сколько штук строки документа лежит именно здесь (место + тара) по его движениям.

    Считается по месту и таре вместе: россыпь другого документа на той же
    ячейке и чужой короб на палете документа сюда не попадают (R18).
    """
    from app.models.inventory_movement import InventoryMovement

    return int(
        await session.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.inbound_intake_line_id == inbound_line_id,
                InventoryMovement.storage_location_id == location_id,
                InventoryMovement.container_kind.is_(None)
                if container_kind is None
                else InventoryMovement.container_kind == container_kind,
                InventoryMovement.container_id.is_(None)
                if container_id is None
                else InventoryMovement.container_id == container_id,
            )
        )
        or 0
    )


async def release_distribution(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    box_id: uuid.UUID | None,
    prefer_location_id: uuid.UUID | None = None,
    prefer_id: uuid.UUID | None = None,
) -> int:
    """Уменьшить строки распределения документа на снятое; вернуть, сколько не нашлось.

    Строка распределения помнит, откуда штука пришла (короб приёмки или «без
    короба»), и место, куда её положили впервые. Снимаем по порядку:
    квитанция самого действия (``prefer_id``), строки этого короба, строки без
    короба (товар, доложенный в короб сканом), и только затем строки других
    коробов. Место после переноса может отличаться от текущего, поэтому оно
    задаёт порядок, а не отбор.
    """
    from app.models.inbound_intake import InboundIntakeDistributionLine

    rows = list(
        (
            await session.scalars(
                select(InboundIntakeDistributionLine)
                .where(
                    InboundIntakeDistributionLine.request_id == request_id,
                    InboundIntakeDistributionLine.product_id == product_id,
                )
                .order_by(
                    InboundIntakeDistributionLine.created_at.desc(),
                    InboundIntakeDistributionLine.id.desc(),
                )
            )
        ).all()
    )
    rows.sort(
        key=lambda row: (
            row.id != prefer_id,
            0 if row.box_id == box_id else 1 if row.box_id is None else 2,
            row.storage_location_id != prefer_location_id,
        )
    )
    left = quantity
    for row in rows:
        if left <= 0:
            break
        taken = min(left, int(row.quantity))
        left -= taken
        if taken == row.quantity:
            await session.delete(row)
        else:
            row.quantity -= taken
    return left


async def rebalance_distribution(
    session: AsyncSession, request: InboundIntakeRequest
) -> None:
    """Строки распределения по наборам — ровно как «разложено» (WMS-650).

    «Распределить по ячейкам» делит строки на наборы: каждый короб приёмки и
    россыпь. Строки набора считаются проведёнными, пока их не больше
    «разложено» этого набора: короба — его собственное, россыпи — документа
    минус короба. Действия раскладки двигают штуки между наборами: вынутое из
    короба и разложенное россыпью, доложенное сканом в короб и снятое вместе с
    ним. После каждого такого действия и после «назад» излишек одного набора
    переносится в недостающий набор с тем же местом строки, лишнее
    снимается. Тогда ни одна строка не будет проведена второй раз, а проверка
    завершения распределения не откажет на перекосе наборов.
    """
    from app.models.inbound_intake import InboundIntakeDistributionLine

    await session.flush()
    for line in request.lines:
        box_targets: dict[uuid.UUID | None, int] = {
            box.id: int(content.posted_qty)
            for box in request.boxes
            for content in box.lines
            if content.product_id == line.product_id
        }
        targets: dict[uuid.UUID | None, int] = {
            **box_targets,
            None: max(0, int(line.posted_qty) - sum(box_targets.values())),
        }
        rows = list(
            (
                await session.scalars(
                    select(InboundIntakeDistributionLine)
                    .where(
                        InboundIntakeDistributionLine.request_id == request.id,
                        InboundIntakeDistributionLine.product_id == line.product_id,
                    )
                    .order_by(
                        InboundIntakeDistributionLine.created_at.desc(),
                        InboundIntakeDistributionLine.id.desc(),
                    )
                )
            ).all()
        )
        totals: dict[uuid.UUID | None, int] = defaultdict(int)
        for row in rows:
            totals[row.box_id] += int(row.quantity)
        if all(totals.get(pool, 0) == target for pool, target in targets.items()) and all(
            pool in targets for pool in totals
        ):
            continue
        # Излишек наборов: снимаем с самых новых строк, запоминая их место.
        surplus: list[tuple[uuid.UUID, int]] = []
        deleted: set[int] = set()
        for row in rows:
            excess = totals[row.box_id] - targets.get(row.box_id, 0)
            if excess <= 0:
                continue
            taken = min(excess, int(row.quantity))
            totals[row.box_id] -= taken
            surplus.append((row.storage_location_id, taken))
            if taken == row.quantity:
                deleted.add(id(row))
                await session.delete(row)
            else:
                row.quantity -= taken
        # Недостача наборов: то же количество, на то же место.
        for pool, target in targets.items():
            deficit = target - totals.get(pool, 0)
            while deficit > 0 and surplus:
                location_id, available = surplus[0]
                moved = min(deficit, available)
                deficit -= moved
                if moved == available:
                    surplus.pop(0)
                else:
                    surplus[0] = (location_id, available - moved)
                same = next(
                    (
                        row for row in rows
                        if row.box_id == pool
                        and row.storage_location_id == location_id
                        and id(row) not in deleted
                    ),
                    None,
                )
                if same is not None:
                    same.quantity += moved
                    continue
                created = InboundIntakeDistributionLine(
                    request_id=request.id,
                    product_id=line.product_id,
                    storage_location_id=location_id,
                    quantity=moved,
                    box_id=pool,
                )
                session.add(created)
                rows.append(created)
    await session.flush()


async def _return_balance_to_sorting(
    session: AsyncSession,
    *,
    request: InboundIntakeRequest,
    balance: InventoryBalance,
    quantity: int,
    sorting_location_id: uuid.UUID,
    destination_kind: ContainerKind | None,
    destination_id: uuid.UUID | None,
    group_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    release_container_line: bool,
    only_document_units: bool = False,
) -> None:
    """Вернуть штуки документа с ячейки в «Сортировку» (R15).

    Возвращается только расположение и прогресс раскладки этого документа:
    остаток не меняется — это пара перемещений внутри фулфилмента (R14).
    «Разложено» уменьшается ровно на штуки, которые этот документ туда
    положил (связанные движения в этом месте и в этой таре), поэтому повторная
    постановка снова пройдёт и увеличит его ровно на возвращённое.

    ``only_document_units`` — товар снимают сам по себе (не вместе с тарой):
    тогда снять можно только штуки, положенные этим документом. Чужую россыпь
    на той же ячейке (другой документ, другой селлер) ручка документа не
    трогает — отказ ``qty_exceeds_accepted``, как до WMS-650 (R18).
    """
    line = next((row for row in request.lines if row.product_id == balance.product_id), None)
    source_kind = cast(ContainerKind | None, balance.container_kind)
    source_id = balance.container_id
    location_id = balance.storage_location_id
    linked = 0
    if line is not None:
        proven = await linked_location_quantity(
            session, request.tenant_id, line.id, location_id, source_kind, source_id
        )
        linked = max(0, min(quantity, proven, int(line.posted_qty)))
    if only_document_units and (line is None or linked != quantity):
        raise WarehouseMapError("qty_exceeds_accepted")
    for part, line_id in ((linked, line.id if line else None), (quantity - linked, None)):
        if part <= 0:
            continue
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=request.tenant_id,
            product_id=balance.product_id,
            storage_location_id=location_id,
            quantity_delta=-part,
            _exact_source=True,
            movement_type=MOVEMENT_TYPE_WAREHOUSE_MAP,
            transfer_group_id=group_id,
            inbound_intake_line_id=line_id,
            container_kind=source_kind,
            container_id=source_id,
            actor_user_id=actor_user_id,
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=request.tenant_id,
            product_id=balance.product_id,
            storage_location_id=sorting_location_id,
            quantity_delta=part,
            movement_type=MOVEMENT_TYPE_WAREHOUSE_MAP,
            transfer_group_id=group_id,
            inbound_intake_line_id=line_id,
            container_kind=destination_kind,
            container_id=destination_id,
            actor_user_id=actor_user_id,
        )
    if not linked or line is None:
        return
    line.posted_qty -= linked
    request.distribution_completed_at = None
    if release_container_line and source_kind in {"box", "cargo_place"}:
        containers: list[InboundIntakeBox | InboundIntakeCargoPlace] = [
            *request.boxes,
            *request.cargo_places,
        ]
        content = next(
            (
                row
                for container in containers
                if container.id == source_id
                for row in container.lines
                if row.product_id == balance.product_id
            ),
            None,
        )
        if content is not None:
            content.posted_qty -= min(linked, int(content.posted_qty))
    await release_distribution(
        session,
        request_id=request.id,
        product_id=balance.product_id,
        quantity=linked,
        # Тара снята целиком — строки её короба; товар вынут из короба —
        # «разложено» короба не меняется, поэтому сначала строки россыпи.
        box_id=(
            distribution_box_id(request, source_kind, source_id)
            if release_container_line
            else None
        ),
        prefer_location_id=location_id,
    )


def distribution_box_id(
    request: InboundIntakeRequest, kind: str | None, container_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Короб приёмки, к которому относится строка распределения, иначе None."""
    if kind == "box" and any(box.id == container_id for box in request.boxes):
        return container_id
    return None


async def _relocate_sorting_container(
    session: AsyncSession,
    *,
    request: InboundIntakeRequest,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    kind: ContainerKind,
    object_id: uuid.UUID,
    to_kind: DestinationKind,
    to_id: uuid.UUID | None,
    destination_location_id: uuid.UUID,
    sorting_location_id: uuid.UUID,
    group_id: uuid.UUID,
    is_return: bool,
) -> int:
    """Тара едет целиком с содержимым: на палету, в «Сортировку», снятие с ячейки."""
    if to_kind in {"box", "cargo_place"} or (kind == "pallet" and to_kind == "pallet"):
        raise WarehouseMapError("invalid_container_destination")
    if to_kind == "pallet" and to_id == object_id:
        raise WarehouseMapError("container_cycle")
    current_pallet = await container_pallet_id(session, tenant_id, warehouse_id, kind, object_id)
    source_location_id = await _container_location_id(
        session, tenant_id, warehouse_id, kind, object_id
    )
    target_pallet = to_id if to_kind == "pallet" else None
    if source_location_id == destination_location_id and current_pallet == target_pallet:
        raise WarehouseMapError("nothing_to_move")
    balances = await _container_balances(session, tenant_id, warehouse_id, kind, object_id)
    total = 0
    for balance in balances:
        quantity = int(balance.quantity)
        if quantity <= 0:
            continue
        total += quantity
        if balance.storage_location_id == destination_location_id:
            continue
        balance_kind = cast(ContainerKind | None, balance.container_kind)
        if is_return:
            await _return_balance_to_sorting(
                session,
                request=request,
                balance=balance,
                quantity=quantity,
                sorting_location_id=sorting_location_id,
                destination_kind=balance_kind,
                destination_id=balance.container_id,
                group_id=group_id,
                actor_user_id=actor_user_id,
                release_container_line=True,
            )
            continue
        await _transfer_balance(
            session,
            tenant_id=tenant_id,
            balance=balance,
            quantity=quantity,
            destination_location_id=destination_location_id,
            destination_container_kind=balance_kind,
            destination_container_id=balance.container_id,
            transfer_group_id=group_id,
            actor_user_id=actor_user_id,
            # Вне статуса сортировки (или из ячейки в «Сортировку» без возврата
            # прогресса) это простое перемещение, не связанное с документом.
            inbound_request_id=(
                None if destination_location_id == sorting_location_id else request.id
            ),
        )
    await _place_container(
        session, tenant_id, warehouse_id, kind, object_id, to_kind, to_id, destination_location_id
    )
    return total


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
    inbound_request_id: uuid.UUID | None = None,
    operation_id: uuid.UUID | None = None,
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
    if inbound_request_id is None:
        # Склад целиком, без документа: как до WMS-650 — обычный перенос.
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

    from app.services import inbound_intake_service as intake
    from app.services.inbound_sorting_service import apply_loose_putaway

    request = await intake.get_request(session, tenant_id, inbound_request_id, for_update=True)
    if request is None or request.warehouse_id != warehouse_id:
        raise WarehouseMapError("inbound_request_not_found")
    if operation_id is not None:
        if kind == "cargo_place" and cell_id is not None:
            replayed = await _replayed_sorting_cargo_putaway(
                session,
                tenant_id=tenant_id,
                inbound_request_id=inbound_request_id,
                cargo_place_id=object_id,
                destination_location_id=cell_id,
                operation_id=operation_id,
            )
            if replayed is not None:
                return {"id": str(operation_id), "moved_qty": replayed}
        replay = await _replayed_sorting_action(
            session,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            operation_id=operation_id,
            kind=kind,
            object_id=object_id,
            destination_kind=destination_kind,
            destination_id=destination_id,
        )
        if replay is not None:
            return replay
    op_id = operation_id or uuid.uuid4()
    owned = await sorting_document_containers(session, tenant_id, warehouse_id, inbound_request_id)
    if destination_kind not in {"cell", "unassigned"} and (
        (destination_kind, destination_id) not in owned
    ):
        raise WarehouseMapError("destination_not_found")
    destination_location_id, _kind, _id, to_label = await _destination(
        session, tenant_id, warehouse_id, destination_kind, destination_id
    )
    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
    into_sorting = destination_location_id == sorting.id
    returns_progress = request.status == intake.STATUS_SORTING

    if kind == "product":
        balance = await session.get(InventoryBalance, object_id)
        if balance is None or balance.tenant_id != tenant_id:
            raise WarehouseMapError("object_not_found")
        if balance.container_kind is not None and balance.container_id is not None and (
            (balance.container_kind, balance.container_id) not in owned
        ):
            raise WarehouseMapError("object_not_found")
        source = await session.get(StorageLocation, balance.storage_location_id)
        if source is None or source.warehouse_id != warehouse_id:
            raise WarehouseMapError("object_not_found")
        from_sorting = source.code == SORTING_LOCATION_CODE
        if into_sorting and not from_sorting and returns_progress:
            return await _return_product_to_sorting(
                session,
                request=request,
                balance=balance,
                quantity=quantity,
                sorting_location_id=sorting.id,
                destination_kind=_kind,
                destination_id=_id,
                to_label=to_label,
                op_id=op_id,
                actor_user_id=actor_user_id,
            )
        if cell_id is not None and from_sorting and balance.container_id is None:
            if quantity is None:
                raise WarehouseMapError("quantity_must_be_positive")
            try:
                await apply_loose_putaway(
                    session, tenant_id, inbound_request_id,
                    operation_id=op_id, product_id=balance.product_id,
                    storage_location_id=cell_id, quantity=quantity,
                    performer_id=actor_user_id, commit=False,
                )
            except intake.InboundIntakeError as exc:
                raise WarehouseMapError(exc.code) from exc
            await rebalance_distribution(session, request)
            await session.commit()
            return {"id": str(op_id), "moved_qty": quantity}
        result = await move_object(
            session,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            actor_user_id=actor_user_id,
            kind=kind,
            object_id=object_id,
            to_kind=destination_kind,
            to_id=destination_id,
            quantity=quantity,
            inbound_request_id=inbound_request_id,
            transfer_group_id=op_id,
            event_id=op_id,
            commit=False,
        )
        await rebalance_distribution(session, request)
        await session.commit()
        return {"id": str(op_id), "moved_qty": result["moved_qty"]}

    if (kind, object_id) not in owned:
        raise WarehouseMapError("object_not_found")
    try:
        holder_label = await sorting_holder_label(
            session, tenant_id, warehouse_id, kind, object_id
        )
        source_location_id = await _container_location_id(
            session, tenant_id, warehouse_id, kind, object_id
        )
    except ValueError as exc:
        raise WarehouseMapError("object_not_found") from exc
    from_sorting = source_location_id == sorting.id
    if destination_kind == "cell":
        if kind == "cargo_place" and from_sorting and await _pending_sorting_cargo_quantity(
            session,
            tenant_id=tenant_id,
            inbound_request_id=inbound_request_id,
            cargo_place_id=object_id,
        ) <= 0:
            # Грузоместо в «Сортировке» без неразложенного: устаревшее намерение
            # постановки, а не новый перенос по складу.
            raise WarehouseMapError("nothing_to_move")
        result = await move_object(
            session,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            actor_user_id=actor_user_id,
            kind=kind,
            object_id=object_id,
            to_kind=destination_kind,
            to_id=destination_id,
            quantity=quantity,
            inbound_request_id=inbound_request_id,
            transfer_group_id=op_id,
            event_id=op_id,
            from_label=holder_label,
            commit=False,
        )
        await rebalance_distribution(session, request)
        await session.commit()
        return {"id": str(op_id), "moved_qty": result["moved_qty"]}
    moved = await _relocate_sorting_container(
        session,
        request=request,
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        actor_user_id=actor_user_id,
        kind=kind,
        object_id=object_id,
        to_kind=destination_kind,
        to_id=destination_id,
        destination_location_id=destination_location_id,
        sorting_location_id=sorting.id,
        group_id=op_id,
        is_return=into_sorting and not from_sorting and returns_progress,
    )
    code = await _container_code(session, tenant_id, warehouse_id, kind, object_id)
    session.add(
        WarehouseMapEvent(
            id=op_id,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            actor_user_id=actor_user_id,
            subject=_container_title(kind, code),
            quantity=moved or None,
            from_label=holder_label,
            to_label=to_label,
        )
    )
    await rebalance_distribution(session, request)
    await session.commit()
    return {"id": str(op_id), "moved_qty": moved or None}


async def _return_product_to_sorting(
    session: AsyncSession,
    *,
    request: InboundIntakeRequest,
    balance: InventoryBalance,
    quantity: int | None,
    sorting_location_id: uuid.UUID,
    destination_kind: ContainerKind | None,
    destination_id: uuid.UUID | None,
    to_label: str,
    op_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> dict[str, Any]:
    """«Снять с ячейки» товар или «Вынуть из …» тары на ячейке — в «осталось»."""
    if quantity is None or quantity <= 0:
        raise WarehouseMapError("quantity_must_be_positive")
    await inventory_service.lock_stock_product(session, request.tenant_id, balance.product_id)
    locked = await session.scalar(
        select(InventoryBalance)
        .where(InventoryBalance.id == balance.id, InventoryBalance.quantity > 0)
        .with_for_update()
    )
    if locked is None:
        raise WarehouseMapError("object_not_found")
    if quantity > locked.quantity:
        raise WarehouseMapError("insufficient_stock")
    product = await session.get(Product, locked.product_id)
    assert product is not None
    from_label = await _location_label(session, locked.storage_location_id)
    if locked.container_kind and locked.container_id:
        code = await _container_code(
            session,
            request.tenant_id,
            request.warehouse_id,
            cast(ContainerKind, locked.container_kind),
            locked.container_id,
        )
        from_label = _container_title(locked.container_kind, code)
    await _return_balance_to_sorting(
        session,
        request=request,
        balance=locked,
        quantity=quantity,
        sorting_location_id=sorting_location_id,
        destination_kind=destination_kind,
        destination_id=destination_id,
        group_id=op_id,
        actor_user_id=actor_user_id,
        release_container_line=False,
        only_document_units=True,
    )
    session.add(
        WarehouseMapEvent(
            id=op_id,
            tenant_id=request.tenant_id,
            warehouse_id=request.warehouse_id,
            actor_user_id=actor_user_id,
            subject=product.name,
            quantity=quantity,
            from_label=from_label,
            to_label=to_label,
        )
    )
    await rebalance_distribution(session, request)
    await session.commit()
    return {"id": str(op_id), "moved_qty": quantity}
