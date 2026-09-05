"""Ручное объединение двух карточек товара в одну (WMS-349).

Зачем это нужно. Один и тот же физический товар живёт в каталоге двумя
карточками: одна приехала из Wildberries, вторая заведена под Ozon. Автосвязка
по артикулу (WMS-344) ловит не всё, и оператору нужен ручной путь: отметил две
карточки галками — объединил.

Как это устроено. Объединение — одна операция, а не состояние. Всё, что
ссылалось на исчезающую карточку, начинает ссылаться на остающуюся; остатки в
одной и той же ячейке складываются; исчезающая карточка удаляется. Признака
«объединена», журнала слияний и обратной операции нет: после вызова в базе
просто одна карточка вместо двух, и разъезжаться нечему.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Column, Table, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.models  # noqa: F401  # регистрирует все таблицы в Base.metadata
from app.models.base import Base
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.product_marketplace_link import ProductMarketplaceLink

# Три таблицы обрабатываются отдельно и потому исключены из общего
# перевешивания ссылок:
#
# * остатки — складываются, а не переносятся строками;
# * привязки к площадкам — переносятся с проверкой, не занята ли площадка;
# * мерки исчезающей карточки не переносим вовсе. У объединённой карточки
#   остаются её собственные габариты и её же история измерений. Перенос сложил
#   бы две истории в одну и упёрся бы в частичные уникальные индексы
#   product_dimension_events (одно применённое измерение на карточку и один
#   отпечаток измерения WB на карточку) — а у двух карточек одного товара
#   габариты, как правило, совпадают до миллиметра.
_HANDLED_SEPARATELY = {
    InventoryBalance.__tablename__,
    ProductDimensionEvent.__tablename__,
    ProductMarketplaceLink.__tablename__,
}

# Пустые поля объединённой карточки заполняем значениями второй — это и есть
# «объединённые данные». Габариты в список не входят: см. комментарий выше.
# Настройки публикации остатка FBS тоже не входят — включать публикацию за
# оператора нельзя.
_FILL_IF_EMPTY = (
    "category",
    "wb_nm_id",
    "wb_vendor_code",
    "wb_chrt_id",
    "wb_barcode",
    "wb_size",
    "wb_country_of_origin",
    "country_of_origin_iso_code",
    "wb_shelf_life",
    "packaging_instructions",
)


class ProductMergeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _product_fk_columns() -> list[tuple[Table, Column[uuid.UUID]]]:
    """Все колонки, ссылающиеся на ``products.id`` — по метаданным, не списком.

    Таких колонок под четыре десятка. Списком его пришлось бы дописывать при
    каждой новой таблице, и ровно один раз это забудут — строки забытой таблицы
    молча уедут по ``ON DELETE CASCADE`` вместе с исчезнувшей карточкой, а
    заметят это через месяц по недостаче. Метаданные знают правду всегда.
    """
    seen: set[tuple[str, str]] = set()
    columns: list[tuple[Table, Column[uuid.UUID]]] = []
    for table in Base.metadata.sorted_tables:
        if table.name in _HANDLED_SEPARATELY:
            continue
        for column in table.columns:
            if not any(fk.target_fullname == "products.id" for fk in column.foreign_keys):
                continue
            key = (table.name, column.name)
            if key in seen:
                continue
            seen.add(key)
            columns.append((table, column))
    return columns


def _has_wb_identity(product: Product) -> bool:
    return (
        product.wb_nm_id is not None
        or bool(product.wb_vendor_code)
        or bool(product.wb_barcode)
    )


def _pick_target(first: Product, second: Product) -> tuple[Product, Product]:
    """Кто остаётся, кто исчезает.

    Остаётся вайлдберрисовская карточка: склад знает товар по её артикулу и
    штрихкоду — они напечатаны на этикетках и по ним ищет ТСД. Озоновская
    сторона живёт отдельной строкой-привязкой, её можно перевесить на любую
    карточку без потерь, поэтому переносить дешевле именно её. Если признак WB
    у обеих или ни у одной — остаётся заведённая раньше.
    """
    if _has_wb_identity(first) != _has_wb_identity(second):
        return (first, second) if _has_wb_identity(first) else (second, first)
    if (first.created_at, str(first.id)) <= (second.created_at, str(second.id)):
        return first, second
    return second, first


async def _sum_inventory_balances(
    session: AsyncSession, target_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """Остатки складываются — решение владельца.

    Ключ — ячейка и контейнер, ровно то, чем уникален остаток
    (``uq_inventory_balance_loc_product_container``). Где остаток есть у обеих
    карточек в одной ячейке, числа суммируются и лишняя строка убирается; где
    ячейка занята только исчезающей карточкой, строка просто меняет владельца.
    Итог по товару поэтому равен сумме двух прежних итогов, ни одна штука не
    теряется.
    """
    target_rows = (
        await session.execute(
            select(InventoryBalance).where(InventoryBalance.product_id == target_id)
        )
    ).scalars().all()
    by_cell = {(row.storage_location_id, row.container_id): row for row in target_rows}

    source_rows = (
        await session.execute(
            select(InventoryBalance).where(InventoryBalance.product_id == source_id)
        )
    ).scalars().all()
    for row in source_rows:
        kept = by_cell.get((row.storage_location_id, row.container_id))
        if kept is None:
            row.product_id = target_id
            continue
        kept.quantity += row.quantity
        kept.quantity_unpacked += row.quantity_unpacked
        kept.quantity_packed += row.quantity_packed
        await session.delete(row)


async def _move_marketplace_links(
    session: AsyncSession, target_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """Привязки к площадкам переезжают на остающуюся карточку.

    Ради этого объединение и затевается: после него у одной карточки есть и
    вайлдберрисовская сторона, и озоновская. Если по одной площадке привязка
    есть у обеих карточек, побеждает привязка остающейся — переносить вторую
    некуда, ключ занят (``uq_product_marketplace_links_product_provider``).
    """
    kept_markets = set(
        (
            await session.execute(
                select(ProductMarketplaceLink.marketplace).where(
                    ProductMarketplaceLink.product_id == target_id
                )
            )
        )
        .scalars()
        .all()
    )
    if kept_markets:
        await session.execute(
            delete(ProductMarketplaceLink).where(
                ProductMarketplaceLink.product_id == source_id,
                ProductMarketplaceLink.marketplace.in_(kept_markets),
            )
        )
    await session.execute(
        update(ProductMarketplaceLink)
        .where(ProductMarketplaceLink.product_id == source_id)
        .values(product_id=target_id)
    )


def _fill_empty_fields(target: Product, source_values: dict[str, object]) -> None:
    for field in _FILL_IF_EMPTY:
        current = getattr(target, field)
        if current is not None and current != "":
            continue
        value = source_values[field]
        if value is None or value == "":
            continue
        setattr(target, field, value)
    # Требование Честного Знака — про сам товар, а не про карточку. Если хотя бы
    # одна из двух его требовала, требует и объединённая.
    if bool(source_values["requires_honest_sign"]):
        target.requires_honest_sign = True


async def merge_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: Sequence[uuid.UUID],
) -> Product:
    """Объединить ровно две карточки. Возвращает ту, что осталась."""
    ids = list(dict.fromkeys(product_ids))
    if len(ids) != 2:
        raise ProductMergeError("merge_needs_exactly_two")

    products = list(
        (
            await session.execute(
                select(Product)
                .options(selectinload(Product.seller))
                .where(Product.tenant_id == tenant_id, Product.id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    if len(products) != 2:
        raise ProductMergeError("product_not_found")
    if products[0].seller_id != products[1].seller_id:
        # Разные продавцы — разные юрлица и разный товар на полке. Объединение
        # переложило бы остаток одного продавца другому.
        raise ProductMergeError("merge_different_sellers")

    target, source = _pick_target(products[0], products[1])
    source_id = source.id
    source_values: dict[str, object] = {
        field: getattr(source, field) for field in _FILL_IF_EMPTY
    }
    source_values["requires_honest_sign"] = source.requires_honest_sign

    try:
        await _sum_inventory_balances(session, target.id, source_id)
        await session.execute(
            delete(ProductDimensionEvent).where(ProductDimensionEvent.product_id == source_id)
        )
        await _move_marketplace_links(session, target.id, source_id)
        for table, column in _product_fk_columns():
            await session.execute(
                update(table).where(column == source_id).values({column.name: target.id})
            )
        await session.flush()
        # Карточка удаляется до заполнения пустых полей: артикул продавца и
        # штрихкод уникальны внутри продавца, и копировать их, пока вторая
        # карточка ещё в базе, значит упереться в собственное ограничение.
        await session.execute(delete(Product).where(Product.id == source_id))
        await session.flush()
        _fill_empty_fields(target, source_values)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ProductMergeError("merge_conflict") from exc

    return target
