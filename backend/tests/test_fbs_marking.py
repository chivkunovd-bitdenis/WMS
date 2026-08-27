from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    META_STATUS_UNKNOWN,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import reset_mock_marketplace_order_meta
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS marking {suffix}",
            "slug": f"fbs-marking-{suffix}",
            "admin_email": f"fbs-marking-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _setup_seller_with_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[str, str, uuid.UUID]:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    reg = await async_client.get("/auth/me", headers=headers)
    assert reg.status_code == 200
    tenant_id = uuid.UUID(reg.json()["tenant_id"])
    return seller_id, warehouse.json()["id"], tenant_id


def _wb_order_row(
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID, **extra: Any
) -> dict[str, Any]:
    row = {
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
    row.update(extra)
    return row


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    status: str | None = None,
    wb_row_extra: dict[str, Any] | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        row = _wb_order_row(order_id=order_id, **(wb_row_extra or {}))
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            row,
        )
        if status is not None:
            order.status = status
        await session.commit()
        return order.id


@pytest.fixture
def enable_wb_marketplace_marking_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)
    reset_mock_marketplace_order_meta()


# TC-NEW-FBS-MARK-002 — sync updates check_status from official batch meta
@pytest.mark.asyncio
async def test_fbs_marking_sync_updates_check_status(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=920001,
        status=FBS_ORDER_STATUS_PACKED,
    )
    cis = "01CIS-SYNC-001"
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=cis,
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    from app.services.wildberries_fbs_client import (
        MarketplaceMetaDetail,
        MarketplaceOrderMetaRow,
    )

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [920001]
        return [
            MarketplaceOrderMetaRow(
                order_id=920001,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin",
                        value=cis,
                        decision="pending",
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text
    rows = sync.json()
    assert len(rows) == 1
    assert rows[0]["check_status"] == CHECK_STATUS_CHECKING


# TC-NEW-FBS-MARK-004 — GET list all kinds; empty → []
@pytest.mark.asyncio
async def test_fbs_marking_get_list_all_kinds(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=940001,
        status=FBS_ORDER_STATUS_PACKED,
    )

    empty = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    async with SessionLocal() as session:
        session.add_all(
            [
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind=kind,
                    value=value,
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
                for kind, value in (
                    ("sgtin", "01CIS-A"),
                    ("sgtin", "01CIS-B"),
                    ("imei", "356938035643809"),
                )
            ]
        )
        await session.commit()

    listed = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 3
    kinds = {row["kind"] for row in rows}
    assert kinds == {"sgtin", "imei"}
    values = {row["value"] for row in rows}
    assert values == {"01CIS-A", "01CIS-B", "356938035643809"}


# TC-14 — metadata gate: rejected blocks; allowed_without_check continues
@pytest.mark.asyncio
async def test_fbs_metadata_gate_rejected_blocks_allowed_without_check_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.fbs_marking_service import compute_delivery_allowed

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960201,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )

    meta = await async_client.get(
        f"/operations/fbs-orders/{order_id}/metadata",
        headers=headers,
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["required"] == ["sgtin"]
    assert meta.json()["delivery_allowed"] is False

    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.required_meta_json = ["sgtin"]
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-REJECTED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_REJECTED,
                reason="invalid_kiz",
            )
        )
        await session.commit()
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is False

    async with SessionLocal() as session:
        await session.execute(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        for row in (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
        ).scalars():
            await session.delete(row)
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-ALLOWED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ALLOWED_WITHOUT_CHECK,
                meta_details_json={"decision": "optional", "reason": None},
            )
        )
        await session.commit()
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is True


def test_fbs_metadata_gate_pending_blocks_filled_allows() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import (
        compute_delivery_allowed,
        derive_meta_status,
    )

    order = SimpleNamespace(required_meta_json=["sgtin"])
    pending = SimpleNamespace(
        kind="sgtin",
        value="01CIS-PENDING",
        meta_status=META_STATUS_PENDING,
        meta_details_json={"decision": "pending", "reason": None},
        reason=None,
    )
    assert compute_delivery_allowed(order, [pending]) is False
    assert (
        derive_meta_status(
            check_status=None,
            decision="filled",
            has_value=True,
        )
        == META_STATUS_ACCEPTED
    )
    filled = SimpleNamespace(
        kind="sgtin",
        value="01CIS-FILLED",
        meta_status=META_STATUS_ACCEPTED,
        meta_details_json={"decision": "filled", "reason": None},
        reason=None,
    )
    assert compute_delivery_allowed(order, [filled]) is True
    filled.meta_details_json = {"decision": "filled", "reason": "uinBadStatus"}
    assert compute_delivery_allowed(order, [filled]) is False
    filled.meta_status = META_STATUS_REPLACEMENT_REQUIRED
    filled.meta_details_json = {
        "decision": "filled",
        "reason": None,
        "value": "01CIS-OTHER",
    }
    assert compute_delivery_allowed(order, [filled]) is False


@pytest.mark.asyncio
async def test_fbs_intake_stores_required_optional_meta(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960301,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )
    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.required_meta_json == ["sgtin"]
        assert order.optional_meta_json == ["imei"]


# TC-NEW-FBS-MARK-005 — batch polling keeps progressing after a local WB batch failure.
@pytest.mark.asyncio
async def test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing WB row or one failed batch must never become a local sync."""
    from app.services import fbs_autopoll_service as autopoll
    from app.services.fbs_autopoll_service import SellerPollTarget
    from app.services.wildberries_errors import WildberriesClientError
    from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    wb_order_ids = list(range(970000, 970201))
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            warehouse_id=warehouse_uuid,
            wb_supply_id=f"WB-BATCH-{suffix[-8:]}",
            name="Batch marking supply",
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        for index, wb_order_id in enumerate(wb_order_ids):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_order_id=wb_order_id,
                wb_rid=f"batch-rid-{wb_order_id}",
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply.id,
                created_at_wb=now + timedelta(seconds=index),
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsOrderMarking(
                    order_id=order.id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01BATCH{wb_order_id}",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
            )
        await session.commit()

    requested_batches: list[list[int]] = []
    completed_batches: list[list[int]] = []
    synced_wb_order_ids: list[int] = []
    omitted_wb_order_ids: list[int] = []
    notified_order_ids: list[uuid.UUID] = []
    active_batch_requests = 0
    max_active_batch_requests = 0

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal active_batch_requests, max_active_batch_requests
        active_batch_requests += 1
        max_active_batch_requests = max(max_active_batch_requests, active_batch_requests)
        requested_batches.append(order_ids)
        try:
            # Yield control so this test observes overlap if batches are ever
            # changed from sequential awaits to concurrently scheduled tasks.
            await asyncio.sleep(0)
            if len(requested_batches) == 2:
                raise WildberriesClientError("upstream_error")
            # The first response deliberately omits an order and reverses the rest:
            # matching must use order_id, not row position, and the omitted order is
            # not allowed to look like a successful local update.
            response_ids = order_ids[:-1] if len(requested_batches) == 1 else order_ids
            return [
                MarketplaceOrderMetaRow(order_id=order_id)
                for order_id in reversed(response_ids)
            ]
        finally:
            completed_batches.append(order_ids)
            active_batch_requests -= 1

    async def fake_sync(
        session: object,
        order: FbsOrder,
        http_client: object,
        token: str,
        *,
        meta_batch: list[MarketplaceOrderMetaRow] | None = None,
    ) -> list[object]:
        assert meta_batch is not None
        if meta_batch:
            assert [row.order_id for row in meta_batch] == [order.wb_order_id]
        else:
            omitted_wb_order_ids.append(order.wb_order_id)
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.id)
            )
            assert marking is not None
            marking.meta_status = META_STATUS_UNKNOWN
        synced_wb_order_ids.append(order.wb_order_id)
        return []

    async def fake_notify(
        session: object,
        tenant: uuid.UUID,
        order_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        assert actor_user_id is None
        notified_order_ids.append(order_id)

    async def fake_list_markings(
        session: object, tenant: uuid.UUID, order_id: uuid.UUID
    ) -> list[object]:
        return [object()]

    async def fake_token(session: object, tenant: uuid.UUID, seller: uuid.UUID) -> str:
        return "test-token"

    monkeypatch.setattr(
        "app.services.wildberries_fbs_client.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )
    monkeypatch.setattr("app.services.fbs_marking_service._sync_order_meta_from_wb", fake_sync)
    monkeypatch.setattr(
        "app.services.fbs_marking_service._notify_supply_marking_update", fake_notify
    )
    monkeypatch.setattr("app.services.fbs_marking_service.list_order_markings", fake_list_markings)
    monkeypatch.setattr("app.services.fbs_marking_service.require_marketplace_token", fake_token)

    async with SessionLocal() as session:
        synced = await autopoll.sync_marking_statuses_for_assembling_supplies(
            session,
            SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
            async_client,
        )
        omitted_marking = await session.scalar(
            select(FbsOrderMarking)
            .join(FbsOrder, FbsOrder.id == FbsOrderMarking.order_id)
            .where(FbsOrder.wb_order_id == wb_order_ids[99])
        )
        assert omitted_marking is not None
        assert omitted_marking.meta_status == META_STATUS_UNKNOWN

    assert [len(batch) for batch in requested_batches] == [100, 100, 1]
    assert all(len(batch) <= 100 and len(batch) == len(set(batch)) for batch in requested_batches)
    assert requested_batches == [wb_order_ids[:100], wb_order_ids[100:200], wb_order_ids[200:]]
    assert completed_batches == requested_batches
    assert max_active_batch_requests == 1
    expected_synced = wb_order_ids[:99] + wb_order_ids[200:]
    assert synced == len(expected_synced)
    assert set(synced_wb_order_ids) == set([*expected_synced, wb_order_ids[99]])
    assert omitted_wb_order_ids == [wb_order_ids[99]]
    assert len(notified_order_ids) == len(expected_synced)

    async with SessionLocal() as session:
        failed_batch_markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking)
                    .join(FbsOrder, FbsOrder.id == FbsOrderMarking.order_id)
                    .where(FbsOrder.wb_order_id.in_(wb_order_ids[100:200]))
                )
            ).scalars()
        )
    assert len(failed_batch_markings) == 100
    assert all(
        marking.check_status == CHECK_STATUS_NEW
        and marking.meta_status == META_STATUS_PENDING
        for marking in failed_batch_markings
    )
