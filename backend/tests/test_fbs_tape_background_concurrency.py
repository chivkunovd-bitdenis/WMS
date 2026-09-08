"""WMS-080: background status/cancellation and slow HTTP must not lock unrelated work."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_fbs_order_tape_concurrency import print_tape, seed_tape, stock_snapshot

from app.core.settings import settings
from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderReservation
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.models.marking_code import MarkingCode
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.services import fbs_order_tape_print_service as tape
from app.services import fbs_print_asset_service as assets
from app.services import wb_marketplace_orders_service as wb
from app.services.wildberries_errors import WildberriesClientError


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_postgres_background_status_http_overlaps_tape_with_reverse_uuid_dates(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as session:
        orders = list((await session.scalars(select(FbsOrder).order_by(FbsOrder.id))).all())
        seller_id = orders[0].seller_id
        for i, order in enumerate(orders):
            order.created_at_wb = datetime.now(UTC) - timedelta(days=i)
        await session.commit()
    fetching, proceed = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(wb, "SYNC_STATUS_BATCH_SIZE", 1)

    async def delayed_status(_client, *, order_ids, **_kwargs):
        fetching.set()
        await proceed.wait()
        return [{"id": oid, "wbStatus": "cancel" if cancel else "waiting"} for oid in order_ids]

    monkeypatch.setattr(wb, "fetch_marketplace_orders_status", delayed_status)
    async with SessionLocal() as background, SessionLocal() as printing:

        async def sync():
            count = await wb.sync_order_statuses(
                background,
                seed.tenant_id,
                seller_id,
                async_client,
                "test",
                actor_user_id=None,
            )
            await background.commit()
            return count

        syncing = asyncio.create_task(sync())
        try:
            await asyncio.wait_for(fetching.wait(), 5)
            first = await asyncio.wait_for(print_tape(printing, async_client, seed), 5)
            repeated = await asyncio.wait_for(print_tape(printing, async_client, seed), 5)
            assert first.orders and not first.order_errors
            assert repeated.orders[0].codes == first.orders[0].codes
            proceed.set()
            assert await asyncio.wait_for(syncing, 5) == 2
        finally:
            proceed.set()
            if not syncing.done():
                syncing.cancel()
            await asyncio.gather(syncing, return_exceptions=True)
    async with SessionLocal() as session:
        orders = list((await session.scalars(select(FbsOrder))).all())
        assert all(o.status == ("cancelled" if cancel else "assembling") for o in orders)
        assert all(o.supply_id == (None if cancel else seed.supply_id) for o in orders)
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MarkingCode)
                .where(
                    MarkingCode.status == "printed",
                )
            )
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(FbsOrderReservation)) == (
            0 if cancel else 2
        )


async def separate_second_product(seed):
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, seed.line_id)
        order = await session.get(FbsOrder, seed.order_ids[1])
        assert line and order
        product = await session.scalar(select(Product).where(Product.id != line.product_id))
        assert product
        order.product_id, order.required_meta_json = product.id, []
        line.qty_total = 1
        other_line = PackagingTaskLine(
            task_id=seed.task_id,
            product_id=product.id,
            storage_location_id=line.storage_location_id,
            qty_total=1,
            qty_suggested_packed=0,
            qty_confirmed_packed=0,
            qty_packed_in_task=0,
        )
        reservation = await session.scalar(
            select(FbsOrderReservation).where(
                FbsOrderReservation.fbs_order_id == order.id,
            )
        )
        assert reservation
        reservation.product_id = product.id
        session.add_all(
            [
                other_line,
                InventoryBalance(
                    tenant_id=seed.tenant_id,
                    product_id=product.id,
                    storage_location_id=line.storage_location_id,
                    quantity=3,
                    quantity_unpacked=3,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()
        return product.id, line.storage_location_id, other_line.id


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["qr", "cz"])
async def test_postgres_slow_tape_http_allows_other_product_work(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 2)
    product_id, location_id, line_id = await separate_second_product(seed)
    before = await stock_snapshot()
    fetching, proceed = asyncio.Event(), asyncio.Event()
    if kind == "qr":
        original = assets.fetch_marketplace_order_stickers
        monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
        monkeypatch.setattr(assets, "_require_marketplace_token", AsyncMock(return_value="test"))
        target, name = assets, "fetch_marketplace_order_stickers"
    else:
        target, name = tape.marking_svc, "put_marketplace_order_meta"
        original = target.put_marketplace_order_meta

    async def delayed(*args, **kwargs):
        fetching.set()
        await proceed.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(target, name, delayed)
    async with SessionLocal() as session:
        request = asyncio.create_task(
            tape.print_fbs_order_tape(
                session,
                seed.tenant_id,
                seed.supply_id,
                order_ids=[seed.order_ids[0]],
                layout={"units": [] if kind == "qr" else [{"block": "cz", "copies": 1}]},
                include_order_qr=kind == "qr",
                allow_partial=False,
                reprint=False,
                actor_user_id=seed.user_id,
                http_client=async_client,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)
            if kind == "qr":
                independent = await asyncio.wait_for(
                    async_client.post(
                        f"/operations/fbs-supplies/{seed.supply_id}/pick/set",
                        headers=seed.headers,
                        json={
                            "product_id": str(product_id),
                            "storage_location_id": str(location_id),
                            "quantity": 1,
                        },
                    ),
                    5,
                )
            else:
                independent = await asyncio.wait_for(
                    async_client.post(
                        f"/operations/packaging-tasks/{seed.task_id}/lines/{line_id}/pack",
                        headers=seed.headers,
                        json={"quantity": 1, "order_id": str(seed.order_ids[1])},
                    ),
                    5,
                )
            assert independent.status_code == 200, independent.text
            assert not request.done()
            proceed.set()
            result = await asyncio.wait_for(request, 5)
            assert result.orders and not result.order_errors
        finally:
            proceed.set()
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)
    if kind == "cz":
        assert await stock_snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["put", "get"])
async def test_tape_uncertain_wb_write_keeps_code_and_retries_get_only(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    original_put = tape.marking_svc.put_marketplace_order_meta
    original_get = tape.marking_svc.fetch_marketplace_orders_meta_batch
    calls = []
    fail = True

    async def put(*args, **kwargs):
        calls.append("put")
        await original_put(*args, **kwargs)
        if failure == "put":
            raise WildberriesClientError("transport_error")

    async def get(*args, **kwargs):
        calls.append("get")
        if fail:
            raise WildberriesClientError("transport_error")
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(tape.marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(tape.marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        uncertain = await print_tape(session, async_client, seed)
        assert uncertain.order_errors[0].code == "wb_pending_confirmation"
        fail = False
        recovered = await print_tape(session, async_client, seed)
        assert recovered.orders and not recovered.order_errors
        assert calls.count("put") == 1
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        assert (
            await session.scalar(
                select(MarkingCode.status).where(
                    MarkingCode.cis_code == recovered.orders[0].codes[0],
                )
            )
            == "printed"
        )
        assert await session.scalar(select(FbsWbOperation.state)) == "confirmed"
        fail = True
        repeated = await print_tape(session, async_client, seed)
        assert repeated.orders and not repeated.order_errors
        assert repeated.orders[0].codes == recovered.orders[0].codes
        assert calls.count("put") == 1
        operation_id = await session.scalar(select(FbsWbOperation.id))
        # A later incomplete WB response invalidates the local positive verdict.
        monkeypatch.setattr(
            tape.marking_svc, "fetch_marketplace_orders_meta_batch", AsyncMock(return_value=[]),
        )
        await tape.marking_svc.sync_order_marking_statuses(
            session, seed.tenant_id, seed.order_ids[0], async_client, actor_user_id=seed.user_id,
        )
        await session.commit()
        monkeypatch.setattr(tape.marking_svc, "fetch_marketplace_orders_meta_batch", get)
        second_uncertain = await print_tape(session, async_client, seed)
        assert second_uncertain.order_errors[0].code == "wb_pending_confirmation"
        operation = await session.scalar(select(FbsWbOperation))
        assert operation.id == operation_id and operation.state == "pending_confirmation"
        assert operation.confirmed_at is None and operation.failed_at is None
        fail = False
        second_recovery = await print_tape(session, async_client, seed)
        assert second_recovery.orders and not second_recovery.order_errors
        assert second_recovery.orders[0].codes == recovered.orders[0].codes
        assert calls.count("put") == 2
        assert await session.scalar(select(func.count()).select_from(FbsWbOperation)) == 1
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        assert operation.state == "confirmed"


@pytest.mark.asyncio
async def test_postgres_metadata_poll_and_tape_use_same_order_lock_order(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import text
    from test_fbs_order_tape_concurrency import wait_for_row_lock

    from app.services import fbs_autopoll_service as poll
    from app.services import wildberries_fbs_client as wb_client
    from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow

    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as session:
        for i in range(2):
            assert (await print_tape(session, async_client, seed, i)).orders
        orders = list((await session.scalars(select(FbsOrder).order_by(FbsOrder.id))).all())
        target = poll.SellerPollTarget(seed.tenant_id, orders[0].seller_id)
        meta = []
        for i, order in enumerate(orders):
            order.created_at_wb = datetime.now(UTC) - timedelta(days=i)
            value = await session.scalar(
                select(FbsOrderMarking.value).where(
                    FbsOrderMarking.order_id == order.id,
                )
            )
            meta.append(
                MarketplaceOrderMetaRow(
                    order_id=order.wb_order_id,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision="filled"),
                    ),
                )
            )
        await session.commit()
    monkeypatch.setattr(
        wb_client, "fetch_marketplace_orders_meta_batch", AsyncMock(return_value=meta)
    )
    locked, proceed = asyncio.Event(), asyncio.Event()
    original_sync = tape.marking_svc._sync_order_meta_from_wb
    visited = []

    async def pause_first(session, order, *args, **kwargs):
        result = await original_sync(session, order, *args, **kwargs)
        if kwargs.get("meta_batch") is not None:
            visited.append(order.id)
            if len(visited) == 1:
                locked.set()
                await proceed.wait()
        return result

    monkeypatch.setattr(tape.marking_svc, "_sync_order_meta_from_wb", pause_first)
    async with SessionLocal() as background, SessionLocal() as printer:

        async def sync():
            result = await poll.sync_marking_statuses_for_assembling_supplies(
                background,
                target,
                async_client,
            )
            await background.commit()
            return result

        pending = asyncio.create_task(sync())
        printing = None
        try:
            await asyncio.wait_for(locked.wait(), 5)
            pid = await printer.scalar(text("select pg_backend_pid()"))
            printing = asyncio.create_task(print_tape(printer, async_client, seed))
            await wait_for_row_lock(pid)
            proceed.set()
            assert await asyncio.wait_for(pending, 5) == 2
            result = await asyncio.wait_for(printing, 5)
            assert result.orders and not result.order_errors
            assert visited == sorted(seed.order_ids)
        finally:
            proceed.set()
            running = [task for task in (pending, printing) if task is not None]
            for task in running:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*running, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
async def test_metadata_get_does_not_overwrite_a_new_binding_after_http(
    background: bool,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import fbs_autopoll_service as poll
    from app.services import fbs_kiz_service as kiz
    from app.services import wildberries_fbs_client as wb_client

    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as initial:
        assert (await print_tape(initial, async_client, seed)).orders
        printed_wb_id = await initial.scalar(select(FbsOrder.wb_order_id).where(
            FbsOrder.id == seed.order_ids[0],
        ))
    fetching, proceed = asyncio.Event(), asyncio.Event()
    original_get = tape.marking_svc.fetch_marketplace_orders_meta_batch

    async def delayed(*args, **kwargs):
        # The single-order WB fake must target the printed order in a batch too.
        kwargs["order_ids"] = [printed_wb_id]
        result = await original_get(*args, **kwargs)
        fetching.set()
        await proceed.wait()
        return result

    monkeypatch.setattr(
        wb_client if background else tape.marking_svc,
        "fetch_marketplace_orders_meta_batch", delayed,
    )
    async with SessionLocal() as reader, SessionLocal() as writer:
        seller_id = await reader.scalar(select(FbsOrder.seller_id).where(
            FbsOrder.id == seed.order_ids[0],
        ))
        reading = asyncio.create_task(
            poll.sync_marking_statuses_for_assembling_supplies(
                reader, poll.SellerPollTarget(seed.tenant_id, seller_id), async_client,
            ) if background else tape.marking_svc.sync_order_marking_statuses(
                reader,
                seed.tenant_id,
                seed.order_ids[0],
                async_client,
                actor_user_id=seed.user_id,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)
            await asyncio.wait_for(
                kiz.cancel_order_kiz(
                    writer,
                    seed.tenant_id,
                    seed.user_id,
                    seed.order_ids[0],
                    async_client,
                ),
                5,
            )
            monkeypatch.setattr(
                tape.marking_svc,
                "fetch_marketplace_orders_meta_batch",
                original_get,
            )
            replaced = await asyncio.wait_for(print_tape(writer, async_client, seed), 5)
            assert replaced.orders and not replaced.order_errors
            assert not reading.done()
            proceed.set()
            current = await asyncio.wait_for(reading, 5)
            if background:
                current = await tape.marking_svc.list_order_markings(
                    reader, seed.tenant_id, seed.order_ids[0],
                )
            assert len(current) == 1 and current[0].value == replaced.orders[0].codes[0]
            assert current[0].meta_status == "accepted"
            await reader.commit()
        finally:
            proceed.set()
            if not reading.done():
                reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        statuses = dict(
            (
                await session.execute(
                    select(MarkingCode.status, func.count()).group_by(MarkingCode.status)
                )
            ).all()
        )
        assert statuses == {"void": 1, "printed": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("new_status", ["ship_available", "validation_in_process"])
async def test_ozon_delayed_status_preserves_replacement(
    db_session, monkeypatch, new_status,
):
    from test_fbs_ozon_lane import _seed_ozon_supply_case, _seed_physical_ozon_packaging

    from app.models.fbs_order import FbsOrderProduct
    from app.services import fbs_kiz_service as kiz
    from app.services import ozon_kiz_service as ozon_kiz
    from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

    if engine.dialect.name != "postgresql":
        pytest.skip("Requires independent PostgreSQL transactions")
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    await _seed_physical_ozon_packaging(db_session, order, supply, [(product, 1)])
    order.required_meta_json = ["sgtin"]
    position = FbsOrderProduct(
        order_id=order.id, product_id=product.id,
        position_index=0, ozon_sku=3001, quantity=1,
    )
    db_session.add(position)
    await db_session.commit()
    transport = FakeMarketplaceTransport(endpoint_responses={
        "/v6/fbs/posting/product/exemplar/create-or-get": {
            "posting_number": order.external_order_id,
            "products": [{"product_id": 3001, "exemplars": [{"exemplar_id": 81}]}],
        },
        "/v5/fbs/posting/product/exemplar/validate": {
            "products": [{"product_id": 3001, "valid": True, "exemplars": []}],
        },
        "/v6/fbs/posting/product/exemplar/set": {},
        "/v5/fbs/posting/product/exemplar/status": {
            "posting_number": order.external_order_id,
            "status": "ship_available", "products": [],
        },
    })
    provider = OzonMarketplaceProvider(transport=transport)
    await ozon_kiz.commit_ozon_kiz(
        db_session, order, "010460123456789021OLD", False, None, AsyncMock(), provider,
    )
    await db_session.commit()
    stale_status = "validation_in_process" if new_status == "ship_available" else "ship_available"
    stale_provider = OzonMarketplaceProvider(transport=FakeMarketplaceTransport(
        endpoint_responses={"/v5/fbs/posting/product/exemplar/status": {
            "posting_number": order.external_order_id, "status": stale_status, "products": [],
        }},
    ))
    fetching, proceed = asyncio.Event(), asyncio.Event()
    original_read = tape.marking_svc.read_marking_status

    async def delayed(**kwargs):
        result = await original_read(**kwargs)
        fetching.set()
        await proceed.wait()
        return result

    monkeypatch.setattr(tape.marking_svc, "read_marking_status", delayed)
    async with SessionLocal() as reader, SessionLocal() as writer:
        reading = asyncio.create_task(tape.marking_svc.sync_order_marking_statuses(
            reader, tenant.id, order.id, AsyncMock(), actor_user_id=None,
            ozon_provider=stale_provider,
        ))
        try:
            await asyncio.wait_for(fetching.wait(), 5)
            transport.endpoint_responses["/v5/fbs/posting/product/exemplar/status"] = {
                "posting_number": order.external_order_id, "status": new_status, "products": [],
            }
            current_order = await kiz._get_order_for_kiz(
                writer, tenant.id, order.id, for_update=True,
            )
            await asyncio.wait_for(ozon_kiz.commit_ozon_kiz(
                writer, current_order, "010460123456789021NEW", True, None, AsyncMock(), provider,
            ), 5)
            await writer.commit()
            replacement = await writer.scalar(select(FbsOrderMarking).where(
                FbsOrderMarking.order_id == order.id,
            ))
            replacement_id = replacement.id
            expected = "accepted" if new_status == "ship_available" else "pending"
            assert replacement.meta_status == expected
            proceed.set()
            rows = await asyncio.wait_for(reading, 5)
            assert [(row.id, row.meta_status) for row in rows] == [(replacement_id, expected)]
            await reader.commit()
        finally:
            proceed.set()
            if not reading.done():
                reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)
    async with SessionLocal() as check:
        refreshed = await check.get(FbsOrder, order.id)
        assert refreshed.metadata_delivery_allowed is (new_status == "ship_available")
