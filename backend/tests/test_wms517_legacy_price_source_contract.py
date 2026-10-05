"""Analyst-authorized R22 source migration: valid sale survives bad legacy price."""

import uuid

import pytest
from sqlalchemy import delete
from test_withdrawal_ledger import (
    legacy_sales_http,  # noqa: F401 -- exact same isolated HTTP boundary
    seed,
)

from app.db.session import SessionLocal
from app.db.withdrawal_repository import current_items, registry
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot
from app.services.wb_order_price_service import capture_wb_price_snapshot
from app.services.withdrawal_service import create_operation

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("legacy", ["missing", "bad_currency"])
async def test_valid_sale_is_not_blocked_by_missing_or_bad_legacy_snapshot(db_session, legacy):
    scope, marking, order, _ = await seed(db_session)
    if legacy == "missing":
        # Delete only generated fixture observations before creating any items.
        await db_session.execute(delete(WbOrderPriceSnapshot).where(
            WbOrderPriceSnapshot.order_id == order.id,
        ))
    else:
        await capture_wb_price_snapshot(
            db_session, tenant_id=scope.tenant_id, seller_id=scope.seller_id,
            order_id=order.id, row={"finalPrice": 100, "currencyCode": 840},
        )
    await db_session.commit()
    rows, total = await registry(db_session, scope)
    assert total == 1 and rows[0]["row_id"] == marking.id
    assert rows[0]["status"] == "not_withdrawn" and rows[0]["error"] is None
    operation = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4(),
    )
    await db_session.commit()
    async with SessionLocal() as reader:
        items = await current_items(reader, scope, operation.id)
        assert len(items) == 1 and items[0].state == "pending"
        assert items[0].product_cost == 99999999999999999
        evidence = items[0].preflight_evidence["wb_sale"]
        assert evidence["source"] == "/api/v1/supplier/sales"
        assert evidence["order_id"] == str(order.id) and evidence["srid"] == order.wb_rid
        assert evidence["finishedPrice"] == "999999999999999.99"
        assert evidence["complete"] is True
