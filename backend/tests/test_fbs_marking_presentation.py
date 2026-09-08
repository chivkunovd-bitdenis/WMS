"""WMS-086: the saved WB decision/reason reaches the packing workspace intact."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_fbs_packing_selection import inventory_snapshot, seed_selection

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.services import fbs_marking_service
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_requirements", [False, True])
@pytest.mark.parametrize(
    "decision,reason,status",
    [
        ("accepted", None, "accepted"),
        ("pending", None, "pending"),
        ("sgtinApplied", None, "rejected"),
        ("invalid", "Код принадлежит другому товару", "rejected"),
        ("replacementRequired", "Нужно заменить код", "replacement_required"),
        ("somethingNew", None, "unknown"),
    ],
)
async def test_wb_verdict_is_saved_and_reread_in_workspace(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    reason: str | None,
    status: str,
    missing_requirements: bool,
) -> None:
    headers, supply_id, orders = await seed_selection(async_client)
    before = await inventory_snapshot()
    async with SessionLocal() as session:
        marking = (await session.execute(select(FbsOrderMarking))).scalar_one()
        value = marking.value

    async def get_meta(client, *, order_ids, **kwargs):
        assert order_ids == [orders[0].wb_order_id]
        return [
            MarketplaceOrderMetaRow(
                order_id=orders[0].wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin",
                        value=value,
                        decision=decision,
                        reason=reason,
                    ),
                ),
            )
        ]

    monkeypatch.setattr(fbs_marking_service, "fetch_marketplace_orders_meta_batch", get_meta)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, orders[0].order_id)
        assert order
        if missing_requirements:
            order.required_meta_json = None
            order.optional_meta_json = None
        await fbs_marking_service._sync_order_meta_from_wb(
            session,
            order,
            async_client,
            "synthetic-test-token",
        )
        await session.commit()
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    row = next(row for row in response.json()["orders"] if row["id"] == str(orders[0].order_id))
    assert row["metadata"]["required"] == ([] if missing_requirements else ["sgtin"])
    state = row["metadata"]["states"][0]
    assert state["status"] == status
    assert state["reason"] == reason
    assert state["decision"] == decision
    assert state["value_tail"] == value[-8:]
    assert response.json()["blockers"] == []
    assert await inventory_snapshot() == before


@pytest.mark.asyncio
async def test_put_refusal_exposes_only_this_orders_saved_decision(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, orders = await seed_selection(async_client)
    async with SessionLocal() as session:
        marking = (await session.execute(select(FbsOrderMarking))).scalar_one()
        marking.meta_status = "rejected"
        marking.reason = None
        marking.meta_details_json = {
            "meta_validation": [
                {"order_id": orders[1].wb_order_id, "kind": "sgtin", "decision": "sgtinNotFound"},
                {"order_id": orders[0].wb_order_id, "kind": "sgtin", "decision": "sgtinRetired"},
            ]
        }
        await session.commit()
    response = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    row = next(row for row in response.json()["orders"] if row["id"] == str(orders[0].order_id))
    assert row["metadata"]["states"][0]["decision"] == "sgtinRetired"
    assert row["metadata"]["states"][0]["reason"] is None
