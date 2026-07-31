from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_DELIVERY, FBS_ORDER_STATUS_NEW, FbsOrder
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.tenant import Tenant
from app.services.fbs_autopoll_service import (
    SellerPollTarget,
    list_sellers_with_marketplace_token,
    poll_fbs_orders_all_sellers,
    poll_fbs_orders_for_seller,
    sync_fbs_order_statuses_all_sellers,
    sync_fbs_order_statuses_for_seller,
)
from app.services.integration_fernet import encrypt_secret
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError


def _wb_order_row(*, order_id: int) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": "ART-001",
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
    }


async def _ensure_tenant(
    session: Any,
    tenant_id: uuid.UUID,
    *,
    name_suffix: str,
) -> None:
    existing = await session.get(Tenant, tenant_id)
    if existing is not None:
        return
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {name_suffix}",
            slug=f"tenant-{name_suffix}-{time.time_ns()}",
        )
    )


async def _seed_seller_with_marketplace_token(
  tenant_id: uuid.UUID,
  *,
  token_suffix: str,
) -> uuid.UUID:
    seller_id = uuid.uuid4()
    async with SessionLocal() as session:
        await _ensure_tenant(session, tenant_id, name_suffix=token_suffix)
        session.add(
            Seller(
                id=seller_id,
                tenant_id=tenant_id,
                name=f"Seller {token_suffix}",
            )
        )
        session.add(
            SellerWildberriesCredentials(
                seller_id=seller_id,
                marketplace_token_encrypted=encrypt_secret(f"token-{token_suffix}"),
            )
        )
        await session.commit()
    return seller_id


def _patch_wb_order_fetches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    new_rows: list[dict[str, Any]] | None = None,
    status_rows: list[dict[str, Any]] | None = None,
    new_raises: BaseException | None = None,
) -> None:
    async def fake_new(
        client: object, *, api_token: str, marketplace_api_base: str | None = None
    ) -> list[dict[str, Any]]:
        if new_raises is not None:
            raise new_raises
        return new_rows or []

    async def fake_page(
        client: object,
        *,
        api_token: str,
        marketplace_api_base: str | None = None,
        limit: int = 100,
        next_token: int | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        return [], None

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        if status_rows is not None:
            return status_rows
        return [{"id": oid, "wbStatus": "waiting"} for oid in order_ids]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_new",
        fake_new,
    )
    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_page",
        fake_page,
    )
    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )


# TC-NEW-FBS-AUTOPOLL-001
@pytest.mark.asyncio
async def test_fbs_autopoll_syncs_orders_for_one_seller(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="one")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH",
                code=f"wh-{time.time_ns()}",
            )
        )
        await session.commit()

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[_wb_order_row(order_id=900001 + i) for i in range(5)],
    )

    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        stats = await poll_fbs_orders_for_seller(session, target, client)

    assert stats["orders_upserted"] == 5
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(FbsOrder)
            .where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.seller_id == seller_id,
                FbsOrder.status == FBS_ORDER_STATUS_NEW,
            )
        )
    assert count == 5


# TC-NEW-FBS-AUTOPOLL-002
@pytest.mark.asyncio
async def test_fbs_autopoll_iterates_multiple_sellers(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_ids = [
        await _seed_seller_with_marketplace_token(tenant_id, token_suffix=f"s{i}")
        for i in range(3)
    ]

    calls: list[uuid.UUID] = []

    async def fake_sync(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        warehouse_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        calls.append(sid)
        return {
            "orders_upserted": 1,
            "orders_created": 1,
            "statuses_updated": 0,
        }

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_orders",
        fake_sync,
    )

    result = await poll_fbs_orders_all_sellers()
    assert result.sellers_polled == 3
    assert set(calls) == set(seller_ids)


# TC-NEW-FBS-AUTOPOLL-003
@pytest.mark.asyncio
async def test_fbs_autopoll_continues_after_seller_error(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_ids = [
        await _seed_seller_with_marketplace_token(tenant_id, token_suffix=f"e{i}")
        for i in range(3)
    ]
    failing = seller_ids[1]

    async def fake_sync(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        warehouse_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        if sid == failing:
            raise WildberriesClientError("upstream", status_code=500)
        return {"orders_upserted": 2, "orders_created": 2, "statuses_updated": 0}

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_orders",
        fake_sync,
    )

    result = await poll_fbs_orders_all_sellers()
    assert result.sellers_polled == 2
    assert result.seller_errors == 1
    assert result.orders_upserted == 4


# TC-NEW-FBS-AUTOPOLL-004
@pytest.mark.asyncio
async def test_fbs_autopoll_idempotent_upsert(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="idem")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH",
                code=f"wh-{time.time_ns()}",
            )
        )
        await session.commit()

    row = _wb_order_row(order_id=12345)
    _patch_wb_order_fetches(monkeypatch, new_rows=[row])
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        await poll_fbs_orders_for_seller(session, target, client)

    async with SessionLocal() as session:
        first = (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.wb_order_id == 12345,
                )
            )
        ).scalar_one()
        first_updated = first.updated_at

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        await poll_fbs_orders_for_seller(session, target, client)

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(FbsOrder)
            .where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.wb_order_id == 12345,
            )
        )
        second = (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.wb_order_id == 12345,
                )
            )
        ).scalar_one()
    assert count == 1
    assert second.updated_at >= first_updated


# TC-NEW-FBS-AUTOPOLL-005
@pytest.mark.asyncio
async def test_fbs_autopoll_status_sync_updates_sorted(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="status")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH",
                code=f"wh-{time.time_ns()}",
            )
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            warehouse_id,
            _wb_order_row(order_id=880001),
        )
        order.status = FBS_ORDER_STATUS_IN_DELIVERY
        order.wb_status = "waiting"
        await session.commit()

    _patch_wb_order_fetches(
        monkeypatch,
        status_rows=[{"id": 880001, "wbStatus": "sorted"}],
    )
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        updated = await sync_fbs_order_statuses_for_seller(session, target, client)
        await session.commit()

    assert updated == 1
    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.wb_order_id == 880001)
            )
        ).scalar_one()
    assert order.wb_status == "sorted"


@pytest.mark.asyncio
async def test_list_sellers_with_marketplace_token_filters(
    async_client: AsyncClient,
) -> None:
    tenant_id = uuid.uuid4()
    with_token = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="has")
    without_token = uuid.uuid4()
    async with SessionLocal() as session:
        await _ensure_tenant(session, tenant_id, name_suffix="filter")
        session.add(
            Seller(
                id=without_token,
                tenant_id=tenant_id,
                name="No token",
            )
        )
        session.add(SellerWildberriesCredentials(seller_id=without_token))
        await session.commit()
        targets = await list_sellers_with_marketplace_token(session)

    seller_ids = {target.seller_id for target in targets if target.tenant_id == tenant_id}
    assert with_token in seller_ids
    assert without_token not in seller_ids


@pytest.mark.asyncio
async def test_fbs_statuses_autopoll_all_sellers(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    await _seed_seller_with_marketplace_token(tenant_id, token_suffix="all")

    async def fake_sync(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
    ) -> int:
        return 3

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_order_statuses",
        fake_sync,
    )
    result = await sync_fbs_order_statuses_all_sellers()
    assert result.sellers_polled == 1
    assert result.statuses_updated == 3
