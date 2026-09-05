"""Read-only отчёт «приход/расход по товару» поверх журнала inventory_movements.

Ничего не пересчитывает и не пишет: только группирует уже существующие записи
InventoryMovement по товару и по человеко-понятной категории движения за период.
Расхождение между суммой движений и фактическим остатком — сигнал для
расследования, не повод подгонять цифры здесь.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import (
    MOVEMENT_TYPE_DISCREPANCY_ACT,
    MOVEMENT_TYPE_FBS_SHIPMENT,
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
    MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
    MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.services.wb_card_enrichment import first_photo_url_from_card

# Технические raw-строки movement_type, которые не заведены как модульные константы
# (см. app/services/fbs_picking_service.py: scan_pick_product / undo_pick) — сборка
# FBS-заказа физически перекладывает товар в ячейку сортировки под упаковку.
_FBS_ORDER_PICK = "fbs_order_pick"
_FBS_ORDER_PICK_UNDO = "fbs_order_pick_undo"

# Группировка технических movement_type в человеко-понятные категории отчёта.
# Один и тот же тип может давать и приход, и расход (например сторно приёмки) —
# это осознанно остаётся в одной группе, чтобы отчёт показывал реальную картину,
# не скрывал отмены и реверсы.
_GROUP_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("intake", "Приёмка", (MOVEMENT_TYPE_INBOUND_INTAKE,)),
    (
        "transfer",
        "Перемещение",
        (MOVEMENT_TYPE_STOCK_TRANSFER_IN, MOVEMENT_TYPE_STOCK_TRANSFER_OUT),
    ),
    ("tz_import", "Загрузка ТЗ", (MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,)),
    ("mp_unload", "Отгрузка на МП", (MOVEMENT_TYPE_MARKETPLACE_UNLOAD,)),
    (
        "fbs",
        "FBS",
        (MOVEMENT_TYPE_FBS_SHIPMENT, _FBS_ORDER_PICK, _FBS_ORDER_PICK_UNDO),
    ),
    ("outbound_shipment", "Отгрузка", (MOVEMENT_TYPE_OUTBOUND_SHIPMENT,)),
    (
        "discrepancy",
        "Корректировка по акту расхождений",
        (MOVEMENT_TYPE_DISCREPANCY_ACT,),
    ),
)
_OTHER_GROUP_KEY = "other"
_OTHER_GROUP_LABEL = "Прочее"

_TYPE_TO_GROUP: dict[str, str] = {
    mtype: key for key, _label, mtypes in _GROUP_DEFS for mtype in mtypes
}
REPORT_MOVEMENT_TYPE_GROUPS: dict[str, str] = dict(_TYPE_TO_GROUP)
_GROUP_LABELS: dict[str, str] = {key: label for key, label, _ in _GROUP_DEFS}

#: Порядок колонок отчёта — стабильный, чтобы фронт мог рендерить фиксированную
#: сетку колонок независимо от того, какие типы встретились в конкретной выборке.
REPORT_GROUP_ORDER: tuple[str, ...] = (
    *(key for key, _l, _t in _GROUP_DEFS),
    _OTHER_GROUP_KEY,
)
REPORT_GROUP_LABELS: dict[str, str] = {**_GROUP_LABELS, _OTHER_GROUP_KEY: _OTHER_GROUP_LABEL}


def movement_group_label(movement_type: str) -> str:
    key = _TYPE_TO_GROUP.get(movement_type, _OTHER_GROUP_KEY)
    return REPORT_GROUP_LABELS[key]


@dataclass
class ProductMovementSummaryRow:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    wb_vendor_code: str | None
    wb_barcode: str | None
    seller_id: uuid.UUID | None
    seller_name: str | None
    photo_url: str | None = None
    groups: dict[str, tuple[int, int]] = field(default_factory=dict)  # key -> (in, out)

    @property
    def total_in(self) -> int:
        return sum(v[0] for v in self.groups.values())

    @property
    def total_out(self) -> int:
        return sum(v[1] for v in self.groups.values())

    @property
    def net(self) -> int:
        return self.total_in - self.total_out


async def list_product_movement_summary(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
) -> list[ProductMovementSummaryRow]:
    """Сводка приход/расход по товару за период, сгруппированная по смыслу движения.

    Читает только InventoryMovement + Product/Seller (join). Ничего не изменяет и
    не пересчитывает остатки — сырые суммы delta по типам движений за период.
    """
    in_qty = func.coalesce(
        func.sum(
            case((InventoryMovement.quantity_delta > 0, InventoryMovement.quantity_delta), else_=0)
        ),
        0,
    )
    out_qty = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.quantity_delta < 0, -InventoryMovement.quantity_delta),
                else_=0,
            )
        ),
        0,
    )

    stmt = (
        select(
            Product.id,
            Product.sku_code,
            Product.name,
            Product.wb_vendor_code,
            Product.wb_barcode,
            Product.wb_nm_id,
            Product.seller_id,
            Seller.name,
            InventoryMovement.movement_type,
            in_qty,
            out_qty,
        )
        .select_from(InventoryMovement)
        .join(Product, Product.id == InventoryMovement.product_id)
        .outerjoin(Seller, Seller.id == Product.seller_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at < date_to,
        )
        .group_by(
            Product.id,
            Product.sku_code,
            Product.name,
            Product.wb_vendor_code,
            Product.wb_barcode,
            Product.wb_nm_id,
            Product.seller_id,
            Seller.name,
            InventoryMovement.movement_type,
        )
        .order_by(Product.sku_code)
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    if warehouse_id is not None:
        stmt = stmt.join(
            StorageLocation, StorageLocation.id == InventoryMovement.storage_location_id
        ).where(StorageLocation.warehouse_id == warehouse_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(pattern),
                Product.sku_code.ilike(pattern),
                Product.wb_vendor_code.ilike(pattern),
                Product.wb_barcode.ilike(pattern),
            )
        )

    res = await session.execute(stmt)
    rows_by_product: dict[uuid.UUID, ProductMovementSummaryRow] = {}
    order: list[uuid.UUID] = []
    nm_by_product: dict[uuid.UUID, int | None] = {}
    for (
        pid,
        sku_code,
        name,
        vendor_code,
        barcode,
        nm_id,
        s_id,
        s_name,
        mtype,
        m_in,
        m_out,
    ) in res.all():
        row = rows_by_product.get(pid)
        if row is None:
            row = ProductMovementSummaryRow(
                product_id=pid,
                sku_code=sku_code,
                product_name=name,
                wb_vendor_code=vendor_code,
                wb_barcode=barcode,
                seller_id=s_id,
                seller_name=s_name,
            )
            rows_by_product[pid] = row
            order.append(pid)
            nm_by_product[pid] = nm_id
        group_key = _TYPE_TO_GROUP.get(mtype, _OTHER_GROUP_KEY)
        prev_in, prev_out = row.groups.get(group_key, (0, 0))
        row.groups[group_key] = (prev_in + int(m_in), prev_out + int(m_out))

    if not order:
        return []

    seller_nm_by_product = {
        pid: (rows_by_product[pid].seller_id, nm_by_product[pid]) for pid in order
    }
    photo_by_product = await load_report_photo_urls(session, tenant_id, seller_nm_by_product)
    for pid, row in rows_by_product.items():
        row.photo_url = photo_by_product.get(pid)

    return [rows_by_product[pid] for pid in order]


async def load_report_photo_urls(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_nm_by_product: dict[uuid.UUID, tuple[uuid.UUID | None, int | None]],
) -> dict[uuid.UUID, str | None]:
    """Первое фото карточки маркетплейса для товаров, привязанных к продавцу и карточке.

    Лёгкая версия обогащения, без sync-состояния FBS, которое отчёту не нужно.
    Полная версия: app/services/seller_wb_catalog_service.py.
    """
    # Функции нужны заполненные seller_id и nm_id у товара.
    seller_ids = {
        sid for sid, nm in seller_nm_by_product.values() if sid is not None and nm is not None
    }
    if not seller_ids:
        return {}
    card_stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id.in_(seller_ids),
    )
    res = await session.execute(card_stmt)
    by_seller_nm: dict[tuple[uuid.UUID, int], dict[str, Any]] = {}
    for card in res.scalars().all():
        if isinstance(card.raw_json, dict):
            by_seller_nm[(card.seller_id, int(card.nm_id))] = card.raw_json

    out: dict[uuid.UUID, str | None] = {}
    for pid, (sid, nm) in seller_nm_by_product.items():
        if sid is None or nm is None:
            continue
        card_raw = by_seller_nm.get((sid, nm))
        if card_raw is not None:
            out[pid] = first_photo_url_from_card(card_raw)
    return out
