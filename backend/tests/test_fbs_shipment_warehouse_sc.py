from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    STICKER_STATUS_READY,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderReservation,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING,
    FbsWbOperation,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.product import Product
from app.services import inventory_service
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_errors import WildberriesBusinessError
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS shipment {suffix}",
            "slug": f"fbs-ship-{suffix}",
            "admin_email": f"fbs-ship-{suffix}@example.com",
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
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID
) -> dict[str, Any]:
    return {
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


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    product: Product | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=order_id),
        )
        order.status = FBS_ORDER_STATUS_NEW
        if product is not None:
            order.product_id = product.id
        await session.commit()
        return order.id


async def _create_supply(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    *,
    name: str,
    delivery_type: str = "warehouse_sc",
) -> dict[str, Any]:
    resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": name,
            "delivery_type": delivery_type,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _prepare_supply_with_orders(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    tenant_id: uuid.UUID,
    *,
    wb_order_ids: list[int],
    order_status: str = FBS_ORDER_STATUS_PACKED,
    supply_status: str = FBS_SUPPLY_STATUS_PACKED,
    products: list[Product | None] | None = None,
    supply_name: str,
    delivery_type: str = "warehouse_sc",
    sticker_ready: bool = True,
) -> tuple[dict[str, Any], list[uuid.UUID]]:
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    order_ids: list[uuid.UUID] = []
    for idx, wb_order_id in enumerate(wb_order_ids):
        product = products[idx] if products is not None else None
        if product is None:
            async with SessionLocal() as session:
                product = Product(
                    tenant_id=tenant_id,
                    seller_id=seller_uuid,
                    name=f"Shipment product {wb_order_id}",
                    sku_code=f"SHIP-{wb_order_id}-{uuid.uuid4().hex[:8]}",
                )
                session.add(product)
                await session.commit()
                await session.refresh(product)
        order_ids.append(
            await _create_order(
                tenant_id,
                seller_uuid,
                warehouse_uuid,
                order_id=wb_order_id,
                product=product,
            )
        )

    supply = await _create_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        name=supply_name,
        delivery_type=delivery_type,
    )
    for local_order_id in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(local_order_id)},
        )
        assert add.status_code == 200, add.text

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        supply_row.status = supply_status
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            order.status = order_status
            if sticker_ready:
                order.sticker_status = STICKER_STATUS_READY
                order.sticker_file = f"fbs/orders/{order.id}.png"
            if order_status == FBS_ORDER_STATUS_PACKED:
                order.pack_status = "packed"
        await session.commit()

    return supply, order_ids


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    _mock_actual_composition_from_local_links(monkeypatch)


def _mock_actual_composition_from_local_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch_actual_order_ids(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_order_ids: list[int] | None = None,
    ) -> list[int]:
        async with SessionLocal() as session:
            return list(
                (
                    await session.scalars(
                        select(FbsOrder.wb_order_id).where(
                            FbsOrder.wb_supply_id == wb_supply_id
                        )
                    )
                ).all()
            )

    monkeypatch.setattr(
        "app.services.fbs_supply_composition_service.fetch_wb_supply_order_ids",
        fetch_actual_order_ids,
    )


async def _delivery_preflight(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
) -> dict[str, Any]:
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/delivery-preflight",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_and_fill_physical_box(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
    order_ids: list[uuid.UUID],
) -> None:
    created = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes",
        headers=headers,
        json={"count": 1, "idempotency_key": f"box-{supply_id}"},
    )
    assert created.status_code == 201, created.text
    box_id = created.json()["boxes"][0]["id"]
    assigned = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/boxes/{box_id}/orders",
        headers=headers,
        json={"order_ids": [str(order_id) for order_id in order_ids]},
    )
    assert assigned.status_code == 200, assigned.text


async def _deliver_with_preflight(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
    *,
    idempotency_key: str | None = None,
    confirmed_preflight_version: str | None = None,
) -> Response:
    preflight = await _delivery_preflight(async_client, headers, supply_id)
    version = confirmed_preflight_version or preflight["version"]
    payload = {
        "idempotency_key": idempotency_key or str(uuid.uuid4()),
        "confirmed_preflight_version": version,
    }
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/deliver",
        headers=headers,
        json=payload,
    )


async def _deliver_direct(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: str,
    *,
    idempotency_key: str | None = None,
) -> Response:
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/deliver",
        headers=headers,
        json={"idempotency_key": idempotency_key or str(uuid.uuid4())},
    )


# TC-NEW-FBS-SHIPWH-001 — deliver → in_delivery; bad order status → 400
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_ok_and_orders_not_ready(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950001, 950002],
        supply_name="Deliver OK",
    )
    async with SessionLocal() as session:
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            order.pack_status = "packed"
        await session.commit()
    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert body["stage"] == "tracking"
    assert body["supply"]["barcode_asset"]["kind"] == "supply_qr"
    assert body["supply"]["barcode_asset"]["status"] == "ready"
    assert body["supply"]["barcode_asset"]["preview_url"]
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY
        assert supply_row.delivered_at is not None
        assert supply_row.barcode_asset_id is not None
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert order.status == FBS_ORDER_STATUS_IN_DELIVERY

        # Simulate a confirmed delivery whose QR asset was lost or unavailable.
        supply_row.barcode_file = None
        supply_row.barcode_asset_id = None
        await session.commit()

    retry_qr = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/retry-supply-qr",
        headers=headers,
    )
    assert retry_qr.status_code == 200, retry_qr.text
    assert retry_qr.json()["supply"]["barcode_asset"]["status"] == "ready"
    assert retry_qr.json()["supply"]["barcode_asset"]["preview_url"]

    supply_bad, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950003],
        order_status=FBS_ORDER_STATUS_NEW,
        supply_name="Deliver bad status",
    )

    # Отсутствие физических коробов больше не запрет, а предупреждение:
    # решение владельца от 01.09.2026 — склад из-за коробов не стоит.
    preflight = await _delivery_preflight(async_client, headers, supply_bad["id"])
    assert preflight["can_deliver"] is True
    boxes_check = next(
        check for check in preflight["checks"] if check["code"] == "physical_boxes_required"
    )
    assert boxes_check["severity"] == "warning"

    bad = await _deliver_with_preflight(async_client, headers, supply_bad["id"])
    assert bad.status_code == 200, bad.text


# TC-NEW-FBS-SHIP-STOCK-002, TC-NEW-FBS-SHIP-STOCK-003
@pytest.mark.asyncio
async def test_fbs_delivery_writes_zero_stock_negative_once_and_releases_reserve(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            name="Negative FBS stock",
            sku_code=f"NEG-FBS-{suffix[-8:]}",
            wb_barcode=f"NEG-FBS-BAR-{suffix[-8:]}",
        )
        session.add(product)
        await session.commit()

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950091],
        products=[product],
        supply_name="Negative stock delivery",
    )
    order_id = order_ids[0]
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.reserve_status = "reserved"
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product.id,
                warehouse_id=uuid.UUID(warehouse_id),
                quantity=1,
            )
        )
        await session.commit()

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    idempotency_key = f"negative-stock-{suffix}"
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    delivered = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=idempotency_key,
        confirmed_preflight_version=preflight["version"],
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY

    repeated = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=idempotency_key,
        confirmed_preflight_version=preflight["version"],
    )
    assert repeated.status_code == 200, repeated.text

    async with SessionLocal() as session:
        ledger = await session.scalar(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order_id
            )
        )
        assert ledger is not None
        assert ledger.shipment_movement_id is not None
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.product_id == product.id,
                        InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                    )
                )
            ).scalars()
        )
        assert [(row.id, row.quantity_delta) for row in movements] == [
            (ledger.shipment_movement_id, -1)
        ]
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.storage_location_id == ledger.storage_location_id,
            )
        )
        assert balance is not None
        assert (balance.quantity, balance.quantity_unpacked, balance.quantity_packed) == (
            -1,
            -1,
            0,
        )
        reservation = await session.scalar(
            select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order_id)
        )
        assert reservation is None
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.reserve_status == "released"
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=ledger.storage_location_id,
            quantity_delta=1,
            movement_type="inbound_intake",
            actor_user_id=None,
        )
        await session.flush()
        await session.refresh(balance)
        assert (balance.quantity, balance.quantity_unpacked, balance.quantity_packed) == (
            0,
            0,
            0,
        )


# TC-NEW-FBS-SHIPWH-006 — temporary WB dispatch rejection is actionable and retryable.
@pytest.mark.asyncio
async def test_fbs_shipment_translates_temporary_dispatch_rejection(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950004],
        supply_name="Temporary WB dispatch rejection",
    )
    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    deliver_calls = 0

    async def reject_dispatch(*_args: object, **_kwargs: object) -> None:
        nonlocal deliver_calls
        deliver_calls += 1
        raise WildberriesBusinessError(
            "meta_validation_fail",
            status_code=409,
            wb_code="MetaValidationFail",
            message="Fix them to dispatch items",
        )

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        reject_dispatch,
    )

    response = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "meta_validation_fail"
    assert detail["message"] == (
        "Wildberries ещё обрабатывает поставку. Повторите передачу через минуту."
    )
    assert detail["retryable"] is True
    assert deliver_calls == 1


# TC-NEW-FBS-SHIPWH-001b — pick/pack status is optional; boxes remain required
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_allows_optional_pick_pack(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    in_supply, in_supply_order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950010],
        order_status=FBS_ORDER_STATUS_IN_SUPPLY,
        supply_status=FBS_SUPPLY_STATUS_ASSEMBLING,
        supply_name="Deliver blocked in_supply",
    )
    await _create_and_fill_physical_box(
        async_client, headers, in_supply["id"], in_supply_order_ids
    )
    delivered = await _deliver_with_preflight(async_client, headers, in_supply["id"])
    assert delivered.status_code == 200, delivered.text

    assembling, assembling_order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950011],
        order_status=FBS_ORDER_STATUS_ASSEMBLING,
        supply_status=FBS_SUPPLY_STATUS_ASSEMBLING,
        supply_name="Deliver blocked assembling",
    )
    await _create_and_fill_physical_box(
        async_client, headers, assembling["id"], assembling_order_ids
    )
    delivered_assembling = await _deliver_with_preflight(
        async_client, headers, assembling["id"]
    )
    assert delivered_assembling.status_code == 200, delivered_assembling.text


# TC-NEW-FBS-SHIPWH-002 — barcode PNG cached
@pytest.mark.asyncio
async def test_fbs_shipment_barcode_png_cached(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[951001],
        supply_name="Barcode cache",
    )

    before_deliver = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert before_deliver.status_code == 409
    assert before_deliver.json()["detail"]["code"] == "supply_bad_status"

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text

    # Deliver creates the canonical print asset. Clear only the legacy binary
    # cache so this test can prove the deprecated endpoint is cached post-deliver.
    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        supply_row.barcode_file = None
        await session.commit()

    fetch_calls = 0

    async def counting_fetch(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        type: str = "png",
        marketplace_api_base: str | None = None,
    ) -> bytes:
        nonlocal fetch_calls
        fetch_calls += 1
        from app.services.wildberries_client import _tiny_png_bytes

        return _tiny_png_bytes()

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.fetch_marketplace_supply_barcode",
        counting_fetch,
    )

    first = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("image/png")
    assert len(first.content) > 0
    assert fetch_calls == 1

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.barcode_file is not None
        cached_path = Path(settings.wms_data_dir) / supply_row.barcode_file
        assert cached_path.is_file()

    second = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert second.status_code == 200, second.text
    assert second.content == first.content
    assert fetch_calls == 1


# TC-NEW-FBS-SHIPWH-003 — requires_honest_sign without sgtin → 400; with sgtin → ok
@pytest.mark.asyncio
async def test_fbs_shipment_marking_required_and_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            name="CHZ product",
            sku_code=f"CHZ-{suffix[-8:]}",
            requires_honest_sign=True,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[952001],
        products=[product],
        supply_name="Marking required",
    )

    # Ненанесённый Честный знак виден оператору, но передачу не запрещает.
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True
    marking_check = next(
        check for check in preflight["checks"] if check["code"] == "marking_required"
    )
    assert marking_check["severity"] == "warning"

    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_ids[0],
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-SHIP-001",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ACCEPTED,
            )
        )
        await session.commit()

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text
    assert deliver.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY


# TC-NEW-FBS-SHIPWH-004 — WB error → statuses unchanged
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_wb_error_no_status_change(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953001],
        supply_name="WB fail",
    )
    idempotency_key = str(uuid.uuid4())
    active_key = {"value": idempotency_key}
    deliver_calls = 0

    async def fail_deliver(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        nonlocal deliver_calls
        deliver_calls += 1
        # Отдельная сессия видит журнал и план источника до внешнего вызова WB.
        # Flush здесь недостаточен: этот assert проходит только после commit.
        async with SessionLocal() as audit_session:
            operation = await audit_session.scalar(
                select(FbsWbOperation).where(
                    FbsWbOperation.idempotency_key == active_key["value"]
                )
            )
            assert operation is not None
            assert operation.state == WB_OPERATION_STATE_PENDING
            ledger = await audit_session.scalar(
                select(FbsShipmentReversalLedger).where(
                    FbsShipmentReversalLedger.fbs_order_id == order_ids[0]
                )
            )
            assert ledger is not None
            assert ledger.shipment_movement_id is None
            checkpoint_ids = (operation.request_summary_json or {}).get(
                "checkpoint_ledger_ids"
            )
            assert checkpoint_ids == [str(ledger.id)]
            if deliver_calls == 1:
                assert ledger.wb_operation_id == operation.id
            else:
                assert ledger.wb_operation_id != operation.id
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        fail_deliver,
    )

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    resp = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=idempotency_key,
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "wb_upstream_error_502"

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_PACKED
        assert supply_row.delivered_at is None
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_PACKED
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.idempotency_key == idempotency_key
            )
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_FAILED
        ledger = await session.scalar(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order_ids[0]
            )
        )
        assert ledger is not None
        original_checkpoint = (
            ledger.id,
            ledger.wb_operation_id,
            ledger.product_id,
            ledger.storage_location_id,
            ledger.source_warehouse_id,
            ledger.container_kind,
            ledger.container_id,
            ledger.source_mode,
            ledger.quantity,
            ledger.shortage_quantity,
            ledger.negative_quantity,
        )

    closed_key = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=idempotency_key,
    )
    assert closed_key.status_code == 409, closed_key.text
    assert closed_key.json()["detail"]["code"] == "idempotency_key_reused"
    assert deliver_calls == 1

    replacement_key = str(uuid.uuid4())
    active_key["value"] = replacement_key
    replacement = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=replacement_key,
    )
    assert replacement.status_code == 502, replacement.text
    assert deliver_calls == 2

    async with SessionLocal() as session:
        ledger = await session.get(FbsShipmentReversalLedger, original_checkpoint[0])
        assert ledger is not None
        assert (
            ledger.id,
            ledger.wb_operation_id,
            ledger.product_id,
            ledger.storage_location_id,
            ledger.source_warehouse_id,
            ledger.container_kind,
            ledger.container_id,
            ledger.source_mode,
            ledger.quantity,
            ledger.shortage_quantity,
            ledger.negative_quantity,
        ) == original_checkpoint
        replacement_operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.idempotency_key == replacement_key
            )
        )
        assert replacement_operation is not None
        assert (replacement_operation.request_summary_json or {}).get(
            "checkpoint_ledger_ids"
        ) == [str(ledger.id)]


@pytest.mark.asyncio
async def test_pending_delivery_recovers_after_process_crash_without_second_wb_call(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953051],
        supply_name="WB process crash checkpoint",
    )
    idempotency_key = str(uuid.uuid4())
    stale_failed_key = str(uuid.uuid4())

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        session.add(
            FbsWbOperation(
                tenant_id=tenant_id,
                seller_id=supply_row.seller_id,
                operation_kind="supply_deliver",
                idempotency_key=stale_failed_key,
                local_entity_type="fbs_supply",
                local_entity_id=supply_row.id,
                state=WB_OPERATION_STATE_FAILED,
                error_code="meta_validation_fail",
            )
        )
        await session.commit()

    import app.services.fbs_shipment_service as shipment_mod

    real_persist = shipment_mod._persist_confirmed_delivery
    deliver_calls = 0

    async def accepted_by_wb(*_args: object, **_kwargs: object) -> None:
        nonlocal deliver_calls
        deliver_calls += 1

    async def crash_before_local_confirmation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated process crash after WB 2xx")

    monkeypatch.setattr(shipment_mod, "deliver_marketplace_supply", accepted_by_wb)
    monkeypatch.setattr(
        shipment_mod,
        "_persist_confirmed_delivery",
        crash_before_local_confirmation,
    )

    with pytest.raises(RuntimeError, match="simulated process crash"):
        await _deliver_with_preflight(
            async_client,
            headers,
            supply["id"],
            idempotency_key=idempotency_key,
        )

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.idempotency_key == idempotency_key
            )
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING

    async def confirmed_on_reconcile(*_args: object, **_kwargs: object) -> str:
        return WB_OPERATION_STATE_CONFIRMED

    monkeypatch.setattr(shipment_mod, "_persist_confirmed_delivery", real_persist)
    monkeypatch.setattr(shipment_mod, "reconcile_supply_delivered", confirmed_on_reconcile)

    retry = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        # Another tab may still hold an older definitively failed key.  The
        # active supply-scoped checkpoint wins over that stale key and must be
        # reconciled instead of sending WB a second time.
        idempotency_key=stale_failed_key,
    )
    assert retry.status_code == 200, retry.text
    assert deliver_calls == 1
    assert retry.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY


@pytest.mark.asyncio
async def test_pending_reconcile_never_overwrites_parallel_definitive_failure(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, _order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953061],
        supply_name="WB reconcile definitive race",
    )
    idempotency_key = str(uuid.uuid4())

    import app.services.fbs_shipment_service as shipment_mod

    deliver_calls = 0

    async def accepted_by_wb(*_args: object, **_kwargs: object) -> None:
        nonlocal deliver_calls
        deliver_calls += 1

    async def crash_after_wb(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated process crash after WB 2xx")

    monkeypatch.setattr(shipment_mod, "deliver_marketplace_supply", accepted_by_wb)
    monkeypatch.setattr(shipment_mod, "_persist_confirmed_delivery", crash_after_wb)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        await _deliver_with_preflight(
            async_client,
            headers,
            supply["id"],
            idempotency_key=idempotency_key,
        )

    async def failed_while_reconcile_was_in_flight(*_args: object, **_kwargs: object) -> str:
        async with SessionLocal() as parallel_session:
            operation = await parallel_session.scalar(
                select(FbsWbOperation).where(
                    FbsWbOperation.idempotency_key == idempotency_key
                )
            )
            assert operation is not None
            operation.state = WB_OPERATION_STATE_FAILED
            operation.error_code = "meta_validation_fail"
            await parallel_session.commit()
        return "pending_confirmation"

    monkeypatch.setattr(
        shipment_mod,
        "reconcile_supply_delivered",
        failed_while_reconcile_was_in_flight,
    )
    retry = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=str(uuid.uuid4()),
    )
    assert retry.status_code == 409, retry.text
    assert retry.json()["detail"]["code"] == "meta_validation_fail"
    assert deliver_calls == 1

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.idempotency_key == idempotency_key
            )
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_FAILED


@pytest.mark.asyncio
async def test_pending_delivery_key_cannot_be_rebound_to_another_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply_a, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953071],
        supply_name="WB operation owner A",
    )
    supply_b, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953072],
        supply_name="WB operation owner B",
    )
    reused_key = str(uuid.uuid4())

    async with SessionLocal() as session:
        supply_a_row = await session.get(FbsSupply, uuid.UUID(supply_a["id"]))
        assert supply_a_row is not None
        operation = FbsWbOperation(
            tenant_id=tenant_id,
            seller_id=supply_a_row.seller_id,
            operation_kind="supply_deliver",
            idempotency_key=reused_key,
            # Legacy pending rows may predate request hashes.  Immutable local
            # ownership must still reject using this key for another supply.
            request_hash=None,
            local_entity_type="fbs_supply",
            local_entity_id=supply_a_row.id,
            state=WB_OPERATION_STATE_PENDING,
        )
        session.add(operation)
        await session.commit()
        operation_id = operation.id

    response = await _deliver_with_preflight(
        async_client,
        headers,
        supply_b["id"],
        idempotency_key=reused_key,
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_reused"

    async with SessionLocal() as session:
        operation = await session.get(FbsWbOperation, operation_id)
        assert operation is not None
        assert operation.local_entity_id == uuid.UUID(supply_a["id"])
        assert operation.state == WB_OPERATION_STATE_PENDING


# TC-NEW-FBS-SHIPWH-007 — successful WB deliver survives QR failure and retry does not deliver again
@pytest.mark.asyncio
async def test_warehouse_sc_deliver_qr_failure_keeps_confirmed_delivery_and_retries_qr_only(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953101],
        supply_name="Deliver QR checkpoint",
    )

    import app.services.fbs_shipment_service as shipment_mod

    deliver_calls = 0
    qr_calls = 0
    real_deliver = shipment_mod.deliver_marketplace_supply
    real_fetch_qr = shipment_mod.fetch_marketplace_supply_barcode

    async def counted_deliver(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        nonlocal deliver_calls
        deliver_calls += 1
        await real_deliver(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            marketplace_api_base=marketplace_api_base,
        )

    async def fail_first_qr_fetch(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        type: str = "png",
        marketplace_api_base: str | None = None,
    ) -> bytes:
        nonlocal qr_calls
        qr_calls += 1
        if qr_calls == 1:
            raise WildberriesClientError("upstream_error", status_code=502)
        return await real_fetch_qr(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            type=type,
            marketplace_api_base=marketplace_api_base,
        )

    monkeypatch.setattr(shipment_mod, "deliver_marketplace_supply", counted_deliver)
    monkeypatch.setattr(shipment_mod, "fetch_marketplace_supply_barcode", fail_first_qr_fetch)

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    idem_key = str(uuid.uuid4())
    first = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": idem_key,
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert first.status_code == 502, first.text
    assert first.json()["detail"]["code"] == "wb_upstream_error_502"
    assert deliver_calls == 1

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY
        assert supply_row.delivered_at is not None
        assert supply_row.barcode_file is None
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_IN_DELIVERY

    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": idem_key,
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert retry.status_code == 200, retry.text
    retry_workspace = retry.json()
    assert retry_workspace["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert retry_workspace["stage"] == "tracking"
    assert deliver_calls == 1
    assert qr_calls == 2

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.barcode_file is not None


# TC-NEW-FBS-SHIPWH-008 — retry-supply-qr fetches QR only; never calls WB deliver again
@pytest.mark.asyncio
async def test_retry_supply_qr_never_calls_wb_deliver(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953201],
        supply_name="Retry supply QR only",
    )

    import app.services.fbs_shipment_service as shipment_mod

    deliver_calls = 0
    real_deliver = shipment_mod.deliver_marketplace_supply

    async def counted_deliver(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        nonlocal deliver_calls
        deliver_calls += 1
        await real_deliver(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            marketplace_api_base=marketplace_api_base,
        )

    monkeypatch.setattr(shipment_mod, "deliver_marketplace_supply", counted_deliver)

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text
    assert deliver_calls == 1

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        supply_row.barcode_file = None
        supply_row.barcode_asset_id = None
        await session.commit()

    retry_qr = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/retry-supply-qr",
        headers=headers,
    )
    assert retry_qr.status_code == 200, retry_qr.text
    assert retry_qr.json()["supply"]["barcode_asset"]["status"] == "ready"
    assert deliver_calls == 1


# TC-NEW-FBS-SHIPWH-009 — retry-supply-qr also works for PVZ supplies.
# WB's GET /api/v3/supplies/{id}/barcode issues a supply QR regardless of
# delivery_type — verified against the live WB API on 2026-08-17 for both a
# pvz supply (WB-GI-266096235) and a warehouse_sc supply (WB-GI-265889432),
# both returning 200 with a PNG. The screen used to hide the supply-QR block
# and tell operators WB "does not issue" a supply QR for PVZ pickup points;
# that was false and cost a real warehouse half a shift of confusion, so the
# backend must not gate this on delivery_type either.
@pytest.mark.asyncio
async def test_retry_supply_qr_succeeds_for_pvz_delivery_type(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953301],
        supply_name="PVZ retry QR",
        delivery_type="pvz",
    )

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 200, deliver.text

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        supply_row.barcode_file = None
        supply_row.barcode_asset_id = None
        await session.commit()

    retry_qr = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/retry-supply-qr",
        headers=headers,
    )
    assert retry_qr.status_code == 200, retry_qr.text
    assert retry_qr.json()["supply"]["barcode_asset"]["status"] == "ready"


# TC-NEW-FBS-SHIPWH-005 — ПВЗ уезжает и без физических коробов (решение владельца 01.09.2026)
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_pvz_without_boxes_still_goes(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[954001, 954002],
        supply_name="PVZ supply",
        delivery_type="pvz",
    )

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True
    assert {
        check["code"]
        for check in preflight["checks"]
        if check["severity"] == "blocker"
    } == set()

    resp = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert resp.status_code == 200, resp.text


# TC-NEW-FBS-SHIPWH-006 — cancelled WB order is skipped without blocking deliver
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_cancelled_order_in_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[955001, 955002],
        order_status=FBS_ORDER_STATUS_IN_SUPPLY,
        supply_name="Cancelled in supply",
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()

    await _create_and_fill_physical_box(
        async_client,
        headers,
        supply["id"],
        [order_ids[1]],
    )

    resp = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert resp.status_code == 200, resp.text

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY
        assert supply_row.delivered_at is not None
        cancelled_order = await session.get(FbsOrder, order_ids[0])
        active_order = await session.get(FbsOrder, order_ids[1])
        assert cancelled_order is not None and active_order is not None
        assert cancelled_order.status == FBS_ORDER_STATUS_CANCELLED
        assert active_order.status == FBS_ORDER_STATUS_IN_DELIVERY
