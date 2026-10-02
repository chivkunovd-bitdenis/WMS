"""WMS-635 R4: the packing scan never waits for WB — any WB answer keeps the KIZ bound."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    META_STATUS_ACCEPTED,
    META_STATUS_REJECTED,
    META_STATUS_UNKNOWN,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode
from app.models.packaging_task import STATUS_IN_PROGRESS, PackagingTask
from app.services import fbs_kiz_service as kiz_svc
from app.services import fbs_marking_service as fbs_marking_svc
from app.services.wildberries_errors import WildberriesBusinessError, WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow
from tests.test_fbs_kiz import (
    _cis,
    _create_order,
    _create_supply,
    _register_ff_admin,
    _setup_seller_warehouse,
)

pytestmark = pytest.mark.asyncio


async def _seed(async_client: AsyncClient, wb_order_id: int) -> dict[str, Any]:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    order = await _create_order(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        supply_id=supply_id, suffix=suffix, wb_order_id=wb_order_id,
        sticker_code=f"WMS635-{wb_order_id}", wb_barcode=f"WMS635-BAR-{wb_order_id}",
        with_packaging=True,
    )
    value = _cis(f"W635{wb_order_id}")
    async with SessionLocal() as session:
        session.add(MarkingCode(
            tenant_id=tenant_id, seller_id=seller_id, product_id=order.product_id,
            cis_code=value, source="pool", status=STATUS_AVAILABLE,
        ))
        await session.commit()
    return {"headers": headers, "supply_id": supply_id, "order": order, "value": value}


def _wb_row(order_id: int, value: str | None, decision: str) -> list[MarketplaceOrderMetaRow]:
    return [MarketplaceOrderMetaRow(
        order_id=order_id,
        meta_details=(MarketplaceMetaDetail(key="sgtin", value=value, decision=decision),),
        meta={},
    )]


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_status", "operation_state"),
    [
        ("429", "wb_pending_confirmation", META_STATUS_UNKNOWN, "pending_confirmation"),
        ("404", "wb_rejected_kept", META_STATUS_REJECTED, "failed"),
        ("409", "wb_rejected_kept", META_STATUS_REJECTED, "failed"),
    ],
)
async def test_any_wb_answer_keeps_the_scanned_kiz_bound(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_code: str,
    expected_status: str,
    operation_state: str,
) -> None:
    seed = await _seed(async_client, 635_000 + int(failure))
    order, value = seed["order"], seed["value"]
    calls: list[str] = []

    async def fake_put(*_args: Any, **_kwargs: Any) -> None:
        calls.append("put")
        if failure == "429":
            raise WildberriesClientError("upstream_error", status_code=429)
        if failure == "404":
            raise WildberriesClientError("upstream_error", status_code=404)
        raise WildberriesBusinessError(
            "conflict", status_code=409, message="КИЗ не введён в оборот"
        )

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append("get")
        return _wb_row(order.wb_order_id, None, "required")

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=seed["headers"],
        json={"idempotency_key": f"w635-{failure}", "pairs": [
            {"order_id": str(order.order_id), "value": value, "confirmed": False},
        ]},
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["code"] == expected_code
    async with SessionLocal() as session:
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
        )
        assert marking is not None and marking.value == value
        assert marking.meta_status == expected_status
        if expected_status == META_STATUS_REJECTED:
            assert marking.reason
        operation = await session.scalar(select(FbsWbOperation))
        assert operation is not None and operation.state == operation_state
    # A final refusal is never sent again; 429 waits for the background reconciliation.
    assert calls.count("put") == 1


async def test_background_reconciliation_resends_a_kiz_wb_does_not_have(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4.2: after 429 the autopoll reads WB first and sends the same KIZ again."""
    seed = await _seed(async_client, 635_501)
    order, value = seed["order"], seed["value"]
    calls: list[str] = []
    remote: dict[str, str | None] = {"value": None, "decision": "required"}

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        calls.append("put")
        if calls.count("put") == 1:
            raise WildberriesClientError("upstream_error", status_code=429)
        assert kwargs["value"] == value
        remote.update(value=value, decision="filled")

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append("get")
        return _wb_row(order.wb_order_id, remote["value"], str(remote["decision"]))

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    first = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=seed["headers"],
        json={"idempotency_key": "w635-resend", "pairs": [
            {"order_id": str(order.order_id), "value": value, "confirmed": False},
        ]},
    )
    assert first.json()[0]["code"] == "wb_pending_confirmation"
    async with SessionLocal() as session:
        marking = await session.scalar(select(FbsOrderMarking))
        assert marking is not None
        keys = [(order.order_id, marking.tenant_id)]
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        handled = await fbs_marking_svc.resend_pending_kiz_bindings(
            session, keys, http_client, "token"
        )
    assert handled == 1
    # Read before the second write, never a blind resend.
    assert calls[calls.index("put") + 1:].index("get") < calls[calls.index("put") + 1:].index("put")
    assert calls.count("put") == 2
    async with SessionLocal() as session:
        marking = await session.scalar(select(FbsOrderMarking))
        operation = await session.scalar(select(FbsWbOperation))
        assert marking is not None and marking.meta_status == META_STATUS_ACCEPTED
        assert operation is not None and operation.state == "confirmed"


async def test_step_back_undoes_a_kiz_wb_refused(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4.3 + R3: «Назад» removes a WB-refused binding without calling WB."""
    seed = await _seed(async_client, 635_404)
    order, value = seed["order"], seed["value"]
    calls: list[str] = []

    async def fake_put(*_args: Any, **_kwargs: Any) -> None:
        calls.append("put")
        raise WildberriesClientError("upstream_error", status_code=404)

    async def fake_delete(*_args: Any, **_kwargs: Any) -> None:
        calls.append("delete")

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(kiz_svc, "delete_marketplace_order_meta", fake_delete)
    committed = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=seed["headers"],
        json={"idempotency_key": "w635-undo", "pairs": [
            {"order_id": str(order.order_id), "value": value, "confirmed": False},
        ]},
    )
    assert committed.json()[0]["code"] == "wb_rejected_kept"
    async with SessionLocal() as session:
        # The shared fixture builds a finished task; packing is still open here.
        supply = await session.get(FbsSupply, seed["supply_id"])
        task = await session.scalar(select(PackagingTask)) if supply is not None else None
        assert task is not None
        task.status = STATUS_IN_PROGRESS
        if supply is not None:
            supply.packaging_task_id = task.id
        await session.commit()
    undone = await async_client.post(
        f"/operations/fbs-supplies/{seed['supply_id']}/scan-undo",
        headers=seed["headers"],
        json={"order_id": str(order.order_id), "kiz_keys": ["w635-undo"]},
    )
    assert undone.status_code == 200, undone.text
    async with SessionLocal() as session:
        left = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
        )
    assert left is None
    assert "delete" not in calls
