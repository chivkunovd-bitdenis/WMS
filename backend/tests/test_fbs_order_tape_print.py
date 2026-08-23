from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import MARKING_KIND_SGTIN, FbsOrder, FbsOrderMarking
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode, MarkingCodeEvent
from app.models.product import Product
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_order_tape_print_service as order_tape_svc
from tests.test_fbs_box_clear_and_workspace_extras import _packed_supply


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# S-03-TC-004 — the picking-list print mode produces only WB -> WMS pairs,
# even when every order requires an Honest Sign marking code.
@pytest.mark.asyncio
async def test_picking_list_mode_does_not_release_reprint_or_sync_marking_codes(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, order_ids, product_id, tenant_id = await _packed_supply(
        async_client,
        order_specs=[(1, timedelta(hours=3)), (2, timedelta(hours=4))],
    )
    started = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work",
        headers=headers,
    )
    assert started.status_code == 200, started.text

    seeded_code_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.requires_honest_sign = True
        orders = list(
            (
                await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids)))
            ).scalars()
        )
        for index, order in enumerate(orders):
            order.required_meta_json = [MARKING_KIND_SGTIN]
            code_id = uuid.uuid4()
            code = MarkingCode(
                id=code_id,
                tenant_id=tenant_id,
                seller_id=order.seller_id,
                product_id=product_id,
                cis_code=f"010000000000012321{index:02d}{uuid.uuid4().hex}",
                gtin="00000000000001",
                status=STATUS_AVAILABLE,
            )
            session.add(code)
            seeded_code_ids.append(code_id)
        await session.commit()

    picking = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/picking-list",
        headers=headers,
    )
    assert picking.status_code == 200, picking.text
    picking_body = picking.json()
    canonical_order_ids = [
        order_id
        for item in picking_body["items"]
        for order_id in item["order_ids"]
    ]
    missing_snapshot = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": canonical_order_ids,
            "mode": "picking_list",
            "include_order_qr": True,
        },
    )
    assert missing_snapshot.status_code == 422, missing_snapshot.text
    assert missing_snapshot.json()["detail"]["code"] == "picking_list_snapshot_required"

    preflight_codes = AsyncMock(side_effect=AssertionError("marking pool was inspected"))
    print_codes = AsyncMock(side_effect=AssertionError("marking code was printed"))
    sync_marking = AsyncMock(side_effect=AssertionError("marking was synced with WB"))
    promote_supply = AsyncMock(side_effect=AssertionError("printing changed supply state"))
    monkeypatch.setattr(order_tape_svc, "_preflight_new_code_shortage", preflight_codes)
    monkeypatch.setattr(order_tape_svc, "_print_or_reprint_order_code", print_codes)
    monkeypatch.setattr(marking_svc, "attach_order_meta_to_wb_and_sync", sync_marking)
    monkeypatch.setattr(
        order_tape_svc.pack_int_svc,
        "try_promote_fbs_supply_if_ready",
        promote_supply,
    )

    def fail_layout_parse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("picking-list mode parsed a marking layout")

    monkeypatch.setattr(order_tape_svc, "parse_layout", fail_layout_parse)

    printed = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": canonical_order_ids,
            "picking_list_snapshot": picking_body["snapshot"],
            "mode": "picking_list",
            "layout_json": {"not": "a marking layout"},
            "allow_partial": False,
            "include_order_qr": True,
            "reprint": True,
        },
    )
    assert printed.status_code == 200, printed.text
    body = printed.json()
    assert body["shortage"] == 0
    assert body["requested"] == len(order_ids)
    assert body["ready"] == len(order_ids)
    assert body["missing"] == 0
    assert body["failed"] == 0
    assert body["order_errors"] == []
    assert [row["order_id"] for row in body["orders"]] == canonical_order_ids
    assert [row["order_number"] for row in body["orders"]] == list(
        range(1, len(order_ids) + 1)
    )
    for row in body["orders"]:
        assert row["qr_asset"]["status"] == "ready"
        assert row["qr_asset"]["order_number"] == row["order_number"]
        assert row["codes"] == []
        assert row["printed_codes"] == []
        assert row["shortage"] is None

    preflight_codes.assert_not_awaited()
    print_codes.assert_not_awaited()
    sync_marking.assert_not_awaited()
    promote_supply.assert_not_awaited()

    async with SessionLocal() as session:
        marking_rows = await session.scalar(
            select(func.count())
            .select_from(FbsOrderMarking)
            .where(FbsOrderMarking.order_id.in_(order_ids))
        )
        marking_events = await session.scalar(
            select(func.count())
            .select_from(MarkingCodeEvent)
            .where(MarkingCodeEvent.code_id.in_(seeded_code_ids))
        )
        code_statuses = list(
            (
                await session.execute(
                    select(MarkingCode.status).where(MarkingCode.id.in_(seeded_code_ids))
                )
            ).scalars()
        )
        print_assets = await session.scalar(
            select(func.count())
            .select_from(FbsPrintAsset)
            .where(
                FbsPrintAsset.fbs_order_id.in_(order_ids),
                FbsPrintAsset.status == "ready",
            )
        )
    assert marking_rows == 0
    assert marking_events == 0
    assert code_statuses == [STATUS_AVAILABLE] * len(order_ids)
    assert print_assets == len(order_ids)
