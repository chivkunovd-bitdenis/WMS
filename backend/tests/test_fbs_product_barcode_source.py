"""Штрихкод товара на экранах сборки — всегда из карточки WMS, а не из задания WB.

Бой 27.08.2026: на вкладке упаковки печаталась наклейка со штрихкодом 2052614836412,
а на коробке производителя стоял 4630452627195. Оба кода лежат в карточке WB у одной
позиции: первый — внутренний код самого WB (префикс 20…, по GS1 код ограниченного
обращения), второй — настоящий производственный (префикс 463…). WB кладёт в задание
свой внутренний, и печать по нему разводила склад с коробками.

От WB на упаковке нужен только QR стикера заказа. Штрихкод товара — наш.
"""

from __future__ import annotations

import uuid

from app.models.fbs_order import FbsOrder
from app.models.product import Product

WB_INTERNAL_BARCODE = "2052614836412"
PRODUCER_BARCODE = "4630452627195"


def _order(barcode: str | None) -> FbsOrder:
    order = FbsOrder()
    order.id = uuid.uuid4()
    order.wb_barcode = barcode
    return order


def _product(barcode: str | None) -> Product:
    product = Product()
    product.id = uuid.uuid4()
    product.wb_barcode = barcode
    return product


def _worklist_barcode(order: FbsOrder, product: Product | None) -> str | None:
    """Ровно то выражение, что стоит в fbs_worklist_service для блока product."""
    return (product.wb_barcode if product else None) or order.wb_barcode


def test_product_card_barcode_wins_over_wb_order() -> None:
    """У сопоставленного товара печатается код с коробки, а не внутренний код WB."""
    order = _order(WB_INTERNAL_BARCODE)
    product = _product(PRODUCER_BARCODE)
    assert _worklist_barcode(order, product) == PRODUCER_BARCODE


def test_wb_order_barcode_is_fallback_when_product_has_none() -> None:
    """Товар без штрихкода в карточке — лучше показать код задания, чем ничего."""
    order = _order(WB_INTERNAL_BARCODE)
    product = _product(None)
    assert _worklist_barcode(order, product) == WB_INTERNAL_BARCODE


def test_unmapped_order_falls_back_to_wb_barcode() -> None:
    """Заказ без сопоставленного товара — показываем то, что прислал WB."""
    order = _order(WB_INTERNAL_BARCODE)
    assert _worklist_barcode(order, None) == WB_INTERNAL_BARCODE


def test_no_barcode_anywhere_gives_none() -> None:
    order = _order(None)
    product = _product(None)
    assert _worklist_barcode(order, product) is None
