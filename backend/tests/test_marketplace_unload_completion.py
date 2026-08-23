"""OUT-BE-01: unified complete_unload with has_discrepancy flag."""

from __future__ import annotations

import time
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_marketplace_unload_and_discrepancy_acts import (
    E2E_BARCODE,
    _finish_unload_packaging,
    _inventory_in_sorting_zone,
    _link_product_wb_barcode,
    _patch_mp_planned_date,
    _patch_packaging_instructions,
    _post_inventory,
    _seller_wb_mp_warehouse,
)

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.services.marketplace_unload_service import (
    MarketplaceUnloadError,
    complete_unload,
    compute_has_discrepancy,
    get_request,
    scan_barcode_into_box,
)


async def _confirmed_unload_with_stock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan_qty: int,
) -> tuple[dict[str, str], uuid.UUID, str]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Unload Complete Co",
            "slug": f"uc-{suffix}",
            "admin_email": f"uc-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=max(plan_qty, 5),
        location_code=f"UC-{suffix}",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=max(plan_qty, 5)
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": plan_qty},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit",
        headers=h,
    )
    assert sub.status_code == 200, sub.text
    await _finish_unload_packaging(async_client, h, mid)
    return h, uuid.UUID(mid), loc_id


async def _collect_qty_via_scan(
    async_client: AsyncClient,
    h: dict[str, str],
    mid: uuid.UUID,
    *,
    loc_id: str,
    qty: int,
) -> None:
    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    wid = detail.json()["warehouse_id"]
    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in locs.json() if x["id"] == loc_id)["barcode"]

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    loc_scan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text

    for _ in range(qty):
        prod_scan = await async_client.post(
            f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/scan",
            headers=h,
            json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
        )
        assert prod_scan.status_code == 200, prod_scan.text


def _ship_url(mid: uuid.UUID) -> str:
    return f"/operations/marketplace-unload-requests/{mid}/ship"


@pytest.mark.asyncio
async def test_ship_unload_without_discrepancy_http(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-001: HTTP POST /ship completes when plan equals picked qty."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=2
    )
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=2)

    ship = await async_client.post(_ship_url(mid), headers=h)
    assert ship.status_code == 200, ship.text
    body = ship.json()
    assert body["status"] == "shipped"
    assert body["ff_modified"] is False
    line = body["lines"][0]
    assert line["picked_qty"] == 2
    assert line["quantity"] == 2
    assert line["has_discrepancy"] is False


@pytest.mark.asyncio
async def test_cancel_shipped_unload_records_one_reversal_http(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-31-TC-016: late cancellation preserves shipped stock and reverses billing once."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=2
    )
    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    seller_id = uuid.UUID(detail.json()["seller_id"])
    me = await async_client.get("/auth/me", headers=h)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    performer_id = uuid.UUID(me.json()["id"])
    tariff = await async_client.post(
        "/billing/tariffs",
        headers=h,
        json={
            "seller_id": str(seller_id),
            "service_code": "marketplace_outbound",
            "unit": "item",
            "amount": "12.50",
            "valid_from": date.today().isoformat(),
        },
    )
    assert tariff.status_code == 201, tariff.text
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=2)

    ship = await async_client.post(_ship_url(mid), headers=h)
    assert ship.status_code == 200, ship.text
    stock_after_ship = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": loc_id},
    )
    assert stock_after_ship.status_code == 200, stock_after_ship.text
    assert len(stock_after_ship.json()) == 1
    assert stock_after_ship.json()[0]["quantity"] == 3

    cancelled = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/cancel", headers=h
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "shipped"

    repeated = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/cancel", headers=h
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["status"] == "shipped"

    stored = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "shipped"
    stock_after_repeated_cancel = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": loc_id},
    )
    assert stock_after_repeated_cancel.status_code == 200, stock_after_repeated_cancel.text
    assert stock_after_repeated_cancel.json() == stock_after_ship.json()

    async with SessionLocal() as session:
        entries = list(
            (
                await session.scalars(
                    select(BillingLedgerEntry)
                    .where(
                        BillingLedgerEntry.tenant_id == tenant_id,
                        BillingLedgerEntry.service_code == "marketplace_outbound",
                    )
                    .order_by(BillingLedgerEntry.entry_type)
                )
            ).all()
        )
        original = await session.scalar(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                BillingLedgerEntry.source_type == "marketplace_unload",
                BillingLedgerEntry.source_id == mid,
            )
        )
        assert original is not None
        reversal = await session.scalar(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.reversal_of_id == original.id,
            )
        )

    assert len(entries) == 2
    assert original.entry_type == "charge"
    assert original.performer_id == performer_id
    assert original.quantity == 2
    assert original.amount == 25
    assert reversal is not None
    assert reversal.entry_type == "reversal"
    assert reversal.performer_id == performer_id
    assert reversal.quantity == -2
    assert reversal.rate == original.rate
    assert reversal.amount == -25


@pytest.mark.asyncio
async def test_ship_unload_with_discrepancy_rejects_without_ack_http(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-002: HTTP POST /ship without ack → 422 distribution_incomplete."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=3
    )
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=1)

    ship = await async_client.post(_ship_url(mid), headers=h)
    assert ship.status_code == 422
    assert ship.json()["detail"] == "distribution_incomplete"


@pytest.mark.asyncio
async def test_ship_unload_with_discrepancy_succeeds_with_ack_http(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-002: HTTP POST /ship with acknowledge_discrepancy completes."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=3
    )
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=1)

    ship = await async_client.post(
        _ship_url(mid),
        headers=h,
        json={"acknowledge_discrepancy": True},
    )
    assert ship.status_code == 200, ship.text
    body = ship.json()
    assert body["status"] == "shipped"
    assert body["ff_modified"] is True
    line = body["lines"][0]
    assert line["picked_qty"] == 1
    assert line["quantity"] == 3
    assert line["has_discrepancy"] is True


@pytest.mark.asyncio
async def test_complete_unload_without_discrepancy(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-001: full pick → complete_unload sets has_discrepancy=False."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=2
    )
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=2)

    reg = await async_client.get("/auth/me", headers=h)
    tenant_id = uuid.UUID(reg.json()["tenant_id"])

    async with SessionLocal() as session:
        req = await complete_unload(session, tenant_id, mid)
        assert req.status == "shipped"
        assert req.has_discrepancy is False
        assert compute_has_discrepancy(req) is False


@pytest.mark.asyncio
async def test_complete_unload_with_discrepancy_requires_ack(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-002: partial pick blocks completion until acknowledge_discrepancy."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=3
    )
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=1)

    reg = await async_client.get("/auth/me", headers=h)
    tenant_id = uuid.UUID(reg.json()["tenant_id"])

    async with SessionLocal() as session:
        req_loaded = await get_request(session, tenant_id, mid)
        assert req_loaded is not None
        assert compute_has_discrepancy(req_loaded) is True

        with pytest.raises(MarketplaceUnloadError) as exc:
            await complete_unload(session, tenant_id, mid)
        assert exc.value.code == "distribution_incomplete"

        req = await complete_unload(
            session, tenant_id, mid, acknowledge_discrepancy=True
        )
        assert req.status == "shipped"
        assert req.has_discrepancy is True
        assert req.ff_modified is True


@pytest.mark.asyncio
async def test_scan_barcode_into_box_service_wrapper_parity(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-OUT-003: scan_barcode_into_box on unload service matches box collect path."""
    h, mid, loc_id = await _confirmed_unload_with_stock(
        async_client, monkeypatch, plan_qty=1
    )
    reg = await async_client.get("/auth/me", headers=h)
    tenant_id = uuid.UUID(reg.json()["tenant_id"])

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    box_id = uuid.UUID(box.json()["id"])

    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    wid = detail.json()["warehouse_id"]
    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in locs.json() if x["id"] == loc_id)["barcode"]

    async with SessionLocal() as session:
        loc_result = await scan_barcode_into_box(
            session,
            tenant_id,
            box_id,
            barcode=loc_barcode,
            storage_location_id=None,
        )
        assert loc_result.kind == "location"

        prod_result = await scan_barcode_into_box(
            session,
            tenant_id,
            box_id,
            barcode=E2E_BARCODE,
            storage_location_id=uuid.UUID(loc_id),
        )
        assert prod_result.kind == "product"
        assert prod_result.picked_qty == 1

        req = await get_request(session, tenant_id, mid)
        assert req is not None
        assert req.status == "collecting"
