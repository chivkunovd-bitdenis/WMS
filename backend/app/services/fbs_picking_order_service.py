"""One deterministic order for the FBS picking list and full sticker tape."""

from __future__ import annotations

import uuid

from app.models.fbs_order import FbsOrder

PickingListGroupKey = tuple[str, str | None, str | None, str]
PickingListGroupSortKey = tuple[str, str, str, str]


def picking_list_group_key(order: FbsOrder) -> PickingListGroupKey:
    product = order.product
    article = order.wb_article or (product.sku_code if product is not None else "") or ""
    sku_code = product.sku_code if product is not None else None
    size = product.wb_size if product is not None and product.wb_size else None
    product_name = product.name if product is not None else (order.wb_article or "Unknown")
    return article, sku_code, size, product_name


def picking_list_group_sort_key(key: PickingListGroupKey) -> PickingListGroupSortKey:
    article, sku_code, size, product_name = key
    return article, sku_code or "", size or "", product_name


def picking_list_order_key(order: FbsOrder) -> tuple[PickingListGroupSortKey, int, uuid.UUID]:
    return (
        picking_list_group_sort_key(picking_list_group_key(order)),
        int(order.wb_order_id),
        order.id,
    )
