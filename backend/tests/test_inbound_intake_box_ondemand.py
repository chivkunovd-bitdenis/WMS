"""IN-BE-02: on-demand inbound intake boxes (service-level)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import set_planned_boxes

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBoxLine, InboundIntakeLine
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services import inbound_cargo_place_service as cargo_svc
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as intake_svc
from app.services.product_code_resolver_service import build_product_code_index
from app.services.tokens import decode_access_token


async def _register_admin(
    async_client: AsyncClient, suffix: str
) -> tuple[dict[str, str], uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"OnDemand FF {suffix}",
            "slug": f"ondemand-{suffix}",
            "admin_email": f"ondemand-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    ah = {"Authorization": f"Bearer {token}"}
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    return ah, tenant_id


def _actor_user_id(headers: dict[str, str]) -> uuid.UUID:
    token = headers["Authorization"].removeprefix("Bearer ")
    return uuid.UUID(str(decode_access_token(token)["sub"]))


async def _submitted_request(
    async_client: AsyncClient,
    ah: dict[str, str],
    suffix: str,
    *,
    expected_qty: int = 5,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    seller = await async_client.post(
        "/sellers",
        headers=ah,
        json={"name": f"Seller {suffix}"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"sku-{suffix}",
            "seller_id": seller_id,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = uuid.UUID(pr.json()["id"])
    sku = pr.json()["sku_code"]

    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": seller_id},
    )
    assert cr.status_code == 201, cr.text
    rid = uuid.UUID(cr.json()["id"])

    ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=ah,
        json={"product_id": str(pid), "expected_qty": expected_qty},
    )
    assert ln.status_code == 201, ln.text

    await set_planned_boxes(
        async_client, "/operations/inbound-intake-requests", str(rid), ah
    )
    sub = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=ah,
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == intake_svc.STATUS_SUBMITTED

    return rid, pid, sku


@pytest.mark.asyncio
async def test_create_three_boxes_on_demand_are_distinct(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    async with SessionLocal() as session:
        boxes = [await box_svc.create_open_box(session, tenant_id, rid) for _ in range(3)]
        assert [b.box_number for b in boxes] == [1, 2, 3]
        assert len({b.id for b in boxes}) == 3
        assert all(b.intake_opened_at is not None for b in boxes)
        assert all(b.intake_closed_at is None for b in boxes)

        reloaded = await box_svc.list_boxes(session, tenant_id, rid)
        assert [b.box_number for b in reloaded] == [1, 2, 3]


@pytest.mark.asyncio
async def test_box_two_scans_only_box_two(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 1)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=4)

    async with SessionLocal() as session:
        boxes = [await box_svc.create_open_box(session, tenant_id, rid) for _ in range(3)]
        box2 = boxes[1]
        for _ in range(2):
            line = await box_svc.scan_product_into_box(
                session,
                tenant_id,
                rid,
                box2.id,
                barcode=sku,
            )
        assert line.quantity == 2

        async with SessionLocal() as verify_session:
            loaded = await box_svc.list_boxes_with_lines(verify_session, tenant_id, rid)
        by_number = {b.box_number: b for b in loaded}
        assert by_number[1].lines == []
        assert by_number[3].lines == []
        assert len(by_number[2].lines) == 1
        assert by_number[2].lines[0].quantity == 2


@pytest.mark.asyncio
async def test_box_scan_resolves_ozon_external_barcode(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 14)
    _headers, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, _sku = await _submitted_request(async_client, _headers, suffix, expected_qty=2)
    barcode = f"OZN-BOX-{suffix}"
    async with SessionLocal() as session:
        request = await intake_svc.get_request(session, tenant_id, rid)
        assert request is not None and request.seller_id is not None
        session.add(
            ProductMarketplaceLink(
                tenant_id=tenant_id,
                seller_id=request.seller_id,
                product_id=pid,
                marketplace="ozon",
                external_barcodes=[barcode],
            )
        )
        await session.commit()
        box = await box_svc.create_open_box(session, tenant_id, rid)
        scanned = await box_svc.scan_product_into_box(
            session, tenant_id, rid, box.id, barcode=barcode
        )
    assert scanned.product_id == pid
    assert scanned.quantity == 1


@pytest.mark.asyncio
async def test_loose_box_and_cargo_scans_share_additional_wb_aliases(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 141)
    headers, tenant_id = await _register_admin(async_client, suffix)
    request_id, product_id, sku = await _submitted_request(
        async_client, headers, suffix, expected_qty=6
    )
    additional_barcode = f"WB-ALT-{suffix}"

    async with SessionLocal() as session:
        request = await intake_svc.get_request(session, tenant_id, request_id)
        assert request is not None and request.seller_id is not None
        session.add(
            ProductBarcode(
                tenant_id=tenant_id,
                seller_id=request.seller_id,
                product_id=product_id,
                barcode=additional_barcode,
                source="wb",
            )
        )
        await session.commit()
        box = await box_svc.create_open_box(session, tenant_id, request_id)
        cargo_place = (
            await intake_svc.create_cargo_places(
                session, tenant_id, request_id, quantity=1
            )
        )[0]

        loose = await intake_svc.scan_barcode_to_loose_intake(
            session,
            tenant_id,
            request_id,
            barcode=sku.swapcase(),
        )
        boxed = await box_svc.scan_product_into_box(
            session,
            tenant_id,
            request_id,
            box.id,
            barcode=additional_barcode.lower(),
        )
        cargo = await cargo_svc.scan_product(
            session,
            tenant_id,
            request_id,
            cargo_place.id,
            barcode=additional_barcode,
        )

    assert loose.product_id == product_id
    assert boxed.product_id == product_id
    assert cargo.lines[0].product_id == product_id


@pytest.mark.asyncio
async def test_ambiguous_external_barcode_does_not_change_box_or_cargo_place(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 15)
    headers, tenant_id = await _register_admin(async_client, suffix)
    rid, first_product_id, _sku = await _submitted_request(
        async_client, headers, suffix, expected_qty=2
    )
    async with SessionLocal() as session:
        request = await intake_svc.get_request(session, tenant_id, rid)
        assert request is not None and request.seller_id is not None
        seller_id = request.seller_id
    second_product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Second shared barcode product",
            "sku_code": f"second-{suffix}",
            "seller_id": str(seller_id),
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert second_product.status_code == 200, second_product.text
    second_product_id = uuid.UUID(second_product.json()["id"])
    barcode = f"OZN-SHARED-{suffix}"
    async with SessionLocal() as session:
        request = await intake_svc.get_request(session, tenant_id, rid, for_update=True)
        assert request is not None
        request.status = intake_svc.STATUS_RECEIVING
        session.add(
            InboundIntakeLine(
                request_id=rid,
                product_id=second_product_id,
                expected_qty=2,
                actual_qty=0,
            )
        )
        links = [
            ProductMarketplaceLink(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                marketplace="ozon",
                external_barcodes=[barcode],
            )
            for product_id in (first_product_id, second_product_id)
        ]
        session.add_all(links)
        await session.commit()
        box = await box_svc.create_open_box(session, tenant_id, rid)
        places = await intake_svc.create_cargo_places(session, tenant_id, rid, quantity=1)
        with pytest.raises(box_svc.InboundIntakeBoxError, match="barcode_ambiguous"):
            await box_svc.scan_product_into_box(session, tenant_id, rid, box.id, barcode=barcode)
        with pytest.raises(intake_svc.InboundIntakeError, match="barcode_ambiguous"):
            await cargo_svc.scan_product(session, tenant_id, rid, places[0].id, barcode=barcode)
        boxes = await box_svc.list_boxes_with_lines(session, tenant_id, rid)
        assert boxes[0].lines == []
        cargo_before = await cargo_svc._load_cargo_place(session, tenant_id, rid, places[0].id)
        assert cargo_before.lines == []
        with pytest.raises(box_svc.InboundIntakeBoxError, match="barcode_ambiguous"):
            await box_svc.scan_product_into_box(
                session,
                tenant_id,
                rid,
                box.id,
                barcode=barcode,
                product_id_hint=first_product_id,
            )
        with pytest.raises(intake_svc.InboundIntakeError, match="barcode_ambiguous"):
            await cargo_svc.scan_product(
                session,
                tenant_id,
                rid,
                places[0].id,
                barcode=barcode,
                product_id_hint=second_product_id,
            )

        links[1].external_barcodes = []
        await session.commit()
        box_line = await box_svc.scan_product_into_box(
            session, tenant_id, rid, box.id, barcode=barcode
        )
        cargo = await cargo_svc.scan_product(
            session, tenant_id, rid, places[0].id, barcode=barcode
        )
        assert box_line.product_id == first_product_id
        assert cargo.lines[0].product_id == first_product_id


@pytest.mark.asyncio
async def test_receiving_scans_build_one_seller_catalog_index_per_scan(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000) + 10)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=4)
    looked_up_product_ids: list[frozenset[uuid.UUID] | None] = []
    async def capture_index(*args: Any, **kwargs: Any) -> Any:
        scope = kwargs.get("scope")
        product_ids = getattr(scope, "product_ids", None)
        looked_up_product_ids.append(
            product_ids if isinstance(product_ids, frozenset) else None
        )
        return await build_product_code_index(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.inbound_intake_service.build_product_code_index", capture_index
    )

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        for _ in range(2):
            line = await intake_svc.scan_barcode_to_loose_intake(
                session, tenant_id, rid, barcode=sku
            )
        assert line.actual_qty == 2

        for _ in range(2):
            box_line = await box_svc.scan_product_into_box(
                session, tenant_id, rid, box.id, barcode=sku
            )
        assert box_line.quantity == 2

    assert looked_up_product_ids == [None] * 4


@pytest.mark.asyncio
async def test_product_hint_is_verified_and_updates_only_resolved_line(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 13)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=4)

    loose = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": sku, "product_id": str(pid)},
    )
    assert loose.status_code == 200, loose.text
    assert loose.json()["actual_qty"] == 1

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        box_id = box.id

    boxed = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}/scan",
        headers=ah,
        json={"barcode": sku, "product_id": str(pid)},
    )
    assert boxed.status_code == 200, boxed.text
    assert boxed.json()["quantity"] == 1

    # WMS-473: a hint that is not a product of this organisation is refused without the
    # catalogue; nothing is added to the document.
    wrong_hint = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}/scan",
        headers=ah,
        json={"barcode": sku, "product_id": str(uuid.uuid4())},
    )
    assert wrong_hint.status_code == 404, wrong_hint.text
    assert wrong_hint.json()["detail"] == "product_not_found"


@pytest.mark.asyncio
async def test_box_total_validation_keeps_zero_quantity_box_line_membership(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 11)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=1)

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        session.add(InboundIntakeBoxLine(box_id=box.id, product_id=pid, quantity=0))
        await session.flush()
        req = await intake_svc.get_request_for_receiving_scan(session, tenant_id, rid)
        assert req is not None
        req.lines[0].posted_qty = 1

        with pytest.raises(box_svc.InboundIntakeBoxError, match="actual_below_posted"):
            await box_svc._sync_line_actuals_from_box_totals(session, req)


@pytest.mark.asyncio
async def test_loose_scan_api_does_not_reload_full_request(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000) + 12)
    ah, _tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=2)

    async def full_request_must_not_be_used(*args: object, **kwargs: object) -> object:
        raise AssertionError("full request graph must not be loaded by loose scan API")

    monkeypatch.setattr(
        "app.api.inbound_intake.svc.get_request", full_request_must_not_be_used
    )
    response = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": sku},
    )
    assert response.status_code == 200, response.text
    assert response.json()["actual_qty"] == 1


@pytest.mark.asyncio
async def test_delete_empty_box_on_demand(async_client: AsyncClient) -> None:
    suffix = f"{int(time.time() * 1000)}-del"
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=2)

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        box_id = box.id

    del_res = await async_client.delete(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}",
        headers=ah,
    )
    assert del_res.status_code == 204, del_res.text

    async with SessionLocal() as session:
        boxes = await box_svc.list_boxes(session, tenant_id, rid)
    assert boxes == []


@pytest.mark.asyncio
async def test_loose_scan_stays_loose_and_completion_does_not_require_close(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 2)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=1)

    async with SessionLocal() as session:
        await box_svc.create_open_box(session, tenant_id, rid)
        await box_svc.create_open_box(session, tenant_id, rid)

        loose = await intake_svc.scan_barcode_to_loose_intake(
            session,
            tenant_id,
            rid,
            barcode=sku,
        )
        assert loose.actual_qty == 1

        req = await intake_svc.get_request(session, tenant_id, rid)
        assert req is not None
        line = next(ln for ln in req.lines if ln.product_id == pid)
        assert line.actual_qty == 1

        boxes = await box_svc.list_boxes_with_lines(session, tenant_id, rid)
        assert all(not b.lines for b in boxes)

        done = await intake_svc.complete_receiving(
            session, tenant_id, rid, actor_user_id=_actor_user_id(ah)
        )
        assert done.status == intake_svc.STATUS_SORTING
        assert done.lines[0].actual_qty == 1
