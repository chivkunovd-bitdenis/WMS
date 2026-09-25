"""WMS-534: lowering a box/cargo-place quantity drops units from the FF document
instead of turning them into loose stock (partial revert of WMS-440 D5).

Each test below is named after the check it proves in
docs/requirements/WMS-534.md (C1..C12). C6 (ТСД) and C13 (no interface/DB diff)
are not automatable pytest checks: C6 is covered by exercising the same HTTP
endpoints the mobile client calls (confirmed by reading
mobile/android/.../InboundReceivingViewModel.kt — box quantity PUT and box scan
POST only, no cargo-place calls in that checkout), and C13 is a `git diff`
inspection performed separately. C14 (regression) is the existing suite run
alongside this file.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.inventory_movement import InventoryMovement
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as svc
from app.services.box_import_service import (
    BoxImportBoxPreview,
    BoxImportLinePreview,
    BoxImportPreviewResult,
    BoxImportPreviewSummary,
    apply_inbound_box_import,
)
from app.services.tokens import decode_access_token
from tests.test_wms440_ff_intake import BASE, _setup


async def _open_container(
    async_client: AsyncClient, headers: dict[str, str], rid: str, kind: str
) -> str:
    if kind == "boxes":
        resp = await async_client.post(f"{BASE}/{rid}/boxes", headers=headers)
        assert resp.status_code == 201, resp.text
        return str(resp.json()["id"])
    resp = await async_client.post(
        f"{BASE}/{rid}/cargo-places", headers=headers, json={"quantity": 1}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


def _tenant_id(headers: dict[str, str]) -> uuid.UUID:
    return uuid.UUID(str(decode_access_token(headers["Authorization"].split()[1])["tenant_id"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("container_kind", ["boxes", "cargo-places"])
async def test_c1_c4_two_scans_then_correct_to_one_reaches_stock(
    async_client: AsyncClient, container_kind: str
) -> None:
    """C1 (boxes) / C4 (cargo places): the owner's exact case.

    A brand-new product with no loose gets scanned into a container twice, then
    corrected to 1. The accepted total must drop to 1 (not stay at 2), reload
    must show the same numbers, and completion must post exactly 1 unit.
    """
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    cid = await _open_container(async_client, h, rid, container_kind)
    path = f"{BASE}/{rid}/{container_kind}/{cid}"

    for _ in range(2):
        scan = await async_client.post(
            f"{path}/scan",
            headers=h,
            json={"barcode": "wms534-c1", "product_id": pid, "mutation_id": str(uuid.uuid4())},
        )
        assert scan.status_code == 200, scan.text

    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = next(ln for ln in read.json()["lines"] if ln["product_id"] == pid)
    assert line["effective_actual_qty"] == 2
    assert line["actual_qty"] == 0

    corrected = await async_client.put(
        f"{path}/lines/{pid}", headers=h, json={"quantity": 1, "mutation_id": str(uuid.uuid4())}
    )
    assert corrected.status_code == 200, corrected.text

    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line2 = next(ln for ln in read2.json()["lines"] if ln["product_id"] == pid)
    assert line2["effective_actual_qty"] == 1
    assert line2["actual_qty"] == 0

    # Reload (web tab refresh / TSD reopen) must show the same numbers.
    reread = await async_client.get(f"{BASE}/{rid}", headers=h)
    line3 = next(ln for ln in reread.json()["lines"] if ln["product_id"] == pid)
    assert line3["effective_actual_qty"] == 1
    assert line3["actual_qty"] == 0

    done = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "sorting"
    done_line = next(ln for ln in done.json()["lines"] if ln["product_id"] == pid)
    assert done_line["actual_qty"] == 1

    async with SessionLocal() as db:
        total = await db.scalar(
            select(func.sum(InventoryMovement.quantity_delta)).where(
                InventoryMovement.inbound_intake_line_id == uuid.UUID(done_line["id"])
            )
        )
        assert total == 1


@pytest.mark.asyncio
async def test_c2_loose_then_scan_into_box_draws_down_first(async_client: AsyncClient) -> None:
    """C2/R2: scanning into a box still draws from existing loose stock first."""
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 3}
    )
    assert added.status_code == 201, added.text
    box = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    bid = box.json()["id"]

    for _ in range(2):
        scan = await async_client.post(
            f"{BASE}/{rid}/boxes/{bid}/scan",
            headers=h,
            json={"barcode": "wms534-c2", "product_id": pid, "mutation_id": str(uuid.uuid4())},
        )
        assert scan.status_code == 200, scan.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 3
    assert line["actual_qty"] == 1

    for _ in range(2):
        scan = await async_client.post(
            f"{BASE}/{rid}/boxes/{bid}/scan",
            headers=h,
            json={"barcode": "wms534-c2", "product_id": pid, "mutation_id": str(uuid.uuid4())},
        )
        assert scan.status_code == 200, scan.text
    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line2 = read2.json()["lines"][0]
    assert line2["effective_actual_qty"] == 4
    assert line2["actual_qty"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("container_kind", ["boxes", "cargo-places"])
async def test_c3_c4_reduce_to_zero_keeps_loose_and_drops_the_row(
    async_client: AsyncClient, container_kind: str
) -> None:
    """C3 (boxes) / C4 (cargo places): setting a container's quantity to 0.

    Start with 1 loose + 3 in the container (total 4). Zeroing the container must
    leave loose at 1 (untouched) and drop the total to 1, with the container's own
    line for the product gone (row deleted, matching the pre-existing zero-qty
    delete behaviour).
    """
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 4}
    )
    assert added.status_code == 201, added.text
    cid = await _open_container(async_client, h, rid, container_kind)
    path = f"{BASE}/{rid}/{container_kind}/{cid}"

    filled = await async_client.put(
        f"{path}/lines/{pid}", headers=h, json={"quantity": 3, "mutation_id": str(uuid.uuid4())}
    )
    assert filled.status_code == 200, filled.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 4
    assert line["actual_qty"] == 1

    zeroed = await async_client.put(
        f"{path}/lines/{pid}", headers=h, json={"quantity": 0, "mutation_id": str(uuid.uuid4())}
    )
    assert zeroed.status_code == 200, zeroed.text

    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line2 = read2.json()["lines"][0]
    assert line2["effective_actual_qty"] == 1
    assert line2["actual_qty"] == 1
    containers_key = "boxes" if container_kind == "boxes" else "cargo_places"
    container = next(c for c in read2.json()[containers_key] if c["id"] == cid)
    assert container["lines"] == []


@pytest.mark.asyncio
async def test_c5_edit_after_reopen_receiving(async_client: AsyncClient) -> None:
    """C5/R1/R3/R4: correcting a box down after «Редактировать» (reopen-receiving).

    Complete with 2 in a box, reopen, correct the box to 1, complete again — the
    final stock in sorting must be exactly 1, with the original 2-unit posting
    reversed rather than left in place.
    """
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    box = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    bid = box.json()["id"]
    for _ in range(2):
        scan = await async_client.post(
            f"{BASE}/{rid}/boxes/{bid}/scan",
            headers=h,
            json={"barcode": "wms534-c5", "product_id": pid, "mutation_id": str(uuid.uuid4())},
        )
        assert scan.status_code == 200, scan.text

    done = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "sorting"
    assert done.json()["lines"][0]["actual_qty"] == 2

    bal1 = await async_client.get("/operations/inventory-balances/summary", headers=h)
    row1 = next(r for r in bal1.json() if r["product_id"] == pid)
    assert row1["quantity_in_sorting"] == 2

    reopened = await async_client.post(f"{BASE}/{rid}/reopen-receiving", headers=h)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "receiving"

    bal2 = await async_client.get("/operations/inventory-balances/summary", headers=h)
    row2 = next(r for r in bal2.json() if r["product_id"] == pid)
    assert row2["quantity_in_sorting"] == 0

    corrected = await async_client.put(
        f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
        headers=h,
        json={"quantity": 1, "mutation_id": str(uuid.uuid4())},
    )
    assert corrected.status_code == 200, corrected.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 1
    assert line["actual_qty"] == 0

    done2 = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert done2.status_code == 200, done2.text
    assert done2.json()["lines"][0]["actual_qty"] == 1
    box_lines = [ln for b in done2.json()["boxes"] for ln in b["lines"]]
    assert sum(int(ln["quantity"]) for ln in box_lines) == 1

    bal3 = await async_client.get("/operations/inventory-balances/summary", headers=h)
    row3 = next(r for r in bal3.json() if r["product_id"] == pid)
    assert row3["quantity_in_sorting"] == 1


@pytest.mark.asyncio
async def test_c7_excel_box_import_shares_the_same_rule(async_client: AsyncClient) -> None:
    """C7/R3: applying an imported box uses the same set_product_quantity path.

    Loose 2, import a new box with 3 of the same product -> total 3 (loose fully
    drawn down, +1 beyond it). Then reducing that box to 1 must drop the total
    to 1 exactly like a manual PUT would (same shared function, same rule).
    """
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 2}
    )
    assert added.status_code == 201, added.text

    tenant_id = _tenant_id(h)
    preview = BoxImportPreviewResult(
        boxes=(
            BoxImportBoxPreview(
                address="A1",
                lines=(
                    BoxImportLinePreview(
                        barcode="wms534-c7",
                        product_id=uuid.UUID(pid),
                        sku_code=None,
                        product_name=None,
                        quantity=3,
                    ),
                ),
                total_qty=3,
            ),
        ),
        errors=(),
        summary=BoxImportPreviewSummary(boxes_count=1, positions=1, total_units=3, error_count=0),
    )
    async with SessionLocal() as db:
        boxes, errors = await apply_inbound_box_import(db, tenant_id, uuid.UUID(rid), preview)
        assert list(errors) == []
        assert len(boxes) == 1
        box_id = boxes[0].id

    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 3
    assert line["actual_qty"] == 0

    decreased = await async_client.put(
        f"{BASE}/{rid}/boxes/{box_id}/lines/{pid}",
        headers=h,
        json={"quantity": 1, "mutation_id": str(uuid.uuid4())},
    )
    assert decreased.status_code == 200, decreased.text
    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line2 = read2.json()["lines"][0]
    assert line2["effective_actual_qty"] == 1
    assert line2["actual_qty"] == 0


@pytest.mark.asyncio
async def test_c8_duplicate_request_does_not_double_deduct(async_client: AsyncClient) -> None:
    """C8/R6: the same PUT sent twice (or replayed after a lost response) must
    lower the accepted total exactly once, never twice."""
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    box = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    bid = box.json()["id"]
    for _ in range(2):
        scan = await async_client.post(
            f"{BASE}/{rid}/boxes/{bid}/scan",
            headers=h,
            json={"barcode": "wms534-c8", "product_id": pid, "mutation_id": str(uuid.uuid4())},
        )
        assert scan.status_code == 200, scan.text

    same_key = str(uuid.uuid4())
    for _ in range(2):
        put = await async_client.put(
            f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
            headers=h,
            json={"quantity": 1, "mutation_id": same_key},
        )
        assert put.status_code == 200, put.text

    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 1
    assert line["actual_qty"] == 0

    # A third arrival of the same key, well after the first two (simulated lost
    # response / late retry), must still be a pure no-op.
    put_again = await async_client.put(
        f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
        headers=h,
        json={"quantity": 1, "mutation_id": same_key},
    )
    assert put_again.status_code == 200, put_again.text
    reread = await async_client.get(f"{BASE}/{rid}", headers=h)
    reread_line = reread.json()["lines"][0]
    assert reread_line["effective_actual_qty"] == 1
    assert reread_line["actual_qty"] == 0


@pytest.mark.asyncio
async def test_c9_concurrent_box_quantity_corrections_apply_exactly_one(
    async_client: AsyncClient,
) -> None:
    """C9/R6: two concurrent absolute corrections on the same box line settle on
    exactly one of the two targets — no lost update, no double subtraction, and
    loose (which starts at 0) never goes negative or picks up the removed units.
    """
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    h, wid, sid, pid = await _setup(async_client)
    tenant = _tenant_id(h)
    product = uuid.UUID(pid)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid)
        )
        rid = request.id
        await svc.add_line(db, tenant, rid, product_id=product, expected_qty=3)
        box = await box_svc.create_open_box(db, tenant, rid)
        box_id = box.id
    async with SessionLocal() as db:
        # Draw all 3 loose units into the box, leaving loose at 0 before the race.
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=3
        )

    async def put_qty(quantity: int) -> None:
        async with SessionLocal() as db:
            await box_svc.set_product_quantity_in_open_box(
                db, tenant, rid, box_id, product_id=product,
                quantity=quantity, mutation_id=uuid.uuid4(),
            )

    await asyncio.wait_for(asyncio.gather(put_qty(1), put_qty(2)), 20)

    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        assert line.actual_qty == 0
        effective = await svc.effective_actual_qty(db, rid, line)
        box_total = sum(ln.quantity for box in request.boxes for ln in box.lines)
        assert box_total in (1, 2)
        assert effective == box_total


@pytest.mark.asyncio
async def test_c9_concurrent_scan_and_correction_settle_on_one_order(
    async_client: AsyncClient,
) -> None:
    """C9/R6: a +1 scan racing an absolute correction on the same box line."""
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    h, wid, sid, pid = await _setup(async_client)
    tenant = _tenant_id(h)
    product = uuid.UUID(pid)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid)
        )
        rid = request.id
        await svc.add_line(db, tenant, rid, product_id=product, expected_qty=2)
        box = await box_svc.create_open_box(db, tenant, rid)
        box_id = box.id
    async with SessionLocal() as db:
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=2
        )

    async def scan_one() -> None:
        async with SessionLocal() as db:
            await box_svc.scan_product_into_box(
                db, tenant, rid, box_id, barcode="synthetic", product_id_hint=product,
                mutation_id=uuid.uuid4(),
            )

    async def put_one() -> None:
        async with SessionLocal() as db:
            await box_svc.set_product_quantity_in_open_box(
                db, tenant, rid, box_id, product_id=product, quantity=1, mutation_id=uuid.uuid4(),
            )

    await asyncio.wait_for(asyncio.gather(scan_one(), put_one()), 20)

    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        assert line.actual_qty == 0
        effective = await svc.effective_actual_qty(db, rid, line)
        box_total = sum(ln.quantity for box in request.boxes for ln in box.lines)
        assert box_total in (1, 2)
        assert effective == box_total


@pytest.mark.asyncio
async def test_c10_seller_created_receiving_unaffected(async_client: AsyncClient) -> None:
    """C10/R5: a seller-created receiving keeps its pre-existing rule — lowering a
    box just lowers the total by the same amount; redistribute never runs for it."""
    h, wid, sid, pid = await _setup(async_client)
    tenant = _tenant_id(h)
    product = uuid.UUID(pid)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid),
            created_by_seller_id=uuid.UUID(sid),
        )
        rid = request.id
        assert not svc.is_ff_inbound(request)
        await svc.add_line(db, tenant, rid, product_id=product, expected_qty=5)
        # A seller-created draft cannot open boxes yet (_intake_editable requires
        # submitted/receiving for a non-FF document) — submit it first, same as
        # the seller would from their own dashboard.
        await svc.patch_request_draft(
            db, tenant, rid, planned_box_count=1, planned_box_count_set=True
        )
        await svc.submit_request(db, tenant, rid)
        box = await box_svc.create_open_box(db, tenant, rid)
        box_id = box.id

    async with SessionLocal() as db:
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=2
        )
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        # Untouched by redistribute (which never runs for a seller-created plan);
        # the box's own 2 units are the whole story via effective_actual_qty.
        assert line.actual_qty is None
        assert await svc.effective_actual_qty(db, rid, line) == 2

    async with SessionLocal() as db:
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=1
        )
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        assert line.actual_qty is None
        assert await svc.effective_actual_qty(db, rid, line) == 1


@pytest.mark.asyncio
async def test_c10_return_receiving_unaffected(async_client: AsyncClient) -> None:
    """C10/R5: a return document keeps its pre-existing rule — is_ff_inbound is
    False for every return regardless of author, so redistribute never runs."""
    h, wid, sid, pid = await _setup(async_client)
    tenant = _tenant_id(h)
    product = uuid.UUID(pid)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid),
            operation_type=svc.OPERATION_TYPE_RETURN,
        )
        rid = request.id
        assert not svc.is_ff_inbound(request)
        await svc.add_line(db, tenant, rid, product_id=product, expected_qty=5)
        await svc.patch_request_draft(
            db, tenant, rid, planned_box_count=1, planned_box_count_set=True
        )
        await svc.submit_request(db, tenant, rid)
        box = await box_svc.create_open_box(db, tenant, rid)
        box_id = box.id

    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        assert request.lines[0].actual_qty == 5

    async with SessionLocal() as db:
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=2
        )
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        assert line.actual_qty == 5  # loose is untouched — no redistribute call at all
        assert await svc.effective_actual_qty(db, rid, line) == 7  # 5 loose + 2 boxed

    async with SessionLocal() as db:
        await box_svc.set_product_quantity_in_open_box(
            db, tenant, rid, box_id, product_id=product, quantity=0
        )
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        line = request.lines[0]
        assert line.actual_qty == 5
        assert await svc.effective_actual_qty(db, rid, line) == 5


@pytest.mark.asyncio
async def test_c11_move_between_boxes_with_loose_present(async_client: AsyncClient) -> None:
    """C11/R8: emptying box1 (R1, unit leaves the document) then scanning the same
    physical unit into box2 draws the pre-existing loose unit (R2). The accepted
    total ends up 1 less than it started — an accepted consequence, not a bug."""
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 2}
    )
    assert added.status_code == 201, added.text

    box1 = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    box2 = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    box1_id, box2_id = box1.json()["id"], box2.json()["id"]

    filled = await async_client.put(
        f"{BASE}/{rid}/boxes/{box1_id}/lines/{pid}",
        headers=h,
        json={"quantity": 1, "mutation_id": str(uuid.uuid4())},
    )
    assert filled.status_code == 200, filled.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    line = read.json()["lines"][0]
    assert line["effective_actual_qty"] == 2
    assert line["actual_qty"] == 1

    emptied = await async_client.put(
        f"{BASE}/{rid}/boxes/{box1_id}/lines/{pid}",
        headers=h,
        json={"quantity": 0, "mutation_id": str(uuid.uuid4())},
    )
    assert emptied.status_code == 200, emptied.text
    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line2 = read2.json()["lines"][0]
    assert line2["effective_actual_qty"] == 1
    assert line2["actual_qty"] == 1

    scanned = await async_client.post(
        f"{BASE}/{rid}/boxes/{box2_id}/scan",
        headers=h,
        json={"barcode": "wms534-c11", "product_id": pid, "mutation_id": str(uuid.uuid4())},
    )
    assert scanned.status_code == 200, scanned.text
    read3 = await async_client.get(f"{BASE}/{rid}", headers=h)
    line3 = read3.json()["lines"][0]
    assert line3["effective_actual_qty"] == 1
    assert line3["actual_qty"] == 0
    box2_lines = next(b for b in read3.json()["boxes"] if b["id"] == box2_id)["lines"]
    assert box2_lines[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_c12_wms440_r12_scenario_still_works(async_client: AsyncClient) -> None:
    """C12/R7: WMS-440 D6/R12 example still holds after this change.

    Total 4, all 4 in one box. The operator corrects the box down to 2 (now an
    immediate R1 drop to 2), then separately submits the overall total 2 via the
    plan «expected» field. The result must stay 2 — not drop again to 0.
    """
    h, wid, sid, pid = await _setup(async_client)
    created = await async_client.post(BASE, headers=h, json={"warehouse_id": wid, "seller_id": sid})
    rid = created.json()["id"]
    added = await async_client.post(
        f"{BASE}/{rid}/lines", headers=h, json={"product_id": pid, "expected_qty": 4}
    )
    lid = added.json()["id"]
    box = await async_client.post(f"{BASE}/{rid}/boxes", headers=h)
    bid = box.json()["id"]
    filled = await async_client.put(
        f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
        headers=h,
        json={"quantity": 4, "mutation_id": str(uuid.uuid4())},
    )
    assert filled.status_code == 200, filled.text
    read = await async_client.get(f"{BASE}/{rid}", headers=h)
    assert read.json()["lines"][0]["effective_actual_qty"] == 4
    assert read.json()["lines"][0]["actual_qty"] == 0

    corrected = await async_client.put(
        f"{BASE}/{rid}/boxes/{bid}/lines/{pid}",
        headers=h,
        json={"quantity": 2, "mutation_id": str(uuid.uuid4())},
    )
    assert corrected.status_code == 200, corrected.text
    read2 = await async_client.get(f"{BASE}/{rid}", headers=h)
    assert read2.json()["lines"][0]["effective_actual_qty"] == 2
    assert read2.json()["lines"][0]["actual_qty"] == 0

    applied = await async_client.patch(
        f"{BASE}/{rid}/lines/{lid}/expected",
        headers=h,
        json={"expected_qty": 2, "mutation_id": str(uuid.uuid4())},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["effective_actual_qty"] == 2

    done = await async_client.post(f"{BASE}/{rid}/complete-receiving", headers=h)
    assert done.status_code == 200, done.text
    assert done.json()["lines"][0]["actual_qty"] == 2
