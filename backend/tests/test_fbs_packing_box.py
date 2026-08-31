"""Physical FBS box API — a box is local, but (since 2026-08-17) every box also
gets a linked WB cargo place (trbx) + QR, for warehouse/SC exactly like PVZ.
See the module docstring in app/services/fbs_shipment_pvz_service.py for why
the old PVZ-only cargo-place restriction was dropped."""

from __future__ import annotations

import uuid
from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import PACK_STATUS_PACKED, FbsOrder
from app.models.fbs_packing_box import FbsPackingBox
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services.fbs_packing_box_service import (
    FbsPackingBoxError,
    get_delivery_box_readiness,
    set_boxes_without_distribution,
)
from app.services.fbs_supply_reconcile_service import OPERATION_KIND_CARGO_PLACES_CREATE
from app.services.fbs_workspace_service import (
    WorkspaceProgress,
    _compute_stage,
    _compute_workspace_blockers,
)
from app.services.wildberries_errors import WildberriesClientError
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py"
)
_migration_spec = spec_from_file_location(
    "fbs_boxes_without_distribution_migration", _MIGRATION_PATH
)
assert _migration_spec is not None and _migration_spec.loader is not None
_migration = module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(_migration)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


async def _packed_supply(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, list[uuid.UUID]]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    # Box creation now always registers a WB cargo place, so every caller of
    # _packed_supply needs a marketplace token — see enable_wb_marketplace_supplies_mock.
    token = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert token.status_code == 200, token.text
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"box-{suffix[-8:]}",
        barcode=f"2200{suffix[-9:]}",
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=[(1, timedelta(hours=3)), (2, timedelta(hours=4))],
        barcode=f"2200{suffix[-9:]}",
    )
    async with SessionLocal() as session:
        result = await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
        for order in result.scalars().all():
            order.pack_status = PACK_STATUS_PACKED
        await session.commit()
    return headers, supply_id, order_ids


# Warehouse/SC boxes stay local (an internal barcode, not sent to WB as such)
# but — like PVZ boxes — each one also gets its own WB cargo place (trbx) and
# QR sticker once created; that used to be PVZ-only, dropped on 2026-08-17
# (see module docstring).
@pytest.mark.asyncio
async def test_warehouse_boxes_get_cargo_places_and_orders_are_exclusive(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 2, "idempotency_key": "boxes-create-1"},
    )
    assert created.status_code == 201, created.text
    boxes = created.json()["boxes"]
    assert len(boxes) == 2
    assert [box["box_number"] for box in boxes] == [1, 2]
    assert all(box["barcode"].startswith("FBS-") for box in boxes)
    assert all(box["trbx_id"] is not None and box["wb_trbx_id"] is not None for box in boxes)
    assert all(box["qr_asset"] is not None for box in boxes)

    first = boxes[0]["id"]
    second = boxes[1]["id"]
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[1])
        assert order is not None
        order.pack_status = "pending"
        await session.commit()
    assigned_unpacked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[1])]},
    )
    assert assigned_unpacked.status_code == 200, assigned_unpacked.text
    assert assigned_unpacked.json()["boxes"][0]["assigned_order_ids"] == [
        str(order_ids[1])
    ]

    unpacked_duplicate = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{second}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[1])]},
    )
    assert unpacked_duplicate.status_code == 409, unpacked_duplicate.text
    assert unpacked_duplicate.json()["detail"]["code"] == "order_already_in_box"

    removed_unpacked = await async_client.delete(
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}/orders/{order_ids[1]}",
        headers=headers,
    )
    assert removed_unpacked.status_code == 200, removed_unpacked.text

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["boxes"][0]["assigned_order_ids"] == [str(order_ids[0])]

    duplicate = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{second}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "order_already_in_box"

    nonempty_delete = await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}",
        headers=headers,
        json={"idempotency_key": "boxes-delete-1"},
    )
    assert nonempty_delete.status_code == 409, nonempty_delete.text

    removed = await async_client.delete(
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}/orders/{order_ids[0]}",
        headers=headers,
    )
    assert removed.status_code == 200, removed.text
    deleted = await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}",
        headers=headers,
        json={"idempotency_key": "boxes-delete-1"},
    )
    assert deleted.status_code == 200, deleted.text
    assert len(deleted.json()["boxes"]) == 1


@pytest.mark.asyncio
async def test_unpacked_wb_orders_do_not_block_existing_distribution_boxes(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "unpacked-readiness-box"},
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        orders = list(
            (
                await session.scalars(
                    select(FbsOrder).where(FbsOrder.id.in_(order_ids))
                )
            ).all()
        )
        for order in orders:
            order.pack_status = "pending"
        await session.flush()
        readiness = await get_delivery_box_readiness(
            session,
            orders[0].tenant_id,
            supply_id,
            orders,
        )

    assert readiness.has_physical_boxes is True
    assert readiness.without_distribution is False
    assert readiness.unassigned_packed_order_ids == frozenset()


@pytest.mark.asyncio
async def test_box_creation_key_is_idempotent_and_rejects_different_count(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, supply_id, _ = await _packed_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/boxes"
    body = {"count": 1, "idempotency_key": "same-key"}

    first = await async_client.post(url, headers=headers, json=body)
    second = await async_client.post(url, headers=headers, json=body)
    conflict = await async_client.post(
        url,
        headers=headers,
        json={"count": 2, "idempotency_key": "same-key"},
    )
    mode_conflict = await async_client.post(
        url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": "same-key",
            "without_distribution": True,
        },
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["boxes"] == second.json()["boxes"]
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "idempotency_key_reused"
    assert mode_conflict.status_code == 409, mode_conflict.text
    assert mode_conflict.json()["detail"]["code"] == "idempotency_key_reused"


@pytest.mark.asyncio
async def test_box_creation_wb_409_cleans_local_boxes_and_same_key_can_retry(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, _ = await _packed_supply(async_client)
    original_create = pvz_svc.create_marketplace_supply_trbx
    attempts = 0

    async def reject_once_then_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WildberriesClientError("upstream_error", status_code=409)
        return await original_create(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", reject_once_then_create)
    url = f"/operations/fbs-supplies/{supply_id}/boxes"
    body = {"count": 1, "idempotency_key": "retry-after-wb-409"}

    rejected = await async_client.post(url, headers=headers, json=body)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"] == {
        "code": "box_create_rejected_by_wb",
        "message": (
            "Wildberries отклонил создание коробов. Обновите поставку и повторите; "
            "если ошибка сохранится, проверьте состояние поставки в кабинете WB."
        ),
        "context": {},
        "retryable": True,
    }
    async with SessionLocal() as session:
        assert await session.scalar(
            select(func.count(FbsPackingBox.id)).where(FbsPackingBox.supply_id == supply_id)
        ) == 0
        failed_operations = list(
            (
                await session.scalars(
                    select(FbsWbOperation).where(
                        FbsWbOperation.local_entity_id == supply_id,
                        FbsWbOperation.operation_kind == OPERATION_KIND_CARGO_PLACES_CREATE,
                    )
                )
            ).all()
        )
        assert [(item.state, item.error_code) for item in failed_operations] == [
            (WB_OPERATION_STATE_FAILED, "wb_upstream_error_409")
        ]

    retried = await async_client.post(url, headers=headers, json=body)
    assert retried.status_code == 201, retried.text
    assert len(retried.json()["boxes"]) == 1
    assert retried.json()["boxes"][0]["wb_trbx_id"] is not None
    async with SessionLocal() as session:
        operations = list(
            (
                await session.scalars(
                    select(FbsWbOperation).where(
                        FbsWbOperation.local_entity_id == supply_id,
                        FbsWbOperation.operation_kind == OPERATION_KIND_CARGO_PLACES_CREATE,
                    )
                )
            ).all()
        )
        assert {item.state for item in operations} == {
            WB_OPERATION_STATE_FAILED,
            WB_OPERATION_STATE_CONFIRMED,
        }
    assert attempts == 2


@pytest.mark.asyncio
async def test_box_retry_after_409_reconciles_timeout_with_same_operator_key(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, _ = await _packed_supply(async_client)
    remote_ids: list[str] = []
    attempts = 0

    async def reject_then_create_and_lose_response(
        *args: object, **kwargs: object
    ) -> list[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WildberriesClientError("upstream_error", status_code=409)
        if attempts == 2:
            remote_ids.append("WB-MP-RETRY-TIMEOUT")
            raise WildberriesClientError("transport_error")
        raise AssertionError("same operator key issued a blind third WB create")

    async def list_remote_ids(*args: object, **kwargs: object) -> list[str]:
        return list(remote_ids)

    monkeypatch.setattr(
        pvz_svc,
        "create_marketplace_supply_trbx",
        reject_then_create_and_lose_response,
    )
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", list_remote_ids)
    url = f"/operations/fbs-supplies/{supply_id}/boxes"
    body = {"count": 1, "idempotency_key": "retry-409-then-timeout"}

    rejected = await async_client.post(url, headers=headers, json=body)
    assert rejected.status_code == 409, rejected.text
    timed_out = await async_client.post(url, headers=headers, json=body)
    assert timed_out.status_code == 504, timed_out.text
    assert timed_out.json()["detail"]["code"] == "wb_timeout"
    async with SessionLocal() as session:
        states = list(
            (
                await session.scalars(
                    select(FbsWbOperation.state).where(
                        FbsWbOperation.local_entity_id == supply_id,
                        FbsWbOperation.operation_kind == OPERATION_KIND_CARGO_PLACES_CREATE,
                    )
                )
            ).all()
        )
        assert set(states) == {
            WB_OPERATION_STATE_FAILED,
            WB_OPERATION_STATE_PENDING_CONFIRMATION,
        }

    reconciled = await async_client.post(url, headers=headers, json=body)
    assert reconciled.status_code == 201, reconciled.text
    assert reconciled.json()["boxes"][0]["wb_trbx_id"] == "WB-MP-RETRY-TIMEOUT"
    assert attempts == 2
    async with SessionLocal() as session:
        states = list(
            (
                await session.scalars(
                    select(FbsWbOperation.state).where(
                        FbsWbOperation.local_entity_id == supply_id,
                        FbsWbOperation.operation_kind == OPERATION_KIND_CARGO_PLACES_CREATE,
                    )
                )
            ).all()
        )
        assert set(states) == {WB_OPERATION_STATE_FAILED, WB_OPERATION_STATE_CONFIRMED}


@pytest.mark.asyncio
async def test_without_distribution_boxes_do_not_accept_order_assignment(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": "boxes-without-distribution-1",
            "without_distribution": True,
        },
    )
    assert created.status_code == 201, created.text
    box = created.json()["boxes"][0]
    assert box["without_distribution"] is True
    assert box["assigned_order_ids"] == []

    async with SessionLocal() as session:
        stored_box = await session.get(FbsPackingBox, uuid.UUID(box["id"]))
        assert stored_box is not None
        assert (
            stored_box.creation_idempotency_key
            == "boxes-without-distribution-1"
        )

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box['id']}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 400, assigned.text
    assert assigned.json()["detail"]["code"] == "box_without_distribution"


@pytest.mark.asyncio
async def test_legacy_create_boxes_toggle_rejects_existing_assignment(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-006: the legacy create endpoint cannot bypass assignment guard."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "assigned-before-legacy-toggle"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]
    assigned = await async_client.post(
        f"{boxes_url}/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text
    legacy_toggle = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": "legacy-toggle-with-assignment",
            "without_distribution": True,
        },
    )
    assert legacy_toggle.status_code == 409, legacy_toggle.text
    assert legacy_toggle.json()["detail"]["code"] == "boxes_already_distributed"


@pytest.mark.asyncio
async def test_legacy_without_distribution_marker_still_blocks_assignment(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-007: pre-migration mode remains effective after deployment."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "legacy-compatible-box"},
    )
    assert created.status_code == 201, created.text
    box_id = uuid.UUID(created.json()["boxes"][0]["id"])

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        box = await session.get(FbsPackingBox, box_id)
        assert supply is not None and box is not None
        box.creation_idempotency_key = "no-distribution:legacy-compatible-box"
        await session.flush()
        await session.run_sync(
            lambda sync_session: _migration._backfill_legacy_boxes_without_distribution(
                sync_session.connection()
            )
        )
        await session.refresh(supply)
        assert supply.boxes_without_distribution_at is not None
        await session.commit()

    assigned = await async_client.post(
        f"{boxes_url}/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 400, assigned.text
    assert assigned.json()["detail"]["code"] == "box_without_distribution"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_prefix",
    ["no-distribution:", "retired-no-dist:"],
)
async def test_legacy_without_distribution_create_retry_returns_existing_box(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    stored_prefix: str,
) -> None:
    """A retried pre-migration create never duplicates its physical box."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    idempotency_key = "legacy-compatible-box"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": idempotency_key},
    )
    assert created.status_code == 201, created.text
    created_box_id = created.json()["boxes"][0]["id"]

    async with SessionLocal() as session:
        box = await session.get(FbsPackingBox, uuid.UUID(created_box_id))
        assert box is not None
        box.creation_idempotency_key = f"{stored_prefix}{idempotency_key}"
        await session.flush()
        await session.run_sync(
            lambda sync_session: _migration._backfill_legacy_boxes_without_distribution(
                sync_session.connection()
            )
        )
        await session.refresh(box)
        assert box.created_without_distribution is True
        await session.commit()

    retried = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": idempotency_key,
            "without_distribution": True,
        },
    )
    assert retried.status_code == 201, retried.text
    assert [box["id"] for box in retried.json()["boxes"]] == [created_box_id]

    async with SessionLocal() as session:
        stored_boxes = list(
            (
                await session.scalars(
                    select(FbsPackingBox).where(FbsPackingBox.supply_id == supply_id)
                )
            ).all()
        )
        assert [str(box.id) for box in stored_boxes] == [created_box_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_prefix",
    ["no-distribution:", "retired-no-dist:"],
)
async def test_truncated_legacy_key_does_not_capture_distinct_long_key(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    stored_prefix: str,
) -> None:
    """A lossy legacy key must not match a distinct 128-character API key."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    shared_prefix = "x" * 112
    original_key = f"{shared_prefix}{'A' * 16}"
    distinct_key = f"{shared_prefix}{'B' * 16}"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": original_key,
            "without_distribution": True,
        },
    )
    assert created.status_code == 201, created.text
    created_box_id = created.json()["boxes"][0]["id"]

    async with SessionLocal() as session:
        box = await session.get(FbsPackingBox, uuid.UUID(created_box_id))
        assert box is not None
        box.creation_idempotency_key = f"{stored_prefix}{shared_prefix}"
        await session.commit()

    distinct_create = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": distinct_key,
            "without_distribution": True,
        },
    )
    assert distinct_create.status_code == 201, distinct_create.text
    assert len(distinct_create.json()["boxes"]) == 2
    assert distinct_create.json()["boxes"][1]["id"] != created_box_id

    async with SessionLocal() as session:
        stored_keys = set(
            (
                await session.scalars(
                    select(FbsPackingBox.creation_idempotency_key).where(
                        FbsPackingBox.supply_id == supply_id
                    )
                )
            ).all()
        )
        assert stored_keys == {f"{stored_prefix}{shared_prefix}", distinct_key}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_prefix",
    ["no-distribution:", "retired-no-dist:"],
)
async def test_truncated_legacy_key_retry_returns_existing_box(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    stored_prefix: str,
) -> None:
    """The WB operation journal disambiguates a retry of a lossy legacy key."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    idempotency_key = f"{'x' * 112}{'A' * 16}"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": idempotency_key,
            "without_distribution": True,
        },
    )
    assert created.status_code == 201, created.text
    created_box_id = created.json()["boxes"][0]["id"]

    async with SessionLocal() as session:
        box = await session.get(FbsPackingBox, uuid.UUID(created_box_id))
        assert box is not None
        box.creation_idempotency_key = f"{stored_prefix}{idempotency_key[:112]}"
        await session.commit()

    retried = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": idempotency_key,
            "without_distribution": True,
        },
    )
    assert retried.status_code == 201, retried.text
    assert [box["id"] for box in retried.json()["boxes"]] == [created_box_id]

    async with SessionLocal() as session:
        stored_box_ids = list(
            (
                await session.scalars(
                    select(FbsPackingBox.id).where(
                        FbsPackingBox.supply_id == supply_id
                    )
                )
            ).all()
        )
        assert [str(box_id) for box_id in stored_box_ids] == [created_box_id]


@pytest.mark.asyncio
async def test_without_distribution_mode_depends_on_assignments_not_box_count(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"

    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "mode-empty-1"},
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        tenant_id = supply.tenant_id
        await set_boxes_without_distribution(
            session, tenant_id, supply_id, True, actor_user_id=None
        )
        await session.commit()

    deleted = await async_client.request(
        "DELETE",
        f"{boxes_url}/" + created.json()["boxes"][0]["id"],
        headers=headers,
        json={"idempotency_key": "mode-empty-delete-1"},
    )
    assert deleted.status_code == 200, deleted.text
    recreated = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "mode-empty-2"},
    )
    assert recreated.status_code == 201, recreated.text

    async with SessionLocal() as session:
        await set_boxes_without_distribution(
            session, tenant_id, supply_id, False, actor_user_id=None
        )
        await session.commit()

    box_id = recreated.json()["boxes"][0]["id"]
    assigned = await async_client.post(
        f"{boxes_url}/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text

    async with SessionLocal() as session:
        with pytest.raises(FbsPackingBoxError, match="boxes_already_distributed"):
            await set_boxes_without_distribution(
                session, tenant_id, supply_id, True, actor_user_id=None
            )
        await session.rollback()

    removed = await async_client.delete(
        f"{boxes_url}/{box_id}/orders/{order_ids[0]}", headers=headers
    )
    assert removed.status_code == 200, removed.text
    async with SessionLocal() as session:
        assert await set_boxes_without_distribution(
            session, tenant_id, supply_id, True, actor_user_id=None
        )


@pytest.mark.asyncio
async def test_without_distribution_toggle_preserves_full_key_for_create_retry(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-005: toggling never breaks a new-format create retry."""
    headers, supply_id, _ = await _packed_supply(async_client)
    idempotency_key = "k" * 128
    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": idempotency_key,
            "without_distribution": True,
        },
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        tenant_id = supply.tenant_id
        first_at = supply.boxes_without_distribution_at
        first_by = supply.boxes_without_distribution_by_user_id
        await set_boxes_without_distribution(
            session, tenant_id, supply_id, True, actor_user_id=uuid.uuid4()
        )
        assert supply.boxes_without_distribution_at == first_at
        assert supply.boxes_without_distribution_by_user_id == first_by
        await set_boxes_without_distribution(
            session, tenant_id, supply_id, False, actor_user_id=None
        )
        await session.commit()

    retried = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": idempotency_key,
            "without_distribution": True,
        },
    )
    assert retried.status_code == 201, retried.text
    assert [box["id"] for box in retried.json()["boxes"]] == [
        created.json()["boxes"][0]["id"]
    ]
    assert retried.json()["boxes"][0]["without_distribution"] is False

    async with SessionLocal() as session:
        box_id = uuid.UUID(created.json()["boxes"][0]["id"])
        box = await session.get(FbsPackingBox, box_id)
        assert box is not None
        assert box.creation_idempotency_key is not None
        assert box.creation_idempotency_key == idempotency_key
        assert len(box.creation_idempotency_key) == 128
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.boxes_without_distribution_at is None


@pytest.mark.asyncio
async def test_without_distribution_keeps_distinct_max_length_idempotency_keys(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Two valid keys with the same first 112 characters never collide."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    first_key = f"{'x' * 112}{'A' * 16}"
    second_key = f"{'x' * 112}{'B' * 16}"

    first = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": first_key,
            "without_distribution": True,
        },
    )
    second = await async_client.post(
        boxes_url,
        headers=headers,
        json={
            "count": 1,
            "idempotency_key": second_key,
            "without_distribution": True,
        },
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert len(first.json()["boxes"]) == 1
    assert len(second.json()["boxes"]) == 2
    assert second.json()["boxes"][1]["id"] != first.json()["boxes"][0]["id"]

    async with SessionLocal() as session:
        stored_keys = set(
            (
                await session.scalars(
                    select(FbsPackingBox.creation_idempotency_key).where(
                        FbsPackingBox.supply_id == supply_id
                    )
                )
            ).all()
        )
        assert stored_keys == {first_key, second_key}


@pytest.mark.asyncio
async def test_boxes_without_distribution_api_persists_mode_across_empty_box_lifecycle(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-003: the persisted mode survives empty box lifecycle and can be reverted."""
    headers, supply_id, _ = await _packed_supply(async_client)

    enabled = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes-without-distribution",
        headers=headers,
        json={"enabled": True},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["supply"]["boxes_without_distribution"] is True

    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "persist-mode-after-last-box-delete"},
    )
    assert created.status_code == 201, created.text
    deleted = await async_client.request(
        "DELETE",
        f"{boxes_url}/{created.json()['boxes'][0]['id']}",
        headers=headers,
        json={"idempotency_key": "delete-last-box-with-persisted-mode"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["boxes"] == []

    recreated = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "recreate-box-with-persisted-mode"},
    )
    assert recreated.status_code == 201, recreated.text
    assert recreated.json()["supply"]["boxes_without_distribution"] is True

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["supply"]["boxes_without_distribution"] is True

    disabled = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes-without-distribution",
        headers=headers,
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["supply"]["boxes_without_distribution"] is False


@pytest.mark.asyncio
async def test_migration_moves_provable_legacy_marker_to_supply_before_empty_box_lifecycle(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-006: a pre-0094 marker survives removal of its last empty box."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    raw_key = "pre-0094-mode-marker"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": raw_key},
    )
    assert created.status_code == 201, created.text
    box_id = uuid.UUID(created.json()["boxes"][0]["id"])

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        box = await session.get(FbsPackingBox, box_id)
        assert supply is not None and box is not None
        # Recreate the exact pre-0094 representation: the box carried the
        # prefix, while the operation journal retained the raw client key.
        supply.boxes_without_distribution_at = None
        supply.boxes_without_distribution_by_user_id = None
        box.creation_idempotency_key = f"no-distribution:{raw_key}"
        await session.flush()
        await session.run_sync(
            lambda sync_session: _migration._backfill_legacy_boxes_without_distribution(
                sync_session.connection()
            )
        )
        await session.refresh(supply)
        await session.refresh(box)
        assert supply.boxes_without_distribution_at is not None
        assert box.created_without_distribution is True
        await session.commit()

    deleted = await async_client.request(
        "DELETE",
        f"{boxes_url}/{box_id}",
        headers=headers,
        json={"idempotency_key": "delete-pre-0094-mode-box"},
    )
    assert deleted.status_code == 200, deleted.text
    recreated = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "recreate-pre-0094-mode-box"},
    )
    assert recreated.status_code == 201, recreated.text

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["supply"]["boxes_without_distribution"] is True


@pytest.mark.asyncio
async def test_client_key_with_legacy_prefix_is_not_mode_marker_and_stays_idempotent(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-007: an ordinary prefixed client key stays an ordinary retry key."""
    headers, supply_id, _ = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    body = {"count": 1, "idempotency_key": "no-distribution:abc"}

    first = await async_client.post(boxes_url, headers=headers, json=body)
    second = await async_client.post(boxes_url, headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert [box["id"] for box in second.json()["boxes"]] == [
        box["id"] for box in first.json()["boxes"]
    ]
    assert second.json()["supply"]["boxes_without_distribution"] is False

    async with SessionLocal() as session:
        await session.run_sync(
            lambda sync_session: _migration._backfill_legacy_boxes_without_distribution(
                sync_session.connection()
            )
        )
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        await session.refresh(supply)
        assert supply.boxes_without_distribution_at is None
        box_count = await session.scalar(
            select(func.count(FbsPackingBox.id)).where(
                FbsPackingBox.supply_id == supply_id
            )
        )
        assert box_count == 1


@pytest.mark.asyncio
async def test_boxes_without_distribution_api_conflicts_when_order_is_assigned(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """TC-NEW-004: assigned orders prevent changing the persisted mode."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    created = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "api-mode-conflict"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]
    assigned = await async_client.post(
        f"{boxes_url}/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text

    conflict = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes-without-distribution",
        headers=headers,
        json={"enabled": True},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "boxes_already_distributed"

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["supply"]["boxes_without_distribution"] is False


def test_workspace_distribution_enabled_requires_boxes_and_order_assignment() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=771,
        pick_status="picked",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(picked=1, packed=1, metadata_ready=1, stickers_ready=1, total=1)

    stage_without_boxes = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=False,
    )
    assert stage_without_boxes == "handoff_prep"
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage_without_boxes,
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )
    assert {(item["code"], item["stage"]) for item in blockers} == {
        ("physical_boxes_required", "handoff_prep"),
        ("packed_order_unassigned", "handoff_prep"),
    }


def test_workspace_opens_boxes_while_order_sticker_is_not_ready() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=773,
        pick_status="picked",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(
        picked=1,
        packed=1,
        metadata_ready=1,
        stickers_ready=0,
        total=1,
    )

    stage = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage,
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )

    assert stage == "handoff_prep"
    assert any(item["code"] == "stickers_not_ready" for item in blockers)


def test_workspace_active_wb_unlocks_handoff_before_pick_and_pack() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=774,
        pick_status="pending",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(
        picked=0,
        packed=0,
        metadata_ready=1,
        stickers_ready=0,
        total=1,
    )

    stage = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )

    assert stage == "handoff_prep"


def test_workspace_without_distribution_skips_assignment_gate() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=772,
        pick_status="picked",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(picked=1, packed=1, metadata_ready=1, stickers_ready=1, total=1)

    stage = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=True,
        without_distribution=True,
        unassigned_packed_order_ids={order_id},
    )
    assert stage == "delivery"
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage,
        progress,
        has_physical_boxes=True,
        without_distribution=True,
        unassigned_packed_order_ids={order_id},
    )
    assert all(item["code"] != "packed_order_unassigned" for item in blockers)
