"""WMS-517: one-off backfill of WB order prices for orders older than price capture."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import backfill_wb_order_prices as cli
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot
from app.services.wb_order_price_service import capture_wb_price_snapshot, resolve_wb_product_cost


async def _order(
    session: AsyncSession, tenant: Tenant, seller: Seller, warehouse: Warehouse, wb_id: int
) -> FbsOrder:
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        wb_order_id=wb_id,
        wb_rid=f"rid-{wb_id}.0.0",
        marketplace="wb",
        status="in_delivery",
        created_at_wb=datetime.now(UTC) - timedelta(days=10),
        deadline_at=datetime.now(UTC),
        mapping_status="mapped",
        reserve_status="reserved",
        price=999999,
    )
    session.add(order)
    await session.flush()
    session.add(
        FbsOrderMarking(
            tenant_id=tenant.id,
            order_id=order.id,
            kind="sgtin",
            value=f"0104601234567890215{wb_id}",
            source="external",
            meta_status="sent",
        )
    )
    await session.flush()
    return order


async def test_backfill_uses_statistics_then_orders_api_and_is_idempotent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = Tenant(name="backfill", slug=uuid.uuid4().hex)
    db_session.add(tenant)
    await db_session.flush()
    seller = Seller(tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(tenant_id=tenant.id, code="wh", name="Warehouse")
    db_session.add_all([seller, warehouse])
    await db_session.flush()
    in_report = await _order(db_session, tenant, seller, warehouse, 101)
    in_orders_api = await _order(db_session, tenant, seller, warehouse, 102)
    nowhere = await _order(db_session, tenant, seller, warehouse, 103)
    already = await _order(db_session, tenant, seller, warehouse, 104)
    await capture_wb_price_snapshot(
        db_session, tenant_id=tenant.id, seller_id=seller.id, order_id=already.id,
        row={"finalPrice": 5000, "currencyCode": 643},
    )
    # The regular /api/v3/orders sync leaves a price-less revision on top.
    await capture_wb_price_snapshot(
        db_session, tenant_id=tenant.id, seller_id=seller.id, order_id=in_report.id,
        row={"price": 150000},
    )
    await db_session.commit()
    tenant_id, seller_id = tenant.id, seller.id
    report_id, api_id, nowhere_id, already_id = (
        in_report.id, in_orders_api.id, nowhere.id, already.id
    )

    requests: list[str] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/supplier/orders":
            rows: list[dict[str, Any]] = [
                {"srid": "rid-101.0.0", "finishedPrice": 1404, "isCancel": False,
                 "lastChangeDate": "2026-09-20T10:00:00"},
                {"srid": "rid-104.0.0", "finishedPrice": 1, "isCancel": False,
                 "lastChangeDate": "2026-09-20T10:00:00"},
                {"srid": "foreign", "finishedPrice": 7, "isCancel": False,
                 "lastChangeDate": "2026-09-20T10:00:00"},
            ]
            return httpx.Response(200, json=rows)
        assert request.url.path == "/api/v3/orders"
        assert int(request.url.params["dateTo"]) > int(request.url.params["dateFrom"])
        if request.url.params["next"] != "0":
            return httpx.Response(200, json={"orders": [], "next": 0})
        return httpx.Response(200, json={"next": 0, "orders": [
            {"id": 102, "price": 13740, "currencyCode": 933,
             "convertedPrice": 137400, "convertedCurrencyCode": 643},
            {"id": 103, "convertedPrice": 1, "convertedCurrencyCode": 840},
        ]})

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(*args, transport=transport, **kwargs)

    async def token(*_: Any) -> str:
        return "token"

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(cli.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(cli, "get_decrypted_marketplace_token", token)
    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)

    async def snapshot_count() -> int:
        db_session.expire_all()
        return int(await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) or 0)

    before = await snapshot_count()
    [dry] = await cli.run(apply=False, seller_id=seller_id)
    assert (dry.orders_without_price, dry.statistics_found, dry.orders_api_found) == (3, 1, 1)
    assert dry.not_found == [103] and dry.written == 0 and dry.error is None
    assert await snapshot_count() == before

    [applied] = await cli.run(apply=True, seller_id=seller_id)
    assert applied.written == 2
    assert await snapshot_count() == before + 2
    for order_id, expected in ((report_id, 140400), (api_id, 137400), (already_id, 5000)):
        cost = await resolve_wb_product_cost(
            db_session, tenant_id=tenant_id, seller_id=seller_id, order_id=order_id
        )
        assert cost.product_cost == expected
    sources = set(await db_session.scalars(
        select(WbOrderPriceSnapshot.source).where(
            WbOrderPriceSnapshot.order_id.in_([report_id, api_id])
        )
    ))
    assert {cli.STATISTICS_SOURCE, cli.ORDERS_SOURCE} <= sources
    assert nowhere_id not in set(await db_session.scalars(select(WbOrderPriceSnapshot.order_id)))

    [again] = await cli.run(apply=True, seller_id=seller_id)
    assert again.orders_without_price == 1 and again.written == 0
    assert await snapshot_count() == before + 2
