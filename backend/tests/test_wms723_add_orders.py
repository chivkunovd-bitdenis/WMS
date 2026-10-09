"""WMS-723 preserves real WB add-orders and refuses invalid direct requests."""

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.services import fbs_supply_service as svc
from app.services.wildberries_client import WildberriesClientError
from tests.fbs_supply_card_fixture import add_orders as add
from tests.fbs_supply_card_fixture import ready_wb_supply as setup
from tests.fbs_supply_card_fixture import snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "assembling", "packed"])
async def test_c2_c6_editable_wb_add_readback_and_repeat_have_one_link(
    async_client, monkeypatch, status
):
    headers, _tenant, supply, orders = await setup(async_client, monkeypatch)
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        row.status = status
        await session.commit()
    confirmed = {723000}
    writes = []

    async def read(client, **kwargs):
        return "confirmed", set(confirmed)

    async def write(client, *, order_ids, **kwargs):
        writes.append(order_ids)
        confirmed.update(order_ids)

    monkeypatch.setattr(svc, "reconcile_supply_orders", read)
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", write)
    response = await add(async_client, headers, supply, orders[1:2])
    assert response.status_code == 200, response.text
    # Independent saved read after discarding the successful mutation response.
    readback = await async_client.get(
        f"/operations/fbs-supplies/{supply}/workspace", headers=headers
    )
    assert [o["id"] for o in readback.json()["orders"]].count(str(orders[1])) == 1
    repeated = await add(async_client, headers, supply, orders[1:2])
    assert repeated.status_code in (200, 409), repeated.text
    assert writes == [[723001]]
    async with SessionLocal() as session:
        rows = list(
            (await session.scalars(select(FbsOrder).where(FbsOrder.supply_id == supply))).all()
        )
        assert {o.id for o in rows} == set(orders[:2])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,marketplace", [("in_delivery", "wb"), ("done", "wb"), ("assembling", "ozon")]
)
async def test_c5_ineligible_status_or_marketplace_cannot_add(
    async_client, monkeypatch, status, marketplace
):
    headers, _tenant, supply, orders = await setup(async_client, monkeypatch)
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        row.status = status
        row.marketplace = marketplace
        if marketplace == "ozon":
            for oid in orders:
                order = await session.get(FbsOrder, oid)
                order.marketplace = marketplace
        await session.commit()
    before = await snapshot(exclude=("fbs_warehouse_bindings",))
    response = await add(async_client, headers, supply, orders[1:2])
    assert response.status_code == 409, response.text
    if marketplace == "wb":
        assert response.json()["detail"]["code"] == "supply_not_editable"
    assert await snapshot(exclude=("fbs_warehouse_bindings",)) == before


@pytest.mark.asyncio
async def test_c5_foreign_and_incompatible_orders_do_not_change_supplies(async_client, monkeypatch):
    headers, _tenant, supply, orders = await setup(async_client, monkeypatch)
    foreign_headers, _, _foreign, foreign_orders = await setup(async_client, monkeypatch)
    hidden = await async_client.get(f"/operations/fbs-supplies/{supply}", headers=foreign_headers)
    assert hidden.status_code in (403, 404), hidden.text
    before = await snapshot(exclude=("fbs_warehouse_bindings",))
    response = await add(async_client, foreign_headers, supply, orders[1:2])
    assert response.status_code in (403, 404), response.text
    response = await add(async_client, headers, supply, foreign_orders[1:2])
    assert response.status_code in (400, 404, 409), response.text
    assert await snapshot(exclude=("fbs_warehouse_bindings",)) == before


@pytest.mark.asyncio
async def test_c6_wb_refusal_preserves_link_and_retry_uses_readback(async_client, monkeypatch):
    headers, _tenant, supply, orders = await setup(async_client, monkeypatch)
    confirmed = {723000}

    async def read(client, **kwargs):
        return "confirmed", set(confirmed)

    async def reject(client, **kwargs):
        raise WildberriesClientError("http_error", message="WB rejected", status_code=400)

    monkeypatch.setattr(svc, "reconcile_supply_orders", read)
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", reject)
    response = await add(async_client, headers, supply, orders[1:2])
    assert response.status_code == 502, response.text
    async with SessionLocal() as session:
        assert (await session.get(FbsOrder, orders[1])).supply_id is None
    # Marketplace has accepted this order, but the first local response was lost.
    confirmed.add(723001)
    repeated = await add(async_client, headers, supply, orders[1:2])
    assert repeated.status_code == 200, repeated.text
    assert [o["id"] for o in repeated.json()["orders"]].count(str(orders[1])) == 1
