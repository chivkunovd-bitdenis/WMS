"""Physical FBS box API — a box is local, but (since 2026-08-17) every box also
gets a linked WB cargo place (trbx) + QR, for warehouse/SC exactly like PVZ.
See the module docstring in app/services/fbs_shipment_pvz_service.py for why
the old PVZ-only cargo-place restriction was dropped."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import PACK_STATUS_PACKED, PACK_STATUS_PENDING, FbsOrder
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_SUPPLY_STATUS_PACKED
from app.models.tenant import Tenant
from app.services.fbs_workspace_service import (
    WorkspaceProgress,
    _compute_stage,
    _compute_workspace_blockers,
)
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


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
    unpacked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{first}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[1])]},
    )
    assert unpacked.status_code == 400, unpacked.text
    assert unpacked.json()["detail"]["code"] == "order_not_packed"

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

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["boxes"] == second.json()["boxes"]
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "idempotency_key_reused"


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

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box['id']}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 400, assigned.text
    assert assigned.json()["detail"]["code"] == "box_without_distribution"


@pytest.mark.asyncio
async def test_assign_orders_auto_passes_packing_when_tenant_disables_requirement(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Тенант выключил fbs_packing_required — заказ, упаковку которого никто
    не отмечал, всё равно попадает в короб. Значение pack_status при этом
    по-настоящему становится "packed", проверка не просто обходится стороной."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.pack_status = PACK_STATUS_PENDING
        order.packed_at = None
        tenant = await session.get(Tenant, order.tenant_id)
        assert tenant is not None
        tenant.fbs_packing_required = False
        await session.commit()

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "boxes-auto-pack-1"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["boxes"][0]["assigned_order_ids"] == [str(order_ids[0])]

    async with SessionLocal() as session:
        refreshed = await session.get(FbsOrder, order_ids[0])
        assert refreshed is not None
        assert refreshed.pack_status == PACK_STATUS_PACKED
        assert refreshed.packed_at is not None


@pytest.mark.asyncio
async def test_assign_orders_still_requires_packing_when_tenant_requires_it(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """fbs_packing_required=True (в т.ч. значение по умолчанию) — поведение
    не меняется: заказ без отметки упаковки в короб не попадает."""
    headers, supply_id, order_ids = await _packed_supply(async_client)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.pack_status = PACK_STATUS_PENDING
        order.packed_at = None
        tenant = await session.get(Tenant, order.tenant_id)
        assert tenant is not None
        # Явно фиксируем True, поскольку полагаться только на значение по умолчанию рискованно.
        tenant.fbs_packing_required = True
        await session.commit()

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": "boxes-still-required-1"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]

    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_ids[0])]},
    )
    assert assigned.status_code == 400, assigned.text
    assert assigned.json()["detail"]["code"] == "order_not_packed"

    async with SessionLocal() as session:
        refreshed = await session.get(FbsOrder, order_ids[0])
        assert refreshed is not None
        assert refreshed.pack_status == PACK_STATUS_PENDING


def test_workspace_handoff_requires_boxes_and_every_packed_order_assignment() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
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


def test_workspace_without_distribution_skips_assignment_gate() -> None:
    order_id = uuid.uuid4()
    supply = SimpleNamespace(
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
