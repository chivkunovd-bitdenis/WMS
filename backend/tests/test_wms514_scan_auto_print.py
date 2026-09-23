from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import (
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.kiz_reprint import KizReprint
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _seed_wb_supply(
    client: AsyncClient,
    *,
    order_count: int = 2,
    marketplace: str = "wb",
) -> tuple[dict[str, str], uuid.UUID, str]:
    suffix = str(time.time_ns())
    email = f"wms514-{suffix}@example.com"
    registered = await client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-514 {suffix}",
            "slug": f"wms514-{suffix}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller_response = await client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {suffix}"},
    )
    assert seller_response.status_code in {200, 201}, seller_response.text
    warehouse_response = await client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WMS-514 WH", "code": f"wms514-{suffix[-8:]}"},
    )
    assert warehouse_response.status_code in {200, 201}, warehouse_response.text

    seller_id = uuid.UUID(seller_response.json()["id"])
    warehouse_id = uuid.UUID(warehouse_response.json()["id"])
    barcode = f"460-WMS514-{suffix}"
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        product = Product(
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            name="Футболка WMS-514, M",
            sku_code=f"WMS514-{suffix}",
            wb_barcode=barcode,
            wb_nm_id=514,
            wb_chrt_id=51401,
            wb_size="M",
        )
        supply = FbsSupply(
            tenant_id=user.tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace=marketplace,
            wb_supply_id=f"WB-WMS514-{suffix}",
            name="WMS-514 supply",
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add_all([product, supply])
        await session.flush()
        for index in range(order_count):
            session.add(
                FbsOrder(
                    tenant_id=user.tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    product_id=product.id,
                    marketplace=marketplace,
                    wb_order_id=514_000 + index,
                    wb_rid=f"wms514-rid-{index}-{suffix}",
                    wb_nm_id=product.wb_nm_id,
                    wb_chrt_id=product.wb_chrt_id,
                    wb_article=product.sku_code,
                    wb_barcode=barcode,
                    price=100,
                    is_legal=False,
                    cargo_type="mgt",
                    wb_office_id=1,
                    wb_warehouse_id=1,
                    can_pvz=False,
                    supply_id=supply.id,
                    sticker_code=f"514 {index:04d}",
                    sticker_barcode=f"*WMS514{index}",
                    status=FBS_ORDER_STATUS_PACKED,
                    created_at_wb=now,
                    deadline_at=now + timedelta(hours=index),
                    mapping_status=MAPPING_STATUS_MAPPED,
                    reserve_status=RESERVE_STATUS_RESERVED,
                )
            )
        await session.commit()
        return headers, supply.id, barcode


async def test_product_scan_selects_one_order_and_replay_does_not_advance(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    first_body = {
        "barcode": barcode,
        "idempotency_key": "physical-scan-1",
        "print_qr": False,
        "print_chz": True,
    }
    first = await async_client.post(url, headers=headers, json=first_body)
    replay = await async_client.post(url, headers=headers, json=first_body)
    second = await async_client.post(
        url,
        headers=headers,
        json={**first_body, "idempotency_key": "physical-scan-2"},
    )

    assert first.status_code == replay.status_code == second.status_code == 200
    assert replay.json()["scan_id"] == first.json()["scan_id"]
    assert replay.json()["order_id"] == first.json()["order_id"]
    assert replay.json()["replayed"] is True
    assert second.json()["order_id"] != first.json()["order_id"]
    assert first.json()["wb_order_id"] < second.json()["wb_order_id"]

    exhausted = await async_client.post(
        url,
        headers=headers,
        json={**first_body, "idempotency_key": "physical-scan-3"},
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"]["code"] == "scan_product_exhausted"

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 2


async def test_all_off_scans_are_inert_and_do_not_consume_first_unit(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    async with SessionLocal() as session:
        before = await session.scalar(select(func.count()).select_from(DocumentEvent))

    for request_id in ("off-scan-1", "off-scan-2"):
        response = await async_client.post(
            url,
            headers=headers,
            json={
                "barcode": barcode,
                "idempotency_key": request_id,
                "print_qr": False,
                "print_chz": False,
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "scan_auto_print_disabled"

    async with SessionLocal() as session:
        after = await session.scalar(select(func.count()).select_from(DocumentEvent))
    assert after == before

    enabled = await async_client.post(
        url,
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "first-enabled-scan",
            "print_qr": False,
            "print_chz": True,
        },
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["wb_order_id"] == 514_000


async def test_scan_idempotency_rejects_changed_checkbox_snapshot(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "same-delivery",
        "print_qr": False,
        "print_chz": True,
    }
    assert (await async_client.post(url, headers=headers, json=body)).status_code == 200
    changed = await async_client.post(
        url,
        headers=headers,
        json={**body, "print_qr": True},
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "idempotency_key_reused"

    changed_to_reprint = await async_client.post(
        url,
        headers=headers,
        json={
            **body,
            "print_chz": False,
            "reprint_chz": True,
        },
    )
    assert changed_to_reprint.status_code == 409
    assert changed_to_reprint.json()["detail"]["code"] == "idempotency_key_reused"


async def test_concurrent_replay_returns_one_scan_selection(async_client: AsyncClient) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=2)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "concurrent-delivery",
        "print_qr": False,
        "print_chz": True,
    }
    first, second = await asyncio.gather(
        async_client.post(url, headers=headers, json=body),
        async_client.post(url, headers=headers, json=body),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["scan_id"] == second.json()["scan_id"]
    assert first.json()["order_id"] == second.json()["order_id"]
    assert sorted([first.json()["replayed"], second.json()["replayed"]]) == [False, True]


async def test_concurrent_distinct_scans_select_distinct_units(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=2)
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    first, second = await asyncio.gather(
        async_client.post(
            url,
            headers=headers,
            json={
                "barcode": barcode,
                "idempotency_key": "physical-scan-a",
                "print_qr": False,
                "print_chz": True,
            },
        ),
        async_client.post(
            url,
            headers=headers,
            json={
                "barcode": barcode,
                "idempotency_key": "physical-scan-b",
                "print_qr": False,
                "print_chz": True,
            },
        ),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["order_id"] != second.json()["order_id"]


async def test_product_scan_is_wb_only(async_client: AsyncClient) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client,
        order_count=1,
        marketplace="ozon",
    )
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print",
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "ozon-scan",
            "print_qr": True,
            "print_chz": False,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "scan_auto_print_wb_only"


async def test_reprint_product_scan_selects_exact_order_without_allocating_code(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        before_codes = await session.scalar(select(func.count()).select_from(MarkingCode))

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print",
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "reprint-product-scan",
            "print_qr": False,
            "print_chz": False,
            "reprint_chz": True,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["binding_target"]["order_id"] == payload["order_id"]
    assert payload["binding_target"]["wb_order_id"] == payload["wb_order_id"]
    assert payload["qr_asset"] is None
    assert payload["printed_codes"] == []
    async with SessionLocal() as session:
        after_codes = await session.scalar(select(func.count()).select_from(MarkingCode))
    assert after_codes == before_codes


async def test_print_target_claim_is_durable_and_never_blindly_retries(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    selected = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print",
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "durable-print-target",
            "print_qr": False,
            "print_chz": True,
        },
    )
    assert selected.status_code == 200, selected.text
    base = (
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print/"
        f"{selected.json()['scan_id']}"
    )
    first = {"target": "chz", "attempt_key": "browser-a"}
    second = {"target": "chz", "attempt_key": "browser-b"}

    claimed = await async_client.post(f"{base}/print-claim", headers=headers, json=first)
    replay = await async_client.post(f"{base}/print-claim", headers=headers, json=first)
    blocked = await async_client.post(f"{base}/print-claim", headers=headers, json=second)
    assert claimed.json() == {"claimed": True, "started": False}
    assert replay.json() == {"claimed": True, "started": False}
    assert blocked.json() == {"claimed": False, "started": False}

    released = await async_client.post(f"{base}/print-failed", headers=headers, json=first)
    reclaimed = await async_client.post(f"{base}/print-claim", headers=headers, json=second)
    started = await async_client.post(f"{base}/print-started", headers=headers, json=second)
    after_started = await async_client.post(
        f"{base}/print-claim",
        headers=headers,
        json={"target": "chz", "attempt_key": "browser-c"},
    )
    assert released.json() == {"claimed": False, "started": False}
    assert reclaimed.json() == {"claimed": True, "started": False}
    assert started.json() == {"claimed": False, "started": True}
    assert after_started.json() == {"claimed": False, "started": True}

    disabled = await async_client.post(
        f"{base}/print-claim",
        headers=headers,
        json={"target": "qr", "attempt_key": "not-enabled"},
    )
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["code"] == "scan_print_target_disabled"


async def test_print_target_claim_respects_tenant_and_supply_boundaries(
    async_client: AsyncClient,
) -> None:
    owner_headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    other_headers, other_supply_id, _ = await _seed_wb_supply(
        async_client, order_count=1
    )
    selected = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print",
        headers=owner_headers,
        json={
            "barcode": barcode,
            "idempotency_key": "tenant-isolated-target",
            "print_qr": False,
            "print_chz": True,
        },
    )
    assert selected.status_code == 200, selected.text
    scan_id = selected.json()["scan_id"]
    target = {"target": "chz", "attempt_key": "other-tenant"}

    wrong_tenant = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print/{scan_id}/print-claim",
        headers=other_headers,
        json=target,
    )
    wrong_supply = await async_client.post(
        f"/operations/fbs-supplies/{other_supply_id}/scan-auto-print/{scan_id}/print-claim",
        headers=owner_headers,
        json=target,
    )
    assert wrong_tenant.status_code == 404
    assert wrong_supply.status_code == 404


async def test_direct_full_kiz_reprint_does_not_touch_marking_pool(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _barcode = await _seed_wb_supply(async_client, order_count=1)
    gs = "\x1d"
    kiz = f"010460000000000121SERIAL514{gs}91ABCD{gs}92{'A' * 44}"
    base = f"/operations/fbs-supplies/{supply_id}/scan-kiz-reprint"

    saved = await async_client.post(
        base,
        headers=headers,
        json={"kiz": kiz, "idempotency_key": "direct-kiz-scan"},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["kiz"] == kiz

    claim = await async_client.post(
        f"{base}/{saved.json()['id']}/print-claim",
        headers=headers,
        json={"attempt_key": "browser-print-attempt"},
    )
    assert claim.status_code == 200
    assert claim.json()["claimed"] is True
    started = await async_client.post(
        f"{base}/{saved.json()['id']}/print-started",
        headers=headers,
    )
    assert started.status_code == 200
    assert started.json()["print_started_at"] is not None

    replay_claim = await async_client.post(
        f"{base}/{saved.json()['id']}/print-claim",
        headers=headers,
        json={"attempt_key": "duplicate-delivery"},
    )
    assert replay_claim.status_code == 200
    assert replay_claim.json()["claimed"] is False

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(KizReprint)) == 1
        assert await session.scalar(select(func.count()).select_from(MarkingCode)) == 0
