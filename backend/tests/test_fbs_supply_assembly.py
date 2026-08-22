from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_NEW, FbsOrder
from app.models.fbs_supply import FBS_SUPPLY_STATUS_DRAFT, FbsSupply
from app.models.product import Product
from app.services.fbs_order_tape_print_service import (
    _is_complete_supply_order_set,
    _orders_in_canonical_order,
    _select_requested_orders,
)
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.test_fbs_shipment_warehouse_sc import _deliver_with_preflight


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS supply {suffix}",
            "slug": f"fbs-supply-{suffix}",
            "admin_email": f"fbs-supply-{suffix}@example.com",
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


def _wb_order_row(
    *,
    order_id: int,
    article: str = "ART-001",
    barcode: str = "FBS-BARCODE-001",
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": article,
        "skus": [barcode],
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
    article: str = "ART-001",
    barcode: str | None = None,
    product: Product | None = None,
) -> uuid.UUID:
    row = _wb_order_row(
        order_id=order_id,
        article=article,
        barcode=barcode or f"BAR-{order_id}",
    )
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
            row,
        )
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
    name: str = "Supply A",
) -> dict[str, Any]:
    resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": name,
            "delivery_type": "warehouse_sc",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-SUPPLY-001 — create supply draft + wb_supply_id; WB error → no orphan row
@pytest.mark.asyncio
async def test_fbs_supply_create_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

    body = await _create_supply(async_client, headers, seller_id, warehouse_id)
    assert body["status"] == FBS_SUPPLY_STATUS_DRAFT
    assert body["wb_supply_id"].startswith("WB-GI-MOCK-")
    assert body["name"] == "Supply A"
    assert body["delivery_type"] == "warehouse_sc"


# TC-NEW-FBS-SUPPLY-005 — full tape input is normalized to the picking-list order.
def test_fbs_order_tape_canonical_order_is_independent_of_requested_order() -> None:
    product_a = SimpleNamespace(sku_code="SKU-A", wb_size="M", name="Alpha")
    product_b = SimpleNamespace(sku_code="SKU-B", wb_size="L", name="Beta")
    first = SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        wb_order_id=200,
        wb_article="ART-B",
        product=product_b,
    )
    second = SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        wb_order_id=100,
        wb_article="ART-A",
        product=product_a,
    )

    assert _orders_in_canonical_order(SimpleNamespace(orders=[first, second])) == [second, first]


# TC-NEW-FBS-SUPPLY-005 — row reprint may select one order, but keeps its full-tape number.
def test_fbs_order_tape_subset_keeps_full_supply_sequence() -> None:
    first = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000001"))
    second = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000002"))
    third = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000003"))

    selected = _select_requested_orders([first, second, third], [third.id])

    assert selected == [third]
    assert {order.id: number for number, order in enumerate([first, second, third], 1)}[
        selected[0].id
    ] == 3


def test_fbs_order_tape_rejects_order_outside_supply() -> None:
    first = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000001"))
    outside = uuid.UUID("00000000-0000-0000-0000-000000000099")

    with pytest.raises(KeyError):
        _select_requested_orders([first], [outside])


# TC-NEW-FBS-SUPPLY-006 — a full tape must name every current order exactly once.
def test_fbs_order_tape_full_set_check_requires_every_order_exactly_once() -> None:
    first = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000001"))
    second = SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000002"))

    assert _is_complete_supply_order_set([first, second], [second.id, first.id])
    assert not _is_complete_supply_order_set([first, second], [first.id])
    assert not _is_complete_supply_order_set([first, second], [first.id, first.id])


# TC-NEW-FBS-SUPPLY-ORDER-001 — supply.orders is stable by WB id, then UUID.
@pytest.mark.asyncio
async def test_fbs_supply_orders_are_returned_in_stable_order(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_uuid)
        assert seller is not None
        tenant_id = seller.tenant_id

    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)

    # A duplicate WB ID is impossible for one seller by the production unique
    # constraint.  Two sellers let this relationship-level test exercise the
    # tie-breaker without disabling that constraint.
    second_seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Second seller {suffix}"}
    )
    assert second_seller.status_code in (200, 201), second_seller.text

    first_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    second_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        session.add_all(
            [
                FbsOrder(
                    id=first_id,
                    tenant_id=tenant_id,
                    seller_id=seller_uuid,
                    warehouse_id=warehouse_uuid,
                    supply_id=uuid.UUID(supply["id"]),
                    wb_order_id=810101,
                    status=FBS_ORDER_STATUS_IN_SUPPLY,
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                    mapping_status="missing",
                    reserve_status="skipped_no_product",
                ),
                FbsOrder(
                    id=second_id,
                    tenant_id=tenant_id,
                    seller_id=uuid.UUID(second_seller.json()["id"]),
                    warehouse_id=warehouse_uuid,
                    supply_id=uuid.UUID(supply["id"]),
                    wb_order_id=810101,
                    status=FBS_ORDER_STATUS_IN_SUPPLY,
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                    mapping_status="missing",
                    reserve_status="skipped_no_product",
                ),
            ]
        )
        await session.commit()

    loaded = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}", headers=headers
    )
    assert loaded.status_code == 200, loaded.text
    assert [row["wb_order_id"] for row in loaded.json()["orders"]] == [810101, 810101]
    assert [row["id"] for row in loaded.json()["orders"]] == [str(second_id), str(first_id)]


def test_fbs_supply_relationship_orders_by_wb_id_then_internal_id() -> None:
    order_by = FbsSupply.orders.property.order_by
    assert len(order_by) == 2
    assert str(order_by[0]).endswith("fbs_orders.wb_order_id")
    assert str(order_by[1]).endswith("fbs_orders.id")


@pytest.mark.asyncio
async def test_fbs_supply_create_wb_error_no_db_row(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

    async def fail_create(
        client: object, *, api_token: str, name: str, marketplace_api_base: str | None = None
    ) -> dict[str, Any]:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.create_marketplace_supply",
        fail_create,
    )

    resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Fail supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "wb_upstream_error_502"

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(FbsSupply))
        assert count == 0


# TC-NEW-FBS-SUPPLY-002 — add order → in_supply; already in other supply → error
@pytest.mark.asyncio
async def test_fbs_supply_add_order_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810001
    )
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)

    add = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert add.status_code == 200, add.text
    body = add.json()
    assert len(body["orders"]) == 1
    assert body["orders"][0]["status"] == FBS_ORDER_STATUS_IN_SUPPLY
    assert body["orders"][0]["supply_id"] == supply["id"]


@pytest.mark.asyncio
async def test_fbs_supply_deliver_blocked_from_in_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810003
    )
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)

    add = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert add.status_code == 200, add.text

    deliver = await _deliver_with_preflight(async_client, headers, supply["id"])
    assert deliver.status_code == 400
    assert deliver.json()["detail"]["code"] == "packaging_required"


@pytest.mark.asyncio
async def test_fbs_supply_add_order_already_in_other_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810002
    )
    supply_a = await _create_supply(async_client, headers, seller_id, warehouse_id, name="A")
    supply_b = await _create_supply(async_client, headers, seller_id, warehouse_id, name="B")

    first = await async_client.post(
        f"/operations/fbs-supplies/{supply_a['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert first.status_code == 200, first.text

    second = await async_client.post(
        f"/operations/fbs-supplies/{supply_b['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "order_already_in_supply"


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_fbs_supply_add_order_concurrent_race(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Two parallel adds of the same order to different supplies — exactly one wins."""
    if "sqlite" in os.environ.get("DATABASE_URL", "").lower():
        pytest.skip("row-level FOR UPDATE locking requires PostgreSQL")

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810099
    )
    supply_a = await _create_supply(async_client, headers, seller_id, warehouse_id, name="Race A")
    supply_b = await _create_supply(async_client, headers, seller_id, warehouse_id, name="Race B")

    resp_a, resp_b = await asyncio.gather(
        async_client.post(
            f"/operations/fbs-supplies/{supply_a['id']}/orders",
            headers=headers,
            json={"order_id": str(order_id)},
        ),
        async_client.post(
            f"/operations/fbs-supplies/{supply_b['id']}/orders",
            headers=headers,
            json={"order_id": str(order_id)},
        ),
    )

    statuses = sorted([resp_a.status_code, resp_b.status_code])
    assert statuses == [200, 409], (
        resp_a.status_code,
        resp_a.text,
        resp_b.status_code,
        resp_b.text,
    )
    bodies = [resp_a, resp_b]
    winner = next(r for r in bodies if r.status_code == 200)
    loser = next(r for r in bodies if r.status_code == 409)
    assert winner.json()["orders"][0]["status"] == FBS_ORDER_STATUS_IN_SUPPLY
    assert loser.json()["detail"] in {"order_already_in_supply", "order_bad_status"}

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY
        assert order.supply_id is not None


@pytest.mark.asyncio
async def test_fbs_supply_add_order_warehouse_mismatch(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    other_wh = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Other WH", "code": f"wh-other-{suffix[-6:]}"},
    )
    assert other_wh.status_code in (200, 201), other_wh.text
    other_warehouse_uuid = uuid.UUID(other_wh.json()["id"])

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810100
    )
    supply = await _create_supply(
        async_client, headers, seller_id, str(other_warehouse_uuid), name="Wrong WH"
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "order_warehouse_mismatch"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_NEW
        assert order.supply_id is None


@pytest.mark.asyncio
async def test_fbs_supply_add_order_wb_error_leaves_order_new(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(
        tenant_id, seller_uuid, warehouse_uuid, order_id=810101
    )
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)

    async def fail_add(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_order_to_marketplace_supply",
        fail_add,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "wb_upstream_error_502"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_NEW
        assert order.supply_id is None


# TC-NEW-FBS-SUPPLY-003 — picking list grouping + empty supply
@pytest.mark.asyncio
async def test_fbs_supply_picking_list_grouping(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    product_a = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Leggings",
            "sku_code": f"LEG-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "BAR-A",
            "wb_size": "M",
        },
    )
    assert product_a.status_code in (200, 201)
    product_b = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Top",
            "sku_code": f"TOP-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "BAR-B",
            "wb_size": "L",
        },
    )
    assert product_b.status_code in (200, 201)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id
        prod_a = await session.get(Product, uuid.UUID(product_a.json()["id"]))
        prod_b = await session.get(Product, uuid.UUID(product_b.json()["id"]))
        assert prod_a is not None and prod_b is not None

    canonical_order_ids = [
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820000,
            article="",
            barcode="BAR-EMPTY-A",
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820001,
            article="",
            barcode="BAR-EMPTY-B",
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820002,
            article="ART-A",
            barcode="BAR-A",
            product=prod_a,
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820003,
            article="ART-A",
            barcode="BAR-A",
            product=prod_a,
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820004,
            article="ART-B",
            barcode="BAR-B",
            product=prod_b,
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820005,
            article="ART-C",
            barcode="BAR-C",
        ),
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=820006,
            article="ART-D",
            barcode="BAR-D",
        ),
    ]
    # The supply is deliberately assembled in a different order.  The API must
    # return the product-group order, not relationship/insertion order.
    order_ids = [
        canonical_order_ids[5],
        canonical_order_ids[3],
        canonical_order_ids[1],
        canonical_order_ids[6],
        canonical_order_ids[0],
        canonical_order_ids[4],
        canonical_order_ids[2],
    ]

    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)
    for oid in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(oid)},
        )
        assert add.status_code == 200, add.text

    picking = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/picking-list",
        headers=headers,
    )
    assert picking.status_code == 200, picking.text
    items = picking.json()["items"]
    assert len(items) == 5
    unknown = next(i for i in items if i["product_name"] == "Unknown")
    assert (unknown["article"], unknown["sku_code"], unknown["size"]) == ("", None, None)
    assert unknown["quantity"] == 2
    assert (unknown["number_start"], unknown["number_end"]) == (1, 2)
    assert [uuid.UUID(value) for value in unknown["order_ids"]] == canonical_order_ids[:2]
    leggings = next(i for i in items if i["product_name"] == "Leggings")
    assert leggings["quantity"] == 2
    assert leggings["article"] == "ART-A"
    assert leggings["size"] == "M"
    assert (leggings["number_start"], leggings["number_end"]) == (3, 4)
    assert [uuid.UUID(value) for value in leggings["order_ids"]] == canonical_order_ids[2:4]
    actual_keys = [
        (item["article"], item["sku_code"], item["size"], item["product_name"])
        for item in items
    ]
    assert actual_keys == [
        ("", None, None, "Unknown"),
        ("ART-A", prod_a.sku_code, prod_a.wb_size, prod_a.name),
        ("ART-B", prod_b.sku_code, prod_b.wb_size, prod_b.name),
        ("ART-C", None, None, "ART-C"),
        ("ART-D", None, None, "ART-D"),
    ]
    assert [(item["number_start"], item["number_end"]) for item in items] == [
        (1, 2),
        (3, 4),
        (5, 5),
        (6, 6),
        (7, 7),
    ]

    repeated = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/picking-list",
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json() == picking.json()

    empty_supply = await _create_supply(
        async_client, headers, seller_id, warehouse_id, name="Empty"
    )
    empty = await async_client.get(
        f"/operations/fbs-supplies/{empty_supply['id']}/picking-list",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


# TC-NEW-FBS-SUPPLY-004 — stickers cached; WB error surfaced
@pytest.mark.asyncio
async def test_fbs_supply_stickers_cached(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_ids = [
        await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=830001),
        await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=830002),
        await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=830003),
    ]
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)
    for oid in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(oid)},
        )
        assert add.status_code == 200, add.text

    stickers = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/stickers",
        headers=headers,
        json={"force": False},
    )
    assert stickers.status_code == 200, stickers.text
    body = stickers.json()["stickers"]
    assert len(body) == 3
    for row in body:
        assert row["sticker_code"] == f"{row['wb_order_id']} {row['wb_order_id'] + 1}"
        assert row["sticker_file"] is not None
        assert row["sticker_file"].startswith("fbs-print-assets/order-stickers/")
        sticker_path = Path(settings.wms_data_dir) / row["sticker_file"]
        assert sticker_path.is_file()

    async with SessionLocal() as session:
        for oid in order_ids:
            order = await session.get(FbsOrder, oid)
            assert order is not None
            assert order.sticker_file is not None
            assert order.sticker_code is not None


@pytest.mark.asyncio
async def test_fbs_supply_stickers_wb_error(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=840001)
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)
    add = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert add.status_code == 200, add.text

    async def fail_stickers(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
        width: int = 58,
        height: int = 40,
    ) -> list[dict[str, Any]]:
        raise WildberriesClientError("upstream_error", status_code=503)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.fetch_marketplace_order_stickers",
        fail_stickers,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/stickers",
        headers=headers,
        json={"force": True},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "wb_upstream_error_503"


@pytest.mark.asyncio
async def test_fbs_supply_stickers_incomplete(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_ids = [
        await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=840010),
        await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=840011),
    ]
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)
    for oid in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(oid)},
        )
        assert add.status_code == 200, add.text

    async def partial_stickers(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
        width: int = 58,
        height: int = 40,
    ) -> list[dict[str, Any]]:
        tiny_png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        return [
            {
                "orderId": order_ids[0],
                "barcode": f"MOCK-{order_ids[0]}",
                "partA": order_ids[0],
                "partB": order_ids[0] + 1,
                "file": tiny_png,
            }
        ]

    monkeypatch.setattr(
        "app.services.fbs_supply_service.fetch_marketplace_order_stickers",
        partial_stickers,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/stickers",
        headers=headers,
        json={"force": True},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "wb_stickers_incomplete"


@pytest.mark.asyncio
async def test_fbs_supply_add_order_bad_status(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_id = await _create_order(tenant_id, seller_uuid, warehouse_uuid, order_id=850001)
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)

    first = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert first.status_code == 200

    again = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "order_bad_status"
