"""WMS-659: contract for atomic, retry-safe bulk inbound box creation."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.db.session import SessionLocal, engine
from app.models.inbound_intake import InboundIntakeRequest
from app.services import inbound_intake_service as intake_svc


BASE = "/operations/inbound-intake-requests"


async def _tenant(
    client: AsyncClient, label: str
) -> tuple[dict[str, str], str]:
    suffix = f"{label}-{time.time_ns()}"
    registered = await client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-659 {label}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    warehouse = await client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"Warehouse {label}", "code": suffix},
    )
    assert warehouse.status_code == 200, warehouse.text
    return headers, str(warehouse.json()["id"])


async def _request(
    client: AsyncClient,
    headers: dict[str, str],
    warehouse_id: str,
    *,
    operation_type: str = "inbound",
    status: str = "draft",
) -> str:
    created = await client.post(
        BASE,
        headers=headers,
        json={"warehouse_id": warehouse_id, "operation_type": operation_type},
    )
    assert created.status_code == 201, created.text
    request_id = str(created.json()["id"])
    if status != "draft":
        async with SessionLocal() as session:
            request = await session.get(InboundIntakeRequest, uuid.UUID(request_id))
            assert request is not None
            request.status = status
            await session.commit()
    return request_id


async def _seller_headers(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    label: str,
) -> dict[str, str]:
    seller = await client.post(
        "/sellers", headers=admin_headers, json={"name": f"Seller {label}"}
    )
    assert seller.status_code in (200, 201), seller.text
    email = f"wms659-seller-{label}-{time.time_ns()}@example.com"
    account = await client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={
            "seller_id": seller.json()["id"],
            "email": email,
            "password": "password123",
        },
    )
    assert account.status_code in (200, 201), account.text
    login = await client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _detail(
    client: AsyncClient, headers: dict[str, str], request_id: str
) -> dict[str, Any]:
    response = await client.get(f"{BASE}/{request_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _batch(
    client: AsyncClient,
    headers: dict[str, str],
    request_id: str,
    *,
    quantity: int,
    mutation_id: uuid.UUID | None = None,
) -> Response:
    body: dict[str, object] = {"quantity": quantity}
    if mutation_id is not None:
        body["mutation_id"] = str(mutation_id)
    return await client.post(f"{BASE}/{request_id}/boxes", headers=headers, json=body)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"quantity": 0}, {"quantity": -1}, {"quantity": 1.5}])
async def test_wms659_c2_rejects_invalid_quantity_without_creating_boxes(
    async_client: AsyncClient, body: dict[str, object]
) -> None:
    headers, warehouse_id = await _tenant(async_client, "invalid")
    request_id = await _request(async_client, headers, warehouse_id)

    response = await async_client.post(
        f"{BASE}/{request_id}/boxes", headers=headers, json=body
    )

    assert response.status_code == 422, response.text
    assert (await _detail(async_client, headers, request_id))["boxes"] == []


@pytest.mark.asyncio
async def test_wms659_c3_bulk_create_persists_exact_boxes_only_in_current_inbound(
    async_client: AsyncClient,
) -> None:
    headers, warehouse_id = await _tenant(async_client, "inbound")
    request_a = await _request(async_client, headers, warehouse_id)
    request_b = await _request(async_client, headers, warehouse_id)

    before_a = await _detail(async_client, headers, request_a)
    created = await _batch(
        async_client, headers, request_a, quantity=3, mutation_id=uuid.uuid4()
    )

    assert created.status_code == 201, created.text
    rows = created.json()
    assert len(rows) == 3
    assert len({row["id"] for row in rows}) == 3
    assert len({row["internal_barcode"] for row in rows}) == 3
    assert [row["box_number"] for row in rows] == [1, 2, 3]

    reloaded_a = await _detail(async_client, headers, request_a)
    reloaded_b = await _detail(async_client, headers, request_b)
    assert [row["id"] for row in reloaded_a["boxes"]] == [row["id"] for row in rows]
    assert reloaded_b["boxes"] == []
    assert reloaded_a["status"] == before_a["status"]
    assert reloaded_a["lines"] == before_a["lines"]


@pytest.mark.asyncio
async def test_wms659_c4_bulk_create_works_in_editable_return_and_stays_isolated(
    async_client: AsyncClient,
) -> None:
    headers, warehouse_id = await _tenant(async_client, "return")
    return_a = await _request(
        async_client, headers, warehouse_id, operation_type="return"
    )
    return_b = await _request(
        async_client, headers, warehouse_id, operation_type="return"
    )

    created = await _batch(
        async_client, headers, return_a, quantity=3, mutation_id=uuid.uuid4()
    )

    assert created.status_code == 201, created.text
    rows = created.json()
    assert len(rows) == 3
    assert [row["id"] for row in (await _detail(async_client, headers, return_a))["boxes"]] == [
        row["id"] for row in rows
    ]
    assert (await _detail(async_client, headers, return_b))["boxes"] == []


@pytest.mark.asyncio
async def test_wms659_c6_batch_rolls_back_wholly_after_mid_write_failure(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, warehouse_id = await _tenant(async_client, "atomic")
    request_id = await _request(async_client, headers, warehouse_id)
    original = intake_svc.record_container_mutation
    calls = 0
    fail = True

    async def fail_on_second_container(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if fail and calls == 2:
            raise RuntimeError("controlled WMS-659 failure")
        await original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(intake_svc, "record_container_mutation", fail_on_second_container)
    try:
        failed = await _batch(
            async_client, headers, request_id, quantity=3, mutation_id=uuid.uuid4()
        )
    except RuntimeError as exc:
        assert str(exc) == "controlled WMS-659 failure"
    else:
        assert failed.status_code == 500, failed.text

    assert (await _detail(async_client, headers, request_id))["boxes"] == []
    fail = False
    calls = 0
    retried = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=uuid.uuid4()
    )
    assert retried.status_code == 201, retried.text
    assert len(retried.json()) == 3


@pytest.mark.asyncio
async def test_wms659_c7_same_mutation_is_concurrent_safe(
    async_client: AsyncClient,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row and unique-index locks required")
    headers, warehouse_id = await _tenant(async_client, "retry")
    request_id = await _request(async_client, headers, warehouse_id)
    mutation_id = uuid.uuid4()

    first, duplicate = await asyncio.wait_for(
        asyncio.gather(
            _batch(async_client, headers, request_id, quantity=3, mutation_id=mutation_id),
            _batch(async_client, headers, request_id, quantity=3, mutation_id=mutation_id),
        ),
        timeout=20,
    )
    assert first.status_code == 201, first.text
    assert duplicate.status_code == 201, duplicate.text
    first_ids = [row["id"] for row in first.json()]
    assert [row["id"] for row in duplicate.json()] == first_ids
    assert len((await _detail(async_client, headers, request_id))["boxes"]) == 3

    intentional_next_batch = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=uuid.uuid4()
    )
    assert intentional_next_batch.status_code == 201, intentional_next_batch.text
    assert len((await _detail(async_client, headers, request_id))["boxes"]) == 6


@pytest.mark.asyncio
async def test_wms659_c8_same_mutation_replays_saved_batch_after_lost_response(
    async_client: AsyncClient,
) -> None:
    headers, warehouse_id = await _tenant(async_client, "lost-response")
    request_id = await _request(async_client, headers, warehouse_id)
    mutation_id = uuid.uuid4()

    saved = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=mutation_id
    )
    assert saved.status_code == 201, saved.text
    saved_ids = [row["id"] for row in saved.json()]

    replay = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=mutation_id
    )
    assert replay.status_code == 201, replay.text
    assert [row["id"] for row in replay.json()] == saved_ids
    assert len((await _detail(async_client, headers, request_id))["boxes"]) == 3

    next_batch = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=uuid.uuid4()
    )
    assert next_batch.status_code == 201, next_batch.text
    assert len((await _detail(async_client, headers, request_id))["boxes"]) == 6


@pytest.mark.asyncio
async def test_wms659_c10_c11_status_permission_and_tenant_boundaries_create_nothing(
    async_client: AsyncClient,
) -> None:
    headers_a, warehouse_a = await _tenant(async_client, "scope-a")
    inbound_done = await _request(
        async_client, headers_a, warehouse_a, status="done"
    )
    return_done = await _request(
        async_client,
        headers_a,
        warehouse_a,
        operation_type="return",
        status="done",
    )
    request_draft = await _request(async_client, headers_a, warehouse_a)
    seller_headers = await _seller_headers(async_client, headers_a, label="no-reception")
    headers_b, warehouse_b = await _tenant(async_client, "scope-b")
    request_b = await _request(async_client, headers_b, warehouse_b)

    done_responses = [
        await _batch(
            async_client, headers_a, request_id, quantity=3, mutation_id=uuid.uuid4()
        )
        for request_id in (inbound_done, return_done)
    ]
    forbidden = await _batch(
        async_client, seller_headers, request_draft, quantity=3, mutation_id=uuid.uuid4()
    )
    foreign = await _batch(
        async_client, headers_b, request_draft, quantity=3, mutation_id=uuid.uuid4()
    )

    assert [response.status_code for response in done_responses] == [409, 409]
    assert forbidden.status_code == 403, forbidden.text
    assert foreign.status_code == 404, foreign.text
    assert (await _detail(async_client, headers_a, inbound_done))["boxes"] == []
    assert (await _detail(async_client, headers_a, return_done))["boxes"] == []
    assert (await _detail(async_client, headers_a, request_draft))["boxes"] == []
    assert (await _detail(async_client, headers_b, request_b))["boxes"] == []


@pytest.mark.asyncio
async def test_wms659_c12_existing_tare_print_and_pallet_actions_remain_intact(
    async_client: AsyncClient,
) -> None:
    headers, warehouse_id = await _tenant(async_client, "neighbors")
    request_id = await _request(
        async_client, headers, warehouse_id, status="receiving"
    )

    single = await _batch(
        async_client, headers, request_id, quantity=1, mutation_id=uuid.uuid4()
    )
    assert single.status_code == 201, single.text
    box_id = single.json()[0]["id"]
    printed = await async_client.post(
        f"{BASE}/{request_id}/boxes/{box_id}/mark-label-printed", headers=headers
    )
    assert printed.status_code == 200, printed.text
    cargo = await async_client.post(
        f"{BASE}/{request_id}/cargo-places", headers=headers, json={"quantity": 2}
    )
    assert cargo.status_code == 201, cargo.text
    pallet = await async_client.post(
        f"/warehouses/{warehouse_id}/pallets/combine",
        headers=headers,
        json={
            "inbound_request_id": request_id,
            "inbound_box_ids": [box_id],
            "cargo_place_ids": [],
            "warehouse_box_ids": [],
        },
    )
    assert pallet.status_code == 200, pallet.text
    before = await _detail(async_client, headers, request_id)

    batch = await _batch(
        async_client, headers, request_id, quantity=3, mutation_id=uuid.uuid4()
    )

    assert batch.status_code == 201, batch.text
    after = await _detail(async_client, headers, request_id)
    assert after["status"] == before["status"]
    assert after["lines"] == before["lines"]
    assert [row["id"] for row in after["cargo_places"]] == [
        row["id"] for row in before["cargo_places"]
    ]
    original_box = next(row for row in after["boxes"] if row["id"] == box_id)
    before_box = next(row for row in before["boxes"] if row["id"] == box_id)
    assert original_box == before_box
    assert len(after["boxes"]) == len(before["boxes"]) + 3
