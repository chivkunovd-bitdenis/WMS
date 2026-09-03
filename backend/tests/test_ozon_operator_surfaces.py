"""Подписи и границы, которые на озоновской ветке врали оператору.

Ни одна из этих правок не меняет вайлдберрисовский путь: везде либо отдельная
ветка по маркетплейсу, либо запасной вариант, до которого Wildberries не
доходит.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.api.fbs_errors import fbs_error_message
from app.models.fbs_order import FbsOrder
from app.services import fbs_workspace_service as workspace_svc
from app.services.operation_fact_service import normalize_marketplace


def _order(*, marketplace: str, external_order_id: str | None) -> FbsOrder:
    now = datetime.now(UTC)
    return FbsOrder(
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        marketplace=marketplace,
        external_order_id=external_order_id,
        wb_order_id=-3665971690784702775,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )


def test_operator_gate_shows_the_number_a_person_can_find_in_the_cabinet() -> None:
    """У заказа Ozon в `wb_order_id` лежит хеш, а не номер отправления.

    Оператор видел в тексте ворот «Заказ №-3665971690784702775» — число, которого
    нет ни в одном кабинете, и сопоставить его было не с чем.
    """
    ozon = _order(marketplace="ozon", external_order_id="0195832-0021-1")
    assert workspace_svc._order_number(ozon) == "0195832-0021-1"


def test_operator_gate_keeps_the_wb_number_untouched() -> None:
    wb = _order(marketplace="wb", external_order_id=None)
    wb.wb_order_id = 1200123
    assert workspace_svc._order_number(wb) == "1200123"


def test_ozon_error_code_has_a_human_fallback_like_the_wb_one() -> None:
    """Запасной текст был только у вайлдберрисовских кодов."""
    assert fbs_error_message("wb_something_new") == "Ошибка Wildberries."
    assert fbs_error_message("ozon_ship_unconfirmed") == "Ошибка Ozon."
    # Явное сообщение всегда важнее запасного.
    assert fbs_error_message("ozon_ship_unconfirmed", "Ozon не подтвердил сборку.") == (
        "Ozon не подтвердил сборку."
    )


def test_marketplace_dictionary_is_one_at_the_fact_boundary() -> None:
    """Приёмка писала `wildberries`, заказы и поставки — `wb`, в одну колонку."""
    assert normalize_marketplace("wildberries") == "wb"
    assert normalize_marketplace("wb") == "wb"
    assert normalize_marketplace("ozon") == "ozon"
    assert normalize_marketplace(None) is None
    assert normalize_marketplace("  ") is None
