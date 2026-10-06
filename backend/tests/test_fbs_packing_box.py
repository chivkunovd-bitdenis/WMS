"""Physical FBS box API — a box is local, but (since 2026-08-17) every box also
gets a linked WB cargo place (trbx) + QR, for warehouse/SC exactly like PVZ.
See the module docstring in app/services/fbs_shipment_pvz_service.py for why
the old PVZ-only cargo-place restriction was dropped."""

from __future__ import annotations

import asyncio
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
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.models.warehouse_box import WarehouseBox
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
    assert assigned_unpacked.json()["boxes"][0]["assigned_order_ids"] == [str(order_ids[1])]

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
async def test_wb_box_readiness_never_depends_on_pack_status(
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
            (await session.scalars(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))).all()
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
    assert readiness.unassigned_packed_order_ids == frozenset(order_ids)


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
@pytest.mark.parametrize("wb_status", [404, 409])
async def test_box_creation_wb_rejection_cleans_local_boxes_and_same_key_can_retry(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
    wb_status: int,
) -> None:
    headers, supply_id, _ = await _packed_supply(async_client)
    original_create = pvz_svc.create_marketplace_supply_trbx
    attempts = 0

    async def reject_once_then_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WildberriesClientError("upstream_error", status_code=wb_status)
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
        assert (
            await session.scalar(
                select(func.count(FbsPackingBox.id)).where(FbsPackingBox.supply_id == supply_id)
            )
            == 0
        )
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
            (WB_OPERATION_STATE_FAILED, f"wb_upstream_error_{wb_status}")
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

    async def reject_then_create_and_lose_response(*args: object, **kwargs: object) -> list[str]:
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


async def _legacy_unlinked_box_group(
    supply_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    count: int = 5,
    without_distribution: bool = False,
    key: str = "wms681-original-physical-group",
    first_box_number: int = 1,
    assigned_order_id: uuid.UUID | None = None,
) -> tuple[list[uuid.UUID], str, uuid.UUID]:
    """Historical pre-hotfix state: physical boxes survived a definitive WB refusal."""
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        ids = []
        for number in range(first_box_number, first_box_number + count):
            physical = WarehouseBox(
                tenant_id=supply.tenant_id, warehouse_id=supply.warehouse_id,
                internal_barcode=f"FBS-681-{number}-{key[-6:]}",
            )
            packing = FbsPackingBox(
                tenant_id=supply.tenant_id, supply_id=supply_id, warehouse_box=physical,
                box_number=number, creation_idempotency_key=key,
                created_without_distribution=without_distribution,
            )
            session.add(packing)
            await session.flush()
            ids.append(packing.id)
        if not without_distribution:
            session.add(FbsPackingBoxItem(
                tenant_id=supply.tenant_id,
                box_id=ids[0],
                fbs_order_id=assigned_order_id or order_ids[0],
            ))
        operation = FbsWbOperation(
            tenant_id=supply.tenant_id, seller_id=supply.seller_id,
            operation_kind=OPERATION_KIND_CARGO_PLACES_CREATE, idempotency_key=key,
            local_entity_type="fbs_supply", local_entity_id=supply_id,
            state=WB_OPERATION_STATE_FAILED, error_code="wb_upstream_error_404",
            request_summary_json={"count": count, "wb_trbx_ids_before": []},
        )
        session.add(operation)
        await session.commit()
        return ids, key, operation.id


async def _physical_group_snapshot(supply_id: uuid.UUID) -> list[tuple[object, ...]]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(FbsPackingBox.id, FbsPackingBox.warehouse_box_id,
                   FbsPackingBox.box_number, FbsPackingBox.creation_idempotency_key,
                   FbsPackingBox.created_without_distribution, WarehouseBox.internal_barcode)
            .join(WarehouseBox, WarehouseBox.id == FbsPackingBox.warehouse_box_id)
            .where(FbsPackingBox.supply_id == supply_id).order_by(FbsPackingBox.box_number)
        )
        return [tuple(row) for row in rows]


async def _business_state_snapshot(supply_id: uuid.UUID) -> tuple[object, ...]:
    """Fields this QR recovery must not turn into a shipment, stock or reserve mutation."""
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        orders = list((await session.scalars(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id).order_by(FbsOrder.id)
        )).all())
        assignments = list((await session.execute(
            select(FbsPackingBoxItem.box_id, FbsPackingBoxItem.fbs_order_id)
            .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
            .where(FbsPackingBox.supply_id == supply_id)
            .order_by(FbsPackingBoxItem.box_id, FbsPackingBoxItem.fbs_order_id)
        )).all())
        return (
            (supply.tenant_id, supply.seller_id, supply.warehouse_id, supply.marketplace,
             supply.status, supply.delivery_type, supply.delivered_at),
            [(order.id, order.tenant_id, order.seller_id, order.warehouse_id, order.supply_id,
              order.marketplace, order.status, order.reserve_status, order.pick_status,
              order.pack_status, order.trbx_id) for order in orders],
            [tuple(row) for row in assignments],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("without_distribution", [False, True])
async def test_wms681_qr_recovers_original_five_box_group_without_recreating_physical_boxes(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
    without_distribution: bool,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, key, failed_id = await _legacy_unlinked_box_group(
        supply_id, order_ids, without_distribution=without_distribution,
    )
    before = await _physical_group_snapshot(supply_id)
    original_create = pvz_svc.create_marketplace_supply_trbx
    calls: list[int] = []
    reads: list[str] = []

    async def create(*args: object, **kwargs: object) -> list[str]:
        reads.append("create")
        calls.append(int(kwargs["amount"]))
        return await original_create(*args, **kwargs)  # type: ignore[arg-type]

    async def remote_list(*args: object, **kwargs: object) -> list[str]:
        reads.append("list")
        return []

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", create)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", remote_list)
    url = f"/operations/fbs-supplies/{supply_id}/boxes/{ids[2]}/retry-qr"
    recovered = await async_client.post(url, headers=headers)
    assert recovered.status_code == 200, recovered.text
    assert calls == [5]
    assert reads.index("list") < reads.index("create")
    assert await _physical_group_snapshot(supply_id) == before
    boxes = recovered.json()["boxes"]
    assert {box["id"] for box in boxes} == {str(one) for one in ids}
    assert all(box["wb_trbx_id"] and box["qr_asset"]["status"] == "ready" for box in boxes)
    assert boxes[0]["assigned_order_ids"] == ([] if without_distribution else [str(order_ids[0])])
    repeated = await async_client.post(url, headers=headers)
    assert repeated.status_code == 200, repeated.text
    assert calls == [5]
    async with SessionLocal() as session:
        operation = await session.scalar(select(FbsWbOperation).where(
            FbsWbOperation.idempotency_key == f"box-retry:{failed_id}",
        ))
        assert operation is not None and operation.state == WB_OPERATION_STATE_CONFIRMED
        assert operation.created_by_user_id is not None
        assert {str(one[3]) for one in before} == {key}


@pytest.mark.asyncio
async def test_wms681_qr_concurrent_group_recovery_creates_once_and_excludes_other_group(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=5)
    other_ids, _, _ = await _legacy_unlinked_box_group(
        supply_id,
        order_ids,
        count=1,
        key="wms681-separate-physical-group",
        first_box_number=6,
        assigned_order_id=order_ids[1],
    )
    calls: list[int] = []
    original_create = pvz_svc.create_marketplace_supply_trbx

    async def create(*args: object, **kwargs: object) -> list[str]:
        calls.append(int(kwargs["amount"]))
        await asyncio.sleep(0.03)
        return await original_create(*args, **kwargs)  # type: ignore[arg-type]

    async def remote_list(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", create)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", remote_list)
    url = f"/operations/fbs-supplies/{supply_id}/boxes/{ids[2]}/retry-qr"
    first, second = await asyncio.gather(
        async_client.post(url, headers=headers), async_client.post(url, headers=headers),
    )
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert calls == [5]
    workspace = second.json()
    assert {box["id"] for box in workspace["boxes"] if box["wb_trbx_id"]} == {
        str(one) for one in ids
    }
    assert all(
        box["wb_trbx_id"] is None
        for box in workspace["boxes"] if box["id"] in {str(one) for one in other_ids}
    )


@pytest.mark.asyncio
async def test_wms681_qr_pending_readback_does_not_take_trbx_owned_by_other_physical_group(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact remote delta is still unsafe when its local owner is another group."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    _ = order_ids
    boxes_url = f"/operations/fbs-supplies/{supply_id}/boxes"
    original_create = pvz_svc.create_marketplace_supply_trbx

    async def lose_a_result(*args: object, **kwargs: object) -> list[str]:
        raise WildberriesClientError("transport_error")

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", lose_a_result)
    created_a = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "wms681-pending-a"},
    )
    assert created_a.status_code == 504, created_a.text
    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", original_create)
    created_b = await async_client.post(
        boxes_url,
        headers=headers,
        json={"count": 1, "idempotency_key": "wms681-owned-b"},
    )
    assert created_b.status_code == 201, created_b.text
    async with SessionLocal() as session:
        box_a = await session.scalar(select(FbsPackingBox).where(
            FbsPackingBox.supply_id == supply_id,
            FbsPackingBox.creation_idempotency_key == "wms681-pending-a",
        ))
        box_b = await session.scalar(select(FbsPackingBox).where(
            FbsPackingBox.supply_id == supply_id,
            FbsPackingBox.creation_idempotency_key == "wms681-owned-b",
        ))
        assert box_a is not None and box_b is not None and box_b.trbx_id is not None
        trbx_b = await session.get(FbsTrbx, box_b.trbx_id)
        assert trbx_b is not None
        box_a_id = box_a.id
        box_b_id = box_b.id
        wb_trbx_b = trbx_b.wb_trbx_id
        assert box_a.trbx_id is None
        assert box_b.trbx_id == trbx_b.id
        assert trbx_b.packaging_box_id == box_b.warehouse_box_id

    creates = 0

    async def forbidden_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal creates
        creates += 1
        raise AssertionError("a locally owned WB trbx must not trigger a new create")

    async def read(*args: object, **kwargs: object) -> list[str]:
        return [wb_trbx_b]

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", forbidden_create)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", read)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_a_id}/retry-qr", headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] in {
        "wb_pending_confirmation",
        "idempotency_key_reused",
    }
    assert creates == 0
    async with SessionLocal() as session:
        box_a = await session.get(FbsPackingBox, box_a_id)
        box_b = await session.get(FbsPackingBox, box_b_id)
        trbx_b = await session.scalar(select(FbsTrbx).where(
            FbsTrbx.wb_trbx_id == wb_trbx_b,
        ))
        assert box_a is not None and box_b is not None and trbx_b is not None
        assert box_a.trbx_id is None
        assert box_b.trbx_id == trbx_b.id
        assert trbx_b.packaging_box_id == box_b.warehouse_box_id


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_result", ["exact", "empty", "ambiguous", "read_error"])
async def test_wms681_qr_reconciles_timeout_without_blind_external_create(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
    remote_result: str,
) -> None:
    headers, supply_id, _ = await _packed_supply(async_client)
    attempts = 0
    remote_ids: list[str] = []
    fail_read = False

    async def lost_response(*args: object, **kwargs: object) -> list[str]:
        nonlocal attempts
        attempts += 1
        raise WildberriesClientError("transport_error")

    async def read(*args: object, **kwargs: object) -> list[str]:
        if fail_read:
            raise WildberriesClientError("transport_error")
        return remote_ids

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", lost_response)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", read)
    timed_out = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes", headers=headers,
        json={"count": 1, "idempotency_key": "wms681-timeout"},
    )
    assert timed_out.status_code == 504, timed_out.text
    before = await _physical_group_snapshot(supply_id)
    box_id = before[0][0]
    remote_ids = {
        "exact": ["WB-MP-681-RECOVERED"],
        "ambiguous": ["WB-MP-681-A", "WB-MP-681-B"],
    }.get(remote_result, [])
    fail_read = remote_result == "read_error"
    recovered = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/retry-qr", headers=headers,
    )
    if remote_result == "exact":
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["boxes"][0]["wb_trbx_id"] == "WB-MP-681-RECOVERED"
        assert recovered.json()["boxes"][0]["qr_asset"]["status"] == "ready"
    else:
        assert recovered.status_code in (409, 504), recovered.text
        assert recovered.json()["detail"]["code"] in {"wb_pending_confirmation", "wb_timeout"}
    assert attempts == 1
    assert await _physical_group_snapshot(supply_id) == before


@pytest.mark.asyncio
async def test_wms681_qr_retries_confirmed_readback_after_qr_failure_without_create(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed exact readback is retried as QR fetch, not rejected or recreated."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, key, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=1)
    before = await _physical_group_snapshot(supply_id)
    async with SessionLocal() as session:
        operation = await session.scalar(select(FbsWbOperation).where(
            FbsWbOperation.idempotency_key == key,
        ))
        box = await session.get(FbsPackingBox, ids[0])
        assert operation is not None and box is not None
        operation.state = WB_OPERATION_STATE_CONFIRMED
        trbx = FbsTrbx(
            supply_id=supply_id,
            wb_trbx_id="WB-MP-681-CONFIRMED",
            packaging_box_id=box.warehouse_box_id,
        )
        session.add(trbx)
        await session.commit()

    fetches = 0

    async def fail_then_fetch(*args: object, **kwargs: object) -> list[object]:
        nonlocal fetches
        fetches += 1
        if fetches == 1:
            raise pvz_svc.FbsShipmentPvzError("wb_timeout")
        return []

    creates = 0

    async def forbidden_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal creates
        creates += 1
        raise AssertionError("confirmed readback must never create another cargo place")

    monkeypatch.setattr(pvz_svc, "fetch_trbx_stickers", fail_then_fetch)
    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", forbidden_create)
    url = f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr"
    failed_qr = await async_client.post(url, headers=headers)
    assert failed_qr.status_code == 504, failed_qr.text
    recovered = await async_client.post(url, headers=headers)
    assert recovered.status_code == 200, recovered.text
    assert fetches == 2
    assert creates == 0
    assert await _physical_group_snapshot(supply_id) == before


@pytest.mark.asyncio
async def test_wms681_qr_partial_wb_sticker_success_is_durable_after_next_sticker_failure(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WB's first real sticker survives if the next cargo-place request fails."""
    import app.services.fbs_print_asset_service as print_svc

    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=2)
    async with SessionLocal() as session:
        group = [await session.get(FbsPackingBox, box_id) for box_id in ids]
        assert all(group)
        for number, packing in enumerate(group, start=1):
            assert packing is not None
            trbx = FbsTrbx(
                supply_id=supply_id,
                wb_trbx_id=f"WB-MP-681-PARTIAL-{number}",
                packaging_box_id=packing.warehouse_box_id,
            )
            session.add(trbx)
            await session.flush()
            packing.trbx_id = trbx.id
        await session.commit()

    original_fetch = print_svc.fetch_marketplace_trbx_stickers
    fetches = 0

    async def fetch_first_then_fail(*args: object, **kwargs: object) -> list[dict[str, object]]:
        nonlocal fetches
        fetches += 1
        if fetches == 2:
            raise WildberriesClientError("transport_error")
        return await original_fetch(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(print_svc, "fetch_marketplace_trbx_stickers", fetch_first_then_fail)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr", headers=headers,
    )
    assert response.status_code in {502, 504}, response.text
    assert fetches == 2
    async with SessionLocal() as session:
        first_ready = await session.scalar(select(FbsPrintAsset).where(
            FbsPrintAsset.fbs_trbx_id == (
                select(FbsPackingBox.trbx_id).where(FbsPackingBox.id == ids[0]).scalar_subquery()
            ),
            FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
            FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
        ))
        assert first_ready is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_prefix", ["no-distribution:", "retired-no-dist:"])
async def test_wms681_qr_legacy_marker_recovers_with_scoped_original_raw_key(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
    stored_prefix: str,
) -> None:
    """QR recovery must resolve a historical marker through its supply-scoped journal key."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    raw_key = "wms681-legacy-raw-operator-key"
    ids, _, _ = await _legacy_unlinked_box_group(
        supply_id,
        order_ids,
        count=1,
        without_distribution=True,
        key=raw_key,
    )
    async with SessionLocal() as session:
        box = await session.get(FbsPackingBox, ids[0])
        assert box is not None
        box.creation_idempotency_key = f"{stored_prefix}{raw_key}"
        await session.commit()

    calls: list[int] = []
    original_create = pvz_svc.create_marketplace_supply_trbx

    async def create(*args: object, **kwargs: object) -> list[str]:
        calls.append(int(kwargs["amount"]))
        return await original_create(*args, **kwargs)  # type: ignore[arg-type]

    async def read(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", create)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", read)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr", headers=headers,
    )
    assert response.status_code == 200, response.text
    assert calls == [1]
    async with SessionLocal() as session:
        box = await session.get(FbsPackingBox, ids[0])
        assert box is not None
        assert box.creation_idempotency_key == f"{stored_prefix}{raw_key}"


@pytest.mark.asyncio
@pytest.mark.parametrize("wb_status", [404, 409])
async def test_wms681_qr_refusal_preserves_old_group_and_next_explicit_retry(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
    wb_status: int,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=1)
    before = await _physical_group_snapshot(supply_id)
    attempts = 0
    original_create = pvz_svc.create_marketplace_supply_trbx

    async def reject_once(*args: object, **kwargs: object) -> list[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WildberriesClientError("upstream_error", status_code=wb_status)
        return await original_create(*args, **kwargs)  # type: ignore[arg-type]

    async def read(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", reject_once)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", read)
    url = f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr"
    rejected = await async_client.post(url, headers=headers)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "box_create_rejected_by_wb"
    assert attempts == 1
    assert await _physical_group_snapshot(supply_id) == before
    async with SessionLocal() as session:
        errors = list(await session.scalars(select(FbsWbOperation.error_code).where(
            FbsWbOperation.local_entity_id == supply_id,
        )))
        assert f"wb_upstream_error_{wb_status}" in errors
    retried = await async_client.post(url, headers=headers)
    assert retried.status_code == 200, retried.text
    assert attempts == 2
    assert await _physical_group_snapshot(supply_id) == before


@pytest.mark.asyncio
async def test_wms681_qr_failed_group_does_not_duplicate_unattributable_remote_ids(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=1)
    calls = 0

    async def forbidden_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("unexpected WB ids must be resolved before another creation")

    async def read(*args: object, **kwargs: object) -> list[str]:
        return ["WB-MP-681-UNATTRIBUTED-A", "WB-MP-681-UNATTRIBUTED-B"]

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", forbidden_create)
    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", read)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr", headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "wb_pending_confirmation"
    assert calls == 0


@pytest.mark.asyncio
async def test_wms681_qr_recovery_preserves_fbs_business_state(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=1)
    before = await _business_state_snapshot(supply_id)

    async def remote_list(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(pvz_svc, "fetch_marketplace_supply_trbx_list", remote_list)
    recovered = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr", headers=headers,
    )
    assert recovered.status_code == 200, recovered.text
    assert await _business_state_snapshot(supply_id) == before


@pytest.mark.asyncio
async def test_wms681_qr_foreign_tenant_cannot_start_recovery(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=1)
    foreign_headers, _, _ = await _packed_supply(async_client)
    calls = 0

    async def forbidden_create(*args: object, **kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("a foreign tenant must never start WB recovery")

    monkeypatch.setattr(pvz_svc, "create_marketplace_supply_trbx", forbidden_create)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{ids[0]}/retry-qr",
        headers=foreign_headers,
    )
    assert response.status_code in {403, 404}, response.text
    assert calls == 0


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
        assert stored_box.creation_idempotency_key == "boxes-without-distribution-1"

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
                    select(FbsPackingBox.id).where(FbsPackingBox.supply_id == supply_id)
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
    assert [box["id"] for box in retried.json()["boxes"]] == [created.json()["boxes"][0]["id"]]
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
            select(func.count(FbsPackingBox.id)).where(FbsPackingBox.supply_id == supply_id)
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


def test_workspace_wb_distribution_does_not_publish_navigation_blockers() -> None:
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
    assert stage_without_boxes == "packing"
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage_without_boxes,
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )
    assert blockers == []


def test_workspace_opens_boxes_without_sticker_navigation_blocker() -> None:
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

    assert stage == "packing"
    assert blockers == []


def test_workspace_active_wb_starts_with_optional_picking() -> None:
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

    assert stage == "picking"
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage,
        progress,
        has_physical_boxes=False,
        unassigned_packed_order_ids={order_id},
    )
    assert all(item["code"] != "order_not_picked" for item in blockers)


def test_workspace_active_wb_stage_does_not_consult_packaging_progress() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=775,
        pick_status="pending",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )

    no_pack_facts = _compute_stage(
        supply,
        [order],
        WorkspaceProgress(
            picked=0,
            packed=0,
            metadata_ready=0,
            stickers_ready=0,
            total=2,
        ),
        has_physical_boxes=False,
    )
    all_pack_facts = _compute_stage(
        supply,
        [order],
        WorkspaceProgress(
            picked=0,
            packed=2,
            metadata_ready=2,
            stickers_ready=0,
            total=2,
        ),
        has_physical_boxes=False,
    )

    assert no_pack_facts == "picking"
    assert all_pack_facts == no_pack_facts


def test_workspace_completed_wb_assembling_never_returns_to_picking() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=776,
        pick_status="picked",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(
        picked=18,
        packed=18,
        metadata_ready=18,
        stickers_ready=18,
        total=18,
    )

    stage = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=True,
        without_distribution=True,
    )
    blockers = _compute_workspace_blockers(
        supply,
        [order],
        stage,
        progress,
        has_physical_boxes=True,
        without_distribution=True,
    )

    assert stage == "handoff_prep"
    assert blockers == []


def test_workspace_wb_never_exposes_navigation_blockers() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="wb",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=777,
        pick_status="pending",
        metadata_delivery_allowed=False,
        required_meta_json=["sgtin"],
        meta_details_json={},
    )
    progress = WorkspaceProgress(
        picked=0,
        packed=0,
        metadata_ready=0,
        stickers_ready=0,
        total=1,
    )

    blockers = _compute_workspace_blockers(
        supply,
        [order],
        "handoff_prep",
        progress,
        has_physical_boxes=False,
        without_distribution=False,
        unassigned_packed_order_ids={order_id},
    )

    assert blockers == []


def test_workspace_fresh_ozon_supply_starts_with_picking_not_boxes() -> None:
    """Новая поставка Ozon начинает подбор до раскладки позиций по коробам."""
    supply = SimpleNamespace(
        marketplace="ozon",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=uuid.uuid4(),
        wb_order_id=-3665971690784702777,
        external_order_id="0195832-0021-3",
        pick_status="pending",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )

    stage = _compute_stage(
        supply,
        [order],
        WorkspaceProgress(picked=0, packed=0, metadata_ready=0, stickers_ready=0, total=3),
        has_physical_boxes=False,
        without_distribution=False,
    )

    assert stage == "picking"


def test_workspace_ozon_never_exposes_navigation_blockers() -> None:
    """Правило AGENTS.md одно для обеих площадок, не только для WB.

    У Ozon этикетка выдаётся только после сборки, поэтому `stickers_ready`
    никогда не догоняет `total` до передачи. Пока сервер публиковал по этому
    факту навигационные блокеры, оператора запирало на «Коробах», где операции
    с коробами у Ozon закрыты.
    """
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="ozon",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=-3665971690784702775,
        external_order_id="0195832-0021-1",
        pick_status="pending",
        metadata_delivery_allowed=False,
        required_meta_json=["sgtin"],
        meta_details_json={},
    )
    progress = WorkspaceProgress(
        picked=0,
        packed=0,
        metadata_ready=0,
        stickers_ready=0,
        total=1,
    )

    blockers = _compute_workspace_blockers(
        supply,
        [order],
        "handoff_prep",
        progress,
        has_physical_boxes=False,
        without_distribution=False,
        unassigned_packed_order_ids={order_id},
    )

    assert blockers == []


def test_workspace_completed_ozon_assembling_never_returns_to_picking() -> None:
    """Запрещённое правило `status == assembling -> picking` снято и для Ozon."""
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
        marketplace="ozon",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=-3665971690784702776,
        external_order_id="0195832-0021-2",
        pick_status="picked",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )
    progress = WorkspaceProgress(
        picked=18,
        packed=18,
        metadata_ready=18,
        # Стикеров у Ozon до передачи нет — и это не повод отправлять оператора
        # назад в подбор.
        stickers_ready=0,
        total=18,
    )

    stage = _compute_stage(
        supply,
        [order],
        progress,
        has_physical_boxes=True,
        without_distribution=True,
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
    assert stage == "handoff_prep"
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
