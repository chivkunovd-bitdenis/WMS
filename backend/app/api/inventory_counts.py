from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ff_permission
from app.db.session import get_db
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.user import User
from app.services import inventory_count_service as service
from app.services import tenant_settings_service, warehouse_map_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE, UNASSIGNED_LABEL
from app.services.staff_permissions_service import PERM_INVENTORY

router = APIRouter(prefix="/operations/inventory-counts", tags=["operations"])
require_inventory_access = require_ff_permission(PERM_INVENTORY)


class InventoryCountObjectIn(BaseModel):
    type: Literal[
        "product",
        "storage_location",
        "location",
        "cell",
        "pallet",
        "box",
        "cargo_place",
    ]
    id: uuid.UUID
    storage_location_id: uuid.UUID | None = None


class InventoryCountFiltersIn(BaseModel):
    seller_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=255)
    warehouse_id: uuid.UUID | None = None
    all: bool = False


class InventoryCountCreateIn(BaseModel):
    source: Literal["object", "planned"]
    object: InventoryCountObjectIn | None = None
    filters: InventoryCountFiltersIn | None = None
    comment: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_source_payload(self) -> InventoryCountCreateIn:
        if self.source == "object" and (self.object is None or self.filters is not None):
            raise ValueError("object_source_requires_object_only")
        if self.source == "planned" and (self.filters is None or self.object is not None):
            raise ValueError("planned_source_requires_filters_only")
        return self


class InventoryCountActualIn(BaseModel):
    line_id: uuid.UUID
    actual_quantity: int | None = Field(default=None, ge=0, le=1_000_000_000)


class InventoryCountActualBatchIn(BaseModel):
    lines: list[InventoryCountActualIn]


class InventoryCountFoundIn(BaseModel):
    """Находка: товар лежит там, где по учёту его нет."""

    # Экран присылает все прочтения кода: как пришло со сканера и как это
    # выглядело бы в латинской раскладке. Иначе товар, который экран только что
    # нашёл переводом раскладки, сервер не находил, и оператор видел зелёное
    # «записываем» рядом с красным «товар не найден».
    barcodes: list[str] = Field(min_length=1, max_length=4)
    # Экран говорит, что ОТКРЫТО у сканера, а не куда писать: тара, ячейка или
    # ничего. Адрес из этого выводит сервер — палета может стоять без ячейки, и
    # знать об этом карточке тары, а не экрану.
    cell_id: uuid.UUID | None = None
    container_kind: Literal["pallet", "box", "cargo_place"] | None = None
    container_id: uuid.UUID | None = None
    # Идентификатор скана: экран генерирует его один раз на пик. Повтор того же
    # скана (оборвался вайфай, оператор пикнул ещё раз) ничего не прибавляет.
    scan_id: str | None = Field(default=None, max_length=64)


class CountFillOut(BaseModel):
    mode: Literal["object", "all", "filters"]
    seller_id: str | None = None
    category: str | None = None
    object_label: str | None = None


class CountProductNodeOut(BaseModel):
    kind: Literal["product"] = "product"
    id: str
    product_id: str
    name: str
    sku: str
    seller: str
    seller_id: str | None = None
    category: str | None = None
    barcode: str | None = None
    wb_vendor_code: str | None = None
    wb_barcode: str | None = None
    wb_size: str | None = None
    photo_url: str | None = None
    expected: int
    actual: int | None
    expected_now: int | None = None


class CountContainerNodeOut(BaseModel):
    kind: Literal["pallet", "box", "cargo_place"]
    id: str
    code: str
    barcode: str | None = None
    children: list[CountProductNodeOut | CountContainerNodeOut]


class CountScannableCellOut(BaseModel):
    """Ячейка склада, которую сканер обязан узнать, даже если она пуста."""

    id: str
    label: str
    barcode: str | None


class CountCellOut(BaseModel):
    id: str
    label: str
    barcode: str | None = Field(default=None, exclude_if=lambda value: value is None)
    children: list[CountProductNodeOut | CountContainerNodeOut]


class InventoryCountLineOut(BaseModel):
    id: str
    product_id: str
    storage_location_id: str | None
    storage_location_code: str | None
    container_kind: str | None
    container_id: str | None
    product_name: str
    sku_code: str
    seller_id: str | None
    seller_name: str | None
    category: str | None
    barcode: str | None
    wb_vendor_code: str | None
    wb_barcode: str | None
    wb_size: str | None
    expected_quantity: int
    current_quantity: int
    actual_quantity: int | None
    posted_delta: int | None
    balance_changed: bool


class InventoryCountSummaryOut(BaseModel):
    id: str
    number: str
    status: str
    source: str
    warehouse_id: str | None
    warehouse_name: str
    seller_id: str | None
    category: str | None
    fill: CountFillOut
    fill_label: str
    created_at: str
    created_by: str
    lines: int
    counted: int
    discrepancies: int
    surplus: int
    shortage: int


class InventoryCountDetailOut(BaseModel):
    id: str
    number: str
    status: str
    source: str
    warehouse_id: str | None
    warehouse_name: str
    seller_id: str | None
    category: str | None
    fill: CountFillOut
    created_at: str
    created_by: str
    posted_at: str | None
    posted_by: str | None
    comment: str
    address_storage: bool
    lines: list[InventoryCountLineOut]
    cells: list[CountCellOut]
    # Ячейки склада, которые сканер обязан узнавать, включая пустые по учёту.
    # В дерево они не попадают, иначе документ распухнет пустыми строками.
    scannable_cells: list[CountScannableCellOut] = []


class ChangedBalanceOut(BaseModel):
    line_id: str
    product_id: str
    storage_location_id: str | None
    expected_quantity: int
    current_quantity: int


class InventoryCountPostOut(BaseModel):
    id: str
    status: str
    posted_lines: int
    unchanged_lines: int
    changed_balance_count: int
    changed_balances: list[ChangedBalanceOut]


def _number(count: InventoryCount) -> str:
    return f"ИНВ-{str(count.id).split('-')[0].upper()}"


def _fill(count: InventoryCount) -> tuple[CountFillOut, str]:
    if count.source == service.SOURCE_OBJECT:
        return CountFillOut(mode="object", object_label="По объекту"), "По объекту"
    if count.seller_id is None and count.category is None:
        return CountFillOut(mode="all"), "Весь склад"
    parts = [count.seller.name if count.seller is not None else None, count.category]
    label = ", ".join(part for part in parts if part)
    return (
        CountFillOut(
            mode="filters",
            seller_id=str(count.seller_id) if count.seller_id is not None else None,
            category=count.category,
        ),
        label or "По фильтрам",
    )


async def _categories(
    session: AsyncSession,
    count: InventoryCount,
) -> dict[uuid.UUID, str | None]:
    unique = {line.product.id: line.product for line in count.lines}
    return await service.product_categories(session, list(unique.values()))


async def _summary_out(
    session: AsyncSession,
    count: InventoryCount,
) -> InventoryCountSummaryOut:
    current = await service.current_quantities(session, count)
    counted = 0
    discrepancies = 0
    surplus = 0
    shortage = 0
    for line in count.lines:
        if line.actual_quantity is None:
            continue
        counted += 1
        delta = int(line.actual_quantity) - current[line.id]
        if delta == 0:
            continue
        discrepancies += 1
        if delta > 0:
            surplus += delta
        else:
            shortage += -delta
    fill, fill_label = _fill(count)
    return InventoryCountSummaryOut(
        id=str(count.id),
        number=_number(count),
        status=count.status,
        source=count.source,
        warehouse_id=str(count.warehouse_id) if count.warehouse_id is not None else None,
        warehouse_name=count.warehouse.name if count.warehouse is not None else "Все склады",
        seller_id=str(count.seller_id) if count.seller_id is not None else None,
        category=count.category,
        fill=fill,
        fill_label=fill_label,
        created_at=count.created_at.isoformat(),
        created_by=count.created_by.email,
        lines=len(count.lines),
        counted=counted,
        discrepancies=discrepancies,
        surplus=surplus,
        shortage=shortage,
    )


def _product_node(
    line: InventoryCountLine,
    *,
    category: str | None,
    current_quantity: int,
) -> CountProductNodeOut:
    product = line.product
    expected_now = current_quantity if current_quantity != line.expected_quantity else None
    return CountProductNodeOut(
        id=str(line.id),
        product_id=str(product.id),
        name=product.name,
        sku=product.sku_code,
        seller=product.seller.name if product.seller is not None else "Без селлера",
        seller_id=str(product.seller_id) if product.seller_id is not None else None,
        category=category,
        barcode=product.wb_barcode,
        wb_vendor_code=product.wb_vendor_code,
        wb_barcode=product.wb_barcode,
        wb_size=product.wb_size,
        expected=int(line.expected_quantity),
        actual=int(line.actual_quantity) if line.actual_quantity is not None else None,
        expected_now=expected_now,
    )


def _container_tree(
    rows: list[dict[str, Any]],
    containers: dict[tuple[str, str], CountContainerNodeOut],
) -> list[CountProductNodeOut | CountContainerNodeOut]:
    result: list[CountProductNodeOut | CountContainerNodeOut] = []
    for row in rows:
        kind = row.get("kind")
        if kind not in {"pallet", "box", "cargo_place"}:
            continue
        node = CountContainerNodeOut(
            kind=kind,
            id=str(row["id"]),
            code=str(row["code"]),
            barcode=str(row["barcode"]) if row.get("barcode") is not None else None,
            children=_container_tree(row.get("children", []), containers),
        )
        containers[(kind, node.id)] = node
        result.append(node)
    return result


async def _detail_out(
    session: AsyncSession,
    count: InventoryCount,
) -> InventoryCountDetailOut:
    address_storage = await tenant_settings_service.is_address_storage_enabled(
        session, count.tenant_id
    )
    current = await service.current_quantities(session, count)
    categories = await _categories(session, count)
    line_rows: list[InventoryCountLineOut] = []
    # Пустой список — нормальное значение: без адресного хранения ячеек нет.
    scannable_cells: list[CountScannableCellOut] = []
    nodes_by_cell: dict[
        tuple[str, str], list[CountProductNodeOut | CountContainerNodeOut]
    ] = defaultdict(list)
    no_address_nodes: list[CountProductNodeOut | CountContainerNodeOut] = []
    containers: dict[tuple[str, str], CountContainerNodeOut] = {}
    cells_by_id: dict[str, CountCellOut] = {}
    unassigned: CountCellOut | None = None
    if count.warehouse_id is not None:
        warehouse_map = await warehouse_map_service.get_warehouse_map(
            session,
            count.tenant_id,
            count.warehouse_id,
        )
        unassigned = CountCellOut(
            id="unassigned",
            label=UNASSIGNED_LABEL if address_storage else "",
            barcode=None,
            children=_container_tree(warehouse_map["unassigned"], containers),
        )
        for map_cell in warehouse_map["cells"]:
            cell = CountCellOut(
                id=str(map_cell["id"]),
                label=str(map_cell["code"]),
                barcode=(
                    str(map_cell["barcode"])
                    if map_cell.get("barcode") is not None
                    else None
                ),
                children=_container_tree(map_cell["children"], containers),
            )
            cells_by_id[cell.id] = cell
    for line in count.lines:
        product = line.product
        location = line.storage_location
        category = categories.get(product.id)
        node = _product_node(
            line,
            category=category,
            current_quantity=current[line.id],
        )
        container = (
            containers.get((line.container_kind, str(line.container_id)))
            if line.container_kind is not None and line.container_id is not None
            else None
        )
        if container is not None:
            container.children.append(node)
        elif address_storage and location is not None:
            label = (
                UNASSIGNED_LABEL
                if location.code == SORTING_LOCATION_CODE
                else location.code
            )
            if location.code == SORTING_LOCATION_CODE and unassigned is not None:
                unassigned.children.append(node)
            elif str(location.id) in cells_by_id:
                cells_by_id[str(location.id)].children.append(node)
            else:
                nodes_by_cell[(str(location.id), label)].append(node)
        else:
            if unassigned is not None:
                unassigned.children.append(node)
            else:
                no_address_nodes.append(node)
        line_rows.append(
            InventoryCountLineOut(
                id=str(line.id),
                product_id=str(line.product_id),
                storage_location_id=(
                    str(line.storage_location_id)
                    if address_storage and line.storage_location_id is not None
                    else None
                ),
                storage_location_code=(
                    location.code if address_storage and location is not None else None
                ),
                container_kind=line.container_kind,
                container_id=str(line.container_id) if line.container_id is not None else None,
                product_name=product.name,
                sku_code=product.sku_code,
                seller_id=str(product.seller_id) if product.seller_id is not None else None,
                seller_name=product.seller.name if product.seller is not None else None,
                category=category,
                barcode=product.wb_barcode,
                wb_vendor_code=product.wb_vendor_code,
                wb_barcode=product.wb_barcode,
                wb_size=product.wb_size,
                expected_quantity=int(line.expected_quantity),
                current_quantity=current[line.id],
                actual_quantity=(
                    int(line.actual_quantity) if line.actual_quantity is not None else None
                ),
                posted_delta=int(line.posted_delta) if line.posted_delta is not None else None,
                balance_changed=current[line.id] != line.expected_quantity,
            )
        )
    if address_storage:
        fallback_cells = [
            CountCellOut(id=cell_id, label=label, barcode=None, children=children)
            for (cell_id, label), children in sorted(
                nodes_by_cell.items(), key=lambda item: item[0][1]
            )
        ]
        cells = [
            *([unassigned] if unassigned is not None and unassigned.children else []),
            *[
                cell
                for cell in cells_by_id.values()
                if cell.children
            ],
            *fallback_cells,
        ]
        # ⛔ Пустые по учёту ячейки в дерево не тащим — иначе документ по складу
        # распухнет сотнями пустых строк. Но сканер обязан их узнавать: «в
        # ячейке лежит то, чего по учёту тут нет» — это первый и главный случай,
        # ради которого пересчёт и делают. Раньше штрихкод такой ячейки сканер
        # не знал, уходил искать товар, не находил и предлагал записать находку
        # со штрихкодом ЯЧЕЙКИ вместо товара.
        scannable_cells = [
            CountScannableCellOut(id=cell.id, label=cell.label, barcode=cell.barcode)
            for cell in cells_by_id.values()
            if cell.barcode
        ]
    else:
        # Frontend flattens children when addressStorage=false and never renders
        # this technical wrapper as a cell.
        cells = [
            CountCellOut(
                id="inventory",
                label="",
                barcode=None,
            children=(unassigned.children if unassigned is not None else no_address_nodes),
            )
        ]
    fill, _ = _fill(count)
    return InventoryCountDetailOut(
        id=str(count.id),
        number=_number(count),
        status=count.status,
        source=count.source,
        warehouse_id=str(count.warehouse_id) if count.warehouse_id is not None else None,
        warehouse_name=count.warehouse.name if count.warehouse is not None else "Все склады",
        seller_id=str(count.seller_id) if count.seller_id is not None else None,
        category=count.category,
        fill=fill,
        created_at=count.created_at.isoformat(),
        created_by=count.created_by.email,
        posted_at=count.posted_at.isoformat() if count.posted_at is not None else None,
        posted_by=count.posted_by.email if count.posted_by is not None else None,
        comment=count.comment or "",
        address_storage=address_storage,
        lines=line_rows,
        cells=cells,
        scannable_cells=scannable_cells,
    )


def _http_error(exc: service.InventoryCountError) -> HTTPException:
    if exc.code in {
        "not_found",
        "count_not_found",
        "container_not_found",
        "warehouse_required_without_address_storage",
        "line_not_found",
        "seller_not_found",
        "warehouse_not_found",
        "object_not_found",
        "product_not_found",
        "storage_location_not_found",
    }:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code in {
        "not_editable",
        "already_posted",
        "not_cancellable",
        "empty_count",
        "container_has_no_stock",
        "balance_changed_during_post",
        "count_not_editable",
        "barcode_is_ambiguous",
        "container_reference_invalid",
    }:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.code)


@router.get("", response_model=list[InventoryCountSummaryOut])
async def list_inventory_counts(
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    count_status: Annotated[str | None, Query(alias="status")] = None,
    warehouse_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[InventoryCountSummaryOut]:
    rows = await service.list_counts(
        session,
        user.tenant_id,
        status=count_status,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        created_from=created_from,
        created_to=created_to,
    )
    return [await _summary_out(session, count) for count in rows]


@router.post(
    "",
    response_model=InventoryCountDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_inventory_count(
    body: InventoryCountCreateIn,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountDetailOut:
    object_scope = (
        service.CountObject(
            type=body.object.type,
            id=body.object.id,
            storage_location_id=body.object.storage_location_id,
        )
        if body.object is not None
        else None
    )
    filters = (
        service.CountFilters(
            seller_id=body.filters.seller_id,
            category=body.filters.category,
            warehouse_id=body.filters.warehouse_id,
            all=body.filters.all,
        )
        if body.filters is not None
        else None
    )
    try:
        count = await service.create_count(
            session,
            user.tenant_id,
            user.id,
            source=body.source,
            object_scope=object_scope,
            filters=filters,
            comment=body.comment,
        )
    except service.InventoryCountError as exc:
        raise _http_error(exc) from None
    return await _detail_out(session, count)


@router.get("/{count_id}", response_model=InventoryCountDetailOut)
async def get_inventory_count(
    count_id: uuid.UUID,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountDetailOut:
    count = await service.get_count(session, user.tenant_id, count_id)
    if count is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return await _detail_out(session, count)


@router.put("/{count_id}/lines", response_model=InventoryCountDetailOut)
async def save_inventory_count_lines(
    count_id: uuid.UUID,
    body: InventoryCountActualBatchIn,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountDetailOut:
    try:
        count = await service.save_actuals(
            session,
            user.tenant_id,
            count_id,
            [(line.line_id, line.actual_quantity) for line in body.lines],
        )
    except service.InventoryCountError as exc:
        raise _http_error(exc) from None
    return await _detail_out(session, count)


class InventoryCountFoundOut(BaseModel):
    """Документ после записи находки плюс честный текст для оператора."""

    count: InventoryCountDetailOut
    # Сколько числится по учёту в этом месте. Ноль — настоящая находка; больше
    # нуля — строка, выпавшая из отбора документа, и место надо считать целиком.
    expected_quantity: int
    notice: str


@router.post("/{count_id}/found", response_model=InventoryCountFoundOut)
async def record_inventory_count_found(
    count_id: uuid.UUID,
    body: InventoryCountFoundIn,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountFoundOut:
    """Добавляет в пересчёт строку товара, которого в этом месте не числится.

    Ровно тот случай, ради которого пересчёт и делают: оператор сканирует в
    короб то, чего по учёту там нет. Строка появляется со счётом 1, повторный
    скан увеличивает счёт.
    """
    try:
        found = await service.record_found(
            session,
            user.tenant_id,
            count_id,
            barcodes=body.barcodes,
            cell_id=body.cell_id,
            container_kind=body.container_kind,
            container_id=body.container_id,
            scan_id=body.scan_id,
        )
    except service.InventoryCountError as exc:
        raise _http_error(exc) from None
    return InventoryCountFoundOut(
        count=await _detail_out(session, found.count),
        expected_quantity=found.expected_quantity,
        notice=found.notice,
    )


@router.post("/{count_id}/post", response_model=InventoryCountPostOut)
async def post_inventory_count(
    count_id: uuid.UUID,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountPostOut:
    try:
        result = await service.post_count(session, user.tenant_id, count_id, user.id)
    except service.InventoryCountError as exc:
        raise _http_error(exc) from None
    address_storage = await tenant_settings_service.is_address_storage_enabled(
        session, user.tenant_id
    )
    changed = [
        ChangedBalanceOut(
            line_id=str(item.line_id),
            product_id=str(item.product_id),
            storage_location_id=(
                str(item.storage_location_id)
                if address_storage and item.storage_location_id is not None
                else None
            ),
            expected_quantity=item.expected_quantity,
            current_quantity=item.current_quantity,
        )
        for item in result.changed_balances
    ]
    return InventoryCountPostOut(
        id=str(result.count.id),
        status=result.count.status,
        posted_lines=result.posted_lines,
        unchanged_lines=result.unchanged_lines,
        changed_balance_count=len(changed),
        changed_balances=changed,
    )


@router.delete("/{count_id}", response_model=InventoryCountDetailOut)
async def cancel_inventory_count(
    count_id: uuid.UUID,
    user: Annotated[User, Depends(require_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryCountDetailOut:
    try:
        count = await service.cancel_count(session, user.tenant_id, count_id)
    except service.InventoryCountError as exc:
        raise _http_error(exc) from None
    return await _detail_out(session, count)
