from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import MOVEMENT_TYPE_INVENTORY_COUNT
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service, tenant_settings_service, warehouse_map_service
from app.services.inventory_container_service import ContainerKind
from app.services.sorting_location_service import SORTING_LOCATION_CODE
from app.services.wb_card_enrichment import subject_name_from_card

STATUS_DRAFT = "draft"
STATUS_POSTED = "posted"
STATUS_CANCELLED = "cancelled"
SOURCE_OBJECT = "object"
SOURCE_PLANNED = "planned"


class InventoryCountError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CountObject:
    type: str
    id: uuid.UUID
    storage_location_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CountFilters:
    seller_id: uuid.UUID | None = None
    category: str | None = None
    warehouse_id: uuid.UUID | None = None
    all: bool = False


@dataclass(frozen=True)
class ChangedBalance:
    line_id: uuid.UUID
    product_id: uuid.UUID
    storage_location_id: uuid.UUID | None
    expected_quantity: int
    current_quantity: int


@dataclass(frozen=True)
class PostResult:
    count: InventoryCount
    posted_lines: int
    unchanged_lines: int
    changed_balances: list[ChangedBalance]


@dataclass(frozen=True)
class ProductScanResult:
    count: InventoryCount
    line_id: uuid.UUID


def _product_category_column() -> Any | None:
    """Use the product category once the neighbouring category wave is merged."""

    return getattr(Product, "category", None)


def _card_category_expression() -> Any:
    raw = SellerWildberriesImportedCard.raw_json
    return func.coalesce(
        raw["subjectName"].as_string(),
        raw["subject_name"].as_string(),
    )


async def _validate_scope(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None,
) -> None:
    if seller_id is not None:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != tenant_id:
            raise InventoryCountError("seller_not_found")
    if warehouse_id is not None:
        warehouse = await session.get(Warehouse, warehouse_id)
        if warehouse is None or warehouse.tenant_id != tenant_id:
            raise InventoryCountError("warehouse_not_found")


async def _container_scope(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> tuple[uuid.UUID, list[tuple[ContainerKind, uuid.UUID]]]:
    refs: list[tuple[ContainerKind, uuid.UUID]] = [(kind, container_id)]
    if kind == "pallet":
        pallet = await session.scalar(
            select(Pallet).where(
                Pallet.id == container_id,
                Pallet.tenant_id == tenant_id,
                Pallet.disbanded_at.is_(None),
            )
        )
        if pallet is None:
            raise InventoryCountError("object_not_found")
        warehouse_id = pallet.warehouse_id
        warehouse_containers = await session.scalars(
            select(WarehouseBox).where(
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.pallet_id == pallet.id,
            )
        )
        inbound_box_ids = await session.scalars(
            select(InboundIntakeBox.id)
            .join(InboundIntakeRequest)
            .where(
                InboundIntakeBox.tenant_id == tenant_id,
                InboundIntakeBox.pallet_id == pallet.id,
                InboundIntakeRequest.tenant_id == tenant_id,
                InboundIntakeRequest.warehouse_id == warehouse_id,
            )
        )
        cargo_place_ids = await session.scalars(
            select(InboundIntakeCargoPlace.id)
            .join(InboundIntakeRequest)
            .where(
                InboundIntakeCargoPlace.tenant_id == tenant_id,
                InboundIntakeCargoPlace.pallet_id == pallet.id,
                InboundIntakeRequest.tenant_id == tenant_id,
                InboundIntakeRequest.warehouse_id == warehouse_id,
            )
        )
        refs.extend((row.container_kind, row.id) for row in warehouse_containers.all())
        refs.extend(("box", row_id) for row_id in inbound_box_ids.all())
        refs.extend(("cargo_place", row_id) for row_id in cargo_place_ids.all())
        return warehouse_id, refs

    if kind == "box":
        warehouse_box = await session.scalar(
            select(WarehouseBox).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.container_kind == "box",
            )
        )
        if warehouse_box is not None:
            return warehouse_box.warehouse_id, refs
        request_warehouse_id = await session.scalar(
            select(InboundIntakeRequest.warehouse_id)
            .join(InboundIntakeBox)
            .where(
                InboundIntakeBox.id == container_id,
                InboundIntakeBox.tenant_id == tenant_id,
                InboundIntakeRequest.tenant_id == tenant_id,
            )
        )
    else:
        warehouse_cargo_place = await session.scalar(
            select(WarehouseBox).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.container_kind == "cargo_place",
            )
        )
        if warehouse_cargo_place is not None:
            return warehouse_cargo_place.warehouse_id, refs
        request_warehouse_id = await session.scalar(
            select(InboundIntakeRequest.warehouse_id)
            .join(InboundIntakeCargoPlace)
            .where(
                InboundIntakeCargoPlace.id == container_id,
                InboundIntakeCargoPlace.tenant_id == tenant_id,
                InboundIntakeRequest.tenant_id == tenant_id,
            )
        )
    if request_warehouse_id is None:
        raise InventoryCountError("object_not_found")
    return request_warehouse_id, refs


def _balance_query(
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    category: str | None,
    warehouse_id: uuid.UUID | None,
    address_storage_enabled: bool,
) -> Select[tuple[InventoryBalance, Product, StorageLocation]]:
    stmt = (
        select(InventoryBalance, Product, StorageLocation)
        .join(Product, Product.id == InventoryBalance.product_id)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            Product.tenant_id == tenant_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.deleted_at.is_(None),
            InventoryBalance.quantity > 0,
        )
        .options(selectinload(Product.seller))
        .order_by(StorageLocation.code, Product.sku_code)
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    if warehouse_id is not None:
        stmt = stmt.where(StorageLocation.warehouse_id == warehouse_id)
    if not address_storage_enabled:
        stmt = stmt.where(StorageLocation.code == SORTING_LOCATION_CODE)
    if category is not None:
        # Категория товара приходит из двух мест: собственное поле каталога и
        # карточка Wildberries. У импортированных товаров заполнено одно, у
        # заведённых руками — другое, поэтому ищем по обоим. Смотреть только в
        # собственное поле значит потерять всё, что приехало импортом.
        stmt = stmt.outerjoin(
            SellerWildberriesImportedCard,
            and_(
                SellerWildberriesImportedCard.tenant_id == tenant_id,
                SellerWildberriesImportedCard.seller_id == Product.seller_id,
                SellerWildberriesImportedCard.nm_id == Product.wb_nm_id,
            ),
        )
        card_matches = _card_category_expression() == category
        category_column = _product_category_column()
        stmt = stmt.where(
            or_(category_column == category, card_matches)
            if category_column is not None
            else card_matches
        )
    return stmt


async def create_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    source: str,
    object_scope: CountObject | None,
    filters: CountFilters | None,
    comment: str | None,
) -> InventoryCount:
    if source not in {SOURCE_OBJECT, SOURCE_PLANNED}:
        raise InventoryCountError("invalid_source")
    if source == SOURCE_OBJECT and object_scope is None:
        raise InventoryCountError("object_required")
    if source == SOURCE_PLANNED and filters is None:
        raise InventoryCountError("filters_required")

    seller_id = filters.seller_id if filters is not None else None
    category = filters.category.strip() if filters and filters.category else None
    warehouse_id = filters.warehouse_id if filters is not None else None
    await _validate_scope(
        session,
        tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
    )
    address_enabled = await tenant_settings_service.is_address_storage_enabled(
        session, tenant_id
    )
    stmt = _balance_query(
        tenant_id,
        seller_id=seller_id,
        category=category,
        warehouse_id=warehouse_id,
        address_storage_enabled=address_enabled,
    )

    container_object = False
    if object_scope is not None:
        if object_scope.type in {"storage_location", "location", "cell"}:
            location = await session.get(StorageLocation, object_scope.id)
            if location is None or location.tenant_id != tenant_id:
                raise InventoryCountError("object_not_found")
            if not address_enabled:
                raise InventoryCountError("object_not_available_without_address_storage")
            warehouse_id = location.warehouse_id
            stmt = stmt.where(InventoryBalance.storage_location_id == location.id)
        elif object_scope.type == "product":
            product = await session.get(Product, object_scope.id)
            if product is None or product.tenant_id != tenant_id:
                raise InventoryCountError("object_not_found")
            stmt = stmt.where(Product.id == product.id)
            if object_scope.storage_location_id is not None:
                location = await session.get(StorageLocation, object_scope.storage_location_id)
                if location is None or location.tenant_id != tenant_id:
                    raise InventoryCountError("object_not_found")
                if not address_enabled:
                    raise InventoryCountError("object_not_available_without_address_storage")
                warehouse_id = location.warehouse_id
                stmt = stmt.where(InventoryBalance.storage_location_id == location.id)
        elif object_scope.type in {"pallet", "box", "cargo_place"}:
            container_object = True
            container_kind = cast(ContainerKind, object_scope.type)
            warehouse_id, container_refs = await _container_scope(
                session,
                tenant_id,
                container_kind,
                object_scope.id,
            )
            predicates = [
                and_(
                    InventoryBalance.container_kind == ref_kind,
                    InventoryBalance.container_id == ref_id,
                )
                for ref_kind, ref_id in container_refs
            ]
            stmt = stmt.where(
                StorageLocation.warehouse_id == warehouse_id,
                or_(*predicates),
            )
        else:
            raise InventoryCountError("unsupported_object_type")

    result = await session.execute(stmt)
    balances = list(result.all())
    if container_object and not balances:
        raise InventoryCountError("container_has_no_stock")
    if warehouse_id is None:
        warehouse_ids = {location.warehouse_id for _, _, location in balances}
        if len(warehouse_ids) == 1:
            warehouse_id = next(iter(warehouse_ids))
        elif not address_enabled and len(warehouse_ids) > 1:
            raise InventoryCountError("warehouse_required_without_address_storage")

    count = InventoryCount(
        tenant_id=tenant_id,
        status=STATUS_DRAFT,
        source=source,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        category=category,
        created_by_user_id=user_id,
        comment=comment.strip() if comment and comment.strip() else None,
    )
    session.add(count)
    await session.flush()
    session.add_all(
        [
            InventoryCountLine(
                count_id=count.id,
                product_id=balance.product_id,
                storage_location_id=balance.storage_location_id,
                container_kind=balance.container_kind,
                container_id=balance.container_id,
                expected_quantity=int(balance.quantity),
                actual_quantity=None,
                posted_delta=None,
            )
            for balance, _, _ in balances
        ]
    )
    await session.commit()
    loaded = await get_count(session, tenant_id, count.id)
    assert loaded is not None
    return loaded


def _load_options() -> tuple[Any, ...]:
    return (
        selectinload(InventoryCount.warehouse),
        selectinload(InventoryCount.seller),
        selectinload(InventoryCount.created_by),
        selectinload(InventoryCount.posted_by),
        selectinload(InventoryCount.lines).selectinload(InventoryCountLine.product).selectinload(
            Product.seller
        ),
        selectinload(InventoryCount.lines).selectinload(
            InventoryCountLine.storage_location
        ),
    )


async def get_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
) -> InventoryCount | None:
    result = await session.execute(
        select(InventoryCount)
        .where(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == tenant_id,
        )
        .options(*_load_options())
    )
    return result.scalar_one_or_none()


async def list_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    warehouse_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[InventoryCount]:
    stmt = select(InventoryCount).where(InventoryCount.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(InventoryCount.status == status)
    if warehouse_id is not None:
        stmt = stmt.where(InventoryCount.warehouse_id == warehouse_id)
    if seller_id is not None:
        stmt = stmt.where(InventoryCount.seller_id == seller_id)
    if created_from is not None:
        stmt = stmt.where(InventoryCount.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(InventoryCount.created_at <= created_to)
    result = await session.execute(
        stmt.options(*_load_options()).order_by(InventoryCount.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def save_actuals(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    values: list[tuple[uuid.UUID, int | None]],
) -> InventoryCount:
    result = await session.execute(
        select(InventoryCount)
        .where(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    count = result.scalar_one_or_none()
    if count is None:
        raise InventoryCountError("not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("not_editable")
    line_ids = [line_id for line_id, _ in values]
    if len(line_ids) != len(set(line_ids)):
        raise InventoryCountError("duplicate_line")
    lines_result = await session.execute(
        select(InventoryCountLine)
        .where(
            InventoryCountLine.count_id == count.id,
            InventoryCountLine.id.in_(line_ids),
        )
        .with_for_update()
    )
    lines = {line.id: line for line in lines_result.scalars()}
    if len(lines) != len(line_ids):
        raise InventoryCountError("line_not_found")
    for line_id, actual_quantity in values:
        if actual_quantity is not None and actual_quantity < 0:
            raise InventoryCountError("invalid_actual_quantity")
        lines[line_id].actual_quantity = actual_quantity
    await session.commit()
    loaded = await get_count(session, tenant_id, count.id)
    assert loaded is not None
    return loaded


async def scan_product_into_container(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    container_kind: ContainerKind,
    container_id: uuid.UUID,
    barcode_candidates: list[str],
    product_id_hint: uuid.UUID | None,
    actual_values: list[tuple[uuid.UUID, int | None]],
) -> ProductScanResult:
    """Add one counted unit to a container, creating the draft line if needed.

    The browser normally counts an existing line locally for scanner speed. This
    path is used only for a physical find: the product has no line in the opened
    container. Existing unsaved facts arrive with the request and are persisted
    under the same document lock, so adding the new line cannot erase the work
    already visible to the operator.
    """

    count = await session.scalar(
        select(InventoryCount)
        .where(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if count is None:
        raise InventoryCountError("not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("not_editable")
    if count.warehouse_id is None:
        raise InventoryCountError("warehouse_required")

    line_ids = [line_id for line_id, _ in actual_values]
    if len(line_ids) != len(set(line_ids)):
        raise InventoryCountError("duplicate_line")
    existing_lines_result = await session.execute(
        select(InventoryCountLine)
        .where(
            InventoryCountLine.count_id == count.id,
            InventoryCountLine.id.in_(line_ids),
        )
        .with_for_update()
    )
    existing_lines = {line.id: line for line in existing_lines_result.scalars()}
    if len(existing_lines) != len(line_ids):
        raise InventoryCountError("line_not_found")
    for line_id, actual_quantity in actual_values:
        if actual_quantity is not None and actual_quantity < 0:
            raise InventoryCountError("invalid_actual_quantity")
        existing_lines[line_id].actual_quantity = actual_quantity

    normalized_codes = {
        candidate.strip().lower() for candidate in barcode_candidates if candidate.strip()
    }
    if not normalized_codes:
        raise InventoryCountError("barcode_empty")

    product: Product | None = None
    if product_id_hint is not None:
        hinted = await session.get(Product, product_id_hint)
        if hinted is None or hinted.tenant_id != tenant_id:
            raise InventoryCountError("product_not_found")
        identifiers = {
            identifier.strip().lower()
            for identifier in (hinted.wb_barcode, hinted.sku_code)
            if identifier and identifier.strip()
        }
        if identifiers.isdisjoint(normalized_codes):
            raise InventoryCountError("product_not_found")
        product = hinted
    else:
        products = list(
            (
                await session.scalars(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        or_(
                            func.lower(Product.wb_barcode).in_(normalized_codes),
                            func.lower(Product.sku_code).in_(normalized_codes),
                        ),
                    )
                )
            ).all()
        )
        if not products:
            raise InventoryCountError("product_not_found")
        if len(products) > 1:
            raise InventoryCountError("product_ambiguous")
        product = products[0]

    try:
        storage_location_id = await warehouse_map_service.resolve_container_location(
            session,
            tenant_id,
            count.warehouse_id,
            container_kind,
            container_id,
        )
    except ValueError as exc:
        raise InventoryCountError("container_not_found") from exc

    line = await session.scalar(
        select(InventoryCountLine)
        .where(
            InventoryCountLine.count_id == count.id,
            InventoryCountLine.product_id == product.id,
            InventoryCountLine.storage_location_id == storage_location_id,
            InventoryCountLine.container_kind == container_kind,
            InventoryCountLine.container_id == container_id,
        )
        .with_for_update()
    )
    if line is None:
        line = InventoryCountLine(
            count_id=count.id,
            product_id=product.id,
            storage_location_id=storage_location_id,
            container_kind=container_kind,
            container_id=container_id,
            expected_quantity=0,
            actual_quantity=1,
            posted_delta=None,
        )
        session.add(line)
        await session.flush()
    else:
        line.actual_quantity = int(line.actual_quantity or 0) + 1

    line_id = line.id
    await session.commit()
    loaded = await get_count(session, tenant_id, count.id)
    assert loaded is not None
    return ProductScanResult(count=loaded, line_id=line_id)


async def _current_quantity(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    line: InventoryCountLine,
    lock: bool,
) -> int:
    if line.storage_location_id is None:
        raise InventoryCountError("line_storage_location_missing")
    stmt = select(InventoryBalance.quantity).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == line.product_id,
        InventoryBalance.storage_location_id == line.storage_location_id,
        InventoryBalance.container_kind == line.container_kind,
        InventoryBalance.container_id == line.container_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    value = await session.scalar(stmt)
    return int(value or 0)


async def current_quantities(
    session: AsyncSession,
    count: InventoryCount,
) -> dict[uuid.UUID, int]:
    values: dict[uuid.UUID, int] = {}
    for line in count.lines:
        if count.status == STATUS_POSTED and line.actual_quantity is not None:
            posted_delta = int(line.posted_delta or 0)
            values[line.id] = int(line.actual_quantity) - posted_delta
        else:
            values[line.id] = await _current_quantity(
                session,
                tenant_id=count.tenant_id,
                line=line,
                lock=False,
            )
    return values


async def post_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PostResult:
    result = await session.execute(
        select(InventoryCount)
        .where(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    count = result.scalar_one_or_none()
    if count is None:
        raise InventoryCountError("not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("already_posted")
    lines_result = await session.execute(
        select(InventoryCountLine)
        .where(InventoryCountLine.count_id == count.id)
        .order_by(InventoryCountLine.id)
        .with_for_update()
    )
    entered_lines = [line for line in lines_result.scalars() if line.actual_quantity is not None]
    if not entered_lines:
        raise InventoryCountError("empty_count")

    changed_balances: list[ChangedBalance] = []
    posted_lines = 0
    for line in entered_lines:
        storage_location_id = line.storage_location_id
        if storage_location_id is None:
            raise InventoryCountError("line_storage_location_missing")
        current = await _current_quantity(
            session,
            tenant_id=tenant_id,
            line=line,
            lock=True,
        )
        if current != line.expected_quantity:
            changed_balances.append(
                ChangedBalance(
                    line_id=line.id,
                    product_id=line.product_id,
                    storage_location_id=storage_location_id,
                    expected_quantity=line.expected_quantity,
                    current_quantity=current,
                )
            )
        assert line.actual_quantity is not None
        delta = int(line.actual_quantity) - current
        line.posted_delta = delta
        if delta == 0:
            continue
        try:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=storage_location_id,
                quantity_delta=delta,
                movement_type=MOVEMENT_TYPE_INVENTORY_COUNT,
                inventory_count_line_id=line.id,
                actor_user_id=user_id,
                container_kind=cast(ContainerKind | None, line.container_kind),
                container_id=line.container_id,
            )
        except ValueError as exc:
            await session.rollback()
            if str(exc) == "insufficient stock":
                raise InventoryCountError("balance_changed_during_post") from exc
            raise
        posted_lines += 1

    count.status = STATUS_POSTED
    count.posted_at = datetime.now(UTC)
    count.posted_by_user_id = user_id
    await session.commit()
    loaded = await get_count(session, tenant_id, count.id)
    assert loaded is not None
    return PostResult(
        count=loaded,
        posted_lines=posted_lines,
        unchanged_lines=len(entered_lines) - posted_lines,
        changed_balances=changed_balances,
    )


async def cancel_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
) -> InventoryCount:
    result = await session.execute(
        select(InventoryCount)
        .where(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    count = result.scalar_one_or_none()
    if count is None:
        raise InventoryCountError("not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("not_cancellable")
    count.status = STATUS_CANCELLED
    await session.commit()
    loaded = await get_count(session, tenant_id, count.id)
    assert loaded is not None
    return loaded


async def product_categories(
    session: AsyncSession,
    products: list[Product],
) -> dict[uuid.UUID, str | None]:
    result = {product.id: getattr(product, "category", None) for product in products}
    missing = [
        product
        for product in products
        if result[product.id] is None
        and product.seller_id is not None
        and product.wb_nm_id is not None
    ]
    if not missing:
        return result
    pairs = {
        (product.seller_id, product.wb_nm_id)
        for product in missing
        if product.seller_id is not None and product.wb_nm_id is not None
    }
    rows = await session.execute(
        select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.tenant_id == missing[0].tenant_id,
            or_(
                *[
                    and_(
                        SellerWildberriesImportedCard.seller_id == seller_id,
                        SellerWildberriesImportedCard.nm_id == nm_id,
                    )
                    for seller_id, nm_id in pairs
                ]
            ),
        )
    )
    by_pair = {
        (card.seller_id, card.nm_id): subject_name_from_card(card.raw_json or {})
        for card in rows.scalars()
    }
    for product in missing:
        seller_id = product.seller_id
        nm_id = product.wb_nm_id
        if seller_id is not None and nm_id is not None:
            result[product.id] = by_pair.get((seller_id, nm_id))
    return result
