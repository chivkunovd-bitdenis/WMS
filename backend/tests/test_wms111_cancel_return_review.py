"""WMS-111/112 regressions from Astra review; isolated DB only.

Run this file with WMS_TEST_DATABASE_URL pointing to a dedicated PostgreSQL
DB to exercise real row locks. The normal suite runs nonconcurrent tests on
SQLite. No external marketplace or stock publication is called.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.storage_location import StorageLocation
from app.services import fbs_cancel_return_document_service as returns
from app.services.fbs_cancellation_service import _finish_local_cancellation, cancel_order
from app.services.fbs_cancelled_after_pack_service import fetch_cancelled_after_pack_page
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    sync_order_statuses,
    upsert_order_from_wb_row,
)
from tests.test_fbs_cancelled_after_pack import _seed_list_scope
from tests.test_wms111_wb_cancel_return import (
    _seed_order,
    _seed_product,
    _seed_seller,
    _seed_supply,
    _seed_tenant,
    _seed_warehouse,
)

TRANSFER = datetime(2026, 8, 20, 12, tzinfo=UTC)
CANCEL = datetime(2026, 8, 22, 15, tzinfo=UTC)


async def seed(session: AsyncSession, *, handed_over: bool = True) -> FbsOrder:
    suffix = uuid.uuid4().hex[:12]
    tenant = await _seed_tenant(session, suffix=suffix)
    warehouse = await _seed_warehouse(session, tenant, suffix)
    seller = await _seed_seller(session, tenant, suffix)
    product = await _seed_product(session, tenant, seller, suffix)
    supply = await _seed_supply(session, tenant_id=tenant, seller_id=seller,
                                warehouse_id=warehouse, handed_over=handed_over,
                                handover_at=TRANSFER)
    # Prove the delivered_at-only path, with no operation fallback.
    await session.execute(delete(FbsWbOperation).where(FbsWbOperation.tenant_id == tenant))
    order = await _seed_order(session, tenant_id=tenant, seller_id=seller,
                              warehouse_id=warehouse, product_id=product,
                              supply=supply, wb_order_id=911100)
    order.picked_at = TRANSFER - timedelta(hours=1)
    await session.commit()
    return order


@pytest.mark.parametrize("manual", [False, True])
async def test_full_cancel_preserves_handover_before_detach(
    db_session: AsyncSession, manual: bool,
) -> None:
    order = await seed(db_session)
    original_supply = order.supply_id
    if manual:
        await _finish_local_cancellation(db_session, order.tenant_id, order, actor_user_id=None)
    else:
        await _apply_wb_status_to_order(db_session, order, "canceled_by_client",
                                       actor_user_id=None, row={"cancelledAt": CANCEL.isoformat()})
    await db_session.commit()
    assert order.supply_id is None
    marker = returns.cancel_return_marker(order)
    assert marker and marker["source_supply_id"] == str(original_supply)
    assert marker["inbound_request_id"]
    page = await fetch_cancelled_after_pack_page(db_session, order.tenant_id)
    assert page.items[0]["cancelled_after_transfer"] is True
    assert page.items[0]["transfer_at"] == TRANSFER
    assert page.items[0]["supply"]["id"] == str(original_supply)
    assert page.items[0]["return_document_id"] == marker["inbound_request_id"]


async def test_late_payload_before_transfer_does_not_create_return(
    db_session: AsyncSession,
) -> None:
    order = await seed(db_session)
    early = TRANSFER - timedelta(seconds=1)
    await _apply_wb_status_to_order(db_session, order, "canceled_by_client",
                                   actor_user_id=None, row={"cancelledAt": early.isoformat()})
    await db_session.commit()
    page = await fetch_cancelled_after_pack_page(db_session, order.tenant_id)
    assert page.items[0]["cancelled_after_transfer"] is False
    assert page.items[0]["cancelled_at"] == early
    assert page.items[0]["return_document_id"] is None
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 0


async def test_pretransfer_observation_is_durable_and_payload_can_improve_it(
    db_session: AsyncSession,
) -> None:
    order = await seed(db_session, handed_over=False)
    await _apply_wb_status_to_order(db_session, order, "canceled", actor_user_id=None,
                                   received_at=CANCEL)
    await db_session.commit()
    await _apply_wb_status_to_order(db_session, order, "canceled", actor_user_id=None,
                                   received_at=CANCEL + timedelta(days=1))
    await db_session.commit()
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "observed_at"
    assert datetime.fromisoformat(marker["cancelled_at"]) == CANCEL
    precise = CANCEL - timedelta(hours=1)
    await _apply_wb_status_to_order(db_session, order, "canceled", actor_user_id=None,
                                   row={"cancelledAt": precise.isoformat()})
    await db_session.commit()
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "wb_payload"
    assert datetime.fromisoformat(marker["cancelled_at"]) == precise
    assert not marker.get("inbound_request_id")


@pytest.mark.parametrize("failure", ["document_flush", "marker_flush", "warehouse", "product"])
async def test_failed_document_keeps_cancel_committable_and_local_sync_retries(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    order = await seed(db_session)
    warehouse, product = order.warehouse_id, order.product_id
    if failure == "warehouse":
        order.warehouse_id = None
    elif failure == "product":
        order.product_id = None
    real_flush = db_session.flush
    real_number = returns.assign_document_number_if_missing
    injected = False

    async def broken_document(*args: Any, **kwargs: Any) -> None:
        nonlocal injected
        injected = True
        req = args[3]
        req.tenant_id = None  # NOT NULL violation on a real INSERT/flush.
        await real_flush()

    if failure == "document_flush":
        monkeypatch.setattr(returns, "assign_document_number_if_missing", broken_document)

    async def failing_flush(*args: Any, **kwargs: Any) -> None:
        nonlocal injected
        # An actual SQL error, including after marker assignment, not a fake
        # Python exception: PostgreSQL marks the savepoint transaction failed.
        should_fail = failure == "marker_flush" and returns.has_cancel_return_marker(order)
        if should_fail and not injected:
            injected = True
            await db_session.execute(text("SELECT 1 / 0") if
                                     db_session.get_bind().dialect.name == "postgresql" else
                                     text("SELECT * FROM wms111_missing_test_table"))
        await real_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", failing_flush)
    await _apply_wb_status_to_order(db_session, order, "canceled", actor_user_id=None,
                                   row={"cancelledAt": CANCEL.isoformat()})
    await db_session.commit()
    assert order.status == "cancelled" and order.supply_id is None
    assert returns.cancel_return_marker(order)["cancelled_at_source"] == "wb_payload"
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 0
    monkeypatch.setattr(db_session, "flush", real_flush)
    monkeypatch.setattr(returns, "assign_document_number_if_missing", real_number)
    if failure in {"document_flush", "marker_flush"}:
        assert injected
    order.warehouse_id, order.product_id = warehouse, product
    await db_session.commit()
    # This order is terminal: WB should not be contacted. Recovery reads local evidence.
    async def unexpected_wb(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("terminal retry must not query WB")
    monkeypatch.setattr("app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
                        unexpected_wb)
    async with httpx.AsyncClient() as client:
        await sync_order_statuses(db_session, order.tenant_id, order.seller_id,
                                  client, "isolated-test", actor_user_id=None)
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 1
    # Manual repeat also succeeds locally and keeps the same document.
    async with httpx.AsyncClient() as client:
        await cancel_order(db_session, order.tenant_id, order.id, client, actor_user_id=None)
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 1


async def test_import_new_cancelled_row_records_observation(db_session: AsyncSession) -> None:
    original = await seed(db_session, handed_over=False)
    order, created = await upsert_order_from_wb_row(
        db_session, original.tenant_id, original.seller_id,
        {"id": 911102, "createdAt": TRANSFER.isoformat(), "wbStatus": "canceled",
         "cancelledAt": CANCEL.isoformat()},
    )
    await db_session.commit()
    assert created and order.status == "cancelled"
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "wb_payload"
    assert datetime.fromisoformat(marker["cancelled_at"]) == CANCEL


async def test_real_http_fields_and_date_filter_use_displayed_time(
    async_client: httpx.AsyncClient,
) -> None:
    headers, tenant, seller, warehouse, product, supply = await _seed_list_scope(async_client)
    async with SessionLocal() as session:
        from app.models.fbs_supply import FbsSupply
        persisted_supply = await session.get(FbsSupply, supply.id)
        persisted_supply.delivered_at = TRANSFER
        ids = []
        for index, at in enumerate([CANCEL, CANCEL + timedelta(days=1)]):
            order = await _seed_order(session, tenant_id=tenant, seller_id=seller,
                                      warehouse_id=warehouse, product_id=product,
                                      supply=persisted_supply, wb_order_id=911110 + index)
            order.picked_at = TRANSFER
            await _apply_wb_status_to_order(session, order, "canceled", actor_user_id=None,
                                           row={"cancelledAt": at.isoformat()})
            # Reverse updated_at order; it must not affect filtering or pagination.
            order.updated_at = CANCEL + timedelta(days=20 - index)
            ids.append(str(order.id))
        await session.commit()
    response = await async_client.get("/fbs/cancelled-after-pack", headers=headers,
                                       params={"limit": 1})
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["order_id"] == ids[1]
    assert item["cancelled_at_source"] == "wb_payload"
    assert item["cancelled_after_transfer"] is True
    assert datetime.fromisoformat(item["transfer_at"].replace("Z", "+00:00")) == TRANSFER
    assert uuid.UUID(item["return_document_id"])
    response = await async_client.get("/fbs/cancelled-after-pack", headers=headers, params={
        "cancelled_from": CANCEL.isoformat(), "cancelled_to": CANCEL.isoformat(),
    })
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["order_id"] == ids[0]


@pytest.mark.postgresql_concurrency
async def test_postgres_stale_concurrent_helper_and_existing_inventory_unchanged(
    db_session: AsyncSession,
) -> None:
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("real PostgreSQL row-lock replay; use dedicated WMS_TEST_DATABASE_URL")
    order = await seed(db_session)
    location = StorageLocation(tenant_id=order.tenant_id, warehouse_id=order.warehouse_id,
                               code="WMS111-TEST", barcode="WMS111-TEST")
    db_session.add(location)
    await db_session.flush()
    db_session.add_all([
        InventoryBalance(tenant_id=order.tenant_id, storage_location_id=location.id,
                         product_id=order.product_id, quantity=17,
                         quantity_unpacked=12, quantity_packed=5),
        InventoryMovement(tenant_id=order.tenant_id, storage_location_id=location.id,
                          product_id=order.product_id, seller_id=order.seller_id,
                          warehouse_id=order.warehouse_id, quantity_delta=17,
                          movement_type="inbound_intake"),
    ])
    await db_session.commit()
    async def stock_snapshot() -> tuple[Any, Any]:
        async with SessionLocal() as session:
            balances = (await session.execute(select(InventoryBalance.__table__))).all()
            movements = (await session.execute(select(InventoryMovement.__table__))).all()
            return balances, movements
    baseline = await stock_snapshot()
    loaded = asyncio.Barrier(2)
    first_has_document = asyncio.Event()
    second_entered = asyncio.Event()
    pids: dict[bool, int] = {}
    async def replay(first: bool) -> uuid.UUID:
        async with SessionLocal() as session:
            assert await session.scalar(text("SHOW transaction_isolation")) == "read committed"
            pids[first] = await session.scalar(text("SELECT pg_backend_pid()"))
            stale = await session.get(FbsOrder, order.id)
            assert stale is not None and not returns.has_cancel_return_marker(stale)
            stale.meta_details_json = {"pending_note": "first" if first else "second"}
            await loaded.wait()
            if not first:
                await first_has_document.wait()
                second_entered.set()
            req = await returns.ensure_cancel_return_document(
                session, stale, cancel_time=returns.CancelTime(CANCEL, "wb_payload"),
            )
            assert req is not None
            if first:
                first_has_document.set()
                await second_entered.wait()
                for _ in range(200):
                    waiting = await session.scalar(text(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"
                    ), {"pid": pids[False]})
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
                assert waiting, "second PostgreSQL connection must really wait on the row lock"
                # Second transaction is waiting on the locked read. This repeat
                # also verifies idempotency inside the first outer transaction.
                repeated = await returns.maybe_create_cancel_return_document(session, stale)
                assert repeated is not None and repeated.id == req.id
            await session.commit()
            return req.id
    ids = await asyncio.wait_for(asyncio.gather(replay(True), replay(False)), timeout=20)
    assert ids[0] == ids[1]
    await db_session.refresh(order)
    assert order.meta_details_json["pending_note"] == "second"
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 1
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeLine)) == 1
    assert await stock_snapshot() == baseline


@pytest.mark.parametrize("caller", ["tracking", "shipment"])
async def test_tracking_and_shipment_preserve_original_wb_cancel_time(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caller: str,
) -> None:
    from sqlalchemy.orm import selectinload

    from app.models.fbs_supply import FbsSupply
    from app.services import fbs_shipment_service as shipment
    from app.services import fbs_tracking_service as tracking

    order = await seed(db_session)
    supply = await db_session.scalar(select(FbsSupply).where(FbsSupply.id == order.supply_id)
                                     .options(selectinload(FbsSupply.orders)))
    async def status_rows(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": order.wb_order_id, "wbStatus": "canceled",
                 "cancelledAt": CANCEL.isoformat()}]
    async def no_marking(*args: Any, **kwargs: Any) -> None:
        pass
    module = tracking if caller == "tracking" else shipment
    monkeypatch.setattr(module, "fetch_marketplace_orders_status", status_rows)
    monkeypatch.setattr(shipment.marking_svc, "sync_order_marking_statuses", no_marking)
    async with httpx.AsyncClient() as client:
        if caller == "tracking":
            await tracking._sync_supply_orders_from_wb(
                db_session, supply, client, "isolated-test", wb_done_hint=False, actor_user_id=None,
            )
        else:
            await shipment._sync_supply_orders_from_wb(
                db_session, order.tenant_id, supply, client, "isolated-test", actor_user_id=None,
            )
    await db_session.commit()
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "wb_payload"
    assert datetime.fromisoformat(marker["cancelled_at"]) == CANCEL
    assert marker["inbound_request_id"]


async def test_precise_time_updates_existing_document_marker_without_second_return(
    db_session: AsyncSession,
) -> None:
    order = await seed(db_session)
    original = await returns.maybe_create_cancel_return_document(
        db_session, order, received_at=CANCEL,
    )
    assert original is not None
    await db_session.commit()
    second = await returns.maybe_create_cancel_return_document(
        db_session, order, row={"cancelledAt": (CANCEL - timedelta(hours=1)).isoformat()},
    )
    await db_session.commit()
    assert second is not None and second.id == original.id
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "wb_payload"
    assert datetime.fromisoformat(marker["cancelled_at"]) == CANCEL - timedelta(hours=1)
    assert await db_session.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 1


async def test_status_batch_observation_precedes_later_pages_and_processing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import wb_marketplace_orders_service as orders_service

    order = await seed(db_session, handed_over=False)
    class Clock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            cls.calls += 1
            return cls.fromtimestamp((CANCEL + timedelta(hours=cls.calls - 1)).timestamp(), UTC)

    async def status_rows(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": 911100, "wbStatus": "canceled"}]

    monkeypatch.setattr(orders_service, "datetime", Clock)
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_status", status_rows)
    async with httpx.AsyncClient() as client:
        rows = await orders_service._fetch_status_rows_resilient(
            client, api_token="isolated-test", tenant_id=order.tenant_id,
            seller_id=order.seller_id, orders_by_wb_id={order.wb_order_id: [order]},
        )
    # Processing happens after the clock advanced; capture is from response handling.
    Clock.calls = 10
    await _apply_wb_status_to_order(db_session, order, "canceled", actor_user_id=None, row=rows[0])
    await db_session.commit()
    marker = returns.cancel_return_marker(order)
    assert marker and marker["cancelled_at_source"] == "observed_at"
    assert datetime.fromisoformat(marker["cancelled_at"]) == CANCEL
