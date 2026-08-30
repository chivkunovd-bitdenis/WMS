from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeCargoPlaceLine

BASE = "/operations/inbound-intake-requests"


async def _register_admin(
    async_client: AsyncClient,
    label: str,
) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:10]
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Cargo place {label}",
            "slug": f"cargo-place-{label}-{suffix}",
            "admin_email": f"cargo-place-{label}-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    label: str,
) -> tuple[str, str]:
    response = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Товар {label}",
            "sku_code": f"SKU-CARGO-{label}-{uuid.uuid4().hex[:8]}",
            "seller_id": seller_id,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"], response.json()["sku_code"]


async def _create_receiving_with_cargo_place(
    async_client: AsyncClient,
    headers: dict[str, str],
    label: str,
) -> tuple[str, str, str, str, str]:
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"Склад {label}", "code": f"cargo-{label}-{uuid.uuid4().hex[:8]}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Селлер {label}"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    product_id, sku_code = await _create_product(
        async_client, headers, seller_id, label
    )
    request = await async_client.post(
        BASE,
        headers=headers,
        json={"warehouse_id": warehouse.json()["id"], "seller_id": seller_id},
    )
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]
    line = await async_client.post(
        f"{BASE}/{request_id}/lines",
        headers=headers,
        json={"product_id": product_id, "expected_qty": 100},
    )
    assert line.status_code == 201, line.text
    planned = await async_client.patch(
        f"{BASE}/{request_id}",
        headers=headers,
        json={"planned_box_count": 1},
    )
    assert planned.status_code == 200, planned.text
    submitted = await async_client.post(
        f"{BASE}/{request_id}/submit",
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    places = await async_client.post(
        f"{BASE}/{request_id}/cargo-places",
        headers=headers,
        json={"quantity": 1},
    )
    assert places.status_code == 201, places.text
    place = places.json()[0]
    assert place["lines"] == []
    assert place["remaining_qty"] == 0
    return request_id, place["id"], product_id, sku_code, seller_id


@pytest.mark.asyncio
async def test_cargo_place_quantity_scan_update_and_remove_one_line(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-001: quantity and scanner mutate one visible cargo-place line."""
    headers = await _register_admin(async_client, "edit")
    request_id, place_id, product_id, sku_code, _seller_id = (
        await _create_receiving_with_cargo_place(async_client, headers, "edit")
    )
    line_url = f"{BASE}/{request_id}/cargo-places/{place_id}/lines/{product_id}"

    created = await async_client.put(line_url, headers=headers, json={"quantity": 3})
    assert created.status_code == 200, created.text
    created_body = created.json()
    assert created_body["id"] == place_id
    assert created_body["remaining_qty"] == 3
    assert len(created_body["lines"]) == 1
    created_line = created_body["lines"][0]
    assert created_line == {
        "id": created_line["id"],
        "product_id": product_id,
        "sku_code": sku_code,
        "product_name": "Товар edit",
        "quantity": 3,
        "posted_qty": 0,
        "remaining_qty": 3,
    }

    updated = await async_client.put(line_url, headers=headers, json={"quantity": 7})
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["lines"]) == 1
    assert updated.json()["lines"][0]["id"] == created_line["id"]
    assert updated.json()["lines"][0]["quantity"] == 7

    scanned = await async_client.post(
        f"{BASE}/{request_id}/cargo-places/{place_id}/scan",
        headers=headers,
        json={"barcode": sku_code},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["id"] == place_id
    assert len(scanned.json()["lines"]) == 1
    assert scanned.json()["lines"][0]["id"] == created_line["id"]
    assert scanned.json()["lines"][0]["quantity"] == 8

    request = await async_client.get(f"{BASE}/{request_id}", headers=headers)
    assert request.status_code == 200, request.text
    request_place = next(
        place for place in request.json()["cargo_places"] if place["id"] == place_id
    )
    assert len(request_place["lines"]) == 1
    assert request_place["lines"][0]["quantity"] == 8

    removed = await async_client.put(line_url, headers=headers, json={"quantity": 0})
    assert removed.status_code == 200, removed.text
    assert removed.json()["remaining_qty"] == 0
    assert removed.json()["lines"] == []


@pytest.mark.asyncio
async def test_cargo_place_scan_increases_accepted_qty_and_posts_stock(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-005: cargo-place intake is visible and enters accepted stock."""
    headers = await _register_admin(async_client, "accepted")
    request_id, place_id, product_id, sku_code, _seller_id = (
        await _create_receiving_with_cargo_place(async_client, headers, "accepted")
    )

    started = await async_client.post(
        f"{BASE}/{request_id}/begin-receiving",
        headers=headers,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "receiving"

    scanned = await async_client.post(
        f"{BASE}/{request_id}/cargo-places/{place_id}/scan",
        headers=headers,
        json={"barcode": sku_code},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["lines"][0]["product_id"] == product_id
    assert scanned.json()["lines"][0]["quantity"] == 1

    request = await async_client.get(f"{BASE}/{request_id}", headers=headers)
    assert request.status_code == 200, request.text
    body = request.json()
    assert body["lines"][0]["effective_actual_qty"] == 1
    request_place = next(place for place in body["cargo_places"] if place["id"] == place_id)
    assert request_place["lines"][0]["product_id"] == product_id
    assert request_place["lines"][0]["quantity"] == 1

    completed = await async_client.post(
        f"{BASE}/{request_id}/complete-receiving",
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "sorting"
    assert completed.json()["lines"][0]["actual_qty"] == 1

    late_scan = await async_client.post(
        f"{BASE}/{request_id}/cargo-places/{place_id}/scan",
        headers=headers,
        json={"barcode": sku_code},
    )
    assert late_scan.status_code == 409, late_scan.text
    assert late_scan.json()["detail"] == "not_editable"
    late_update = await async_client.put(
        f"{BASE}/{request_id}/cargo-places/{place_id}/lines/{product_id}",
        headers=headers,
        json={"quantity": 2},
    )
    assert late_update.status_code == 409, late_update.text
    assert late_update.json()["detail"] == "not_editable"

    unchanged = await async_client.get(f"{BASE}/{request_id}", headers=headers)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["lines"][0]["actual_qty"] == 1
    unchanged_place = next(
        place for place in unchanged.json()["cargo_places"] if place["id"] == place_id
    )
    assert unchanged_place["lines"][0]["quantity"] == 1

    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
    )
    assert balances.status_code == 200, balances.text
    product_balance = next(
        row for row in balances.json() if row["product_id"] == product_id
    )
    assert product_balance["quantity_in_sorting"] == 1


@pytest.mark.asyncio
async def test_box_and_cargo_place_are_counted_once_across_reopen(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-006: box + cargo place stay additive without reopen duplication."""
    headers = await _register_admin(async_client, "mixed")
    request_id, place_id, product_id, sku_code, _seller_id = (
        await _create_receiving_with_cargo_place(async_client, headers, "mixed")
    )
    base = f"{BASE}/{request_id}"

    started = await async_client.post(f"{base}/begin-receiving", headers=headers)
    assert started.status_code == 200, started.text

    box = await async_client.post(f"{base}/boxes", headers=headers)
    assert box.status_code == 201, box.text
    for _ in range(2):
        box_scan = await async_client.post(
            f"{base}/boxes/{box.json()['id']}/scan",
            headers=headers,
            json={"barcode": sku_code},
        )
        assert box_scan.status_code == 200, box_scan.text
    for _ in range(3):
        cargo_scan = await async_client.post(
            f"{base}/cargo-places/{place_id}/scan",
            headers=headers,
            json={"barcode": sku_code},
        )
        assert cargo_scan.status_code == 200, cargo_scan.text

    receiving = await async_client.get(base, headers=headers)
    assert receiving.status_code == 200, receiving.text
    assert receiving.json()["lines"][0]["effective_actual_qty"] == 5

    completed = await async_client.post(f"{base}/complete-receiving", headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["lines"][0]["actual_qty"] == 5

    reopened = await async_client.post(f"{base}/reopen-receiving", headers=headers)
    assert reopened.status_code == 200, reopened.text
    receiving_again = await async_client.get(base, headers=headers)
    assert receiving_again.status_code == 200, receiving_again.text
    assert receiving_again.json()["lines"][0]["effective_actual_qty"] == 5

    completed_again = await async_client.post(
        f"{base}/complete-receiving",
        headers=headers,
    )
    assert completed_again.status_code == 200, completed_again.text
    assert completed_again.json()["lines"][0]["actual_qty"] == 5

    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
    )
    assert balances.status_code == 200, balances.text
    product_balance = next(
        row for row in balances.json() if row["product_id"] == product_id
    )
    assert product_balance["quantity_in_sorting"] == 5


@pytest.mark.asyncio
async def test_cargo_place_rejects_product_not_on_request(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-002: foreign request product is rejected by PUT and scan."""
    headers = await _register_admin(async_client, "foreign-product")
    request_id, place_id, _product_id, sku_code, seller_id = (
        await _create_receiving_with_cargo_place(
            async_client, headers, "foreign-product"
        )
    )
    foreign_product_id, foreign_sku = await _create_product(
        async_client, headers, seller_id, "not-on-request"
    )

    quantity = await async_client.put(
        f"{BASE}/{request_id}/cargo-places/{place_id}/lines/{foreign_product_id}",
        headers=headers,
        json={"quantity": 1},
    )
    assert quantity.status_code == 422, quantity.text
    assert quantity.json()["detail"] == "product_not_on_request"

    scan = await async_client.post(
        f"{BASE}/{request_id}/cargo-places/{place_id}/scan",
        headers=headers,
        json={"barcode": sku_code, "product_id": foreign_product_id},
    )
    assert scan.status_code == 422, scan.text
    assert scan.json()["detail"] == "product_not_on_request"

    barcode_scan = await async_client.post(
        f"{BASE}/{request_id}/cargo-places/{place_id}/scan",
        headers=headers,
        json={"barcode": foreign_sku},
    )
    assert barcode_scan.status_code == 404, barcode_scan.text
    assert barcode_scan.json()["detail"] == "barcode_unknown"


@pytest.mark.asyncio
async def test_cargo_place_quantity_cannot_drop_below_posted(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-003: posted cargo-place quantity is an edit floor."""
    headers = await _register_admin(async_client, "posted")
    request_id, place_id, product_id, _sku_code, _seller_id = (
        await _create_receiving_with_cargo_place(async_client, headers, "posted")
    )
    line_url = f"{BASE}/{request_id}/cargo-places/{place_id}/lines/{product_id}"
    created = await async_client.put(line_url, headers=headers, json={"quantity": 5})
    assert created.status_code == 200, created.text

    async with SessionLocal() as session:
        line = (
            await session.execute(
                select(InboundIntakeCargoPlaceLine).where(
                    InboundIntakeCargoPlaceLine.cargo_place_id == uuid.UUID(place_id),
                    InboundIntakeCargoPlaceLine.product_id == uuid.UUID(product_id),
                )
            )
        ).scalar_one()
        line.posted_qty = 4
        await session.commit()

    rejected = await async_client.put(line_url, headers=headers, json={"quantity": 3})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"] == "actual_below_posted"


@pytest.mark.asyncio
async def test_foreign_tenant_cannot_see_or_edit_cargo_place(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CARGO-004: cargo-place mutation is tenant-isolated."""
    owner_headers = await _register_admin(async_client, "owner")
    request_id, place_id, product_id, _sku_code, _seller_id = (
        await _create_receiving_with_cargo_place(async_client, owner_headers, "owner")
    )
    foreign_headers = await _register_admin(async_client, "foreign-tenant")

    response = await async_client.put(
        f"{BASE}/{request_id}/cargo-places/{place_id}/lines/{product_id}",
        headers=foreign_headers,
        json={"quantity": 1},
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "request_not_found"
