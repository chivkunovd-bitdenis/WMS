"""WMS-440: one FF fact, durable retries, source separation and atomic arrival."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.inbound_intake import InboundIntakeRequest
from app.models.inventory_movement import InventoryMovement
from app.services import inbound_intake_service as svc
from app.services import inbound_marking_service
from app.services.tokens import decode_access_token
from tests.test_staff_reception_inbound_draft import _create_staff, _register_admin

BASE = "/operations/inbound-intake-requests"


async def _setup(client: AsyncClient) -> tuple[dict[str, str], str, str, str]:
    headers, suffix = await _register_admin(client)
    warehouse = await client.post(
        "/warehouses", headers=headers, json={"name": "WMS440", "code": suffix}
    )
    seller = await client.post("/sellers", headers=headers, json={"name": "WMS440 seller"})
    product = await client.post(
        "/products",
        headers=headers,
        json={
            "name": "WMS440 product",
            "sku_code": f"WMS440-{suffix}",
            "seller_id": seller.json()["id"],
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert warehouse.status_code == 200, warehouse.text
    assert product.status_code == 200, product.text
    return headers, warehouse.json()["id"], seller.json()["id"], product.json()["id"]


@pytest.mark.asyncio
async def test_ff_single_fact_and_durable_attempts(async_client: AsyncClient) -> None:
    h, wid, sid, pid = await _setup(async_client)
    body = {"warehouse_id": wid, "seller_id": sid, "client_request_id": str(uuid.uuid4())}
    created = await async_client.post(BASE, headers=h, json=body)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert created.json()["created_by_seller_id"] is None
    first_scan = {
        "product_id": pid,
        "expected_qty": 1,
        "increment": True,
        "mutation_id": str(uuid.uuid4()),
    }
    first = await async_client.post(f"{BASE}/{rid}/lines", headers=h, json=first_scan)
    assert first.status_code == 201, first.text
    lid = first.json()["id"]
    second_scan = {**first_scan, "mutation_id": str(uuid.uuid4())}
    for _ in range(2):
        second = await async_client.post(f"{BASE}/{rid}/lines", headers=h, json=second_scan)
        assert second.status_code == 201, second.text
        assert second.json()["id"] == lid
        assert second.json()["actual_qty"] == 2
    patch = {"expected_qty": 3, "mutation_id": str(uuid.uuid4())}
    for _ in range(2):
        updated = await async_client.patch(
            f"{BASE}/{rid}/lines/{lid}/expected", headers=h, json=patch
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["actual_qty"] == 3
    # A late scan retry must not restore its earlier quantity or add another unit.
    late = await async_client.post(f"{BASE}/{rid}/lines", headers=h, json=second_scan)
    assert late.json()["actual_qty"] == 3
    repeated = await async_client.post(BASE, headers=h, json=body)
    assert repeated.json()["id"] == rid
    assert len(repeated.json()["lines"]) == 1
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    for _ in range(2):
        completed = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "sorting"
        assert completed.json()["lines"][0]["actual_qty"] == 3
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 3
    reopened = await async_client.post(f"{BASE}/{rid}/reopen-receiving", headers=h)
    assert reopened.status_code == 200, reopened.text
    corrected = await async_client.patch(
        f"{BASE}/{rid}/lines/{lid}/actual", headers=h, json={"actual_qty": 2}
    )
    assert corrected.status_code == 200, corrected.text
    completed = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert completed.json()["lines"][0]["actual_qty"] == 2
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 2


@pytest.mark.asyncio
async def test_stale_completion_attempt_cannot_complete_after_reopen(
    async_client: AsyncClient,
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 3,
            "increment": True,
            "mutation_id": str(uuid.uuid4()),
        },
    )
    assert added.status_code == 201, added.text
    original_attempt = {"mutation_id": str(uuid.uuid4())}
    first = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json=original_attempt
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "sorting"
    reopened = await async_client.post(f"{BASE}/{rid}/reopen-receiving", headers=h)
    assert reopened.status_code == 200, reopened.text
    stale_retry = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json=original_attempt
    )
    assert stale_retry.status_code == 200, stale_retry.text
    assert stale_retry.json()["status"] == "receiving"
    fresh = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json={"mutation_id": str(uuid.uuid4())}
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["status"] == "sorting"
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 3


@pytest.mark.asyncio
async def test_sorting_completion_receipt_survives_marking_schedule_failure(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 3,
            "increment": True,
            "mutation_id": str(uuid.uuid4()),
        },
    )
    assert added.status_code == 201, added.text
    first_attempt = {"mutation_id": str(uuid.uuid4())}
    assert (
        await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h, json=first_attempt)
    ).status_code == 200

    async def fail_schedule(*args: object, **kwargs: object) -> None:
        raise RuntimeError("marking unavailable")

    original_schedule = inbound_marking_service.schedule_check
    monkeypatch.setattr(inbound_marking_service, "schedule_check", fail_schedule)
    second_attempt = {"mutation_id": str(uuid.uuid4())}
    repeated = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json=second_attempt
    )
    assert repeated.status_code == 200, repeated.text
    async with SessionLocal() as db:
        receipt = await db.scalar(
            select(DocumentEvent).where(
                DocumentEvent.idempotency_key == f"inbound:complete:{second_attempt['mutation_id']}"
            )
        )
        assert receipt is not None

    monkeypatch.setattr(inbound_marking_service, "schedule_check", original_schedule)
    reopened = await async_client.post(f"{BASE}/{rid}/reopen-receiving", headers=h)
    assert reopened.json()["status"] == "receiving"
    stale = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json=second_attempt
    )
    assert stale.json()["status"] == "receiving"
    fresh = await async_client.post(
        f"{BASE}/{rid}/complete-receiving", headers=h, json={"mutation_id": str(uuid.uuid4())}
    )
    assert fresh.json()["status"] == "sorting"


@pytest.mark.asyncio
async def test_retry_payload_and_scope_validation(async_client: AsyncClient) -> None:
    h, wid, sid, pid = await _setup(async_client)
    body = {"warehouse_id": wid, "seller_id": sid, "client_request_id": str(uuid.uuid4())}
    created = await async_client.post(BASE, headers=h, json=body)
    rid = created.json()["id"]
    mismatch = await async_client.post(BASE, headers=h, json={**body, "waybill_number": "other"})
    assert mismatch.status_code == 409, mismatch.text
    missing = await async_client.post(
        BASE, headers=h, json={**body, "warehouse_id": str(uuid.uuid4())}
    )
    assert missing.status_code == 404
    add = {"product_id": pid, "expected_qty": 3, "mutation_id": str(uuid.uuid4())}
    assert (await async_client.post(f"{BASE}/{rid}/lines", headers=h, json=add)).status_code == 201
    mismatch = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={**add, "expected_qty": 4}
    )
    assert mismatch.status_code == 409, mismatch.text
    negative = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": -1}
    )
    assert negative.status_code == 422
    second_seller = await async_client.post("/sellers", headers=h, json={"name": "Other"})
    other = await async_client.post(
        BASE, headers=h, json={"warehouse_id": wid, "seller_id": second_seller.json()["id"]}
    )
    denied = await async_client.post(f"{BASE}/{other.json()['id']}/lines", headers=h, json=add)
    assert denied.status_code == 409  # Mutation identity belongs to the first document.
    denied = await async_client.post(
        f"{BASE}/{other.json()['id']}/lines", headers=h, json={"product_id": pid, "expected_qty": 1}
    )
    assert denied.status_code == 422, denied.text
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("old_actual", [None, 8])
async def test_old_receiving_never_adopts_plan(
    async_client: AsyncClient, old_actual: int | None
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    token = decode_access_token(h["Authorization"].split()[1])
    tenant = uuid.UUID(str(token["tenant_id"]))
    actor = uuid.UUID(str(token["sub"]))
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid)
        )
        line = await svc.add_line(
            db, tenant, request.id, product_id=uuid.UUID(pid), expected_qty=10
        )
        line.actual_qty = old_actual
        request.status = "receiving"
        await db.commit()
        result = await svc.complete_receiving(db, tenant, request.id, actor_user_id=actor)
        assert result.lines[0].actual_qty == (old_actual or 0)
        again = await svc.complete_receiving(db, tenant, request.id, actor_user_id=actor)
        assert again.lines[0].actual_qty == (old_actual or 0)


@pytest.mark.asyncio
async def test_seller_plan_is_not_ff_fact(async_client: AsyncClient) -> None:
    h, wid, sid, pid = await _setup(async_client)
    token = decode_access_token(h["Authorization"].split()[1])
    tenant = uuid.UUID(str(token["tenant_id"]))
    actor = uuid.UUID(str(token["sub"]))
    async with SessionLocal() as db:
        request = await svc.create_request(
            db,
            tenant,
            warehouse_id=uuid.UUID(wid),
            seller_id=uuid.UUID(sid),
            created_by_seller_id=uuid.UUID(sid),
        )
        line = await svc.add_line(
            db, tenant, request.id, product_id=uuid.UUID(pid), expected_qty=10
        )
        assert line.actual_qty is None
        with pytest.raises(svc.InboundIntakeError, match="not_verifying"):
            await svc.complete_receiving(db, tenant, request.id, actor_user_id=actor)
        request.status = "submitted"
        await db.commit()
        await svc.set_line_actual_qty(db, tenant, request.id, line.id, actual_qty=8)
        result = await svc.complete_receiving(db, tenant, request.id, actor_user_id=actor)
        assert result.lines[0].expected_qty == 10
        assert result.lines[0].actual_qty == 8


@pytest.mark.asyncio
async def test_reception_catalog_and_creation_permissions(async_client: AsyncClient) -> None:
    h, wid, sid, pid = await _setup(async_client)
    staff = await _create_staff(async_client, h, suffix=uuid.uuid4().hex, reception=True)
    denied = await _create_staff(async_client, h, suffix=uuid.uuid4().hex, reception=False)
    catalog = await async_client.get(f"/products/linked-wb-catalog?seller_id={sid}", headers=staff)
    assert catalog.status_code == 200, catalog.text
    assert [p["id"] for p in catalog.json()] == [pid]
    forbidden = await async_client.get(
        f"/products/linked-wb-catalog?seller_id={sid}", headers=denied
    )
    assert forbidden.status_code == 403
    for headers, status in [(staff, 201), (denied, 403)]:
        response = await async_client.post(
            BASE, headers=headers, json={"warehouse_id": wid, "seller_id": sid}
        )
        assert response.status_code == status, response.text


@pytest.mark.asyncio
async def test_create_failure_rolls_back_retry_receipt(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, wid, sid, _ = await _setup(async_client)
    token = decode_access_token(h["Authorization"].split()[1])
    tenant = uuid.UUID(str(token["tenant_id"]))
    attempt = uuid.uuid4()
    original = svc.assign_document_number_if_missing

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic failure before saving document")

    monkeypatch.setattr(svc, "assign_document_number_if_missing", fail)
    async with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="synthetic"):
            await svc.create_request(
                db,
                tenant,
                warehouse_id=uuid.UUID(wid),
                seller_id=uuid.UUID(sid),
                client_request_id=attempt,
            )
        await db.rollback()
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DocumentEvent)
                .where(DocumentEvent.idempotency_key == f"inbound:create:{attempt}")
            )
            == 0
        )
    monkeypatch.setattr(svc, "assign_document_number_if_missing", original)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db,
            tenant,
            warehouse_id=uuid.UUID(wid),
            seller_id=uuid.UUID(sid),
            client_request_id=attempt,
        )
        repeated = await svc.create_request(
            db,
            tenant,
            warehouse_id=uuid.UUID(wid),
            seller_id=uuid.UUID(sid),
            client_request_id=attempt,
        )
        assert request.id == repeated.id


@pytest.mark.asyncio
@pytest.mark.parametrize("container_kind", ["boxes", "cargo-places"])
async def test_ff_container_allocation_and_explicit_correction(
    async_client: AsyncClient, container_kind: str
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 3}
    )
    lid = added.json()["id"]
    container = await async_client.post(
        f"{BASE}/{rid}/{container_kind}",
        headers=h,
        **({"json": {"quantity": 1}} if container_kind == "cargo-places" else {}),
    )
    assert container.status_code == 201, container.text
    cid = (container.json()[0] if container_kind == "cargo-places" else container.json())["id"]
    path = f"{BASE}/{rid}/{container_kind}/{cid}"
    scans = []
    for index in range(4):
        scan = {"barcode": "synthetic-scan", "product_id": pid, "mutation_id": str(uuid.uuid4())}
        scans.append(scan)
        for _ in range(2):
            result = await async_client.post(f"{path}/scan", headers=h, json=scan)
            assert result.status_code == 200, result.text
        read = await async_client.get(f"{BASE}/{rid}", headers=h)
        line = read.json()["lines"][0]
        assert read.json()["status"] == "draft"
        assert line["effective_actual_qty"] == max(3, index + 1)
        assert line["actual_qty"] == max(0, 3 - (index + 1))
    patch = {"expected_qty": 2, "mutation_id": str(uuid.uuid4())}
    incompatible = await async_client.patch(
        f"{BASE}/{rid}/lines/{lid}/expected", headers=h, json=patch
    )
    assert incompatible.status_code == 409, incompatible.text
    assert incompatible.json()["detail"] == "actual_below_container_total"
    quantity = {"quantity": 2, "mutation_id": str(uuid.uuid4())}
    for _ in range(2):
        corrected = await async_client.put(f"{path}/lines/{pid}", headers=h, json=quantity)
        assert corrected.status_code == 200, corrected.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    assert read.json()["lines"][0]["effective_actual_qty"] == 4
    assert read.json()["lines"][0]["actual_qty"] == 2
    applied = await async_client.patch(f"{BASE}/{rid}/lines/{lid}/expected", headers=h, json=patch)
    assert applied.status_code == 200, applied.text
    assert applied.json()["effective_actual_qty"] == 2
    # Lost scan response arriving after a correction must not re-add old physical units.
    late = await async_client.post(f"{path}/scan", headers=h, json=scans[-1])
    assert late.status_code == 200, late.text
    result = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert result.status_code == 200, result.text
    assert result.json()["lines"][0]["actual_qty"] == 2
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", [None, "wildberries", "ozon"])
async def test_return_creation_keeps_existing_marketplace_path(
    async_client: AsyncClient, marketplace: str | None
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    request = await async_client.post(
        BASE,
        headers=h,
        json={
            "warehouse_id": wid,
            "seller_id": sid,
            "operation_type": "return",
            "marketplace": marketplace,
        },
    )
    rid = request.json()["id"]
    line = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 3}
    )
    assert line.status_code == 201, line.text
    assert line.json()["actual_qty"] == (None if marketplace == "ozon" else 3)
    begun = await async_client.post(f"{BASE}/{rid}/begin-receiving", headers=h)
    assert begun.status_code == 200, begun.text
    assert begun.json()["status"] == ("receiving" if marketplace == "ozon" else "sorting")


@pytest.mark.asyncio
async def test_old_ff_draft_displays_entered_fact_and_delete_removes_composition(
    async_client: AsyncClient,
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 3}
    )
    lid = added.json()["id"]
    from app.models.inbound_intake import InboundIntakeLine

    async with SessionLocal() as db:
        line = await db.get(InboundIntakeLine, uuid.UUID(lid))
        assert line is not None
        line.actual_qty = None  # A draft authored before this release.
        await db.commit()
    old_draft = await async_client.get(f"{BASE}/{rid}", headers=h)
    assert old_draft.json()["lines"][0]["effective_actual_qty"] == 3
    box = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    bid = box.json()["id"]
    put = await async_client.put(
        f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
        headers=h,
        json={"quantity": 2, "mutation_id": str(uuid.uuid4())},
    )
    assert put.status_code == 200, put.text
    removed = await async_client.delete(f"{BASE}/{rid}/lines/{lid}", headers=h)
    assert removed.status_code == 204, removed.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    assert read.json()["lines"] == []
    assert read.json()["boxes"][0]["lines"] == []


@pytest.mark.asyncio
async def test_new_ff_three_units_reach_cell_with_one_charge_and_fact(
    async_client: AsyncClient,
) -> None:
    from datetime import date

    from app.models.billing import BillingLedgerEntry, BillingTariffVersion
    from app.models.operation_fact import OperationFact
    from app.models.tenant import Tenant
    from app.services import inbound_sorting_service as sorting
    from app.services.catalog_service import create_location
    from tests.test_wms441_sorting import stock

    h, wid, sid, pid = await _setup(async_client)
    token = decode_access_token(h["Authorization"].split()[1])
    tenant, actor = uuid.UUID(str(token["tenant_id"])), uuid.UUID(str(token["sub"]))
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = uuid.UUID(created.json()["id"])
    await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 3}
    )
    async with SessionLocal() as db:
        location = await create_location(db, tenant, uuid.UUID(wid), code="WMS440-A")
        location_id = location.id
        org = await db.get(Tenant, tenant)
        assert org is not None
        org.billing_enabled_from = date(2020, 1, 1)
        db.add(
            BillingTariffVersion(
                tenant_id=tenant,
                service_code="inbound",
                unit="item",
                amount=100,
                valid_from=date(2020, 1, 1),
            )
        )
        await db.commit()
    result = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert result.status_code == 200, result.text
    operation = uuid.uuid4()
    for _ in range(2):
        async with SessionLocal() as db:
            result_doc = await sorting.apply_loose_putaway(
                db,
                tenant,
                rid,
                operation_id=operation,
                product_id=uuid.UUID(pid),
                storage_location_id=location_id,
                quantity=3,
                performer_id=actor,
            )
            assert result_doc.status == "done"
            assert result_doc.lines[0].posted_qty == 3
    repeated = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["status"] == "done"
    assert await stock(uuid.UUID(pid), location_id) == 3
    async with SessionLocal() as db:
        charges = list(
            await db.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.source_type == "inbound_intake",
                    BillingLedgerEntry.source_id == rid,
                )
            )
        )
        facts = list(
            await db.scalars(select(OperationFact).where(OperationFact.document_id == rid))
        )
        assert len(charges) == len(facts) == 1
        assert charges[0].quantity == 3
        assert charges[0].performer_id == facts[0].actor_user_id == actor
        assert facts[0].item_quantity == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["begin-receiving", "submit"])
@pytest.mark.parametrize("container_kind", ["boxes", "cargo-places"])
async def test_explicit_legacy_recount_keeps_tare_without_duplicating_draft_fact(
    async_client: AsyncClient, transition: str, container_kind: str
) -> None:
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    path = f"{BASE}/{rid}"
    added = await async_client.post(
        f"{path}/lines", headers=h, json={"product_id": pid, "expected_qty": 4}
    )
    lid = added.json()["id"]
    container = await async_client.post(
        f"{path}/{container_kind}", headers=h,
        **({"json": {"quantity": 1}} if container_kind == "cargo-places" else {}),
    )
    assert container.status_code == 201, container.text
    cid = (container.json()[0] if container_kind == "cargo-places" else container.json())["id"]
    quantity_path = f"{path}/{container_kind}/{cid}/lines/{pid}"
    filled = await async_client.put(quantity_path, headers=h, json={"quantity": 2})
    assert filled.status_code == 200, filled.text
    draft = (await async_client.get(path, headers=h)).json()
    assert draft["lines"][0]["actual_qty"] == 2
    assert draft["lines"][0]["effective_actual_qty"] == 4
    if transition == "submit":
        planned = await async_client.patch(path, headers=h, json={"planned_box_count": 1})
        assert planned.status_code == 200, planned.text
    started = await async_client.post(f"{path}/{transition}", headers=h)
    assert started.status_code == 200, started.text
    if transition == "submit":
        started = await async_client.post(f"{path}/begin-receiving", headers=h)
        assert started.status_code == 200, started.text
    after = (await async_client.get(path, headers=h)).json()
    assert after["status"] == "receiving"
    assert after["lines"][0]["id"] == lid
    assert after["lines"][0]["actual_qty"] is None
    assert after["lines"][0]["expected_qty"] == 4
    assert after["lines"][0]["effective_actual_qty"] == 2
    containers = after["boxes" if container_kind == "boxes" else "cargo_places"]
    assert containers[0]["id"] == cid
    assert containers[0]["lines"][0]["quantity"] == 2
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    recounted = await async_client.put(quantity_path, headers=h, json={"quantity": 4})
    assert recounted.status_code == 200, recounted.text
    for _ in range(2):
        completed = await async_client.post(f"{path}/complete-receiving", headers=h)
        assert completed.status_code == 200, completed.text
        assert completed.json()["lines"][0]["actual_qty"] == 4
    async with SessionLocal() as db:
        assert await db.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 4
