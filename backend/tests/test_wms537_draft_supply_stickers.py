"""WMS-537: a draft FBS supply must prefetch stickers of added WB orders too.

Background: the owner reported that orders added to AVpack's draft supply
never picked up their WB sticker until the operator pressed "Start work" or
printed manually. WMS-475 already made ``add_orders_to_existing_supply``
request the sticker of a just-confirmed added order, but only guarded it with
``if supply.status != FBS_SUPPLY_STATUS_DRAFT`` — a draft supply was skipped
on purpose, because WMS-475's own scope was limited to a supply "по которой
работа уже начата". WMS-537 removes that branch: a draft behaves exactly like
a supply already being worked on.

``tests/test_wms475_added_order_stickers.py`` already exercises the
happy-path prefetch for a fresh draft (its ``draft`` scenario) plus the
non-draft failure/partial/retry scenarios. This file adds the combinations
that file does not cover: the same prefetch across every editable WB supply
status (draft/assembling/packed — R2), a draft that already carries a
packaging task from a prior cancel-and-detach (R1, R2), WB failures reached
specifically while the supply is still a draft plus the existing recovery
path (R3), a partial WB confirmation while still a draft (R1, R3), the
idempotent-repeat and later "start work"/"add more orders" sequence acting
only on orders still missing a code (R4), cancelled orders never being asked
for a sticker (R5), a genuine concurrent add of the same order on PostgreSQL
(R4), and that an Ozon supply's add-orders rejection still precedes any
marketplace call (R6).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_SUPPLY,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.marketplace_account import MarketplaceAccount
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_print_asset_service as print_assets
from app.services import fbs_supply_service as supplies
from app.services.fbs_supply_validator_service import SupplyPreflightResult
from app.services.integration_fernet import encrypt_secret
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_supply_from_orders import (
    _create_product,
    _create_ready_order,
    _register_ff_admin,
    _setup_seller_with_token,
)

# ---------------------------------------------------------------------------
# C2 — the same prefetch rule holds for every editable WB supply status.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_status", ["draft", "assembling", "packed"])
async def test_prefetch_is_identical_across_editable_supply_statuses(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, target_status: str
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c2-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537101,
    )
    order_b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537102,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": f"C2 {target_status}",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    if target_status == "assembling":
        started = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
        )
        assert started.status_code == 200, started.text
    elif target_status == "packed":
        async with SessionLocal() as session:
            supply_row = await session.get(FbsSupply, uuid.UUID(supply_id))
            assert supply_row is not None
            supply_row.status = FBS_SUPPLY_STATUS_PACKED
            await session.commit()

    batch_order_ids: list[list[uuid.UUID]] = []
    real_batch = print_assets.request_supply_print_batch

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_b)], "idempotency_key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, resp.text
    assert len(batch_order_ids) == 1
    assert batch_order_ids[0] == [order_b]
    workspace = resp.json()
    b_row = next(row for row in workspace["orders"] if row["wb_order_id"] == 537102)
    assert b_row["sticker"]["code"]
    a_row = next(row for row in workspace["orders"] if row["wb_order_id"] == 537101)
    if target_status == "draft":
        # A was never requested by this action — it has no code either way,
        # since it wasn't touched by "start work" in this scenario.
        assert a_row["sticker"]["code"] is None
    # The status this action started with must be exactly what it ends with;
    # adding orders and prefetching stickers is not allowed to move the
    # supply along the WB FBS pipeline on its own (R2).
    assert workspace["supply"]["status"] == target_status


# ---------------------------------------------------------------------------
# C3 — a draft that already carries a packaging task (post cancel-and-detach)
# behaves the same as a plain draft.
# ---------------------------------------------------------------------------


async def test_draft_with_retained_packaging_task_prefetches_added_order(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c3-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537201,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C3 draft with packaging task",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = uuid.UUID(created.json()["supply"]["id"])

    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
    )
    assert started.status_code == 200, started.text
    packaging_task_id = started.json()["supply"]["packaging_task_id"]
    assert packaging_task_id is not None

    # Simulate the end-state of `detach_cancelled_order_from_supply`: the only
    # order left is gone, the supply falls back to `draft`, but the packaging
    # task it already created is not reset (see fbs_packaging_integration_service).
    async with SessionLocal() as session:
        order_row = await session.get(FbsOrder, order_a)
        assert order_row is not None
        order_row.supply_id = None
        supply_row = await session.get(FbsSupply, supply_id)
        assert supply_row is not None
        supply_row.status = FBS_SUPPLY_STATUS_DRAFT
        await session.commit()

    order_e = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537202,
    )

    batch_order_ids: list[list[uuid.UUID]] = []
    real_batch = print_assets.request_supply_print_batch

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_e)], "idempotency_key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, resp.text
    assert len(batch_order_ids) == 1
    assert batch_order_ids[0] == [order_e]
    workspace = resp.json()
    assert workspace["supply"]["status"] == "draft"
    assert workspace["supply"]["packaging_task_id"] == packaging_task_id
    e_row = next(row for row in workspace["orders"] if row["wb_order_id"] == 537202)
    assert e_row["sticker"]["code"]


# ---------------------------------------------------------------------------
# C5 — a WB/print failure while still a draft does not break the add, and the
# existing recovery paths (start-work / retry) still pick the sticker up.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failure", ["transport_error", "missing", "asset_error", "storage_write"])
async def test_draft_sticker_failure_does_not_break_the_add_and_recovers_later(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    sku = f"c5-{failure[:4]}-{suffix[-6:]}"
    product = await _create_product(async_client, headers, seller_id, sku=sku)
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537301,
    )
    order_b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537302,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": f"C5 {failure}",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    real_fetch = print_assets.fetch_marketplace_order_stickers
    real_batch = print_assets.request_supply_print_batch
    real_add = supplies._execute_wb_batch_add
    wb_add_calls: list[list[int]] = []
    storage_failure = failure == "storage_write"
    real_write_bytes = Path.write_bytes
    if storage_failure:

        def fail_write(path: Path, *args: Any, **kwargs: Any) -> Any:
            if "fbs-print-assets/order-stickers" in str(path):
                raise OSError("Test storage unavailable")
            return real_write_bytes(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_bytes", fail_write)

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        if failure == "asset_error":
            raise print_assets.FbsPrintAssetError(
                "missing_marketplace_token", message="Unavailable"
            )
        return await real_batch(*args, **kwargs)

    async def fetch_stickers(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        if failure == "transport_error":
            raise WildberriesClientError("transport_error")
        rows = await real_fetch(*args, **kwargs)
        if failure == "missing":
            rows = [row for row in rows if row["orderId"] != 537302]
        for row in rows:
            row["partA"] = "703"
            row["partB"] = "0091"
        return rows

    async def track_add(*args: Any, **kwargs: Any) -> None:
        wb_add_calls.append(kwargs["wb_order_ids"])
        await real_add(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)
    monkeypatch.setattr(print_assets, "fetch_marketplace_order_stickers", fetch_stickers)
    monkeypatch.setattr(supplies, "_execute_wb_batch_add", track_add)

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_b)], "idempotency_key": str(uuid.uuid4())},
    )
    # The already-confirmed WB add must not be undone by a sticker failure.
    assert resp.status_code == 200, resp.text
    assert len(wb_add_calls) == 1
    workspace = resp.json()
    assert workspace["supply"]["status"] == "draft"
    b_row = next(row for row in workspace["orders"] if row["wb_order_id"] == 537302)
    assert b_row["sticker"]["code"] is None
    async with SessionLocal() as session:
        order_row = await session.get(FbsOrder, order_b)
        assert order_row is not None
        assert str(order_row.supply_id) == supply_id
        assert order_row.sticker_code is None

    # Recover through the existing "Start work" path: it must not re-add B to
    # WB a second time, and must fetch exactly the still-missing sticker.
    if storage_failure:
        monkeypatch.setattr(Path, "write_bytes", real_write_bytes)
    monkeypatch.setattr(print_assets, "request_supply_print_batch", real_batch)
    monkeypatch.setattr(print_assets, "fetch_marketplace_order_stickers", real_fetch)
    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
    )
    assert started.status_code == 200, started.text
    assert len(wb_add_calls) == 1
    recovered_b = next(
        row for row in started.json()["orders"] if row["wb_order_id"] == 537302
    )
    assert recovered_b["sticker"]["code"]


# ---------------------------------------------------------------------------
# C6 — a partial WB confirmation while still a draft only requests the
# accepted order; the rejected one never gets linked or asked for a sticker.
# ---------------------------------------------------------------------------


async def test_draft_partial_confirmation_requests_only_the_accepted_order(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.fbs_wb_operation import WB_OPERATION_STATE_PENDING_CONFIRMATION

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c6-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537401,
    )
    order_b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537402,
    )
    order_c = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537403,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C6 partial in draft",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    batch_order_ids: list[list[uuid.UUID]] = []
    real_batch = print_assets.request_supply_print_batch

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    async def partial_confirmation(*args: Any, **kwargs: Any) -> tuple[str, set[int]]:
        # Only B is confirmed by WB; C is rejected.
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, {537401, 537402}

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)
    monkeypatch.setattr(supplies, "reconcile_supply_orders", partial_confirmation)

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={
            "order_ids": [str(order_b), str(order_c)],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(batch_order_ids) == 1
    assert batch_order_ids[0] == [order_b]
    workspace = resp.json()
    assert workspace["partial_rejection"]["rejected_orders"][0]["wb_order_id"] == 537403
    b_row = next(row for row in workspace["orders"] if row["wb_order_id"] == 537402)
    assert b_row["sticker"]["code"]
    assert workspace["supply"]["status"] == "draft"
    async with SessionLocal() as session:
        rejected = await session.get(FbsOrder, order_c)
        assert rejected is not None and rejected.supply_id is None


# ---------------------------------------------------------------------------
# C7 — repeat add is still a 409 with no duplicate WB add; a later "start
# work" or another add only ever requests orders still missing a code.
# ---------------------------------------------------------------------------


async def test_repeat_add_then_start_work_then_more_orders_only_request_missing(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c7-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537501,
    )
    order_b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537502,
    )
    order_d = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537503,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C7 repeat",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    # A itself never got a code (created straight from-orders, no start-work
    # yet), matching C1's "A has no code" setup.
    async with SessionLocal() as session:
        a_row = await session.get(FbsOrder, order_a)
        assert a_row is not None
        assert a_row.sticker_code is None

    batch_order_ids: list[list[uuid.UUID]] = []
    real_batch = print_assets.request_supply_print_batch

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)

    add_key = str(uuid.uuid4())
    first = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_b)], "idempotency_key": add_key},
    )
    assert first.status_code == 200, first.text
    assert batch_order_ids == [[order_b]]
    b_code = next(
        row for row in first.json()["orders"] if row["wb_order_id"] == 537502
    )["sticker"]["code"]
    assert b_code

    # Same request repeated: existing conflict behavior, no second add.
    repeated = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_b)], "idempotency_key": add_key},
    )
    assert repeated.status_code == 409, repeated.text
    assert batch_order_ids == [[order_b]]

    # "Start work" only asks for A (still missing), not B (already has a code).
    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
    )
    assert started.status_code == 200, started.text
    assert len(batch_order_ids) == 2
    assert batch_order_ids[1] == [order_a]
    b_after_start = next(
        row for row in started.json()["orders"] if row["wb_order_id"] == 537502
    )
    assert b_after_start["sticker"]["code"] == b_code

    # Adding D only requests D — B and A are untouched.
    added_d = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_d)], "idempotency_key": str(uuid.uuid4())},
    )
    assert added_d.status_code == 200, added_d.text
    assert len(batch_order_ids) == 3
    assert batch_order_ids[2] == [order_d]
    workspace = added_d.json()
    b_final = next(row for row in workspace["orders"] if row["wb_order_id"] == 537502)
    assert b_final["sticker"]["code"] == b_code

    async with SessionLocal() as session:
        for order_id in (order_a, order_b, order_d):
            count = await session.scalar(
                select(FbsPrintAsset)
                .where(
                    FbsPrintAsset.fbs_order_id == order_id,
                    FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
                    FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
                )
                .exists()
                .select()
            )
            assert count, order_id


# ---------------------------------------------------------------------------
# C8 — a genuine race for the same order in the same draft supply: one add
# wins, the other gets the existing rejection, and WB/the sticker are only
# touched once. Needs PostgreSQL row locking (WMS_TEST_DATABASE_URL).
# ---------------------------------------------------------------------------


@pytest.mark.postgresql_concurrency
async def test_concurrent_add_of_the_same_order_to_a_draft_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "sqlite" in os.environ.get("DATABASE_URL", "").lower():
        pytest.skip("row-level FOR UPDATE locking requires PostgreSQL")

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c8-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537601,
    )
    order_x = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537602,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C8 race",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    real_batch = print_assets.request_supply_print_batch
    real_add = supplies._execute_wb_batch_add
    batch_order_ids: list[list[uuid.UUID]] = []
    wb_add_calls: list[list[int]] = []

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        if kwargs["order_ids"]:
            batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    async def track_add(*args: Any, **kwargs: Any) -> None:
        wb_add_calls.append(kwargs["wb_order_ids"])
        await real_add(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)
    monkeypatch.setattr(supplies, "_execute_wb_batch_add", track_add)

    resp_a, resp_b = await asyncio.gather(
        async_client.post(
            f"/operations/fbs-supplies/{supply_id}/orders/batch",
            headers=headers,
            json={"order_ids": [str(order_x)], "idempotency_key": str(uuid.uuid4())},
        ),
        async_client.post(
            f"/operations/fbs-supplies/{supply_id}/orders/batch",
            headers=headers,
            json={"order_ids": [str(order_x)], "idempotency_key": str(uuid.uuid4())},
        ),
    )
    statuses = sorted([resp_a.status_code, resp_b.status_code])
    assert statuses == [200, 409], (resp_a.text, resp_b.text)
    assert len(wb_add_calls) == 1
    assert batch_order_ids == [[order_x]]

    async with SessionLocal() as session:
        order_row = await session.get(FbsOrder, order_x)
        assert order_row is not None
        assert str(order_row.supply_id) == supply_id
        assert order_row.status == FBS_ORDER_STATUS_IN_SUPPLY
        assert order_row.sticker_code
        ready_count = await session.scalar(
            select(FbsPrintAsset.id).where(
                FbsPrintAsset.fbs_order_id == order_x,
                FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
                FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
            )
        )
        assert ready_count is not None
        rows = (
            await session.execute(
                select(FbsPrintAsset).where(
                    FbsPrintAsset.fbs_order_id == order_x,
                    FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
                    FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
                )
            )
        ).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# C9 — cancelled orders never get a sticker requested for them.
# ---------------------------------------------------------------------------


async def test_cancelled_order_cannot_be_added_to_a_draft_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c9a-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537701,
    )
    order_cancelled = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537702,
    )
    async with SessionLocal() as session:
        cancelled_row = await session.get(FbsOrder, order_cancelled)
        assert cancelled_row is not None
        cancelled_row.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()

    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C9a cancelled",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    wb_add_calls: list[list[int]] = []
    monkeypatch.setattr(
        supplies,
        "_execute_wb_batch_add",
        lambda *a, **k: wb_add_calls.append(k.get("wb_order_ids")),
    )
    batch_calls: list[Any] = []
    monkeypatch.setattr(
        print_assets,
        "request_supply_print_batch",
        lambda *a, **k: batch_calls.append(k),
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_cancelled)], "idempotency_key": str(uuid.uuid4())},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "order_incompatible"
    assert wb_add_calls == []
    assert batch_calls == []


async def test_cancelled_order_already_in_draft_is_not_requested_when_adding_another(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"c9b-{suffix[-6:]}")
    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537801,
    )
    order_e = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=537802,
    )
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "C9b cancelled in draft",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]

    # A is already in the draft, cancelled, without a sticker code — a stray
    # order the operator has not detached yet.
    async with SessionLocal() as session:
        a_row = await session.get(FbsOrder, order_a)
        assert a_row is not None
        a_row.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()

    batch_order_ids: list[list[uuid.UUID]] = []
    real_batch = print_assets.request_supply_print_batch
    real_fetch = print_assets.fetch_marketplace_order_stickers
    wb_fetch_calls: list[list[int]] = []

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        return await real_batch(*args, **kwargs)

    async def track_fetch(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        wb_fetch_calls.append(list(kwargs.get("order_ids", [])))
        return await real_fetch(*args, **kwargs)

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)
    monkeypatch.setattr(print_assets, "fetch_marketplace_order_stickers", track_fetch)

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch",
        headers=headers,
        json={"order_ids": [str(order_e)], "idempotency_key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, resp.text
    assert batch_order_ids == [[order_e]]
    assert all(537701 not in chunk for chunk in wb_fetch_calls)

    # A subsequent "start work" answers the cancelled order with the existing
    # `order_cancelled` error, without ever asking WB for it.
    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
    )
    assert started.status_code == 200, started.text
    assert all(537701 not in chunk for chunk in wb_fetch_calls)


# ---------------------------------------------------------------------------
# C10 — Ozon supplies are unaffected: the rejection stands before any WB or
# Ozon marketplace call, and no sticker prefetch is attempted. (The exact
# issue code turns out to be `order_incompatible`/`different_marketplace`
# from the composition check, not literally `marketplace_not_supported` —
# see the assertion below and the report to the lead for the detail.)
# ---------------------------------------------------------------------------


async def _ozon_supply_with_one_order(
    db_session: AsyncSession,
) -> tuple[Tenant, FbsSupply, FbsOrder]:
    tenant = Tenant(name="Ozon draft add", slug=f"ozon-draft-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(
        tenant=tenant,
        name="FBS",
        code=f"ozon-draft-{uuid.uuid4().hex[:8]}",
    )
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="ozon",
        external_supply_id="ozon-draft-supply-1",
        wb_supply_id="ozon-draft-supply-1",
        name="Ozon draft",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        supply=supply,
        marketplace="ozon",
        external_order_id="ozon-draft-posting-1",
        wb_order_id=9001,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add_all([tenant, seller, warehouse, supply, order])
    await db_session.flush()
    db_session.add(
        MarketplaceAccount(
            tenant_id=tenant.id,
            seller_id=seller.id,
            marketplace="ozon",
            account_slot="primary",
            external_account_id="ozon-client",
            secret_encrypted=encrypt_secret("ozon-key"),
            is_active=True,
            validation_status="valid",
        )
    )
    await db_session.commit()
    return tenant, supply, order


async def test_ozon_draft_add_is_rejected_before_any_marketplace_or_sticker_call(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, supply, _existing_order = await _ozon_supply_with_one_order(db_session)
    assert supply.status == FBS_SUPPLY_STATUS_DRAFT

    new_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=supply.seller_id,
        warehouse_id=supply.warehouse_id,
        marketplace="ozon",
        external_order_id="ozon-draft-posting-2",
        wb_order_id=9002,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(new_order)
    await db_session.flush()
    await db_session.commit()

    # Bypass the full compatibility preflight (stock/mapping/etc.) — it is
    # unrelated to this guard and not touched by WMS-537. What matters here
    # is only what happens *after* validation succeeds: does anything call
    # out to a marketplace or request a sticker before the Ozon rejection?
    async def fake_validate(*args: Any, **kwargs: Any) -> SupplyPreflightResult:
        return SupplyPreflightResult(
            compatible=True, summary=None, issues=(), orders=(new_order,)
        )

    monkeypatch.setattr(supplies, "validate_supply_composition", fake_validate)

    async def forbid_wb_add(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not add to WB for an Ozon supply")

    async def forbid_print_batch(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not request a sticker before the marketplace guard")

    monkeypatch.setattr(supplies, "_execute_wb_batch_add", forbid_wb_add)
    monkeypatch.setattr(print_assets, "request_supply_print_batch", forbid_print_batch)

    http_client = httpx.AsyncClient()
    try:
        with pytest.raises(supplies.FbsSupplyError) as caught:
            await supplies.add_orders_to_existing_supply(
                db_session,
                tenant.id,
                supply.id,
                [new_order.id],
                idempotency_key=str(uuid.uuid4()),
                actor_user_id=None,
                http_client=http_client,
            )
    finally:
        await http_client.aclose()

    # This runs entirely before the code WMS-537 touches, so it is a
    # regression guard rather than new behavior. Verified empirically: today
    # `_existing_supply_issues` -> `supply_order_link_discrepancy` rejects any
    # non-WB supply with `different_marketplace` (it was written assuming a
    # WB composition), so the outer error is `order_incompatible`, not the
    # `marketplace_not_supported` the explicit `is_wildberries` guard further
    # down would raise on its own. Either way the add is refused before any
    # marketplace or sticker call, which is what R6 actually requires.
    assert caught.value.http_status == 409
    assert caught.value.code == "order_incompatible"
    issues = caught.value.context["issues"] if caught.value.context else []
    assert any(issue["code"] == "different_marketplace" for issue in issues)
    async with SessionLocal() as session:
        refreshed = await session.get(FbsOrder, new_order.id)
        assert refreshed is not None
        assert refreshed.supply_id is None
        assert refreshed.sticker_code is None
