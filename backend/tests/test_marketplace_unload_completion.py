"""OUT-BE-01: unified complete_unload with has_discrepancy flag."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, tzinfo
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from app.services import marketplace_unload_service
from app.services.marketplace_unload_service import (
    MarketplaceUnloadError,
    complete_unload,
    compute_has_discrepancy,
    get_request,
    scan_barcode_into_box,
)

MSK = ZoneInfo("Europe/Moscow")


def _freeze_marketplace_unload_time(
    monkeypatch: pytest.MonkeyPatch,
    value: datetime,
) -> None:
    class FrozenDateTime:
        @staticmethod
        def now(timezone: tzinfo | None = None) -> datetime:
            if timezone is None:
                return value.replace(tzinfo=None)
            return value.astimezone(timezone)

    monkeypatch.setattr(marketplace_unload_service, "datetime", FrozenDateTime)


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
    """S-31-TC-016: a next-month reversal never rewrites an issued invoice."""
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
    ff_profile = await async_client.put(
        "/billing/profiles/ff",
        headers=h,
        json={
            "legal_name": "ООО Фулфилмент",
            "inn": "7707083893",
            "bank_name": "Банк",
            "bik": "044525225",
            "settlement_account": "40702810000000000001",
            "correspondent_account": "30101810400000000225",
        },
    )
    assert ff_profile.status_code == 200, ff_profile.text
    seller_profile = await async_client.put(
        f"/billing/profiles/sellers/{seller_id}",
        headers=h,
        json={"legal_name": "ООО Селлер", "inn": "7707083893"},
    )
    assert seller_profile.status_code == 200, seller_profile.text

    shipped_at_msk = datetime(2026, 6, 30, 23, 30, tzinfo=MSK)
    reversed_at_msk = datetime(2026, 7, 1, 0, 15, tzinfo=MSK)
    tariff = await async_client.post(
        "/billing/tariffs",
        headers=h,
        json={
            "seller_id": str(seller_id),
            "service_code": "marketplace_outbound",
            "unit": "item",
            "amount": "12.50",
            "valid_from": shipped_at_msk.date().isoformat(),
        },
    )
    assert tariff.status_code == 201, tariff.text
    await _collect_qty_via_scan(async_client, h, mid, loc_id=loc_id, qty=2)

    _freeze_marketplace_unload_time(monkeypatch, shipped_at_msk)
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

    june_invoice = await async_client.post(
        f"/billing/invoices/{seller_id}/2026-06/form",
        headers=h,
    )
    assert june_invoice.status_code == 200, june_invoice.text
    assert june_invoice.json()["status"] == "issued"
    june_invoice_id = uuid.UUID(june_invoice.json()["id"])
    june_detail_before = await async_client.get(
        f"/billing/invoices/{june_invoice_id}", headers=h
    )
    assert june_detail_before.status_code == 200, june_detail_before.text
    june_snapshot = {
        "total_amount": june_detail_before.json()["total_amount"],
        "lines": june_detail_before.json()["lines"],
    }
    assert Decimal(str(june_snapshot["total_amount"])) == Decimal("25.00")
    assert len(june_snapshot["lines"]) == 1
    assert Decimal(june_snapshot["lines"][0]["quantity"]) == Decimal("2")
    assert Decimal(june_snapshot["lines"][0]["amount"]) == Decimal("25.00")
    assert len(june_snapshot["lines"][0]["documents"]) == 1

    _freeze_marketplace_unload_time(monkeypatch, reversed_at_msk)
    cancelled = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/cancel", headers=h
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "shipped"

    july_invoice = await async_client.post(
        f"/billing/invoices/{seller_id}/2026-07/form",
        headers=h,
    )
    assert july_invoice.status_code == 200, july_invoice.text
    assert july_invoice.json()["status"] == "issued"
    july_invoice_id = uuid.UUID(july_invoice.json()["id"])
    july_detail_before = await async_client.get(
        f"/billing/invoices/{july_invoice_id}", headers=h
    )
    assert july_detail_before.status_code == 200, july_detail_before.text
    july_snapshot = {
        "total_amount": july_detail_before.json()["total_amount"],
        "lines": july_detail_before.json()["lines"],
    }
    assert Decimal(str(july_snapshot["total_amount"])) == Decimal("-25.00")
    assert len(july_snapshot["lines"]) == 1
    assert Decimal(july_snapshot["lines"][0]["quantity"]) == Decimal("-2")
    assert Decimal(july_snapshot["lines"][0]["rate"]) == Decimal("12.50")
    assert Decimal(july_snapshot["lines"][0]["amount"]) == Decimal("-25.00")
    assert len(july_snapshot["lines"][0]["documents"]) == 1

    june_detail_after_reversal = await async_client.get(
        f"/billing/invoices/{june_invoice_id}", headers=h
    )
    assert june_detail_after_reversal.status_code == 200, june_detail_after_reversal.text
    assert {
        "total_amount": june_detail_after_reversal.json()["total_amount"],
        "lines": june_detail_after_reversal.json()["lines"],
    } == june_snapshot

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

    june_detail_after_repeat = await async_client.get(
        f"/billing/invoices/{june_invoice_id}", headers=h
    )
    july_detail_after_repeat = await async_client.get(
        f"/billing/invoices/{july_invoice_id}", headers=h
    )
    assert june_detail_after_repeat.status_code == 200, june_detail_after_repeat.text
    assert july_detail_after_repeat.status_code == 200, july_detail_after_repeat.text
    assert {
        "total_amount": june_detail_after_repeat.json()["total_amount"],
        "lines": june_detail_after_repeat.json()["lines"],
    } == june_snapshot
    assert {
        "total_amount": july_detail_after_repeat.json()["total_amount"],
        "lines": july_detail_after_repeat.json()["lines"],
    } == july_snapshot

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
    assert original.occurred_at.replace(tzinfo=UTC) == shipped_at_msk.astimezone(UTC)
    assert reversal.occurred_at.replace(tzinfo=UTC) == reversed_at_msk.astimezone(UTC)
    assert june_snapshot["lines"][0]["documents"][0]["id"] == str(original.id)
    assert july_snapshot["lines"][0]["documents"][0]["id"] == str(reversal.id)


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
