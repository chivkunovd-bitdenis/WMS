from __future__ import annotations

import contextlib
import time
import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
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
    sync_marking_statuses_for_assembling_supplies,
    sync_seller_stocks,
)
from app.services.integration_fernet import encrypt_secret
from app.services.wb_marketplace_orders_service import (
    WbMarketplaceOrdersError,
    upsert_order_from_wb_row,
)
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


def _wb_order_row(
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID
) -> dict[str, Any]:
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
        "warehouseId": wb_warehouse_id,
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


# TC-NEW-FBS-AUTOPOLL-006 — metadata sync batches all assembling orders at 100
@pytest.mark.asyncio
async def test_fbs_autopoll_metadata_sync_batches_over_100_and_preserves_missing_wb_row(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="meta-batch")
    supply_id = uuid.uuid4()
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
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                wb_supply_id="WB-GI-META-BATCH",
                name="Batch metadata",
                status=FBS_SUPPLY_STATUS_ASSEMBLING,
                delivery_type="pvz",
            )
        )
        await session.flush()
        for index in range(101):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_id,
                _wb_order_row(order_id=970000 + index),
            )
            order.supply_id = supply_id
            if index == 100:
                session.add(
                    FbsOrderMarking(
                        order_id=order.id,
                        tenant_id=tenant_id,
                        kind="sgtin",
                        value="01LOCAL-KEEP",
                        marking_code_id=uuid.uuid4(),
                        check_status=CHECK_STATUS_CHECKING,
                    )
                )
        await session.commit()

    batches: list[list[int]] = []

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        batches.append(order_ids)
        # The last order is deliberately absent, matching WB's partial response.
        return [MarketplaceOrderMetaRow(order_id=oid) for oid in order_ids[:-1]]

    monkeypatch.setattr(
        "app.services.wildberries_fbs_client.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    async def noop_supply_update(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.fbs_marking_service._notify_supply_marking_update",
        noop_supply_update,
    )
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        synced = await sync_marking_statuses_for_assembling_supplies(
            session, target, client
        )

    assert [len(batch) for batch in batches] == [100, 1]
    assert all(len(batch) <= 100 for batch in batches)
    assert synced == 101
    async with SessionLocal() as session:
        marking = (
            await session.execute(
                select(FbsOrderMarking).join(FbsOrder).where(FbsOrder.wb_order_id == 970100)
            )
        ).scalar_one()
        assert marking.value == "01LOCAL-KEEP"
        assert marking.marking_code_id is not None


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
            raise WbMarketplaceOrdersError("wb_upstream_500")
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
async def test_fbs_autopoll_status_sync_updates_sorted_then_sold(
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
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
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
    assert order.status == FBS_ORDER_STATUS_SORTED

    _patch_wb_order_fetches(
        monkeypatch,
        status_rows=[{"id": 880001, "supplierStatus": "complete", "wbStatus": "sold"}],
    )
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
    assert order.wb_status == "sold"
    assert order.supplier_status == "complete"
    assert order.status == FBS_ORDER_STATUS_DONE


@pytest.mark.asyncio
async def test_fbs_autopoll_supplier_status_moves_new_order_out_of_new(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="supplier")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH supplier",
                code=f"wh-supplier-{time.time_ns()}",
            )
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=880101),
        )
        assert order.status == FBS_ORDER_STATUS_NEW
        await session.commit()

    _patch_wb_order_fetches(
        monkeypatch,
        status_rows=[{"id": 880101, "supplierStatus": "confirm", "wbStatus": "waiting"}],
    )
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        updated = await sync_fbs_order_statuses_for_seller(session, target, client)
        await session.commit()

    assert updated == 1
    async with SessionLocal() as session:
        order = (
            await session.execute(select(FbsOrder).where(FbsOrder.wb_order_id == 880101))
        ).scalar_one()
    assert order.status == FBS_ORDER_STATUS_EXTERNAL_PROCESSING
    assert order.supplier_status == "confirm"
    assert order.wb_status == "waiting"


@pytest.mark.asyncio
async def test_fbs_autopoll_status_sync_splits_batches_and_skips_bad_order(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="split")
    bad_wb_order_id = 880250

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH split",
                code=f"wh-split-{time.time_ns()}",
            )
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        for wb_order_id in range(880200, 880305):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_id,
                _wb_order_row(order_id=wb_order_id),
            )
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
            order.wb_status = "waiting"
        await session.commit()

    calls: list[list[int]] = []

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, object]]:
        calls.append(list(order_ids))
        assert len(order_ids) <= 100
        if bad_wb_order_id in order_ids:
            raise WildberriesClientError(
                "upstream_error",
                status_code=400,
                endpoint="/api/v3/orders/status",
                response_body='{"message":"unknown order id"}',
            )
        return [{"id": order_id, "wbStatus": "sorted"} for order_id in order_ids]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        updated = await sync_fbs_order_statuses_for_seller(session, target, client)
        await session.commit()

    assert updated == 104
    assert any(len(call) == 100 for call in calls)
    assert [bad_wb_order_id] in calls

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.wb_order_id.between(880200, 880304),
                )
            )
        ).scalars().all()
    by_wb_id = {row.wb_order_id: row for row in rows}
    assert by_wb_id[bad_wb_order_id].wb_status == "waiting"
    assert sum(1 for row in rows if row.wb_status == "sorted") == 104


@pytest.mark.asyncio
async def test_fbs_autopoll_supplier_status_new_keeps_order_new(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="supplier-new")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_id,
                tenant_id=tenant_id,
                name="WH supplier new",
                code=f"wh-supplier-new-{time.time_ns()}",
            )
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=880102),
        )
        await session.commit()

    _patch_wb_order_fetches(
        monkeypatch,
        status_rows=[{"id": 880102, "supplierStatus": "new", "wbStatus": "waiting"}],
    )
    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        updated = await sync_fbs_order_statuses_for_seller(session, target, client)
        await session.commit()

    assert updated == 1
    async with SessionLocal() as session:
        order = (
            await session.execute(select(FbsOrder).where(FbsOrder.wb_order_id == 880102))
        ).scalar_one()
    assert order.status == FBS_ORDER_STATUS_NEW
    assert order.supplier_status == "new"
    assert order.wb_status == "waiting"


@pytest.mark.asyncio
async def test_list_sellers_with_marketplace_token_filters(
    async_client: AsyncClient,
) -> None:
    tenant_id = uuid.uuid4()
    with_token = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="has")
    with_unified_content_token = uuid.uuid4()
    without_token = uuid.uuid4()
    async with SessionLocal() as session:
        await _ensure_tenant(session, tenant_id, name_suffix="filter")
        session.add(
            Seller(
                id=with_unified_content_token,
                tenant_id=tenant_id,
                name="Content token",
            )
        )
        session.add(
            SellerWildberriesCredentials(
                seller_id=with_unified_content_token,
                content_token_encrypted=encrypt_secret("content-token"),
            )
        )
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
    assert with_unified_content_token in seller_ids
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


# TC-NEW-FBS-STOCK-013 — order intake does not write stocks unless explicitly requested
@pytest.mark.asyncio
async def test_fbs_autopoll_intake_success_skips_stock_sync_by_default(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="stock-ok")
    stock_calls: list[uuid.UUID] = []

    async def fake_orders(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        warehouse_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        return {
            "orders_upserted": 1,
            "orders_created": 1,
            "statuses_updated": 0,
        }

    async def fake_stocks(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        wb_warehouse_id: int | None = None,
    ) -> object:
        stock_calls.append(sid)
        from app.services.fbs_autopoll_service import SellerStockSyncResult

        return SellerStockSyncResult(bindings_processed=1)

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_orders",
        fake_orders,
    )
    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_stocks",
        fake_stocks,
    )

    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        stats = await poll_fbs_orders_for_seller(session, target, client)

    assert stock_calls == []
    assert stats["stocks_bindings_processed"] == 0


@pytest.mark.asyncio
async def test_fbs_autopoll_intake_success_can_opt_into_stock_sync(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="stock-opt")
    stock_calls: list[uuid.UUID] = []

    async def fake_orders(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        warehouse_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        return {
            "orders_upserted": 1,
            "orders_created": 1,
            "statuses_updated": 0,
        }

    async def fake_stocks(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        wb_warehouse_id: int | None = None,
    ) -> object:
        stock_calls.append(sid)
        from app.services.fbs_autopoll_service import SellerStockSyncResult

        return SellerStockSyncResult(bindings_processed=1)

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_orders",
        fake_orders,
    )
    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_stocks",
        fake_stocks,
    )

    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        stats = await poll_fbs_orders_for_seller(
            session,
            target,
            client,
            sync_stocks_after_orders=True,
        )

    assert stock_calls == [seller_id]
    assert stats["stocks_bindings_processed"] == 1


# TC-NEW-FBS-STOCK-013 — intake failure must not run stock sync for that seller
@pytest.mark.asyncio
async def test_fbs_autopoll_intake_error_skips_stock_sync(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="stock-skip")
    stock_calls: list[uuid.UUID] = []

    async def fake_stocks(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        wb_warehouse_id: int | None = None,
    ) -> object:
        stock_calls.append(sid)
        from app.services.fbs_autopoll_service import SellerStockSyncResult

        return SellerStockSyncResult()

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_stocks",
        fake_stocks,
    )
    _patch_wb_order_fetches(
        monkeypatch,
        new_raises=WbMarketplaceOrdersError("wb_upstream_500"),
    )

    target = SellerPollTarget(tenant_id=tenant_id, seller_id=seller_id)
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        with contextlib.suppress(WbMarketplaceOrdersError):
            await poll_fbs_orders_for_seller(session, target, client)

    assert stock_calls == []


# TC-NEW-FBS-STOCK-013 — order autopoll all sellers does not run stock writes
@pytest.mark.asyncio
async def test_fbs_autopoll_all_sellers_skips_stock_sync(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_ids = [
        await _seed_seller_with_marketplace_token(tenant_id, token_suffix=f"sa{i}")
        for i in range(2)
    ]
    failing = seller_ids[0]
    stock_calls: list[uuid.UUID] = []

    async def fake_orders(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        warehouse_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        if sid == failing:
            raise WbMarketplaceOrdersError("wb_upstream_500")
        return {"orders_upserted": 1, "orders_created": 1, "statuses_updated": 0}

    async def fake_stocks(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        wb_warehouse_id: int | None = None,
    ) -> object:
        stock_calls.append(sid)
        from app.services.fbs_autopoll_service import SellerStockSyncResult

        return SellerStockSyncResult(bindings_processed=1)

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_orders",
        fake_orders,
    )
    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_seller_stocks",
        fake_stocks,
    )

    result = await poll_fbs_orders_all_sellers()
    assert result.sellers_polled == 1
    assert result.seller_errors == 1
    assert stock_calls == []
    assert result.stocks_bindings_processed == 0


# TC-NEW-FBS-STOCK-013 — binding error is logged but other bindings continue
@pytest.mark.asyncio
async def test_sync_seller_stocks_continues_after_binding_error(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    warehouse_a = uuid.uuid4()
    warehouse_b = uuid.uuid4()
    seller_id = await _seed_seller_with_marketplace_token(tenant_id, token_suffix="bind-err")

    async with SessionLocal() as session:
        from app.models.warehouse import Warehouse

        session.add(
            Warehouse(
                id=warehouse_a,
                tenant_id=tenant_id,
                name="WH A",
                code=f"wh-a-{time.time_ns()}",
            )
        )
        session.add(
            Warehouse(
                id=warehouse_b,
                tenant_id=tenant_id,
                name="WH B",
                code=f"wh-b-{time.time_ns()}",
            )
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_a,
            wb_warehouse_id=501001,
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_b,
            wb_warehouse_id=501002,
        )
        await session.commit()

    calls: list[int] = []

    async def fake_binding_sync(
        session: object,
        tid: uuid.UUID,
        sid: uuid.UUID,
        binding: object,
        http_client: object,
        *,
        rate_limiter: object | None = None,
        marketplace_api_base: str | None = None,
    ) -> object:
        wb_id = binding.wb_warehouse_id
        calls.append(wb_id)
        if wb_id == 501001:
            from app.services.fbs_stock_sync_service import FbsStockSyncError

            raise FbsStockSyncError("binding_mismatch")
        from app.services.fbs_stock_sync_service import FbsStockSyncResult

        return FbsStockSyncResult(bindings_processed=1)

    monkeypatch.setattr(
        "app.services.fbs_autopoll_service.sync_binding_stocks",
        fake_binding_sync,
    )

    async with SessionLocal() as session, httpx.AsyncClient() as client:
        result = await sync_seller_stocks(session, tenant_id, seller_id, client)

    assert calls == [501001, 501002]
    assert result.bindings_processed == 1
    assert result.binding_errors == 1
