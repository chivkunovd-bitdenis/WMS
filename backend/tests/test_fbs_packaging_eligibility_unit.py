from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.fbs_order import PICK_STATUS_PICKED
from app.services.fbs_packaging_integration_service import _eligible_orders_for_product


class _ScalarRows:
    def __init__(self, values: list[uuid.UUID]) -> None:
        self._values = values

    def scalars(self) -> list[uuid.UUID]:
        return self._values


@pytest.mark.asyncio
async def test_eligible_orders_loads_active_picks_in_one_query() -> None:
    product_id = uuid.uuid4()
    order_ids = [uuid.uuid4() for _ in range(100)]
    now = datetime.now(UTC)
    orders = [
        SimpleNamespace(
            id=order_id,
            status="new",
            product_id=product_id,
            pick_status=PICK_STATUS_PICKED,
            deadline_at=now,
            created_at_wb=now,
            wb_order_id=index,
        )
        for index, order_id in enumerate(order_ids)
    ]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _ScalarRows([]),
                _ScalarRows(order_ids),
            ]
        )
    )

    eligible = await _eligible_orders_for_product(
        session,
        SimpleNamespace(orders=orders),
        product_id,
    )

    assert [order.id for order in eligible] == order_ids
    assert session.execute.await_count == 2
