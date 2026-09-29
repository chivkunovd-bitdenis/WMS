"""WMS-575: id кода маркировки доезжает до экрана упаковки.

Круговая стрелка «Перепечатать ЧЗ» (WMS-519) показывается только у кода,
про который экран знает id, и печатает именно его (reprint_marking_ids).
Сервисы worklist и workspace кладут id в состояние маркировки, но схема ответа
его не описывала, и pydantic молча выбрасывал поле: стрелки не было ни у одного
кода, внесённого оператором.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.fbs_orders import FbsWorklistMetadataStateOut
from app.db.session import SessionLocal
from app.models.fbs_order import MARKING_KIND_SGTIN, FbsOrder, FbsOrderMarking
from app.models.marking_code import STATUS_APPLIED
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding
from tests.test_fbs_kiz import (
    _cis,
    _create_order,
    _create_supply,
    _register_ff_admin,
    _seed_active_marking,
    _setup_seller_warehouse,
)


def test_marking_state_id_survives_serialization() -> None:
    dumped = FbsWorklistMetadataStateOut(
        id="4f7c2a52-0f1e-4b0a-9d8e-6a1b2c3d4e5f",
        kind="sgtin",
        status="pending",
        reason=None,
        source="operator",
        value_tail="AbCd1234",
    ).model_dump()
    assert dumped["id"] == "4f7c2a52-0f1e-4b0a-9d8e-6a1b2c3d4e5f"


def test_missing_marking_state_has_no_id() -> None:
    """У заказа без кода id нет — и стрелки перепечатки нет."""
    dumped = FbsWorklistMetadataStateOut(kind="sgtin", status="missing", reason=None).model_dump()
    assert dumped["id"] is None


@pytest.mark.asyncio
async def test_worklist_and_workspace_return_operator_marking_id(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=957501,
        sticker_code="WMS575-STATE-ID",
        wb_barcode="WMS575-STATE-ID-BAR",
        with_packaging=True,
    )
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        db_order.required_meta_json = [MARKING_KIND_SGTIN]
        # Worklist показывает заказ WB только со склада WB, который мы обслуживаем.
        assert db_order.wb_warehouse_id is not None
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=db_order.wb_warehouse_id,
        )
        await session.commit()
    await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=_cis("WMS575ID"),
        code_source="external_fbs",
        marking_source="operator",
        code_status=STATUS_APPLIED,
        qty_marking_printed=0,
        qty_marking_external=1,
    )
    async with SessionLocal() as session:
        marking_id = await session.scalar(
            select(FbsOrderMarking.id).where(FbsOrderMarking.order_id == order.order_id)
        )
    assert marking_id is not None

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_order = next(
        item for item in workspace.json()["orders"] if item["id"] == str(order.order_id)
    )
    workspace_state = workspace_order["metadata"]["states"][0]
    assert workspace_state["source"] == "operator"
    assert workspace_state["id"] == str(marking_id)

    worklist = await async_client.get(
        "/operations/fbs-orders/worklist",
        params={"status_group": "active", "limit": 500},
        headers=headers,
    )
    assert worklist.status_code == 200, worklist.text
    worklist_order = next(
        item for item in worklist.json()["items"] if item["id"] == str(order.order_id)
    )
    assert worklist_order["metadata"]["states"][0]["id"] == str(marking_id)
