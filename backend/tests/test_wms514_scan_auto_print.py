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
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    MARKING_KIND_SGTIN,
    META_STATUS_ASSIGNED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.kiz_reprint import KizReprint
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.models.seller import Seller
from app.models.user import User
from app.services import fbs_kiz_service as kiz_svc
from app.services import fbs_scan_auto_print_service as scan_print_svc

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


async def _bind_canonical_kiz(
    supply_id: uuid.UUID,
    value: str,
    *,
    scan_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id)
        )
        assert order is not None
        marking = FbsOrderMarking(
            order_id=order.id,
            tenant_id=order.tenant_id,
            kind=MARKING_KIND_SGTIN,
            value=value,
            source="operator",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ASSIGNED,
        )
        session.add(marking)
        await session.flush()
        marking_id = marking.id
        if scan_id is not None:
            selection = await session.get(DocumentEvent, scan_id)
            assert selection is not None
            assert selection.actor_user_id is not None
            await scan_print_svc.record_bound_reprint_target(
                session,
                order.tenant_id,
                selection.actor_user_id,
                scan_id,
                order.id,
                marking.id,
            )
        await session.commit()
        return marking_id


async def test_successful_product_bind_atomically_prepares_reprint_recovery(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "bind-and-prepare-in-one-commit",
        "print_qr": False,
        "print_chz": False,
        "reprint_chz": True,
    }
    selected = await async_client.post(url, headers=headers, json=body)
    scan_id = uuid.UUID(selected.json()["scan_id"])
    order_id = uuid.UUID(selected.json()["order_id"])
    canonical = "010460000000000121WMS514-ATOMIC-BIND\x1d91TAIL"

    async with SessionLocal() as session:
        selection = await session.get(DocumentEvent, scan_id)
        order = await session.get(FbsOrder, order_id)
        assert selection is not None and selection.actor_user_id is not None
        assert order is not None
        tenant_id = order.tenant_id
        actor_user_id = selection.actor_user_id

        async def fake_commit_one(*_args: object, **_kwargs: object):
            marking = FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind=MARKING_KIND_SGTIN,
                value=canonical,
                source="operator",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ASSIGNED,
            )
            session.add(marking)
            await session.flush()
            return kiz_svc._FbsKizCommitOutcome(
                meta_status=None,
                newly_bound=True,
                bound_kiz=canonical,
                marking_id=marking.id,
            )

        monkeypatch.setattr(kiz_svc, "_commit_one_kiz_pair", fake_commit_one)
        async with AsyncClient() as http_client:
            rows = await kiz_svc.commit_kiz_pairs(
                session,
                tenant_id,
                actor_user_id,
                [
                    kiz_svc.FbsKizCommitPair(
                        order_id=order_id,
                        value=canonical,
                        confirmed=False,
                        scan_auto_print_id=scan_id,
                    )
                ],
                "atomic-bind-commit",
                http_client,
            )
    assert rows[0].newly_bound is True
    replay = await async_client.post(url, headers=headers, json=body)
    assert replay.json()["reprint_recovery"] == {"status": "available"}
    claim = await async_client.post(
        f"{url}/{scan_id}/reprint-claim",
        headers=headers,
        json={"attempt_key": "first-request-after-lost-preclaim"},
    )
    assert claim.json() == {
        "claimed": True,
        "started": False,
        "kiz": canonical,
    }


async def test_reprint_product_recovers_only_released_canonical_kiz(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "reprint-known-pre-print-failure",
        "print_qr": False,
        "print_chz": False,
        "reprint_chz": True,
    }
    selected = await async_client.post(url, headers=headers, json=body)
    assert selected.status_code == 200, selected.text
    assert selected.json()["reprint_recovery"] == {"status": "not_attempted"}

    canonical_kiz = "010460000000000121WMS514-EXACT-BOUND\x1d91CRYPTO-TAIL"
    await _bind_canonical_kiz(
        supply_id,
        canonical_kiz,
        scan_id=uuid.UUID(selected.json()["scan_id"]),
    )
    target_url = f"{url}/{selected.json()['scan_id']}"
    # The browser's first claim request is lost before reaching the server.
    # A reload therefore observes only the association committed with the bind.
    recovered = await async_client.post(url, headers=headers, json=body)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["scan_id"] == selected.json()["scan_id"]
    assert recovered.json()["order_id"] == selected.json()["order_id"]
    assert recovered.json()["replayed"] is True
    assert recovered.json()["reprint_recovery"] == {"status": "available"}

    split_claim = await async_client.post(
        f"{target_url}/print-claim",
        headers=headers,
        json={"target": "chz", "attempt_key": "stale-split-path"},
    )
    assert split_claim.status_code == 409
    assert split_claim.json()["detail"]["code"] == (
        "scan_reprint_claim_requires_atomic"
    )

    retry_attempt = {"attempt_key": "browser-retry"}
    retry_claim = await async_client.post(
        f"{target_url}/reprint-claim", headers=headers, json=retry_attempt
    )
    assert retry_claim.json() == {
        "claimed": True,
        "started": False,
        "kiz": canonical_kiz,
    }
    released = await async_client.post(
        f"{target_url}/print-failed",
        headers=headers,
        json={"target": "chz", **retry_attempt},
    )
    assert released.json() == {"claimed": False, "started": False}

    exact_retry = {"attempt_key": "browser-exact-retry"}
    exact_claim = await async_client.post(
        f"{target_url}/reprint-claim", headers=headers, json=exact_retry
    )
    assert exact_claim.json() == {
        "claimed": True,
        "started": False,
        "kiz": canonical_kiz,
    }
    started = await async_client.post(
        f"{target_url}/print-started",
        headers=headers,
        json={"target": "chz", **exact_retry},
    )
    assert started.json() == {"claimed": False, "started": True}

    after_started = await async_client.post(url, headers=headers, json=body)
    assert after_started.json()["reprint_recovery"] == {"status": "started"}
    async with SessionLocal() as session:
        assert await session.scalar(
            select(func.count()).select_from(FbsOrderMarking)
        ) == 1
        assert await session.scalar(select(func.count()).select_from(MarkingCode)) == 0


async def test_reprint_product_blocks_unknown_print_outcome(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "reprint-unknown-outcome",
        "print_qr": False,
        "print_chz": False,
        "reprint_chz": True,
    }
    selected = await async_client.post(url, headers=headers, json=body)
    assert selected.status_code == 200, selected.text
    await _bind_canonical_kiz(
        supply_id,
        "010460000000000121WMS514-UNKNOWN-BOUND",
        scan_id=uuid.UUID(selected.json()["scan_id"]),
    )
    target_url = f"{url}/{selected.json()['scan_id']}"
    claimed = await async_client.post(
        f"{target_url}/reprint-claim",
        headers=headers,
        json={"attempt_key": "browser-unknown"},
    )
    assert claimed.json()["claimed"] is True
    assert claimed.json()["kiz"] == "010460000000000121WMS514-UNKNOWN-BOUND"

    replay = await async_client.post(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["reprint_recovery"] == {"status": "outcome_unknown"}
    blocked = await async_client.post(
        f"{target_url}/reprint-claim",
        headers=headers,
        json={"attempt_key": "browser-must-not-retry"},
    )
    assert blocked.json() == {"claimed": False, "started": False, "kiz": None}


async def _replace_bound_kiz(supply_id: uuid.UUID, replacement: str) -> None:
    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id)
        )
        assert order is not None
        current = await session.scalar(
            select(FbsOrderMarking).where(
                FbsOrderMarking.order_id == order.id,
                FbsOrderMarking.meta_status != "rejected",
            )
        )
        assert current is not None
        current.meta_status = "rejected"
        session.add(
            FbsOrderMarking(
                order_id=order.id,
                tenant_id=order.tenant_id,
                kind=MARKING_KIND_SGTIN,
                value=replacement,
                source="operator",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ASSIGNED,
            )
        )
        await session.commit()


async def test_atomic_reprint_claim_rejects_replaced_or_cancelled_marking(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode,
        "idempotency_key": "reprint-replaced-before-claim",
        "print_qr": False,
        "print_chz": False,
        "reprint_chz": True,
    }
    selected = await async_client.post(url, headers=headers, json=body)
    scan_id = uuid.UUID(selected.json()["scan_id"])
    await _bind_canonical_kiz(
        supply_id,
        "010460000000000121WMS514-STALE-A",
        scan_id=scan_id,
    )
    await _replace_bound_kiz(
        supply_id,
        "010460000000000121WMS514-CURRENT-B",
    )
    target_url = f"{url}/{scan_id}"
    replaced = await async_client.post(
        f"{target_url}/reprint-claim",
        headers=headers,
        json={"attempt_key": "must-not-claim-b"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == {"claimed": False, "started": False, "kiz": None}

    cancelled_headers, cancelled_supply_id, cancelled_barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    cancelled_url = (
        f"/operations/fbs-supplies/{cancelled_supply_id}/scan-auto-print"
    )
    cancelled_selected = await async_client.post(
        cancelled_url,
        headers=cancelled_headers,
        json={
            "barcode": cancelled_barcode,
            "idempotency_key": "reprint-cancelled-before-claim",
            "print_qr": False,
            "print_chz": False,
            "reprint_chz": True,
        },
    )
    cancelled_scan_id = uuid.UUID(cancelled_selected.json()["scan_id"])
    await _bind_canonical_kiz(
        cancelled_supply_id,
        "010460000000000121WMS514-CANCELLED",
        scan_id=cancelled_scan_id,
    )
    async with SessionLocal() as session:
        cancelled_order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == cancelled_supply_id)
        )
        assert cancelled_order is not None
        cancelled_order.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()
    cancelled = await async_client.post(
        f"{cancelled_url}/{cancelled_scan_id}/reprint-claim",
        headers=cancelled_headers,
        json={"attempt_key": "must-not-claim-cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json() == {"claimed": False, "started": False, "kiz": None}


async def test_concurrent_atomic_reprint_recovery_claims_only_once(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    selected = await async_client.post(
        url,
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "reprint-concurrent-claim",
            "print_qr": False,
            "print_chz": False,
            "reprint_chz": True,
        },
    )
    scan_id = uuid.UUID(selected.json()["scan_id"])
    canonical = "010460000000000121WMS514-CONCURRENT"
    await _bind_canonical_kiz(supply_id, canonical, scan_id=scan_id)
    target_url = f"{url}/{scan_id}/reprint-claim"
    first, second = await asyncio.gather(
        async_client.post(
            target_url, headers=headers, json={"attempt_key": "claim-a"}
        ),
        async_client.post(
            target_url, headers=headers, json={"attempt_key": "claim-b"}
        ),
    )
    payloads = [first.json(), second.json()]
    assert sum(item["claimed"] is True for item in payloads) == 1
    assert sum(item["kiz"] == canonical for item in payloads) == 1
    assert sum(item == {"claimed": False, "started": False, "kiz": None} for item in payloads) == 1


async def test_atomic_reprint_recovery_is_tenant_supply_and_request_scoped(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(
        async_client, order_count=1
    )
    other_headers, other_supply_id, _ = await _seed_wb_supply(
        async_client, order_count=1
    )
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    selected = await async_client.post(
        url,
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "reprint-scope",
            "print_qr": False,
            "print_chz": False,
            "reprint_chz": True,
        },
    )
    scan_id = uuid.UUID(selected.json()["scan_id"])
    await _bind_canonical_kiz(
        supply_id,
        "010460000000000121WMS514-SCOPED",
        scan_id=scan_id,
    )
    body = {"attempt_key": "scope-check"}
    wrong_tenant = await async_client.post(
        f"{url}/{scan_id}/reprint-claim",
        headers=other_headers,
        json=body,
    )
    wrong_supply = await async_client.post(
        f"/operations/fbs-supplies/{other_supply_id}/scan-auto-print/{scan_id}/reprint-claim",
        headers=headers,
        json=body,
    )
    wrong_request = await async_client.post(
        f"{url}/{uuid.uuid4()}/reprint-claim",
        headers=headers,
        json=body,
    )
    assert wrong_tenant.status_code == 404
    assert wrong_supply.status_code == 404
    assert wrong_request.status_code == 404

    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.supply_id == supply_id)
        )
        assert order is not None
        other_seller = Seller(tenant_id=order.tenant_id, name="Other seller")
        session.add(other_seller)
        await session.flush()
        order.seller_id = other_seller.id
        await session.commit()
    wrong_seller = await async_client.post(
        f"{url}/{scan_id}/reprint-claim",
        headers=headers,
        json={"attempt_key": "wrong-seller"},
    )
    assert wrong_seller.json() == {
        "claimed": False,
        "started": False,
        "kiz": None,
    }


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
