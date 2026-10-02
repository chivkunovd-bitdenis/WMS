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
        json={
            "idempotency_key": key,
            "scan_no_wb_wait": True,
            "pairs": [
                {
                    "order_id": str(seed["order"].order_id),
                    "value": seed["value"],
                    "confirmed": False,
                },
            ],
        },
    )
    return response.json()[0]


async def _resend(seed: dict[str, Any]) -> None:
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        order = await session.get(FbsOrder, seed["order"].order_id)
        assert order is not None
        token = await fbs_marking_svc.require_marketplace_token(
            session, order.tenant_id, order.seller_id
        )
        await fbs_marking_svc.resend_pending_kiz_bindings(
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
    await _resend(seed)
    assert free == ["get", "put", "get"]
    assert wb["value"] == seed["value"]
    async with SessionLocal() as session:
        operation = await session.scalar(select(FbsWbOperation))
        assert operation is not None and operation.state == "confirmed"


async def test_code_removed_during_the_write_is_shown_and_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker never deletes in WB; a code that landed after the cross is visible."""
    from tests.test_fbs_kiz import _cis

    seed = await _seed(async_client, 642_003)
    order_id = seed["order"].order_id
    newer = _cis("NEW642003")
    wb: dict[str, Any] = {"value": None, "crossed": False}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def operator_delete(*_args: Any, **_kwargs: Any) -> None:
        wb["value"] = None

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        if not wb["crossed"]:
            # The operator presses the cross while the write is on its way to WB;
            # the write lands after the operator's delete.
            wb["crossed"] = True
            cross = await async_client.delete(
                f"/operations/fbs-orders/{order_id}/kiz", headers=seed["headers"]
            )
            assert cross.status_code == 204, cross.text
        wb["value"] = kwargs["value"]

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(kiz_svc, "delete_marketplace_order_meta", operator_delete)
    await _scan(async_client, seed, "w642-d")
    await _resend(seed)
    assert wb["value"] == seed["value"]
    async with SessionLocal() as session:
        assert await session.scalar(select(FbsOrderMarking)) is None
    # The right code B is scanned: WB holds the removed A, so B is not written over it
    # and the supply stays with a clear reason.
    seed_b = {**seed, "value": newer}
    await _scan(async_client, seed_b, "w642-d-b")
    check = await _check_supply(seed)
    assert check == fbs_marking_svc.QueuedKizCheck([], [seed["order"].wb_order_id])
    assert wb["value"] == seed["value"]
    # The operator re-does it: cross (removes A in WB) and scan B again.
    cross = await async_client.delete(
        f"/operations/fbs-orders/{order_id}/kiz", headers=seed["headers"]
    )
    assert cross.status_code == 204, cross.text
    await _scan(async_client, seed_b, "w642-d-b2")
    assert await _check_supply(seed) == fbs_marking_svc.QueuedKizCheck([], [])
    assert wb["value"] == newer


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


async def test_queued_kiz_reach_wb_before_the_handover(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_005)
    wb: dict[str, Any] = {"value": None}
    seen_by_deliver: list[str | None] = []

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        wb["value"] = kwargs["value"]

    async def fake_deliver(*_args: Any, **_kwargs: Any) -> Any:
        seen_by_deliver.append(wb["value"])
        raise shipment_svc.FbsShipmentError("stale_preflight", http_status=409)

    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(shipment_svc, "deliver_supply", fake_deliver)
    await _scan(async_client, seed, "w642-f")
    reply = await async_client.post(
        f"/operations/fbs-supplies/{seed['supply_id']}/deliver",
        headers=seed["headers"],
        json={"idempotency_key": "w642-deliver-1"},
    )
    assert reply.json()["detail"]["code"] == "stale_preflight"
    assert seen_by_deliver == [seed["value"]]


# Astra review rounds 1-2: the worker writes only into an empty WB field and never
# deletes; the handover reads the bindings, so nothing leaves unsent or next to another code.


async def _check_supply(seed: dict[str, Any]) -> fbs_marking_svc.QueuedKizCheck:
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        order = await session.get(FbsOrder, seed["order"].order_id)
        assert order is not None
        tenant_id = order.tenant_id
        await session.commit()
        return await fbs_marking_svc.send_queued_kiz_of_supply(
            session, tenant_id, seed["supply_id"], http_client
        )


async def test_code_confirmed_by_another_path_stays_in_wb(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_901)
    wb: dict[str, str | None] = {"value": None}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        wb["value"] = kwargs["value"]
        # An ordinary commit of the same code confirms it before this write returns.
        reply = await async_client.post(
            "/operations/fbs-orders/kiz/commit",
            headers=seed["headers"],
            json={
                "idempotency_key": "w642-parallel",
                "pairs": [
                    {
                        "order_id": str(seed["order"].order_id),
                        "value": seed["value"],
                        "confirmed": False,
                    },
                ],
            },
        )
        assert reply.status_code == 200, reply.text

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    await _scan(async_client, seed, "w642-p1-1")
    await _resend(seed)
    assert wb["value"] == seed["value"]
    async with SessionLocal() as session:
        marking = await session.scalar(select(FbsOrderMarking))
        assert marking is not None and marking.meta_status == "accepted"
    assert await _check_supply(seed) == fbs_marking_svc.QueuedKizCheck([], [])


async def test_another_code_in_wb_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(async_client, 642_903)
    sent: list[str] = []

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, "different-code-A", "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        sent.append(kwargs["value"])

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    await _scan(async_client, seed, "w642-p1-3a")
    check = await _check_supply(seed)
    assert check == fbs_marking_svc.QueuedKizCheck([], [seed["order"].wb_order_id])
    assert sent == []


async def test_sent_code_next_to_another_code_in_wb_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Astra round 2: a written code later read next to another WB code."""
    seed = await _seed(async_client, 642_906)
    wb: dict[str, str | None] = {"value": None}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "required")

    async def fake_put(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    await _scan(async_client, seed, "w642-r2-2")
    await _resend(seed)
    wb["value"] = "different-code-A"
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        order = await session.get(FbsOrder, seed["order"].order_id)
        assert order is not None
        await fbs_marking_svc.sync_order_marking_statuses(
            session, order.tenant_id, order.id, http_client, actor_user_id=None
        )
        await session.commit()
    check = await _check_supply(seed)
    assert check == fbs_marking_svc.QueuedKizCheck([], [seed["order"].wb_order_id])


async def test_replacement_during_the_handover_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_fbs_kiz import _cis

    seed = await _seed(async_client, 642_905)
    newer = _cis("NEW642905")
    wb: dict[str, str | None] = {"value": None}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def operator_delete(*_args: Any, **_kwargs: Any) -> None:
        wb["value"] = None

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        if kwargs["value"] == seed["value"]:
            reply = await async_client.post(
                "/operations/fbs-orders/kiz/commit",
                headers=seed["headers"],
                json={
                    "idempotency_key": "w642-replace",
                    "scan_no_wb_wait": True,
                    "pairs": [
                        {"order_id": str(seed["order"].order_id), "value": newer, "confirmed": True}
                    ],
                },
            )
            assert reply.json()[0]["code"] == "wb_pending_confirmation", reply.text
        wb["value"] = kwargs["value"]

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    monkeypatch.setattr(kiz_svc, "delete_marketplace_order_meta", operator_delete)
    await _scan(async_client, seed, "w642-p1-3b")
    # The late write of A landed after the replacement: B never leaves unseen.
    assert (await _check_supply(seed)).not_sent == [seed["order"].wb_order_id]
    assert wb["value"] == seed["value"]
    assert await _check_supply(seed) == fbs_marking_svc.QueuedKizCheck(
        [], [seed["order"].wb_order_id]
    )


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 429, 500])
async def test_only_a_refusal_of_the_code_turns_red(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    from app.services.wildberries_errors import WildberriesBusinessError

    seed = await _seed(async_client, 643_000 + status_code)

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, None, "optional")

    async def fake_put(*_args: Any, **_kwargs: Any) -> None:
        error_cls = WildberriesBusinessError if status_code == 409 else WildberriesClientError
        raise error_cls("upstream_error", status_code=status_code)

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    await _scan(async_client, seed, f"w642-classify-{status_code}")
    await _resend(seed)
    async with SessionLocal() as session:
        marking = await session.scalar(select(FbsOrderMarking))
        operation = await session.scalar(select(FbsWbOperation))
        assert marking is not None and operation is not None
        if status_code in {400, 409}:
            assert marking.meta_status == "rejected" and operation.state == "failed"
        else:
            assert marking.meta_status != "rejected" and operation.state == "pending_confirmation"


# Astra review round 3: the gate runs inside the handover after its final WB sync,
# and a code bound to a supply already handed over is still sent by the worker.


async def _deliverable_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, wb_order_id: int
) -> Any:
    import uuid

    from app.core.settings import settings
    from app.models.fbs_supply import FbsSupply
    from app.models.packaging_task import PackagingTask, PackagingTaskLine
    from app.models.storage_location import StorageLocation
    from tests.test_fbs_shipment_warehouse_sc import (
        _mock_actual_composition_from_local_links,
        _prepare_supply_with_orders,
        _register_ff_admin,
        _setup_seller_with_token,
    )

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    _mock_actual_composition_from_local_links(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller, warehouse, tenant = await _setup_seller_with_token(async_client, headers, suffix)
    supply, ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller,
        warehouse,
        tenant,
        wb_order_ids=[wb_order_id],
        supply_name=f"W642 {wb_order_id}",
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, ids[0])
        assert order is not None
        order.required_meta_json = []
        task = PackagingTask(
            tenant_id=tenant,
            warehouse_id=uuid.UUID(warehouse),
            status="done",
            document_number=f"PKG-{wb_order_id}",
        )
        location = StorageLocation(
            tenant_id=tenant,
            warehouse_id=uuid.UUID(warehouse),
            code=f"L{wb_order_id}",
            barcode=f"L{wb_order_id}",
        )
        session.add_all([task, location])
        await session.flush()
        session.add(
            PackagingTaskLine(
                task_id=task.id,
                product_id=order.product_id,
                storage_location_id=location.id,
                qty_total=1,
                qty_suggested_packed=0,
                qty_confirmed_packed=0,
                qty_packed_in_task=1,
                qty_marking_printed=0,
                qty_marking_external=0,
            )
        )
        db_supply = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert db_supply is not None
        db_supply.packaging_task_id = task.id
        await session.commit()
    return headers, tenant, seller, supply, ids[0]


async def test_other_code_first_seen_by_the_handover_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_fbs_shipment_warehouse_sc import _delivery_preflight

    headers, tenant, _seller, supply, order_id = await _deliverable_supply(
        async_client, monkeypatch, 642_991
    )
    wb = {"value": "own-A"}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(642_991, wb["value"], "sgtinIntroduced")

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                tenant_id=tenant,
                order_id=order_id,
                kind="sgtin",
                value="own-A",
                source="operator",
                meta_status="accepted",
                check_status="ok",
            )
        )
        await session.commit()
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"]
    wb["value"] = "other-B"
    reply = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": "w642-r3-other",
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert reply.status_code == 409, reply.text
    assert reply.json()["detail"]["code"] == "kiz_not_sent_to_wb"
    assert "другой код" in reply.json()["detail"]["message"]
    async with SessionLocal() as session:
        from app.models.fbs_supply import FbsSupply

        db_supply = await session.get(FbsSupply, __import__("uuid").UUID(supply["id"]))
        assert db_supply is not None and db_supply.status != "in_delivery"


async def test_scan_right_before_the_handover_keeps_the_supply(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import fbs_supplies as api
    from tests.test_fbs_kiz import _cis
    from tests.test_fbs_shipment_warehouse_sc import _delivery_preflight

    headers, _tenant, _seller, supply, order_id = await _deliverable_supply(
        async_client, monkeypatch, 642_994
    )

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(642_994, None, "optional")

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    real_send = api._send_queued_kiz

    async def send_then_operator_scans(*args: Any, **kwargs: Any) -> Any:
        result = await real_send(*args, **kwargs)
        reply = await async_client.post(
            "/operations/fbs-orders/kiz/commit",
            headers=headers,
            json={
                "idempotency_key": "w642-r3-late-scan",
                "scan_no_wb_wait": True,
                "pairs": [
                    {"order_id": str(order_id), "value": _cis("R3642994"), "confirmed": False}
                ],
            },
        )
        assert reply.json()[0]["code"] == "wb_pending_confirmation", reply.text
        return result

    monkeypatch.setattr(api, "_send_queued_kiz", send_then_operator_scans)
    reply = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": "w642-r3-late",
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert reply.status_code == 409, reply.text
    assert "ещё не ушёл" in reply.json()["detail"]["message"]


async def test_code_of_a_handed_over_supply_is_still_sent(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FbsSupply
    from app.services.fbs_autopoll_service import SellerPollTarget, sync_marking_verdicts_for_seller

    seed = await _seed(async_client, 642_995)
    wb: dict[str, str | None] = {"value": None}

    async def fake_get(*_args: Any, **_kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return _wb_row(seed["order"].wb_order_id, wb["value"], "sgtinIntroduced")

    async def fake_put(*_args: Any, **kwargs: Any) -> None:
        wb["value"] = kwargs["value"]

    monkeypatch.setattr(fbs_marking_svc, "fetch_marketplace_orders_meta_batch", fake_get)
    monkeypatch.setattr(fbs_marking_svc, "put_marketplace_order_meta", fake_put)
    await _scan(async_client, seed, "w642-r3-after")
    async with SessionLocal() as session:
        db_supply = await session.get(FbsSupply, seed["supply_id"])
        order = await session.get(FbsOrder, seed["order"].order_id)
        assert db_supply is not None and order is not None
        db_supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
        target = SellerPollTarget(tenant_id=order.tenant_id, seller_id=order.seller_id)
        await session.commit()
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        await sync_marking_verdicts_for_seller(session, target, http_client)
        await session.commit()
    assert wb["value"] == seed["value"]
    async with SessionLocal() as session:
        operation = await session.scalar(select(FbsWbOperation))
        assert operation is not None and operation.state == "confirmed"


@pytest.mark.parametrize("state", ["confirmed", "failed", "pending_confirmation"])
async def test_saved_other_code_keeps_the_supply_whatever_the_operation(
    async_client: AsyncClient, state: str
) -> None:
    seed = await _seed(async_client, 642_992)
    await _scan(async_client, seed, "w642-r3-states")
    async with SessionLocal() as session:
        marking = await session.scalar(select(FbsOrderMarking))
        operation = await session.scalar(select(FbsWbOperation))
        assert marking is not None and operation is not None
        marking.meta_status = "replacement_required"
        operation.state = state
        operation.error_code = "wb_pending_confirmation"
        await session.commit()
    assert await _check_supply(seed) == fbs_marking_svc.QueuedKizCheck(
        [], [seed["order"].wb_order_id]
    )
