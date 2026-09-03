"""История поставки FBS: она обязана помнить и то, чего в поставке уже нет."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document_event import DOCUMENT_TYPE_FBS_SUPPLY, DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.seller import Seller
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.fbs_order_history_service import supply_history


async def _context(async_client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Supply history", "slug": f"hist-{suffix}",
        "admin_email": f"hist-{suffix}@example.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    await async_client.post("/sellers", headers=headers, json={"name": "История"})
    await async_client.post(
        "/warehouses", headers=headers, json={"name": "История", "code": f"hist-{suffix}"}
    )
    me = await async_client.get("/auth/me", headers=headers)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == me.json()["email"]))
        assert user is not None
        seller_id = await session.scalar(
            select(Seller.id).where(Seller.tenant_id == user.tenant_id)
        )
        warehouse_id = await session.scalar(
            select(Warehouse.id).where(Warehouse.tenant_id == user.tenant_id)
        )
        assert seller_id is not None and warehouse_id is not None
        return user.tenant_id, seller_id, warehouse_id


@pytest.mark.asyncio
async def test_cancelled_order_keeps_its_number_in_the_supply_history(
    async_client: AsyncClient,
) -> None:
    """Отменённый заказ отвязывается от поставки — но история его помнит.

    Заказ, снятый при отмене, терял связь с поставкой, и в истории оставались
    безымянные «Заказ добавлен» и «Заказ убран», а сама отмена не показывалась
    вовсе. Номер восстанавливается из журнала поставки, где он записан.
    """
    tenant_id, seller_id, warehouse_id = await _context(async_client)
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            wb_supply_id="WB-GI-1", name="История", delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        cancelled = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            wb_order_id=555000111, supply_id=None, status="cancelled",
            created_at_wb=datetime.now(UTC), deadline_at=datetime.now(UTC) + timedelta(days=1),
            mapping_status="mapped", reserve_status="released",
        )
        session.add(cancelled)
        await session.flush()
        moment = datetime.now(UTC)
        for event_type in ("line_added", "line_removed"):
            session.add(DocumentEvent(
                tenant_id=tenant_id, document_type=DOCUMENT_TYPE_FBS_SUPPLY,
                document_id=supply.id, event_type=event_type, occurred_at=moment,
                source="system",
                payload_json={"qty_before": 0, "qty_after": 1, "fbs_order_id": str(cancelled.id)},
            ))
        await session.commit()
        supply_id = supply.id

    async with SessionLocal() as session:
        history = await supply_history(session, tenant_id=tenant_id, supply_id=supply_id)

    titles = [event["title"] for event in history["events"]]
    assert "Заказ отменён: 555000111" in titles
    moves = [
        event for event in history["events"]
        if event["title"] in {"Заказ добавлен в поставку", "Заказ убран из поставки"}
    ]
    assert moves, "события о движении заказа должны остаться в истории"
    assert all(event["details"] == "555000111" for event in moves)
