from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin


async def _import_codes_to_pool(
    async_client: AsyncClient,
    *,
    code_count: int,
) -> tuple[dict[str, str], str, str, str]:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Ledger Seller", "email": f"lg-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    wh = await async_client.post("/warehouses", headers=h, json={"name": "WLG", "code": "w-lg"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Ledger товар",
            "sku_code": f"LG-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = pr.json()["id"]

    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )

    gtin = "00000000008888"
    codes = [f"01{gtin}21{'G' * 20}{i:04d}" for i in range(code_count)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Ledger pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    return h, seller_id, product_id, wh_id


@pytest.mark.asyncio
async def test_ledger_collapses_import_batch_to_single_row(async_client: AsyncClient) -> None:
    h, seller_id, product_id, _wh_id = await _import_codes_to_pool(async_client, code_count=16)

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "product_id": product_id},
    )
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert body["total"] == 1
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["event_type"] == "imported"
    assert row["aggregated_count"] == 16
    assert row["cis_masked"] in (None, "")
    assert row["document_number"].startswith("ЗАГРКМ-")


@pytest.mark.asyncio
async def test_ledger_printed_events_stay_separate(async_client: AsyncClient) -> None:
    h, seller_id, product_id, wh_id = await _import_codes_to_pool(async_client, code_count=5)
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=3,
        location_code="lg-a1",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {
                    "product_id": product_id,
                    "storage_location_id": loc_id,
                    "quantity": 3,
                }
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == 3

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "product_id": product_id, "event_type": "printed"},
    )
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 3
    for row in body["rows"]:
        assert row["event_type"] == "printed"
        assert row["aggregated_count"] is None
        assert row["cis_masked"] is not None
        assert row["cis_masked"].startswith("…")


@pytest.mark.asyncio
async def test_ledger_pagination_on_collapsed_rows(async_client: AsyncClient) -> None:
    h, seller_id, product_id, _wh_id = await _import_codes_to_pool(async_client, code_count=8)

    page1 = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "product_id": product_id, "limit": 1, "offset": 0},
    )
    assert page1.status_code == 200
    assert page1.json()["total"] == 1
    assert len(page1.json()["rows"]) == 1
    assert page1.json()["rows"][0]["aggregated_count"] == 8

    page2 = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "product_id": product_id, "limit": 1, "offset": 1},
    )
    assert page2.status_code == 200
    assert page2.json()["total"] == 1
    assert page2.json()["rows"] == []
