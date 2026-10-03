"""G-STOCK-5: reservation is independent of publication."""

import pytest

from app.services.fbs_cancellation_service import _finish_local_cancellation
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from tests.guards.stock_helpers import check, reserved, total
from tests.guards.stock_seeds import _seed


@pytest.mark.asyncio
async def test_g_stock_5_import_reserves_without_publication_and_cancel_releases(db_session):
    """G-STOCK-5 · WMS-632 · решение владельца 02.10.2026:
    «Как только упал заказ на ФБС, заказ в резерве».
    """
    seed = await _seed(db_session, on_hand=12)
    seed.product.fbs_stock_sync_enabled = False
    await db_session.commit()
    row = {
        "id": 7654321,
        "rid": "guard-reserve",
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
        check(
            await reserved(db_session, seed.product.id),
            1,
            "импорт и повтор создают один резерв при выключенной публикации",
        )
        check(
            await total(db_session, seed.product.id), 12, "резерв не списывает физический остаток"
        )
    for _ in range(2):
        await _finish_local_cancellation(db_session, seed.tenant.id, order, actor_user_id=None)
        check(
            await reserved(db_session, seed.product.id), 0, "отмена снимает резерв ровно один раз"
        )
        check(
            await total(db_session, seed.product.id), 12, "отмена резерва не создаёт лишний приход"
        )
