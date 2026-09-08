"""WMS-087: persist WB requirement snapshots without inventing a delivery gate."""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.services.fbs_marking_service import apply_wb_meta_requirements_to_order
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from tests.test_fbs_marking import _wb_order_row
from tests.test_fbs_picking import _create_seller_and_warehouse, _register_ff_admin


@pytest.mark.parametrize(("row", "required", "optional"), [
    ({}, ["uin"], ["sgtin"]),
    ({"requiredMeta": None, "optionalMeta": "sgtin"}, ["uin"], ["sgtin"]),
    ({"requiredMeta": [], "optionalMeta": []}, [], []),
    ({"required_meta": [], "optional_meta": []}, [], []),
    ({"requiredMeta": [], "required_meta": ["uin"]}, [], ["sgtin"]),
    ({"requiredMeta": [" IMEI ", "imei"], "optionalMeta": ["sgtin"]}, ["imei"], ["sgtin"]),
])
def test_requirement_snapshot_distinguishes_absent_from_empty(
    row: dict[str, Any], required: list[str], optional: list[str],
) -> None:
    order = FbsOrder(required_meta_json=["uin"], optional_meta_json=["sgtin"],
                     metadata_delivery_allowed=True, meta_details_json=[{"decision": "filled"}])
    apply_wb_meta_requirements_to_order(order, row)
    assert order.required_meta_json == required
    assert order.optional_meta_json == optional
    assert order.metadata_delivery_allowed is True
    assert order.meta_details_json == [{"decision": "filled"}]


@pytest.mark.asyncio
async def test_wb_import_persists_requirements_then_preserves_omitted_and_clears_empty(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, _, _ = await _create_seller_and_warehouse(async_client, headers, suffix)
    # Official /orders/new example puts UIN in requiredMeta and SGTIN in optionalMeta.
    row = _wb_order_row(order_id=87001, requiredMeta=["uin"], optionalMeta=["sgtin"])
    async with SessionLocal() as session:
        order, created = await upsert_order_from_wb_row(
            session, tenant_id, seller_id, row, preserve_unmapped_warehouse=True,
        )
        assert created
        order_id = order.id
        order.metadata_delivery_allowed = True
        await session.commit()
    for payload, required, optional in (
        (row, ["uin"], ["sgtin"]),
        (_wb_order_row(order_id=87001), ["uin"], ["sgtin"]),
        (_wb_order_row(order_id=87001, requiredMeta=[], optionalMeta=[]), [], []),
    ):
        async with SessionLocal() as session:
            updated, created = await upsert_order_from_wb_row(
                session, tenant_id, seller_id, payload, preserve_unmapped_warehouse=True,
            )
            assert not created and updated.id == order_id
            await session.commit()
        async with SessionLocal() as session:
            persisted = await session.get(FbsOrder, order_id)
            assert persisted is not None
            assert persisted.required_meta_json == required
            assert persisted.optional_meta_json == optional
            assert persisted.metadata_delivery_allowed is True
        response = await async_client.get(
            f"/operations/fbs-orders/{order_id}/metadata", headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["required"] == required
        assert response.json()["optional"] == optional
        assert response.json()["delivery_allowed"] is True
