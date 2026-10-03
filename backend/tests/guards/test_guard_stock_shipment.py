"""G-STOCK-3: real WB handover and durable replay."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.services import fbs_shipment_service as shipment
from app.services import fbs_supply_composition_service as composition
from tests.guards.stock_helpers import check, moves, seed_fbs, total


@pytest.mark.asyncio
async def test_g_stock_3_deliver_writes_three_units_once(db_session, monkeypatch):
    """G-STOCK-3 · WMS-632 · решение владельца 02.10.2026:
    «в случае с ФБС нажали передать на ВБ».
    """
    ctx, actor, orders = await seed_fbs(db_session)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    monkeypatch.setattr(
        shipment, "_require_marketplace_token", AsyncMock(return_value="test-token")
    )
    monkeypatch.setattr(
        composition,
        "fetch_wb_supply_order_ids",
        AsyncMock(return_value=[o.wb_order_id for o in orders]),
    )
    monkeypatch.setattr(
        shipment,
        "fetch_marketplace_orders_status",
        AsyncMock(
            return_value=[
                {"id": o.wb_order_id, "supplierStatus": "confirm", "wbStatus": "waiting"}
                for o in orders
            ]
        ),
    )
    delivered = AsyncMock(return_value=None)
    monkeypatch.setattr(shipment, "deliver_marketplace_supply", delivered)
    async with httpx.AsyncClient() as client:
        for _ in range(2):
            await shipment.deliver_supply(
                db_session,
                ctx.tenant.id,
                ctx.supply.id,
                client,
                idempotency_key="guard-deliver",
                actor_user_id=actor.id,
            )
            await db_session.commit()
            check(
                await total(db_session, ctx.product.id),
                7,
                "передача 3 заказов и повтор списывают один раз",
            )
            check(
                sorted(
                    m.quantity_delta
                    for m in await moves(db_session, ctx.product.id, "fbs_shipment")
                ),
                [-1, -1, -1],
                "на каждый заказ приходится одно списание",
            )
        # Two independent requests replay the durable confirmed operation.
        # SQLite proves the replay contract, not PostgreSQL row-lock semantics.
        tenant_id, supply_id, actor_id = ctx.tenant.id, ctx.supply.id, actor.id
        await db_session.commit()
        ready = asyncio.Event()
        arrivals = 0

        async def concurrent_replay():
            nonlocal arrivals
            async with SessionLocal() as replay_session:
                arrivals += 1
                if arrivals == 2:
                    ready.set()
                await ready.wait()
                await shipment.deliver_supply(
                    replay_session,
                    tenant_id,
                    supply_id,
                    client,
                    idempotency_key="guard-deliver",
                    actor_user_id=actor_id,
                )
                await replay_session.commit()

        await asyncio.gather(concurrent_replay(), concurrent_replay())
        check(
            await total(db_session, ctx.product.id), 7, "параллельные повторы сохраняют остаток 7"
        )
        check(
            len(await moves(db_session, ctx.product.id, "fbs_shipment")),
            3,
            "параллельные повторы не добавляют расходных движений",
        )
    ledgers = list(
        await db_session.scalars(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id.in_([o.id for o in orders])
            )
        )
    )
    check(
        len([row for row in ledgers if row.shipment_movement_id]),
        3,
        "все списания имеют запись защиты повторов",
    )
    check(delivered.await_count, 1, "повтор не передаёт WB второй раз")
