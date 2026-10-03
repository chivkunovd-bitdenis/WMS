"""G-STOCK-7: imports, cancellation and sale cannot spend operator caps."""

import pytest
from sqlalchemy import select

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.services.fbs_cancellation_service import _finish_local_cancellation
from app.services.fbs_stock_rule_service import FbsRule, set_rule_for_products
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    upsert_order_from_wb_row,
)
from tests.guards.stock_helpers import check
from tests.test_fbs_stock_rule_service import _seed


@pytest.mark.asyncio
async def test_g_stock_7_order_lifecycle_does_not_spend_operator_limit(db_session, monkeypatch):
    """G-STOCK-7 · WMS-632 · решение владельца 02.10.2026:
    «Лимит меняет только оператор; продажи не расходуют его отдельным журналом».
    """
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish", lambda *_: None
    )
    seed = await _seed(db_session, on_hand=12)
    await set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        FbsRule(
            publish=True,
            same_everywhere=False,
            percent=0,
            units_mode=True,
            units_by_warehouse={501001: 10},
        ),
    )
    pool = await db_session.scalar(
        select(FbsBindingStockPool).where(FbsBindingStockPool.product_id == seed.product.id)
    )
    check(pool.quantity, 10, "оператор сохранил лимит 10")
    for number, status in [(7654322, "cancelled"), (7654323, "sold")]:
        row = {
            "id": number,
            "rid": f"guard-{number}",
            "createdAt": "2026-10-03T12:00:00Z",
            "chrtId": 777,
            "article": seed.product.sku_code,
            "warehouseId": 501001,
            "skus": [],
            "price": 10000,
            "cargoType": 1,
        }
        for _ in range(2):
            order, _created = await upsert_order_from_wb_row(
                db_session, seed.tenant.id, seed.seller.id, row
            )
            await db_session.flush()
            await db_session.refresh(pool)
            check(pool.quantity, 10, "импорт и повтор не расходуют лимит оператора")
        for _ in range(2):
            if status == "cancelled":
                await _finish_local_cancellation(
                    db_session, seed.tenant.id, order, actor_user_id=None
                )
            else:
                await _apply_wb_status_to_order(db_session, order, "sold", actor_user_id=None)
            await db_session.flush()
            await db_session.refresh(pool)
            check(pool.quantity, 10, f"{status} и повтор не переписывают лимит оператора")
