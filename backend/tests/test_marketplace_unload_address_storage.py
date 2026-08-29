"""TASK-002: conditional cell requirement in collect/pick API (DEC-005)."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
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
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox

BASE = "/operations/marketplace-unload-requests"


async def _register_headers(async_client: AsyncClient, slug: str) -> dict[str, str]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Addr Storage FF",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _confirmed_unload_with_box(
    async_client: AsyncClient,
    h: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    address_storage_enabled: bool | None = None,
) -> tuple[str, str, str, str, str]:
    suffix = str(int(time.time() * 1000))
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "MU Addr",
            "sku_code": f"MU-AS-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    assert pr.status_code in (200, 201), pr.text
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=10,
        location_code=f"MU-AS-{suffix}",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=10
    )

    if address_storage_enabled is not None:
        patch = await async_client.patch(
            "/tenant/settings",
            headers=h,
            json={"address_storage_enabled": address_storage_enabled},
        )
        assert patch.status_code == 200, patch.text

    mu = await async_client.post(
        BASE,
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"{BASE}/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(f"{BASE}/{mid}/submit", headers=h)
    assert sub.status_code == 200, sub.text

    await _finish_unload_packaging(async_client, h, mid)

    box = await async_client.post(
        f"{BASE}/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    return mid, box.json()["id"], pid, loc_id, wid


@pytest.mark.asyncio
async def test_collect_without_location_when_address_storage_off(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _register_headers(async_client, f"mu-as-off-{int(time.time())}")
    mid, box_id, pid, _loc_id, _wid = await _confirmed_unload_with_box(
        async_client, h, monkeypatch, address_storage_enabled=False
    )

    manual = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["quantity"] == 1

    scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "quantity": 1},
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["storage_location_id"] is None
    assert scan.json()["location_code"] is None

    legacy_scan = await async_client.post(
        f"{BASE}/{mid}/pick/scan",
        headers=h,
        json={"barcode": E2E_BARCODE},
    )
    assert legacy_scan.status_code == 200, legacy_scan.text
    assert legacy_scan.json()["kind"] == "product"
    assert legacy_scan.json()["storage_location_id"] is None
    assert legacy_scan.json()["location_code"] is None

    detail = await async_client.get(f"{BASE}/{mid}", headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json()["pick_allocations"]
    assert all(
        row["storage_location_id"] is None
        and row["location_code"] is None
        for row in detail.json()["pick_allocations"]
    )

    options = await async_client.get(f"{BASE}/{mid}/pick-options", headers=h)
    assert options.status_code == 200, options.text
    assert all(row["locations"] == [] for row in options.json())


@pytest.mark.asyncio
async def test_collect_requires_location_when_address_storage_on(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _register_headers(async_client, f"mu-as-on-{int(time.time())}")
    mid, box_id, pid, loc_id, wid = await _confirmed_unload_with_box(
        async_client, h, monkeypatch, address_storage_enabled=True
    )
    async with SessionLocal() as session:
        db_product = await session.get(Product, uuid.UUID(pid))
        db_location = await session.get(StorageLocation, uuid.UUID(loc_id))
        assert db_product is not None
        assert db_location is not None
        tenant_id = db_product.tenant_id
        pallet = Pallet(
            tenant_id=tenant_id,
            warehouse_id=uuid.UUID(wid),
            code=f"MP-PALLET-{pid[-8:]}",
            barcode=f"MP-PALLET-BC-{pid[-8:]}",
            storage_location_id=uuid.UUID(loc_id),
        )
        source_box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=uuid.UUID(wid),
            internal_barcode=f"MP-BOX-{pid[-8:]}",
            container_kind="box",
        )
        session.add_all([pallet, source_box])
        await session.flush()
        source_box.pallet_id = pallet.id
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=uuid.UUID(loc_id),
                product_id=uuid.UUID(pid),
                container_kind="box",
                container_id=source_box.id,
                quantity=4,
                quantity_unpacked=4,
                quantity_packed=0,
            )
        )
        await session.commit()
        location_code = db_location.code
        pallet_id = pallet.id
        source_box_id = source_box.id

    # TC-NEW-PICK-CONTAINERS-001: the MP endpoint keeps legacy fields and
    # serializes loose physical sources, including the operator sorting label.
    options = await async_client.get(f"{BASE}/{mid}/pick-options", headers=h)
    assert options.status_code == 200, options.text
    product = next(row for row in options.json() if row["product_id"] == pid)
    locations = {
        location["storage_location_id"]: location
        for location in product["locations"]
    }
    assert locations[loc_id] == {
        "storage_location_id": loc_id,
        "location_code": location_code,
        "quantity": 14,
        "reserved": 0,
        "available": 14,
        "picked": 0,
        "sources": [
            {
                "quantity": 4,
                "picked": 0,
                "is_loose": False,
                "source_label": f"Короб MP-BOX-{pid[-8:]}",
                "container_path": [
                    {
                        "kind": "pallet",
                        "id": str(pallet_id),
                        "code": f"MP-PALLET-{pid[-8:]}",
                        "label": f"Палета MP-PALLET-{pid[-8:]}",
                    },
                    {
                        "kind": "box",
                        "id": str(source_box_id),
                        "code": f"MP-BOX-{pid[-8:]}",
                        "label": f"Короб MP-BOX-{pid[-8:]}",
                    },
                ],
            },
            {
                "quantity": 10,
                "picked": 0,
                "is_loose": True,
                "source_label": "Россыпью",
                "container_path": [],
            },
        ],
    }
    sorting = next(
        location
        for location in product["locations"]
        if location["location_code"] == "Без ячеек"
    )
    assert sorting["quantity"] == 10
    assert sorting["sources"][0]["source_label"] == "Россыпью"

    blocked = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "location_required"

    ok = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 1},
    )
    assert ok.status_code == 200, ok.text

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    loc_scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text
    assert loc_scan.json()["kind"] == "location"

    prod_scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
    )
    assert prod_scan.status_code == 200, prod_scan.text

    async with SessionLocal() as session:
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=uuid.UUID(loc_id),
                product_id=uuid.UUID(pid),
                container_kind="box",
                container_id=uuid.uuid4(),
                quantity=1,
                quantity_unpacked=1,
                quantity_packed=0,
            )
        )
        await session.commit()

    invalid_options = await async_client.get(f"{BASE}/{mid}/pick-options", headers=h)
    assert invalid_options.status_code == 409, invalid_options.text
    assert invalid_options.json()["detail"] == "invalid_container_reference"
