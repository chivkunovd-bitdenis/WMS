from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import (
    InventoryCount,
    InventoryCountCreatedContainer,
    InventoryCountFoundScan,
    InventoryCountLine,
)
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
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    get_or_create_sorting_location,
)
from app.services.wb_card_enrichment import (
    first_photo_url_from_card,
    subject_name_from_card,
)

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
            # ⛔ Раньше здесь стояло «остаток больше нуля», и документ молча
            # собирался без отрицательных строк. А минус в ячейке — самый
            # сильный признак того, что учёт разъехался с полкой: именно её и
            # надо пересчитать, а было нельзя. Решение владельца от 01.09.2026.
            #
            # Нули при этом не тащим. Строка баланса при обнулении не удаляется,
            # поэтому в базе лежат нули по всем сочетаниям «товар, ячейка,
            # тара», которые когда-либо существовали, включая давно уехавшие
            # короба. Тянуть их в документ значит раздуть его фантомными
            # строками. Товар, который лежит там, где по учёту его нет,
            # записывается находкой — для этого есть record_found.
            InventoryBalance.quantity != 0,
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
        # Документ мог быть загружен в этой же сессии до вставки строки: без
        # populate_existing SQLAlchemy вернёт объект из карты идентичности со
        # старой коллекцией строк, и только что записанной находки в ответе не
        # окажется.
        .execution_options(populate_existing=True)
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


async def create_document_container(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    kind: ContainerKind,
) -> InventoryCount:
    """Завести пустую тару прямо в документе пересчёта.

    Тара создаётся на складе документа как обычная тара (`sorting-objects`),
    но дополнительно запоминается за этим документом — иначе прунинг пустой
    тары в API (`_prune_empty_containers`) выбросит её из дерева сразу же:
    она пуста по определению, оператор только что её завёл. Общее правило
    прунинга не трогаем, здесь только точечное исключение для этой пары
    (документ, тара).
    """
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
    if count.warehouse_id is None:
        raise InventoryCountError("warehouse_not_found")
    try:
        created = await warehouse_map_service.create_sorting_object(
            session,
            tenant_id,
            count.warehouse_id,
            kind=kind,
        )
    except warehouse_map_service.WarehouseMapError as exc:
        raise InventoryCountError(exc.code) from exc
    session.add(
        InventoryCountCreatedContainer(
            tenant_id=tenant_id,
            count_id=count_id,
            container_kind=kind,
            container_id=uuid.UUID(str(created["id"])),
        )
    )
    await session.commit()
    loaded = await get_count(session, tenant_id, count_id)
    assert loaded is not None
    return loaded


async def created_container_ids(
    session: AsyncSession,
    count_id: uuid.UUID,
) -> set[tuple[str, str]]:
    """Тара, заведённая прямо в этом документе — исключения из прунинга."""
    rows = await session.scalars(
        select(InventoryCountCreatedContainer).where(
            InventoryCountCreatedContainer.count_id == count_id
        )
    )
    return {(row.container_kind, str(row.container_id)) for row in rows.all()}


@dataclass(frozen=True)
class FoundResult:
    """Результат записи находки вместе с честным текстом для оператора."""

    count: InventoryCount
    expected_quantity: int
    notice: str


def _found_notice(expected_quantity: int) -> str:
    """Что сказать оператору. Правду, а не то, что удобно.

    Экран решает «это находка» по одному признаку: строки нет в документе. Но
    документ бывает отобран — по селлеру, по категории, по одному объекту. Тогда
    «строки нет в документе» и «по учёту здесь ничего нет» — разные вещи, и
    сказать оператору «не числится», когда на месте лежит двадцать штук,
    значит соврать: он посчитает одну и уйдёт, а проведение спишет девятнадцать.
    """
    if expected_quantity == 0:
        return "По учёту здесь ничего не числится — записали находку."
    return (
        f"По учёту здесь числится {expected_quantity} шт., но строки в документе "
        "не было — она добавлена. Посчитайте это место целиком, иначе при "
        "проведении недостающее спишется."
    )


async def record_found(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    barcodes: list[str],
    cell_id: uuid.UUID | None,
    container_kind: str | None,
    container_id: uuid.UUID | None,
    scan_id: str | None = None,
) -> FoundResult:
    """Записывает находку: товар лежит там, где по учёту его нет.

    Ради этого пересчёт и затевают. Раньше такой скан отклонялся словами «код в
    этом документе не числится, находку вносим отдельно» — а «отдельно» не
    существовало ни кнопкой, ни ручкой, и записать факт было нечем. Решение
    владельца от 01.09.2026: отсканировал в короб то, чего там нет — строка
    появляется и в ней становится единица.

    Повторный скан того же товара в том же месте не плодит строки, а
    увеличивает счёт: человек считает штуками.
    """
    # ⛔ Порядок здесь важен. Адрес находки вычисляется ДО блокировки.
    #
    # Внутри вычисления может понадобиться создать зону сортировки, а её
    # создание при гонке делает rollback. Если к тому моменту документ уже
    # заблокирован, rollback снимет блокировку и обнулит загруженный объект —
    # следующее обращение к его строкам упадёт пятисоткой. Случай узкий (первая
    # в жизни склада находка без ячейки), но он есть.
    preview = await get_count(session, tenant_id, count_id)
    if preview is None:
        raise InventoryCountError("count_not_found")
    if preview.status != STATUS_DRAFT:
        raise InventoryCountError("count_not_editable")
    storage_location_id = await _resolve_found_location(
        session,
        tenant_id,
        preview,
        cell_id=cell_id,
        container_kind=container_kind,
        container_id=container_id,
    )

    # Документ блокируется на всё время записи. Без этого два быстрых скана
    # одного и того же кода расходятся: оба читают факт 1, оба пишут 2, и одна
    # штука теряется — а если строки ещё не было, второй ловит уникальный индекс
    # и оператор получает 500 вместо записи.
    locked = await session.execute(
        select(InventoryCount)
        .where(InventoryCount.id == count_id, InventoryCount.tenant_id == tenant_id)
        .with_for_update()
    )
    if locked.scalar_one_or_none() is None:
        raise InventoryCountError("count_not_found")
    count = await get_count(session, tenant_id, count_id)
    if count is None:
        raise InventoryCountError("count_not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("count_not_editable")

    codes = [candidate.strip() for candidate in barcodes if candidate.strip()]
    if not codes:
        raise InventoryCountError("barcode_required")

    # Повтор того же скана ничего не прибавляет. Склад работает по вайфаю,
    # который рвётся: ответ не доехал, экран показал ошибку, а запись уже
    # прошла. Кладовщик сканирует ещё раз — и без этой проверки на остатке
    # оказывается лишняя штука, которую потом нечем найти.
    if scan_id:
        seen = await session.scalar(
            select(InventoryCountFoundScan).where(
                InventoryCountFoundScan.count_id == count_id,
                InventoryCountFoundScan.scan_id == scan_id,
            )
        )
        if seen is not None:
            loaded = await get_count(session, tenant_id, count_id)
            assert loaded is not None
            return FoundResult(
                loaded, seen.expected_quantity, _found_notice(seen.expected_quantity)
            )

    # Сканер — обычная клавиатура, и в русской раскладке он отдаёт кириллицу.
    # Экран умеет переводить раскладку и присылает оба варианта, поэтому ищем по
    # всем кандидатам и без учёта регистра: точное сравнение отвергало товар,
    # который экран только что нашёл, и оператор видел два взаимоисключающих
    # сообщения сразу.
    lowered = [candidate.lower() for candidate in codes]
    product_stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        or_(
            func.lower(Product.wb_barcode).in_(lowered),
            func.lower(Product.sku_code).in_(lowered),
        ),
    )
    # Документ, собранный по одному продавцу, чужой товар не принимает: иначе
    # пересчёт одного селлера начнёт править остатки другого.
    if count.seller_id is not None:
        product_stmt = product_stmt.where(Product.seller_id == count.seller_id)
    products = list((await session.execute(product_stmt)).scalars().all())
    if not products:
        # Запасной поиск по штрихкодам маркетплейса: у товара Ozon свой код
        # вида OZN<sku>, которого нет ни в `wb_barcode`, ни в `sku_code`.
        from app.services.ozon_product_import_service import (
            find_product_ids_by_marketplace_barcode,
        )

        product_ids = await find_product_ids_by_marketplace_barcode(
            session,
            tenant_id,
            list(codes),
            seller_id=count.seller_id,
        )
        if product_ids:
            fallback_stmt = select(Product).where(
                Product.tenant_id == tenant_id,
                Product.id.in_(product_ids),
            )
            if count.seller_id is not None:
                fallback_stmt = fallback_stmt.where(Product.seller_id == count.seller_id)
            products = list((await session.execute(fallback_stmt)).scalars().all())
    if not products:
        raise InventoryCountError("product_not_found")
    if len(products) > 1:
        raise InventoryCountError("barcode_is_ambiguous")
    product = products[0]

    existing = next(
        (
            line
            for line in count.lines
            if line.product_id == product.id
            and line.storage_location_id == storage_location_id
            and line.container_kind == container_kind
            and line.container_id == container_id
        ),
        None,
    )
    if existing is not None:
        existing.actual_quantity = int(existing.actual_quantity or 0) + 1
        expected = int(existing.expected_quantity)
        _remember_scan(session, tenant_id, count_id, existing.id, scan_id, expected)
        await session.commit()
        loaded = await get_count(session, tenant_id, count_id)
        assert loaded is not None
        return FoundResult(loaded, expected, _found_notice(expected))

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
    # «Числится» берём из живого остатка: обычно это ноль, но товар мог
    # приехать сюда уже после наполнения документа, и тогда честнее показать
    # реальное число, а не выдуманный ноль.
    line.expected_quantity = await _current_quantity(
        session, tenant_id=tenant_id, line=line, lock=False
    )
    expected = int(line.expected_quantity)
    session.add(line)
    await session.flush()
    _remember_scan(session, tenant_id, count_id, line.id, scan_id, expected)
    try:
        await session.commit()
    except IntegrityError:
        # Гонку с параллельным сканом того же товара разбираем как инкремент:
        # уникальный индекс по строке документа сработал, значит соседний запрос
        # уже завёл её, и правильный ответ — прибавить штуку, а не отдать 500.
        await session.rollback()
        return await _increment_existing_found_line(
            session,
            tenant_id,
            count_id,
            product_id=product.id,
            storage_location_id=storage_location_id,
            container_kind=container_kind,
            container_id=container_id,
        )
    loaded = await get_count(session, tenant_id, count_id)
    assert loaded is not None
    return FoundResult(loaded, expected, _found_notice(expected))


async def add_manual_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
    cell_id: uuid.UUID | None,
    container_kind: str | None,
    container_id: uuid.UUID | None,
) -> FoundResult:
    """Добавляет в документ товар, которого там нет, — руками, по каталогу.

    Решение владельца от 03.09.2026: находка (`record_found`) ловит только то,
    что оператор смог отсканировать. Штрихкод бывает стёрт или не наклеен, а
    товар в короб класть уже надо — тогда ищут по каталогу и вводят число сразу,
    а не по одной штуке сканом. Адрес выводим тем же способом, что и у находки:
    выделили тару — адрес из её карточки, выделили ячейку — берём её, ничего не
    выделили — зона сортировки. Свой резолвер адреса здесь не пишем, см.
    _resolve_found_location.
    """
    preview = await get_count(session, tenant_id, count_id)
    if preview is None:
        raise InventoryCountError("count_not_found")
    if preview.status != STATUS_DRAFT:
        raise InventoryCountError("count_not_editable")
    storage_location_id = await _resolve_found_location(
        session,
        tenant_id,
        preview,
        cell_id=cell_id,
        container_kind=container_kind,
        container_id=container_id,
    )

    # Тот же порядок блокировки, что у record_found: адрес вычисляем ДО
    # блокировки документа, чтобы возможное создание зоны сортировки внутри
    # резолвера не срабатывало rollback'ом по уже заблокированному объекту.
    locked = await session.execute(
        select(InventoryCount)
        .where(InventoryCount.id == count_id, InventoryCount.tenant_id == tenant_id)
        .with_for_update()
    )
    if locked.scalar_one_or_none() is None:
        raise InventoryCountError("count_not_found")
    count = await get_count(session, tenant_id, count_id)
    if count is None:
        raise InventoryCountError("count_not_found")
    if count.status != STATUS_DRAFT:
        raise InventoryCountError("count_not_editable")

    product = await session.get(Product, product_id)
    # Чужой товар не пускаем той же проверкой, что у находки по штрихкоду:
    # документ по одному селлеру не должен наполниться товаром другого. Ошибка
    # звучит как «не найден», а не «чужой» — так же честно, как found, который
    # просто не находит продукт вне области поиска, ничего не раскрывая про
    # чужой каталог.
    if (
        product is None
        or product.tenant_id != tenant_id
        or (count.seller_id is not None and product.seller_id != count.seller_id)
    ):
        raise InventoryCountError("product_not_found")
    if quantity <= 0:
        raise InventoryCountError("invalid_actual_quantity")

    existing = next(
        (
            line
            for line in count.lines
            if line.product_id == product.id
            and line.storage_location_id == storage_location_id
            and line.container_kind == container_kind
            and line.container_id == container_id
        ),
        None,
    )
    if existing is not None:
        # Тот же товар в то же место добавляют второй раз — прибавляем к тому,
        # что уже насчитано, а не создаём вторую строку поверх первой.
        existing.actual_quantity = int(existing.actual_quantity or 0) + quantity
        expected = int(existing.expected_quantity)
        await session.commit()
        loaded = await get_count(session, tenant_id, count_id)
        assert loaded is not None
        return FoundResult(loaded, expected, _found_notice(expected))

    line = InventoryCountLine(
        count_id=count.id,
        product_id=product.id,
        storage_location_id=storage_location_id,
        container_kind=container_kind,
        container_id=container_id,
        expected_quantity=0,
        actual_quantity=quantity,
        posted_delta=None,
    )
    line.expected_quantity = await _current_quantity(
        session, tenant_id=tenant_id, line=line, lock=False
    )
    expected = int(line.expected_quantity)
    session.add(line)
    try:
        await session.commit()
    except IntegrityError:
        # Гонка с параллельным добавлением той же строки (сканом или тоже
        # руками): уникальный индекс сработал — прибавляем к уже созданной,
        # а не роняем оператора пятисоткой.
        await session.rollback()
        return await _increment_existing_found_line(
            session,
            tenant_id,
            count_id,
            product_id=product.id,
            storage_location_id=storage_location_id,
            container_kind=container_kind,
            container_id=container_id,
            amount=quantity,
        )
    loaded = await get_count(session, tenant_id, count_id)
    assert loaded is not None
    return FoundResult(loaded, expected, _found_notice(expected))


def _remember_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    line_id: uuid.UUID,
    scan_id: str | None,
    expected_quantity: int,
) -> None:
    """Запоминает скан, чтобы его повтор не прибавил вторую штуку."""
    if not scan_id:
        return
    session.add(
        InventoryCountFoundScan(
            tenant_id=tenant_id,
            count_id=count_id,
            line_id=line_id,
            scan_id=scan_id,
            expected_quantity=expected_quantity,
        )
    )


async def _resolve_found_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count: InventoryCount,
    *,
    cell_id: uuid.UUID | None,
    container_kind: str | None,
    container_id: uuid.UUID | None,
) -> uuid.UUID:
    """Определяет адрес находки. Угадывать его на экране нельзя.

    Модель сканера у оператора простая: он пикает МЕСТО, а не адрес. Место —
    это либо тара, либо ячейка, либо ничего. Адрес из места выводит сервер:

    * пикнули тару — адрес берём из карточки самой тары; палета или грузоместо
      могут стоять без ячейки, и это нормальное состояние, а не ошибка: тогда
      адресом становится зона сортировки;
    * пикнули ячейку — она и есть адрес;
    * не пикнули ничего — россыпь без ячейки, то есть та же зона сортировки.

    Раньше адрес считал экран, и на двух этих случаях он присылал строку
    «unassigned» — виртуальную строку дерева, а не ячейку, — и находка падала.
    """
    if (container_kind is None) != (container_id is None):
        raise InventoryCountError("container_reference_invalid")

    warehouse_id = count.warehouse_id
    if warehouse_id is None:
        raise InventoryCountError("warehouse_required_without_address_storage")

    if container_kind is not None and container_id is not None:
        # ⛔ Не писать здесь свой поиск «где стоит эта тара».
        #
        # Он уже есть один на всю систему и знает то, чего не видно с первого
        # взгляда: у короба, положенного на палету, собственная ячейка
        # обнуляется и остаётся только ссылка на палету; приёмочные короба и
        # грузоместа живут в отдельных таблицах; если ничего не проставлено,
        # адрес берётся из фактического остатка этой тары. Своя короткая
        # версия этой функции возвращала «ячейки нет» и уводила находку в зону
        # сортировки — а оттуда товар уходит в кабинет продавца как доступный к
        # продаже, но подобрать его под отгрузку уже нельзя.
        #
        # Проверку тары resolve_container_location делает сам.
        from app.services.warehouse_map_service import resolve_container_location

        try:
            return await resolve_container_location(
                session,
                tenant_id,
                warehouse_id,
                cast(ContainerKind, container_kind),
                container_id,
            )
        except ValueError as exc:
            raise InventoryCountError("container_not_found") from exc

    if cell_id is not None:
        location = await session.get(StorageLocation, cell_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.deleted_at is not None
            or location.warehouse_id != warehouse_id
        ):
            raise InventoryCountError("storage_location_not_found")
        return location.id

    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
    return sorting.id


async def _increment_existing_found_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    container_kind: str | None,
    container_id: uuid.UUID | None,
    amount: int = 1,
) -> FoundResult:
    line = await session.scalar(
        select(InventoryCountLine)
        .where(
            InventoryCountLine.count_id == count_id,
            InventoryCountLine.product_id == product_id,
            InventoryCountLine.storage_location_id == storage_location_id,
            InventoryCountLine.container_kind == container_kind,
            InventoryCountLine.container_id == container_id,
        )
        .with_for_update()
    )
    if line is None:
        raise InventoryCountError("count_not_found")
    line.actual_quantity = int(line.actual_quantity or 0) + amount
    expected = int(line.expected_quantity)
    await session.commit()
    loaded = await get_count(session, tenant_id, count_id)
    assert loaded is not None
    return FoundResult(loaded, expected, _found_notice(expected))


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
    """Сколько числится сейчас по каждой строке документа.

    Раньше здесь был запрос на каждую строку. Документ на тысячу строк давал
    тысячу запросов, и это выполнялось на каждой отдаче документа — то есть на
    каждом сохранении и на каждой находке. Кладовщик сканирует непрерывно, и
    ждать он не должен. Теперь весь остаток по местам документа поднимается
    одним запросом, а строки разбираются по нему в памяти.
    """
    values: dict[uuid.UUID, int] = {}
    pending = [
        line
        for line in count.lines
        if not (count.status == STATUS_POSTED and line.actual_quantity is not None)
    ]
    for line in count.lines:
        if count.status == STATUS_POSTED and line.actual_quantity is not None:
            values[line.id] = int(line.actual_quantity) - int(line.posted_delta or 0)

    if not pending:
        return values

    location_ids = {
        line.storage_location_id for line in pending if line.storage_location_id is not None
    }
    product_ids = {line.product_id for line in pending}
    balances: dict[
        tuple[uuid.UUID, uuid.UUID, str | None, uuid.UUID | None], int
    ] = {}
    if location_ids and product_ids:
        rows = await session.execute(
            select(
                InventoryBalance.product_id,
                InventoryBalance.storage_location_id,
                InventoryBalance.container_kind,
                InventoryBalance.container_id,
                InventoryBalance.quantity,
            ).where(
                InventoryBalance.tenant_id == count.tenant_id,
                InventoryBalance.storage_location_id.in_(location_ids),
                InventoryBalance.product_id.in_(product_ids),
            )
        )
        for product_id, location_id, kind, container_id, quantity in rows:
            balances[(product_id, location_id, kind, container_id)] = int(quantity or 0)

    for line in pending:
        if line.storage_location_id is None:
            raise InventoryCountError("line_storage_location_missing")
        values[line.id] = balances.get(
            (
                line.product_id,
                line.storage_location_id,
                line.container_kind,
                line.container_id,
            ),
            0,
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


async def product_photos(
    session: AsyncSession,
    products: list[Product],
) -> dict[uuid.UUID, str | None]:
    """Снимок товара для печатной описи тары.

    Своей картинки у товара в WMS нет — она живёт в импортированной карточке WB,
    ровно там же, откуда её берёт рабочий список ФБС. Одним запросом на весь
    документ: пересчёт по складу — это сотни строк, и запрос на каждую убил бы
    отдачу документа, которая случается на каждом скане.
    """
    result: dict[uuid.UUID, str | None] = {product.id: None for product in products}
    pairs = {
        (product.seller_id, product.wb_nm_id)
        for product in products
        if product.seller_id is not None and product.wb_nm_id is not None
    }
    if not pairs:
        return result
    rows = await session.execute(
        select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.tenant_id == products[0].tenant_id,
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
        (card.seller_id, card.nm_id): first_photo_url_from_card(card.raw_json or {})
        for card in rows.scalars()
    }
    for product in products:
        seller_id = product.seller_id
        nm_id = product.wb_nm_id
        if seller_id is not None and nm_id is not None:
            result[product.id] = by_pair.get((seller_id, nm_id))
    return result


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
