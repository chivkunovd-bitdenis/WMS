"""WMS-631 R19/R20: releasing a packing-scan selection and undoing a scan."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    MARKING_KIND_SGTIN,
    META_STATUS_ASSIGNED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.models.user import User
from app.services import fbs_kiz_service as kiz_svc
from tests.test_wms514_scan_auto_print import _seed_wb_supply

pytestmark = pytest.mark.asyncio


def _select_body(barcode: str, key: str) -> dict[str, object]:
    # Reprint mode selects without any marketplace call.
    return {
        "barcode": barcode,
        "idempotency_key": key,
        "print_qr": False,
        "print_chz": False,
        "reprint_chz": True,
        "await_honest_sign": True,
    }


async def test_cancel_releases_the_order_for_the_next_ordinary_scan(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    first = await async_client.post(url, headers=headers, json=_select_body(barcode, "esc-1"))
    assert first.status_code == 200, first.text
    scan_id = first.json()["scan_id"]

    cancelled = await async_client.post(f"{url}/{scan_id}/cancel", headers=headers)
    assert cancelled.status_code == 204, cancelled.text
    again = await async_client.post(f"{url}/{scan_id}/cancel", headers=headers)
    assert again.status_code == 204, again.text

    second = await async_client.post(url, headers=headers, json=_select_body(barcode, "esc-2"))
    assert second.status_code == 200, second.text
    assert second.json()["order_id"] == first.json()["order_id"]
    assert second.json()["scan_id"] != scan_id

    # The new reservation still reserves: a third scan advances to the neighbour.
    third = await async_client.post(url, headers=headers, json=_select_body(barcode, "esc-3"))
    assert third.status_code == 200, third.text
    assert third.json()["order_id"] != first.json()["order_id"]

    async with SessionLocal() as session:
        kinds = [
            (event.payload_json or {}).get("kind")
            for event in (
                await session.scalars(
                    select(DocumentEvent).where(DocumentEvent.document_id == supply_id)
                )
            ).all()
        ]
    assert kinds.count("wms631_scan_auto_print_cancelled") == 1


async def test_released_order_can_be_cancelled_and_selected_repeatedly(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    order_ids = set()
    for index in range(3):
        selected = await async_client.post(
            url, headers=headers, json=_select_body(barcode, f"repeat-{index}")
        )
        assert selected.status_code == 200, selected.text
        order_ids.add(selected.json()["order_id"])
        cancelled = await async_client.post(
            f"{url}/{selected.json()['scan_id']}/cancel", headers=headers
        )
        assert cancelled.status_code == 204, cancelled.text
    assert len(order_ids) == 1


async def test_cancel_is_tenant_scoped(async_client: AsyncClient) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client)
    other_headers, _other_supply, _ = await _seed_wb_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    selected = await async_client.post(url, headers=headers, json=_select_body(barcode, "t-1"))
    assert selected.status_code == 200, selected.text
    foreign = await async_client.post(
        f"{url}/{selected.json()['scan_id']}/cancel", headers=other_headers
    )
    assert foreign.status_code == 404
    # The owner's selection is still reserved.
    next_scan = await async_client.post(url, headers=headers, json=_select_body(barcode, "t-2"))
    assert next_scan.status_code == 200, next_scan.text
    assert next_scan.json()["order_id"] != selected.json()["order_id"]


async def test_scan_undo_releases_selection_and_is_idempotent(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    selected = await async_client.post(url, headers=headers, json=_select_body(barcode, "u-1"))
    assert selected.status_code == 200, selected.text
    body = {
        "order_id": selected.json()["order_id"],
        "scan_id": selected.json()["scan_id"],
        # Nothing was packed under this key: unpacking is a no-op.
        "pack_idempotency_key": f"{selected.json()['scan_id']}:packed",
        "release_selection": True,
    }
    undo_url = f"/operations/fbs-supplies/{supply_id}/scan-undo"
    first = await async_client.post(undo_url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json() == {"warning": None}
    second = await async_client.post(undo_url, headers=headers, json=body)
    assert second.status_code == 200, second.text
    again = await async_client.post(url, headers=headers, json=_select_body(barcode, "u-2"))
    assert again.status_code == 200, again.text
    assert again.json()["order_id"] == selected.json()["order_id"]


async def test_scan_undo_rejects_an_order_of_another_supply(async_client: AsyncClient) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client)
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-undo",
        headers=headers,
        json={"order_id": str(uuid.uuid4()), "release_selection": False},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "order_not_found"


async def test_kiz_rollback_refuses_a_code_changed_by_another_action(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder).where(FbsOrder.supply_id == supply_id))
        assert order is not None
        session.add(
            FbsOrderMarking(
                order_id=order.id,
                tenant_id=order.tenant_id,
                kind=MARKING_KIND_SGTIN,
                value="0104600000000001215OtherCode",
                source="operator",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ASSIGNED,
            )
        )
        # This scan's binding receipt: it bound ScannedCode, later someone bound OtherCode.
        actor = await session.scalar(select(User.id).where(User.tenant_id == order.tenant_id))
        await kiz_svc.record_kiz_bound_event(
            session,
            tenant_id=order.tenant_id,
            actor_user_id=actor,
            order=order,
            new_code_id=None,
            new_value="0104600000000001215ScannedCode",
            previous=None,
            idempotency_key=f"test-bound:{order.id}",
        )
        await session.commit()
        order_id = order.id
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-undo",
        headers=headers,
        json={"order_id": str(order_id), "kiz": "0104600000000001215ScannedCode"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "kiz_rollback_changed"
    async with SessionLocal() as session:
        kept = await session.scalar(
            select(FbsOrderMarking.value).where(FbsOrderMarking.order_id == order_id)
        )
    assert kept == "0104600000000001215OtherCode"


async def test_kiz_rollback_without_a_binding_receipt_is_a_no_op(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder).where(FbsOrder.supply_id == supply_id))
        assert order is not None
        order_id = order.id
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-undo",
        headers=headers,
        json={"order_id": str(order_id), "kiz": "0104600000000001215ScannedCode"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"warning": None}


async def test_kiz_rollback_refuses_an_order_moved_to_another_supply(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder).where(FbsOrder.supply_id == supply_id))
        assert order is not None
        order_id = order.id
    other = await async_client.post(
        f"/operations/fbs-supplies/{uuid.uuid4()}/scan-undo",
        headers=headers,
        json={"order_id": str(order_id), "kiz": "0104600000000001215ScannedCode"},
    )
    assert other.status_code == 409, other.text
    assert other.json()["detail"]["code"] == "scan_undo_order_moved"


async def test_sticker_selection_of_a_packed_order_can_be_released(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder).where(FbsOrder.supply_id == supply_id))
        assert order is not None
        order.pack_status = "packed"
        await session.commit()
        order_id = order.id
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    selected = await async_client.post(
        url, headers=headers, json={**_select_body("*WMS5140", "st-1"), "order_id": str(order_id)}
    )
    assert selected.status_code == 200, selected.text
    released = await async_client.post(
        f"{url}/{selected.json()['scan_id']}/cancel", headers=headers
    )
    assert released.status_code == 204, released.text


async def test_honest_sign_skip_means_no_kiz_is_awaited(async_client: AsyncClient) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.honest_sign_skipped_at = datetime.now(UTC)
        product = await session.scalar(select(Product).where(Product.wb_barcode == barcode))
        assert product is not None
        product.requires_honest_sign = True
        await session.commit()
    selected = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print",
        headers=headers,
        json=_select_body(barcode, "skip-1"),
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["binding_target"]["requires_honest_sign"] is False
