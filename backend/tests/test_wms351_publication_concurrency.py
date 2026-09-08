"""Actual PostgreSQL sessions: final zero is serialized against manual WB sync."""

import asyncio
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_sellers import FbsStockSyncBody, start_fbs_stock_sync
from app.models.user import User
from app.services import catalog_service
from app.services import fbs_stock_rule_service as rules
from app.services.fbs_stock_sync_service import sync_binding_stocks
from tests.test_fbs_stock_sync import (
    _configure_rule_amount,
    _MockStocksTransport,
    _product,
    _seed_binding,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["manual_sync", "stale_legacy"])
async def test_final_zero_serializes_wb_writers(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    if db_session.bind is None or db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL")
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=9351,
        sku_suffix="wms351",
        fbs_percent=100,
    )
    db_session.add(product)
    await db_session.commit()
    await _configure_rule_amount(db_session, ctx, product, 10)
    transport = _MockStocksTransport()
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: client_class(
            *a,
            **dict(kw, transport=httpx.MockTransport(transport.handler)),
        ),
    )
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_a: None)
    monkeypatch.setattr(catalog_service, "schedule_seller_stock_publish", lambda *_a: None)
    async with httpx.AsyncClient() as client:
        await sync_binding_stocks(db_session, ctx.tenant.id, ctx.seller.id, ctx.binding, client)
    assert transport.stored[9351] == 10
    view = await rules.get_rule_view(db_session, ctx.tenant.id, product.id)
    await db_session.commit()
    if entry == "stale_legacy":
        product.fbs_stock_sync_enabled = False
        await db_session.commit()
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as stale:
            old = await stale.get(type(product), product.id)
            assert old is not None and not old.fbs_stock_sync_enabled
            product.fbs_stock_sync_enabled = True
            await db_session.commit()
            await catalog_service.update_product_fbs_stock_sync(
                stale,
                ctx.tenant.id,
                product.id,
                fbs_stock_sync_enabled=False,
            )
            assert not old.fbs_stock_sync_enabled
            assert old.fbs_ozon_stock_sync_enabled is True
            assert transport.stored[9351] == 0
        return

    zero_confirmed, finish_save = asyncio.Event(), asyncio.Event()
    original_clear = rules._clear_product_publication

    async def pause_after_zero(*a: Any, **kw: Any) -> None:
        await original_clear(*a, **kw)
        zero_confirmed.set()
        await asyncio.wait_for(finish_save.wait(), 5)

    monkeypatch.setattr(rules, "_clear_product_publication", pause_after_zero)
    async with (
        AsyncSession(bind=db_session.bind, expire_on_commit=False) as setting_session,
        AsyncSession(bind=db_session.bind, expire_on_commit=False) as manual_session,
    ):
        off_task = asyncio.create_task(
            rules.set_rule_for_products(
                setting_session,
                ctx.tenant.id,
                [product.id],
                replace(view.rule, publish=False),
            )
        )
        ready = asyncio.create_task(zero_confirmed.wait())
        await asyncio.wait({ready, off_task}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
        if off_task.done():
            await off_task
        assert ready.done(), "zero did not complete"
        manual_task = asyncio.create_task(
            start_fbs_stock_sync(
                ctx.seller.id,
                FbsStockSyncBody(),
                Response(),
                User(tenant_id=ctx.tenant.id, role="fulfillment_admin"),
                manual_session,
            )
        )
        await asyncio.sleep(0.1)
        assert not manual_task.done()
        assert transport.stored[9351] == 0
        finish_save.set()
        await asyncio.wait_for(off_task, 5)
        result = await asyncio.wait_for(manual_task, 5)
        assert result.products_targeted == 0
        assert transport.stored[9351] == 0
        assert [[x.amount for x in batch] for batch in transport.put_calls] == [[10], [0]]
