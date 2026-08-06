from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_PACKED,
    PACK_STATUS_PACKED,
    PICK_STATUS_PICKED,
    STICKER_STATUS_READY,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.services import fbs_packing_box_service as packing_box_svc
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _seed_packed_supply_with_boxes(
    async_client: AsyncClient,
    *,
    delivery_type: Literal["warehouse_sc", "pvz"] = "warehouse_sc",
    order_count: int = 2,
) -> tuple[dict[str, str], uuid.UUID, list[uuid.UUID], str]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-LC-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-LC-{suffix}", barcode=barcode
    )
    order_specs = [(index + 1, timedelta(hours=12 * (index + 1))) for index in range(order_count)]
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=order_count,
        order_specs=order_specs,
        barcode=barcode,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.delivery_type = delivery_type
        supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.pack_status = PACK_STATUS_PACKED
        await session.commit()

    create_key = str(uuid.uuid4())
    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": create_key},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["packing_boxes"][0]["id"]
    assign = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(row) for row in order_ids],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert assign.status_code == 200, assign.text
    return headers, supply_id, order_ids, box_id


@pytest.mark.asyncio
async def test_manual_pick_explicit_ids_and_undo_are_idempotent(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-MANUAL-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-M-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=12)), (2, timedelta(hours=24))],
        barcode=barcode,
    )

    resolved = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/resolve-location",
        headers=headers,
        json={"location_id": str(location_id)},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["id"] == str(location_id)
    assert resolved.json()["expected_products"][0]["product_id"] == str(product_id)

    pick_key = str(uuid.uuid4())
    body = {
        "location_id": str(location_id),
        "product_id": str(product_id),
        "order_id": str(order_ids[0]),
        "idempotency_key": pick_key,
    }
    first = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/confirm-product",
        headers=headers,
        json=body,
    )
    assert first.status_code == 200, first.text
    assert first.json()["progress"]["picked"] == 1
    repeated = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/confirm-product",
        headers=headers,
        json=body,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["progress"]["picked"] == 1

    reused = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/confirm-product",
        headers=headers,
        json={**body, "order_id": str(order_ids[1])},
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "idempotency_key_reused"

    undo_key = str(uuid.uuid4())
    undo_url = f"/operations/fbs-supplies/{supply_id}/pick/{order_ids[0]}/undo"
    undone = await async_client.post(undo_url, headers=headers, json={"idempotency_key": undo_key})
    assert undone.status_code == 200, undone.text
    assert undone.json()["progress"]["picked"] == 0
    undo_retry = await async_client.post(
        undo_url, headers=headers, json={"idempotency_key": undo_key}
    )
    assert undo_retry.status_code == 200, undo_retry.text
    assert undo_retry.json()["progress"]["picked"] == 0


@pytest.mark.asyncio
async def test_warehouse_packing_boxes_batch_assign_unassign_and_delete(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-BOX-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-B-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=12)), (2, timedelta(hours=24))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.pack_status = PACK_STATUS_PACKED
        await session.commit()

    create_key = str(uuid.uuid4())
    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 2, "idempotency_key": create_key},
    )
    assert created.status_code == 201, created.text
    boxes = created.json()["packing_boxes"]
    assert [box["box_number"] for box in boxes] == [1, 2]
    assert all(box["internal_barcode"].startswith("WHB-") for box in boxes)
    assert all(box["wb_trbx_id"] is None and box["qr_asset"] is None for box in boxes)
    assert set(created.json()["unassigned_order_ids"]) == {str(row) for row in order_ids}

    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 2, "idempotency_key": create_key},
    )
    assert retry.status_code == 201, retry.text
    assert [row["id"] for row in retry.json()["packing_boxes"]] == [row["id"] for row in boxes]

    first_box_id, second_box_id = boxes[0]["id"], boxes[1]["id"]
    assign_body = {
        "order_ids": [str(row) for row in order_ids],
        "idempotency_key": str(uuid.uuid4()),
    }
    assigned = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{first_box_id}/orders",
        headers=headers,
        json=assign_body,
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["unassigned_order_ids"] == []
    assert assigned.json()["packing_boxes"][0]["items_count"] == 2

    assign_retry = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{first_box_id}/orders",
        headers=headers,
        json=assign_body,
    )
    assert assign_retry.status_code == 200, assign_retry.text
    assert assign_retry.json()["packing_boxes"][0]["items_count"] == 2

    conflict = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{second_box_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "orders_already_assigned"

    not_empty = await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{first_box_id}",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert not_empty.status_code == 409
    assert not_empty.json()["detail"]["code"] == "packing_box_not_empty"

    unassigned = await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{first_box_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(row) for row in order_ids],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert unassigned.status_code == 200, unassigned.text
    assert set(unassigned.json()["unassigned_order_ids"]) == {str(row) for row in order_ids}

    deleted = await async_client.request(
        "DELETE",
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{first_box_id}",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert deleted.status_code == 200, deleted.text
    assert [row["id"] for row in deleted.json()["packing_boxes"]] == [second_box_id]


@pytest.mark.asyncio
async def test_pvz_local_boxes_map_one_to_one_to_wb_cargo_without_order_binding(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-PVZ-BOX-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-PVZ-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=12)), (2, timedelta(hours=24))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.delivery_type = "pvz"
        supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.pack_status = PACK_STATUS_PACKED
        await session.commit()

    async def fake_create_cargo(
        session: AsyncSession,
        _tenant_id: uuid.UUID,
        target_supply_id: uuid.UUID,
        _count: int,
        drafts: list[object],
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for index, draft in enumerate(drafts, start=1):
            row = FbsTrbx(
                supply_id=target_supply_id,
                wb_trbx_id=f"WB-CARGO-{index}",
                packaging_box_id=draft.packaging_box_id,  # type: ignore[attr-defined]
            )
            session.add(row)
            await session.flush()
            rows.append({"id": str(row.id), "wb_trbx_id": row.wb_trbx_id})
        return rows

    monkeypatch.setattr(packing_box_svc.pvz_svc, "create_cargo_places", fake_create_cargo)

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 2, "idempotency_key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    boxes = created.json()["packing_boxes"]
    assert [row["wb_trbx_id"] for row in boxes] == ["WB-CARGO-1", "WB-CARGO-2"]
    assert all(row["orders"] == [] for row in boxes)
    async with SessionLocal() as session:
        trbxes = list(
            (await session.execute(select(FbsTrbx).where(FbsTrbx.supply_id == supply_id))).scalars()
        )
        assert len(trbxes) == 2
        persisted_orders = list(
            (await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))).scalars()
        )
        assert all(order.trbx_id is None for order in persisted_orders)


@pytest.mark.asyncio
async def test_workspace_stays_in_handoff_prep_until_every_order_is_distributed(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-STAGE-BOX-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-STAGE-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=12)), (2, timedelta(hours=24))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.status = FBS_SUPPLY_STATUS_PACKED
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.status = FBS_ORDER_STATUS_PACKED
            order.pick_status = PICK_STATUS_PICKED
            order.pack_status = PACK_STATUS_PACKED
            order.metadata_delivery_allowed = True
            order.sticker_status = STICKER_STATUS_READY
        await session.commit()

    no_boxes = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert no_boxes.status_code == 200, no_boxes.text
    assert no_boxes.json()["stage"] == "handoff_prep"
    assert any(
        row["code"] == "packing_boxes_required" and row["stage"] == "packing"
        for row in no_boxes.json()["blockers"]
    )

    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    assert created.json()["stage"] == "handoff_prep"
    box_id = created.json()["packing_boxes"][0]["id"]

    partial = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["stage"] == "handoff_prep"
    assert partial.json()["unassigned_order_ids"] == [str(order_ids[1])]
    assert any(
        row["code"] == "orders_not_distributed"
        and row["stage"] == "packing"
        and row["order_id"] == str(order_ids[1])
        for row in partial.json()["blockers"]
    )

    full = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[1])],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert full.status_code == 200, full.text
    assert full.json()["stage"] == "delivery"
    assert full.json()["unassigned_order_ids"] == []


@pytest.mark.asyncio
async def test_warehouse_packing_box_lifecycle_close_reopen_clear_and_guards(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, order_ids, box_id = await _seed_packed_supply_with_boxes(
        async_client,
        delivery_type="warehouse_sc",
    )
    base = f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}"

    empty_close = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{uuid.uuid4()}/close",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert empty_close.status_code == 404

    second_box = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": str(uuid.uuid4())},
    )
    assert second_box.status_code == 201, second_box.text
    empty_box_id = next(
        row["id"]
        for row in second_box.json()["packing_boxes"]
        if row["items_count"] == 0
    )
    reject_empty = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{empty_box_id}/close",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert reject_empty.status_code == 409
    assert reject_empty.json()["detail"]["code"] == "packing_box_empty"

    close_key = str(uuid.uuid4())
    closed = await async_client.post(
        f"{base}/close",
        headers=headers,
        json={"idempotency_key": close_key},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["packing_boxes"][0]["status"] == "closed"
    assert closed.json()["packing_boxes"][0]["items_count"] == len(order_ids)

    close_retry = await async_client.post(
        f"{base}/close",
        headers=headers,
        json={"idempotency_key": close_key},
    )
    assert close_retry.status_code == 200, close_retry.text
    assert close_retry.json()["packing_boxes"][0]["status"] == "closed"

    blocked_assign = await async_client.put(
        f"{base}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert blocked_assign.status_code == 409
    assert blocked_assign.json()["detail"]["code"] == "packing_box_closed"

    blocked_unassign = await async_client.request(
        "DELETE",
        f"{base}/orders",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert blocked_unassign.status_code == 409
    assert blocked_unassign.json()["detail"]["code"] == "packing_box_closed"

    blocked_clear = await async_client.post(
        f"{base}/clear",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert blocked_clear.status_code == 409
    assert blocked_clear.json()["detail"]["code"] == "packing_box_closed"

    reopen_key = str(uuid.uuid4())
    reopened = await async_client.post(
        f"{base}/reopen",
        headers=headers,
        json={"idempotency_key": reopen_key},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["packing_boxes"][0]["status"] == "open"

    reopen_retry = await async_client.post(
        f"{base}/reopen",
        headers=headers,
        json={"idempotency_key": reopen_key},
    )
    assert reopen_retry.status_code == 200, reopen_retry.text
    assert reopen_retry.json()["packing_boxes"][0]["status"] == "open"

    clear_key = str(uuid.uuid4())
    cleared = await async_client.post(
        f"{base}/clear",
        headers=headers,
        json={"idempotency_key": clear_key},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["packing_boxes"][0]["items_count"] == 0
    assert set(cleared.json()["unassigned_order_ids"]) == {str(row) for row in order_ids}

    clear_retry = await async_client.post(
        f"{base}/clear",
        headers=headers,
        json={"idempotency_key": clear_key},
    )
    assert clear_retry.status_code == 200, clear_retry.text
    assert cleared.json()["packing_boxes"][0]["items_count"] == 0

    conflict = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/packing-boxes/{empty_box_id}/close",
        headers=headers,
        json={"idempotency_key": close_key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_reused"


@pytest.mark.asyncio
async def test_pvz_packing_box_lifecycle_clear_and_skips_wb_cargo_calls(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cargo_calls: list[str] = []

    async def track_create_cargo(
        session: AsyncSession,
        _tenant_id: uuid.UUID,
        target_supply_id: uuid.UUID,
        _count: int,
        drafts: list[object],
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        cargo_calls.append("create")
        rows: list[dict[str, object]] = []
        for index, draft in enumerate(drafts, start=1):
            row = FbsTrbx(
                supply_id=target_supply_id,
                wb_trbx_id=f"WB-LC-{index}",
                packaging_box_id=draft.packaging_box_id,  # type: ignore[attr-defined]
            )
            session.add(row)
            await session.flush()
            rows.append({"id": str(row.id), "wb_trbx_id": row.wb_trbx_id})
        return rows

    async def track_delete_cargo(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        cargo_calls.append("delete")
        return []

    monkeypatch.setattr(packing_box_svc.pvz_svc, "create_cargo_places", track_create_cargo)
    monkeypatch.setattr(packing_box_svc.pvz_svc, "delete_cargo_places", track_delete_cargo)

    headers, supply_id, order_ids, box_id = await _seed_packed_supply_with_boxes(
        async_client,
        delivery_type="pvz",
    )
    assert cargo_calls == ["create"]
    cargo_calls.clear()

    base = f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}"
    close_key = str(uuid.uuid4())
    closed = await async_client.post(
        f"{base}/close",
        headers=headers,
        json={"idempotency_key": close_key},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["packing_boxes"][0]["status"] == "closed"

    reopened = await async_client.post(
        f"{base}/reopen",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert reopened.status_code == 200, reopened.text

    cleared = await async_client.post(
        f"{base}/clear",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert cleared.status_code == 200, cleared.text
    assert set(cleared.json()["unassigned_order_ids"]) == {str(row) for row in order_ids}
    assert cargo_calls == []


@pytest.mark.asyncio
async def test_packing_box_lifecycle_rejected_after_confirmed_delivery(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _order_ids, box_id = await _seed_packed_supply_with_boxes(
        async_client,
        delivery_type="warehouse_sc",
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.delivered_at = datetime.now(tz=UTC)
        await session.commit()

    base = f"/operations/fbs-supplies/{supply_id}/packing-boxes/{box_id}"
    for suffix in ("close", "reopen", "clear"):
        response = await async_client.post(
            f"{base}/{suffix}",
            headers=headers,
            json={"idempotency_key": str(uuid.uuid4())},
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "supply_not_editable"
