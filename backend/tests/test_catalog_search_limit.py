# ruff: noqa: RUF002, RUF003
"""Каталог селлера ищет и ограничивает выборку в БД, а не в памяти."""

from __future__ import annotations

import inspect

from app.api.products import get_seller_wb_catalog
from app.services.catalog_service import list_products
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows


def test_route_has_search_and_limit() -> None:
    """Без потолка ответ по крупному селлеру весил 6 МБ и строился 12 секунд."""
    params = inspect.signature(get_seller_wb_catalog).parameters
    assert "search" in params
    assert "limit" in params
    limit_default = params["limit"].default
    # у Annotated[int, Query(...)] значение лежит либо в самом default,
    # либо в Query-объекте — проверяем оба вида
    value = getattr(limit_default, "default", limit_default)
    assert value == 500


def test_service_passes_filters_down() -> None:
    for fn in (list_seller_wb_catalog_rows, list_products):
        params = inspect.signature(fn).parameters
        assert "search" in params, fn.__name__
        assert "limit" in params, fn.__name__


def test_list_products_filters_in_sql() -> None:
    """Фильтр должен попадать в запрос: иначе БД снова вернёт весь каталог."""
    src = inspect.getsource(list_products)
    assert "ilike" in src
    assert "stmt.limit" in src
