from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_NEW, FbsOrder
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.services import inventory_service
from app.services.fbs_packaging_integration_service import create_packaging_task_for_supply
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS pack {suffix}",
            "slug": f"fbs-pack-{suffix}",
            "admin_email": f"fbs-pack-{suffix}@example.com",
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
) -> tuple[str, str]:
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
    return seller_id, warehouse.json()["id"]


def _wb_order_row(*, order_id: int, article: str = "ART-A") -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": article,
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
    }


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    *,
    sku: str,
    name: str,
) -> str:
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert product.status_code in (200, 201), product.text
    return product.json()["id"]


async def _create_supply_with_orders(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    tenant_id: uuid.UUID,
    *,
    delivery_type: str = "warehouse_sc",
) -> tuple[str, list[uuid.UUID]]:
    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Pack supply",
            "delivery_type": delivery_type,
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = supply_resp.json()["id"]

    product_a = await _create_product(
        async_client, headers, seller_id, sku="prod-a", name="Product A"
    )
    product_b = await _create_product(
        async_client, headers, seller_id, sku="prod-b", name="Product B"
    )

    order_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        for _idx, (order_no, product_id, article) in enumerate(
            [
                (910001, uuid.UUID(product_a), "ART-A"),
                (910002, uuid.UUID(product_b), "ART-B"),
                (910003, uuid.UUID(product_a), "ART-A"),
            ],
            start=1,
        ):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                uuid.UUID(seller_id),
                uuid.UUID(warehouse_id),
                _wb_order_row(order_id=order_no, article=article),
            )
            order.product_id = product_id
            order.supply_id = uuid.UUID(supply_id)
            order.status = FBS_ORDER_STATUS_IN_SUPPLY
            order_ids.append(order.id)
        await session.commit()

    return supply_id, order_ids


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-PACKINT-001
@pytest.mark.asyncio
async def test_fbs_packaging_task_created_on_assembling(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == FBS_SUPPLY_STATUS_ASSEMBLING
    assert body["packaging_task_id"] is not None

    async with SessionLocal() as session:
        task = await session.get(PackagingTask, uuid.UUID(body["packaging_task_id"]))
        assert task is not None
        lines = list(
            (
                await session.execute(
                    select(PackagingTaskLine).where(
                        PackagingTaskLine.task_id == task.id
                    )
                )
            ).scalars()
        )
        assert len(lines) == 2
        qty_by_product = {line.product_id: line.qty_total for line in lines}
        assert sum(qty_by_product.values()) == 3
        assert max(qty_by_product.values()) == 2


# TC-NEW-FBS-PACKINT-002
@pytest.mark.asyncio
async def test_fbs_bind_packaging_box_to_trbx(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        delivery_type="pvz",
    )

    trbx_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert trbx_resp.status_code == 201, trbx_resp.text
    trbx_id = trbx_resp.json()["trbxes"][0]["id"]
    box_id = str(uuid.uuid4())

    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx/bind-box",
        headers=headers,
        json={"trbx_id": trbx_id, "packaging_box_id": box_id},
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["packaging_box_id"] == box_id

    async with SessionLocal() as session:
        trbx = await session.get(FbsTrbx, uuid.UUID(trbx_id))
        assert trbx is not None
        assert str(trbx.packaging_box_id) == box_id


# TC-NEW-FBS-PACKINT-003
@pytest.mark.asyncio
async def test_fbs_supply_packed_after_packaging_complete(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
                )
            ).scalars()
        )
        product_ids = {order.product_id for order in orders if order.product_id is not None}
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        for product_id in product_ids:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=sorting.id,
                quantity_delta=5,
                movement_type="inbound_intake",
            )
        await session.commit()

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    for line in task.json()["lines"]:
        pack = await async_client.post(
            f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
            headers=headers,
            json={"quantity": line["qty_total"]},
        )
        assert pack.status_code == 200, pack.text

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": True},
    )
    assert complete.status_code == 200, complete.text

    supply = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply.status_code == 200, supply.text
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_PACKED


# TC-NEW-FBS-PACKINT-004
@pytest.mark.asyncio
async def test_fbs_warehouse_sc_supply_gets_packaging_task(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        delivery_type="warehouse_sc",
    )

    resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["packaging_task_id"] is not None


# TC-NEW-FBS-PACKINT-005
@pytest.mark.asyncio
async def test_fbs_packaging_task_skips_unmapped_product(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    async with SessionLocal() as session:
        orphan = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
            )
        ).scalars().first()
        assert orphan is not None
        orphan.product_id = None
        await session.commit()

        task = await create_packaging_task_for_supply(
            session, tenant_id, uuid.UUID(supply_id)
        )
        await session.commit()
        lines = list(
            (
                await session.execute(
                    select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
                )
            ).scalars()
        )
    assert len(lines) == 2

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply is not None
        assert supply.packaging_task_id == task.id


# TC-NEW-FBS-PACKINT-006 — нельзя добавить заказ после assembling
@pytest.mark.asyncio
async def test_fbs_supply_add_order_rejected_after_assembling(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, order_ids = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text

    extra_order_id = order_ids[0]
    async with SessionLocal() as session:
        extra = await session.get(FbsOrder, extra_order_id)
        assert extra is not None
        extra.supply_id = None
        extra.status = FBS_ORDER_STATUS_NEW
        await session.commit()

    add_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders",
        headers=headers,
        json={"order_id": str(extra_order_id)},
    )
    assert add_resp.status_code == 409
    assert add_resp.json()["detail"] == "supply_not_editable"


@pytest.mark.asyncio
async def test_fbs_supply_manual_packed_status_rejected(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    packed = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "packed"},
    )
    assert packed.status_code == 400
    assert packed.json()["detail"] == "invalid_status_transition"


# TC-NEW-FBS-PACKINT-003 (marking branch) — после SGTIN отгрузка → packed
@pytest.mark.asyncio
async def test_fbs_supply_promoted_after_marking_when_honest_sign_required(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_put_meta(*_args: object, **_kwargs: object) -> None:
        return None

    async def noop_marking_assert(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.packaging_task_service._assert_marking_done_for_task",
        noop_marking_assert,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        fake_put_meta,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Honest sign product",
            "sku_code": f"cz-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": f"CZ-BAR-{suffix}",
            "requires_honest_sign": True,
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = product.json()["id"]

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "CZ supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = supply_resp.json()["id"]

    async with SessionLocal() as session:
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            uuid.UUID(seller_id),
            uuid.UUID(warehouse_id),
            _wb_order_row(order_id=920001, article="CZ-ART"),
        )
        order.product_id = uuid.UUID(product_id)
        order.supply_id = uuid.UUID(supply_id)
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=uuid.UUID(product_id),
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]
    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": line["qty_total"]},
    )
    assert pack.status_code == 200, pack.text

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": True},
    )
    assert complete.status_code == 200, complete.text

    supply_mid = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply_mid.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING

    mark = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-PACKINT-TEST"},
    )
    assert mark.status_code == 200, mark.text

    async def fake_meta(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> dict[str, object]:
        return {
            "sgtins": [{"value": "01CIS-PACKINT-TEST", "checkStatus": "ok"}],
        }

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_order_meta",
        fake_meta,
    )
    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text

    supply_done = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply_done.json()["status"] == FBS_SUPPLY_STATUS_PACKED
