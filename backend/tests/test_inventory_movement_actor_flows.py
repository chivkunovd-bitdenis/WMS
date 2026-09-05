from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept
from sqlalchemy import select
from test_fbs_packaging_fulfillment import (
    _create_product as _create_fbs_product,
)
from test_fbs_packaging_fulfillment import (
    _register_ff_admin,
    _setup_seller_with_token,
)
from test_inventory_movement_actor import (
    _create_inventory_context,
    _register_admin,
)
from test_marketplace_unload_and_discrepancy_acts import (
    _patch_mp_planned_date,
    _patch_packaging_instructions,
    _post_inventory,
    _seller_wb_mp_warehouse,
)

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.product import Product
from app.services import inventory_service
from app.services.fbs_cancellation_service import reverse_fbs_shipment_if_needed
from app.services.marketplace_unload_collect_service import remove_from_box


async def _actor_id(async_client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return uuid.UUID(me.json()["id"])


async def _assert_general_api_actors(
    async_client: AsyncClient,
    headers: dict[str, str],
    movement_ids: set[uuid.UUID],
    expected_actor_id: uuid.UUID | None,
) -> None:
    listed = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
        params={"limit": 500},
    )
    assert listed.status_code == 200, listed.text
    expected = str(expected_actor_id) if expected_actor_id is not None else None
    rows = [row for row in listed.json() if uuid.UUID(row["id"]) in movement_ids]
    assert {uuid.UUID(row["id"]) for row in rows} == movement_ids
    assert {row["actor_user_id"] for row in rows} == {expected}


@pytest.mark.asyncio
async def test_outbound_post_records_actor_in_row_and_both_movement_apis(
    async_client: AsyncClient,
) -> None:
    """Outbound posting must use authentication, not a spoofable body field."""
    headers, actor_id_text = await _register_admin(async_client, label="outbound")
    _, spoofed_actor = await _register_admin(async_client, label="outbound-spoof")
    warehouse_id, source_id, _, product_id, _ = await _create_inventory_context(
        async_client, headers
    )
    actor_id = uuid.UUID(actor_id_text)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        session.add(
            InventoryBalance(
                tenant_id=product.tenant_id,
                storage_location_id=uuid.UUID(source_id),
                product_id=product.id,
                quantity=8,
                quantity_unpacked=8,
                quantity_packed=0,
            )
        )
        await session.commit()

    base = "/operations/outbound-shipment-requests"
    created = await async_client.post(
        base, headers=headers, json={"warehouse_id": warehouse_id}
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    line = await async_client.post(
        f"{base}/{request_id}/lines",
        headers=headers,
        json={
            "product_id": product_id,
            "quantity": 3,
            "storage_location_id": source_id,
        },
    )
    assert line.status_code == 201, line.text
    submitted = await async_client.post(f"{base}/{request_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    posted = await async_client.post(
        f"{base}/{request_id}/post",
        headers=headers,
        json={"actor_user_id": spoofed_actor},
    )
    assert posted.status_code == 200, posted.text

    async with SessionLocal() as session:
        movement = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.outbound_shipment_line_id
                    == uuid.UUID(line.json()["id"])
                )
            )
        ).scalar_one()
        assert movement.quantity_delta == -3
        assert movement.actor_user_id == actor_id
        movement_id = movement.id

    detail = await async_client.get(f"{base}/{request_id}/movements", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()[0]["actor_user_id"] == actor_id_text
    await _assert_general_api_actors(async_client, headers, {movement_id}, actor_id)


@pytest.mark.asyncio
async def test_discrepancy_act_approval_records_approving_user_as_actor(
    async_client: AsyncClient,
) -> None:
    """A confirmed discrepancy becomes stock only under the approving user."""
    headers, actor_id_text = await _register_admin(async_client, label="discrepancy")
    warehouse_id, _, _, product_id, sku_code = await _create_inventory_context(
        async_client, headers
    )
    actor_id = uuid.UUID(actor_id_text)

    inbound_base = "/operations/inbound-intake-requests"
    inbound = await async_client.post(
        inbound_base, headers=headers, json={"warehouse_id": warehouse_id}
    )
    assert inbound.status_code == 201, inbound.text
    inbound_id = inbound.json()["id"]
    line = await async_client.post(
        f"{inbound_base}/{inbound_id}/lines",
        headers=headers,
        json={"product_id": product_id, "expected_qty": 1},
    )
    assert line.status_code == 201, line.text
    await post_primary_accept(async_client, inbound_base, inbound_id, headers)
    await fulfill_inbound_via_box_scans(
        async_client, headers, inbound_id, sku_code, 1
    )
    verified = await async_client.post(
        f"{inbound_base}/{inbound_id}/verify", headers=headers
    )
    assert verified.status_code == 200, verified.text

    act = await async_client.post(
        "/operations/discrepancy-acts",
        headers=headers,
        json={"inbound_intake_request_id": inbound_id},
    )
    assert act.status_code == 201, act.text
    act_id = act.json()["id"]
    act_line = await async_client.post(
        f"/operations/discrepancy-acts/{act_id}/lines",
        headers=headers,
        json={
            "product_id": product_id,
            "quantity": 2,
            "inbound_intake_line_id": line.json()["id"],
        },
    )
    assert act_line.status_code == 201, act_line.text
    submitted = await async_client.post(
        f"/operations/discrepancy-acts/{act_id}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    approved = await async_client.post(
        f"/operations/discrepancy-acts/{act_id}/approve", headers=headers
    )
    assert approved.status_code == 200, approved.text

    async with SessionLocal() as session:
        movement = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.product_id == uuid.UUID(product_id),
                    InventoryMovement.movement_type == "discrepancy_act",
                )
            )
        ).scalar_one()
        assert movement.quantity_delta == 2
        assert movement.actor_user_id == actor_id
        movement_id = movement.id
    await _assert_general_api_actors(async_client, headers, {movement_id}, actor_id)


@pytest.mark.asyncio
@pytest.mark.skip(
    reason=(
        "Тест закрепляет списание остатка на завершении упаковки. Этого этапа "
        "больше нет: по решению владельца от 28.08.2026 товар списывается ровно "
        "один раз — на подтверждённой доставке, иначе он уходил дважды. "
        "Озоновский заказ с привязанным товаром списывается там же, вместе со "
        "всеми остальными. Тест нужно переписать под этап доставки — это "
        "отдельное решение, а не переписывание проверок под код."
    )
)
async def test_ozon_packaging_write_off_records_operator_actor(
    async_client: AsyncClient,
) -> None:
    """Ozon packaging completion must not fall through to an anonymous write-off."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    actor_id = await _actor_id(async_client, headers)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_fbs_product(
        async_client, headers, seller_id, sku=f"actor-ozon-{suffix}"
    )

    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace="ozon",
            external_supply_id=f"ozon-actor-{suffix}",
            wb_supply_id=f"PENDING-{suffix}",
            name="Ozon actor packaging",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.flush()
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            supply_id=supply.id,
            marketplace="ozon",
            external_order_id=f"ozon-actor-posting-{suffix}",
            wb_order_id=980001,
            created_at_wb=now - timedelta(hours=1),
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            status=FBS_ORDER_STATUS_IN_SUPPLY,
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=product_id,
                ozon_sku=80801,
                offer_id="actor-offer",
                name="Actor Ozon product",
                quantity=1,
                reserved_quantity=1,
                position_index=0,
            )
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="system_seed",
            actor_user_id=None,
        )
        await session.commit()
        supply_id = supply.id
        order_id = order.id

    assembling = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert assembling.status_code == 200, assembling.text
    task_id = assembling.json()["packaging_task_id"]
    picked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/manual",
        headers=headers,
        json={
            "location_id": str(source_location_id),
            "product_id": str(product_id),
            "order_id": str(order_id),
            "idempotency_key": f"ozon-actor-pick-{suffix}",
        },
    )
    assert picked.status_code == 200, picked.text
    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}", headers=headers
    )
    assert task.status_code == 200, task.text
    packed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{task.json()['lines'][0]['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": f"ozon-actor-pack-{suffix}"},
    )
    assert packed.status_code == 200, packed.text
    completed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert completed.status_code == 200, completed.text

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        order = await session.get(FbsOrder, order_id)
        assert supply is not None and supply.marketplace == "ozon"
        assert order is not None and order.marketplace == "ozon"
        movement = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.product_id == product_id,
                    InventoryMovement.movement_type == "fbs_shipment",
                    InventoryMovement.quantity_delta < 0,
                )
            )
        ).scalar_one()
        assert movement.actor_user_id == actor_id
        movement_id = movement.id
    await _assert_general_api_actors(async_client, headers, {movement_id}, actor_id)


@pytest.mark.asyncio
async def test_fbs_cancellation_preserves_shipment_actor_without_returning_stock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation preserves the shipment actor and cannot book a physical return."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    actor_id = await _actor_id(async_client, headers)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_fbs_product(
        async_client, headers, seller_id, sku=f"actor-cancel-{suffix}"
    )

    async with SessionLocal() as session:
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            marketplace="wb",
            external_order_id=f"wb-cancel-{suffix}",
            wb_order_id=980002,
            created_at_wb=now - timedelta(hours=1),
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            status=FBS_ORDER_STATUS_PACKED,
        )
        session.add(order)
        await session.flush()
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="system_seed",
            actor_user_id=None,
        )
        # Даже историческая запись о списании не разрешает отмене оприходовать
        # товар: физический возврат оформляется отдельным документом.
        shipment_movement = await inventory_service.apply_fbs_supply_write_off(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity=1,
            actor_user_id=actor_id,
        )
        await session.flush()
        ledger = FbsShipmentReversalLedger(
            tenant_id=tenant_id,
            fbs_order_id=order.id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity=1,
            shipment_movement_id=shipment_movement.id,
        )
        session.add(ledger)
        await session.commit()
        order_id = order.id

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order", fake_cancel
    )
    cancelled = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
        json={"actor_user_id": str(uuid.uuid4())},
    )
    assert cancelled.status_code == 200, cancelled.text

    async with SessionLocal() as session:
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.product_id == product_id,
                        InventoryMovement.movement_type == "fbs_shipment",
                    )
                )
            ).scalars()
        )
        assert [row.quantity_delta for row in movements] == [-1]
        assert movements[0].actor_user_id == actor_id
        movement_id = movements[0].id
        balance_rows = await session.scalars(
            select(InventoryBalance).where(InventoryBalance.product_id == product_id)
        )
        assert sum(balance.quantity for balance in balance_rows) == 0
        cancelled_order = await session.get(FbsOrder, order_id)
        assert cancelled_order is not None and cancelled_order.status == "cancelled"
    await _assert_general_api_actors(async_client, headers, {movement_id}, actor_id)


@pytest.mark.asyncio
async def test_marketplace_unload_box_add_and_remove_record_actor(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both taking stock into a box and returning it preserve the operator."""
    headers, actor_text = await _register_admin(async_client, label="mp-box")
    _, spoofed_actor = await _register_admin(async_client, label="mp-box-spoof")
    actor_id = uuid.UUID(actor_text)
    unique = uuid.uuid4().hex
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "MP actor warehouse", "code": f"mp-actor-{unique}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]
    seller_id, wb_warehouse_id = await _seller_wb_mp_warehouse(
        async_client, headers, monkeypatch
    )
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "MP actor product",
            "sku_code": f"MP-ACTOR-{unique}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": seller_id,
        },
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["id"]
    await _patch_packaging_instructions(async_client, headers, product_id)
    location_id = await _post_inventory(
        async_client,
        headers,
        warehouse_id=warehouse_id,
        product_id=product_id,
        qty=5,
        location_code="MP-ACTOR-LOC",
    )
    base = "/operations/marketplace-unload-requests"
    unload = await async_client.post(
        base,
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "seller_id": seller_id,
            "wb_mp_warehouse_id": wb_warehouse_id,
        },
    )
    assert unload.status_code == 201, unload.text
    request_id = unload.json()["id"]
    planned = await async_client.post(
        f"{base}/{request_id}/lines",
        headers=headers,
        json={"product_id": product_id, "quantity": 3},
    )
    assert planned.status_code == 201, planned.text
    await _patch_mp_planned_date(async_client, headers, request_id)
    submitted = await async_client.post(
        f"{base}/{request_id}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    box = await async_client.post(
        f"{base}/{request_id}/boxes",
        headers=headers,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]
    added = await async_client.post(
        f"{base}/{request_id}/boxes/{box_id}/manual-line",
        headers=headers,
        json={
            "product_id": product_id,
            "storage_location_id": location_id,
            "quantity": 2,
            "actor_user_id": spoofed_actor,
        },
    )
    assert added.status_code == 200, added.text
    line_id = uuid.UUID(added.json()["id"])

    async with SessionLocal() as session:
        negative = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.marketplace_unload_request_id
                    == uuid.UUID(request_id),
                    InventoryMovement.quantity_delta == -2,
                )
            )
        ).scalar_one()
        assert negative.actor_user_id == actor_id
        removed = await remove_from_box(
            session,
            actor_user_id=actor_id,
            tenant_id=negative.tenant_id,
            request_id=uuid.UUID(request_id),
            box_id=uuid.UUID(box_id),
            line_id=line_id,
            quantity=2,
        )
        assert removed is None

    async with SessionLocal() as session:
        request = await session.get(MarketplaceUnloadRequest, uuid.UUID(request_id))
        assert request is not None
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.marketplace_unload_request_id == request.id
                    )
                )
            ).scalars()
        )
        assert sorted(row.quantity_delta for row in movements) == [-2, 2]
        assert {row.actor_user_id for row in movements} == {actor_id}
        movement_ids = {row.id for row in movements}
    await _assert_general_api_actors(
        async_client, headers, movement_ids, actor_id
    )


@pytest.mark.asyncio
async def test_system_cancellation_does_not_create_a_return_movement(
    async_client: AsyncClient,
) -> None:
    """System cancellation also leaves the physical write-off and its actor unchanged."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_fbs_product(
        async_client, headers, seller_id, sku=f"actor-system-{suffix}"
    )
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            marketplace="wb",
            external_order_id=f"wb-system-{suffix}",
            wb_order_id=980003,
            created_at_wb=now,
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            status=FBS_ORDER_STATUS_PACKED,
        )
        session.add(order)
        await session.flush()
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="system_seed",
            actor_user_id=None,
        )
        shipment_movement = await inventory_service.apply_fbs_supply_write_off(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity=1,
            actor_user_id=None,
        )
        await session.flush()
        session.add(
            FbsShipmentReversalLedger(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                storage_location_id=source_location_id,
                quantity=1,
                shipment_movement_id=shipment_movement.id,
            )
        )
        await session.flush()
        reversed_now = await reverse_fbs_shipment_if_needed(
            session, order, actor_user_id=None
        )
        assert reversed_now is False
        await session.commit()
        movements = list((
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.product_id == product_id,
                    InventoryMovement.movement_type == "fbs_shipment",
                )
            )
        ).scalars())
        assert [row.quantity_delta for row in movements] == [-1]
        assert movements[0].actor_user_id is None
        movement_id = movements[0].id
        balance_rows = await session.scalars(
            select(InventoryBalance).where(InventoryBalance.product_id == product_id)
        )
        assert sum(balance.quantity for balance in balance_rows) == 0
    await _assert_general_api_actors(async_client, headers, {movement_id}, None)
