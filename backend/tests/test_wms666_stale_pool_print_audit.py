"""Opt-in red audit: an old scanner payload cannot print another order's KIZ."""

import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_fbs_order_tape_concurrency import print_tape, seed_tape, stock_snapshot

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.product import Product
from app.services import fbs_kiz_service as kiz


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("WMS666_COMPATIBILITY_AUDIT") != "1",
    reason="Explicit compatibility audit; preserves the unmet release contract",
)
async def test_old_pool_scan_cannot_claim_print_after_code_moves_to_other_order(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 1)
    barcode = "460666AUDIT"
    async with SessionLocal() as session:
        for order_id in seed.order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order
            order.wb_barcode = barcode
            product = await session.get(Product, order.product_id)
            assert product
            product.wb_barcode = barcode
        await session.commit()
    stock_before = await stock_snapshot()
    selected = await async_client.post(
        f"/operations/fbs-supplies/{seed.supply_id}/scan-auto-print",
        headers=seed.headers,
        json={"barcode": barcode, "idempotency_key": "wms666-stale-pool",
              "print_qr": False, "print_chz": True, "reprint_chz": False,
              "await_honest_sign": True},
    )
    assert selected.status_code == 200, selected.text
    saved = selected.json()
    assert len(saved["printed_codes"]) == 1, saved
    order_a = uuid.UUID(saved["order_id"])
    order_b_index = next(i for i, value in enumerate(seed.order_ids) if value != order_a)
    async with SessionLocal() as session:
        await kiz.cancel_order_kiz(
            session, seed.tenant_id, seed.user_id, order_a, async_client,
        )
    async with SessionLocal() as session:
        manual_b = await print_tape(session, async_client, seed, order_b_index)
        await session.commit()
    assert manual_b.orders[0].codes == [saved["printed_codes"][0]["cis_code"]]
    async with SessionLocal() as session:
        active = list((await session.scalars(select(FbsOrderMarking))).all())
        assert len(active) == 1 and active[0].order_id == seed.order_ids[order_b_index]
    assert await stock_snapshot() == stock_before
    claimed = await async_client.post(
        f"/operations/fbs-supplies/{seed.supply_id}/scan-auto-print/{saved['scan_id']}/print-claim",
        headers=seed.headers,
        json={"target": "chz", "attempt_key": "old-browser-payload"},
    )
    print({"stage": "stale-pool-print-claim", "old_order": str(order_a),
           "current_order": str(seed.order_ids[order_b_index]),
           "cis": saved["printed_codes"][0]["cis_code"],
           "claim_http": claimed.status_code, "claim_result": claimed.json(),
           "stock_unchanged": True})
    # WMS-518 may return the code to its pool. That does not authorize this old
    # browser to print it for A after a new, valid binding has assigned it to B.
    assert claimed.status_code != 200 or claimed.json().get("claimed") is False
