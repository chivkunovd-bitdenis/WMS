from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_APPLIED, STATUS_PRINTED, MarkingCode, MarkingCodeEvent


async def _printed_code_cis(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    h = await _register_admin(async_client)
    suffix = uuid.uuid4().hex[:8]
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pair Seller", "email": f"s-{suffix}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "WH", "code": f"wh-{suffix}"},
    )
    wh_id = wh.json()["id"]
    sku = f"PAIR-{suffix}"
    product = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pair Product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = product.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )
    cis = f"01{'0' * 10}5555{'21'}{'P' * 20}0001"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=1,
        location_code=f"p-{suffix}",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 1}],
        },
    )
    line_id = task.json()["lines"][0]["id"]
    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert printed.status_code == 200, printed.text
    return h, cis


@pytest.mark.asyncio
async def test_verify_pair_match_applies_code(async_client: AsyncClient) -> None:
    h, cis = await _printed_code_cis(async_client)

    res = await async_client.post(
        "/operations/marking-codes/verify-pair",
        headers=h,
        json={"cis_a": cis, "cis_b": cis},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["match"] is True
    assert body["applied"] is True
    assert body["code_id"]

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(body["code_id"]))
        assert code is not None
        assert code.status == STATUS_APPLIED
        events = (
            await session.execute(
                select(MarkingCodeEvent).where(MarkingCodeEvent.code_id == code.id)
            )
        ).scalars().all()
        assert any(e.event_type == "applied" for e in events)


@pytest.mark.asyncio
async def test_verify_pair_mismatch_does_not_apply(async_client: AsyncClient) -> None:
    h, cis = await _printed_code_cis(async_client)
    other = cis[:-1] + ("0" if cis[-1] != "0" else "1")

    res = await async_client.post(
        "/operations/marking-codes/verify-pair",
        headers=h,
        json={"cis_a": cis, "cis_b": other},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["match"] is False
    assert body["applied"] is False

    async with SessionLocal() as session:
        code = (
            await session.execute(
                select(MarkingCode).where(MarkingCode.cis_code == cis)
            )
        ).scalar_one()
        assert code.status == STATUS_PRINTED


@pytest.mark.asyncio
async def test_verify_pair_second_apply_is_idempotent_no_event(async_client: AsyncClient) -> None:
    h, cis = await _printed_code_cis(async_client)
    first = await async_client.post(
        "/operations/marking-codes/verify-pair",
        headers=h,
        json={"cis_a": cis, "cis_b": cis},
    )
    assert first.json()["applied"] is True

    second = await async_client.post(
        "/operations/marking-codes/verify-pair",
        headers=h,
        json={"cis_a": cis, "cis_b": cis},
    )
    assert second.status_code == 200
    assert second.json()["match"] is True
    assert second.json()["applied"] is False
