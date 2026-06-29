from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.services import marking_code_service as mc_svc
from app.services.tokens import decode_access_token


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


async def _print_codes_for_line(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    line_id: str,
    quantity: int,
) -> None:
    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == quantity


async def _setup_printed_ledger_events(
    async_client: AsyncClient,
    *,
    code_count: int,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    h, seller_id, product_id, wh_id = await _import_codes_to_pool(
        async_client,
        code_count=code_count,
    )
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=code_count,
        location_code=f"lg-{uuid.uuid4().hex[:6]}",
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
                    "quantity": code_count,
                }
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]
    await _print_codes_for_line(async_client, h, line_id=line_id, quantity=code_count)
    return h, uuid.UUID(seller_id), uuid.UUID(product_id)


def _tenant_id_from_headers(headers: dict[str, str]) -> uuid.UUID:
    token = headers["Authorization"].removeprefix("Bearer ").strip()
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


@pytest.mark.asyncio
async def test_ledger_honest_total_and_pagination_under_raw_cap(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mc_svc, "_LEDGER_EXPORT_MAX", 50)
    h, seller_id, product_id = await _setup_printed_ledger_events(async_client, code_count=8)

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={
            "seller_id": str(seller_id),
            "product_id": str(product_id),
            "event_type": "printed",
            "limit": 3,
            "offset": 0,
        },
    )
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert body["total"] == 8
    assert len(body["rows"]) == 3

    tail = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={
            "seller_id": str(seller_id),
            "product_id": str(product_id),
            "event_type": "printed",
            "limit": 3,
            "offset": 6,
        },
    )
    assert tail.status_code == 200, tail.text
    assert tail.json()["total"] == 8
    assert len(tail.json()["rows"]) == 2


@pytest.mark.asyncio
async def test_ledger_rejects_raw_events_beyond_cap_instead_of_wrong_total(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mc_svc, "_LEDGER_EXPORT_MAX", 5)
    h, seller_id, product_id = await _setup_printed_ledger_events(async_client, code_count=8)
    tenant_id = _tenant_id_from_headers(h)

    async with SessionLocal() as session:
        with pytest.raises(mc_svc.MarkingCodeServiceError) as exc_info:
            await mc_svc.list_ledger(
                session,
                tenant_id,
                seller_id=seller_id,
                pool_id=None,
                product_id=product_id,
                document_number=None,
                event_type="printed",
                cis_mask=None,
                date_from=None,
                date_to=None,
                limit=50,
                offset=0,
            )
    assert exc_info.value.code == "ledger_too_large"
