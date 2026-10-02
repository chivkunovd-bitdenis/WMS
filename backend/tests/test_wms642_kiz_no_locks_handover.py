"""WMS-642: the KIZ worker locks nothing while WB answers; nothing scanned is lost."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_kiz_service as kiz_svc
from app.services import fbs_marking_service as fbs_marking_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow
from tests.test_wms635_kiz_no_wb_wait import _seed, _wb_row

pytestmark = pytest.mark.asyncio


async def _scan(async_client: AsyncClient, seed: dict[str, Any], key: str) -> Any:
    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=seed["headers"],
        json={"idempotency_key": key, "scan_no_wb_wait": True, "pairs": [
            {"order_id": str(seed["order"].order_id), "value": seed["value"], "confirmed": False},
        ]},
    )
    return response.json()[0]


async def _resend(seed: dict[str, Any]) -> list[Any]:
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        order = await session.get(FbsOrder, seed["order"].order_id)
        assert order is not None
        token = await fbs_marking_svc.require_marketplace_token(
            session, order.tenant_id, order.seller_id
        )
        return await fbs_marking_svc.resend_pending_kiz_bindings(
            session, [(order.id, order.tenant_id)], http_client, token
        )


async def _rows_free(order_id: Any) -> bool:
    """True when another transaction can lock the order, its KIZ and operation at once."""
    if engine.dialect.name != "postgresql":
        return True
    async with engine.connect() as conn, conn.begin():
        for sql in (
            "SELECT id FROM fbs_orders WHERE id = :id FOR UPDATE NOWAIT",
            "SELECT id FROM fbs_order_markings WHERE order_id = :id FOR UPDATE NOWAIT",
            "SELECT o.id FROM fbs_wb_operations o JOIN fbs_order_markings m"
            " ON o.local_entity_id = m.id WHERE m.order_id = :id FOR UPDATE OF o NOWAIT",
        ):
            await conn.execute(text(sql), {"id": order_id})
    return True


async def test_repeated_scan_of_a_queued_kiz_never_calls_wb(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_001)
    calls: list[str] = []

    async def fake_put(*_args: Any, **_kwargs: Any) -> None:
        calls.append("put")

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append("get")
        return _wb_row(seed["order"].wb_order_id, None, "required")

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    assert (await _scan(async_client, seed, "w642-a"))["code"] == "wb_pending_confirmation"
    assert (await _scan(async_client, seed, "w642-b"))["code"] == "wb_pending_confirmation"
    assert calls == []


async def test_worker_holds_no_row_while_wb_answers(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_002)
    order_id = seed["order"].order_id
    wb: dict[str, str | None] = {"value": None}
    free: list[str] = []

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        if await _rows_free(order_id):
            free.append("get")
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        if await _rows_free(order_id):
            free.append("put")
        wb["value"] = kwargs["value"]

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    await _scan(async_client, seed, "w642-c")
    assert await _resend(seed) == []
    assert free == ["get", "put", "get"]
    assert wb["value"] == seed["value"]
    async with SessionLocal() as session:
        operation = await session.scalar(select(FbsWbOperation))
        assert operation is not None and operation.state == "confirmed"


async def test_code_removed_during_the_write_is_taken_back_from_wb(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_003)
    order_id = seed["order"].order_id
    wb: dict[str, str | None] = {"value": None}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "required")

    async def fake_delete(*_args: Any, **_kwargs: Any) -> None:
        wb["value"] = None

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        # The operator presses the cross while the write is on its way to WB;
        # the write lands after the operator's delete.
        cross = await async_client.delete(
            f"/operations/fbs-orders/{order_id}/kiz", headers=seed["headers"]
        )
        assert cross.status_code == 204, cross.text
        wb["value"] = kwargs["value"]

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "delete_marketplace_order_meta", fake_delete)
    monkeypatch.setattr(kiz_svc, "delete_marketplace_order_meta", fake_delete)
    await _scan(async_client, seed, "w642-d")
    await _resend(seed)
    assert wb["value"] is None
    async with SessionLocal() as session:
        assert await session.scalar(select(FbsOrderMarking)) is None


async def test_accepted_write_is_not_sent_twice(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_004)
    sent: list[str] = []

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        sent.append(kwargs["value"])

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        # WB took the write but its read does not show the code yet.
        return _wb_row(seed["order"].wb_order_id, None, "required")

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    await _scan(async_client, seed, "w642-e")
    await _resend(seed)
    await _resend(seed)
    assert sent == [seed["value"]]


async def test_supply_is_not_handed_over_before_its_kiz_reached_wb(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_005)
    wb: dict[str, Any] = {"value": None, "down": True}
    delivered: list[str] = []

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        if wb["down"]:
            raise WildberriesClientError("transport_error")
        wb["value"] = kwargs["value"]

    async def fake_deliver(*_args: Any, **_kwargs: Any) -> Any:
        delivered.append(str(wb["value"]))
        raise shipment_svc.FbsShipmentError("stale_preflight", http_status=409)

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(shipment_svc, "deliver_supply", fake_deliver)
    await _scan(async_client, seed, "w642-f")
    url = f"/operations/fbs-supplies/{seed['supply_id']}/deliver"
    refused = await async_client.post(
        url, headers=seed["headers"], json={"idempotency_key": "w642-deliver-1"}
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "kiz_not_sent_to_wb"
    assert str(seed["order"].wb_order_id) in detail["message"]
    assert delivered == []
    wb["down"] = False
    sent_first = await async_client.post(
        url, headers=seed["headers"], json={"idempotency_key": "w642-deliver-2"}
    )
    assert sent_first.json()["detail"]["code"] == "stale_preflight"
    assert delivered == [seed["value"]]
