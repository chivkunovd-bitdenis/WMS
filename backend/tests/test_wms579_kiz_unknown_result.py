"""WMS-579: unknown WB result of a KIZ write must not print or undo the wrong code.

Review of 28.09.2026 (Astra F1-F3, Opus P2-1) reproduced three defects on the
edges of WMS-529 (exact readback) and WMS-560 (tape keeps a code WB accepted
without echo):

* F2 - a tape retry after a lost PUT printed the local code although the
  reconciling read returned no row for the order or returned a different code;
* F3 - the first ordinary print put a code into the tape although the readback
  right after an accepted PUT returned this code with a final negative verdict;
* F1 - a replacement A -> B whose PUT B WB accepted, but whose readback had no
  value yet, was compensated: WMS deleted B at WB, wrote A back and kept A.

The first three tests (four cases) are the reviewer's reproduction from the
Astra review ``release-audit-20260928/review-astra-fbs.md``; the rest guard the
neighbouring variants and the paths WMS-529/WMS-560 allowed (docs/requirements/WMS-579.md).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_fbs_order_tape_concurrency import print_tape, seed_tape
from test_wms560_tape_pending_kiz import _wb_order_ids

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.marking_code import MarkingCode
from app.services import fbs_kiz_service as kiz
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_order_tape_print_service as tape
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow


def _row(wb_id: int, value: str | None, decision: str, reason: str | None = None) -> Any:
    return MarketplaceOrderMetaRow(
        order_id=wb_id,
        meta={},
        meta_details=(
            MarketplaceMetaDetail(key="sgtin", value=value, decision=decision, reason=reason),
        ),
    )


# --- Reviewer reproduction (Astra, 28.09.2026) --------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", ["absent", "different_kiz"])
async def test_retry_after_lost_write_and_still_absent_wb_row_must_not_print(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, readback: str,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    wb_ids = await _wb_order_ids(seed)
    puts: list[int] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["order_id"])
        raise WildberriesClientError("transport_error")

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        if readback == "absent":
            return []
        return [_row(wb_ids[0], "010460043993125321DIFFERENT00001", "filled")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        first = await print_tape(session, async_client, seed)
        assert len(first.order_errors) == 1 and not first.orders
    async with SessionLocal() as session:
        second = await print_tape(session, async_client, seed)
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
        assert len(puts) == 1
        assert not second.orders, "UNCONFIRMED WRITE PRINTED on retry with absent WB row"
        assert len(second.order_errors) == 1


@pytest.mark.asyncio
async def test_successful_put_with_rejected_readback_must_not_print(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    sent: dict[int, str] = {}

    async def put(*args: Any, **kwargs: Any) -> None:
        sent[kwargs["order_id"]] = kwargs["value"]

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        return [_row(wb_id, sent[wb_id], "sgtinNotFound", "КИЗ не найден")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        marking = await session.scalar(select(FbsOrderMarking))
        assert marking is not None
        assert marking.meta_status == "rejected"
        assert not result.orders, "WB REJECTED KIZ printed without error"


@pytest.mark.asyncio
async def test_replacement_ack_without_echo_keeps_new_binding_for_reconciliation(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_fbs_kiz import _cis

    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as session:
        initial = await print_tape(session, async_client, seed)
        assert len(initial.orders) == 1 and not initial.order_errors
        old = await session.scalar(select(FbsOrderMarking.value))
    new = _cis("NEWREPAUDIT")
    calls: list[tuple[str, str | None]] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        calls.append(("put", kwargs["value"]))

    async def delete(*args: Any, **kwargs: Any) -> None:
        calls.append(("delete", None))

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append(("get_empty", None))
        return [_row(kwargs["order_ids"][0], None, "optional")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(kiz, "put_marketplace_order_meta", put)
    monkeypatch.setattr(kiz, "delete_marketplace_order_meta", delete)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=seed.headers,
        json={
            "idempotency_key": "replace-audit",
            "pairs": [{"order_id": str(seed.order_ids[0]), "value": new, "confirmed": True}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["code"] == "wb_pending_confirmation", response.text
    async with SessionLocal() as session:
        values = list(await session.scalars(select(FbsOrderMarking.value)))
    assert ("put", old) not in calls, (
        f"Successfully accepted new code silently overwritten with old: {calls}; saved={values}"
    )
    assert new in values


# --- Neighbouring variants and paths that must stay as they were --------------


async def _print_reprint(session: Any, client: AsyncClient, seed: Any, marking_id: Any) -> Any:
    return await tape.print_fbs_order_tape(
        session,
        seed.tenant_id,
        seed.supply_id,
        order_ids=[seed.order_ids[0]],
        layout={"units": [{"block": "cz", "copies": 1}]},
        allow_partial=False,
        include_order_qr=False,
        reprint=True,
        actor_user_id=seed.user_id,
        http_client=client,
        reprint_marking_ids=[marking_id],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", ["empty_after_resend", "exact_pending"])
async def test_retry_after_lost_write_prints_when_wb_answers_for_this_code(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, readback: str,
) -> None:
    """WMS-560 R1/R2 stay: a retry prints once WB answered for this very code.

    ``empty_after_resend``: the reconciling read is empty, the same code is
    resent, WB answers that PUT and still has no echo. ``exact_pending``: WB
    already holds this code with a pending verdict, no second PUT is made.
    """
    seed = await seed_tape(async_client, monkeypatch, 2)
    wb_id = (await _wb_order_ids(seed))[0]
    puts: list[str] = []
    phase = "lost"

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["value"])
        if phase == "lost":
            raise WildberriesClientError("transport_error")

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        if readback == "exact_pending":
            return [_row(wb_id, puts[0], "pending")]
        return [_row(wb_id, None, "optional")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        first = await print_tape(session, async_client, seed)
        assert not first.orders
        assert [err.code for err in first.order_errors] == ["wb_pending_confirmation"]
    phase = "answered"
    async with SessionLocal() as session:
        second = await print_tape(session, async_client, seed)
        assert not second.order_errors
        assert [row.order_id for row in second.orders] == [seed.order_ids[0]]
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
    assert len(set(puts)) == 1
    assert len(puts) == (2 if readback == "empty_after_resend" else 1)


@pytest.mark.asyncio
async def test_first_print_readback_failure_after_accepted_put_is_not_printed(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WMS-560 R2 stays: a failed readback is not an echo, even after an accepted PUT."""
    seed = await seed_tape(async_client, monkeypatch, 2)
    puts: list[str] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["value"])

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        raise WildberriesClientError("upstream_error", status_code=503)

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        assert not result.orders
        assert [err.code for err in result.order_errors] == ["wb_pending_confirmation"]
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
        assert operation.error_code == "wb_upstream_error_503"
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "unknown"
    assert len(puts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", ["other_code", "replacement_asked_for_this_code"])
async def test_first_print_with_replacement_readback_is_an_order_error(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, readback: str,
) -> None:
    """Opus P2-1 neighbour: WB answered the PUT, then reads back another code
    (or asks to replace this one). The label is not handed out."""
    seed = await seed_tape(async_client, monkeypatch, 2)
    other = "010460043993125321OTHERFIRST0001"
    sent: dict[int, str] = {}

    async def put(*args: Any, **kwargs: Any) -> None:
        sent[kwargs["order_id"]] = kwargs["value"]

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        if readback == "other_code":
            return [_row(wb_id, other, "filled")]
        return [_row(wb_id, sent[wb_id], "replacementRequired")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        assert not result.orders
        assert [err.code for err in result.order_errors] == ["replacement_required"]
        assert result.order_errors[0].message == (
            "WB подтвердил другой код маркировки."
            if readback == "other_code"
            else "WB требует заменить код маркировки."
        )
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "replacement_required"
        order = await session.get(FbsOrder, seed.order_ids[0])
        assert order is not None
        expected_remote = other if readback == "other_code" else marking.value
        assert order.meta_details_json["sgtin"]["value"] == expected_remote
        assert order.metadata_delivery_allowed is False


@pytest.mark.asyncio
async def test_rejected_readback_keeps_wb_verdict_and_reason_for_the_operator(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F3: the order error carries WB's reason; the verdict read from WB is kept as read."""
    seed = await seed_tape(async_client, monkeypatch, 2)
    sent: dict[int, str] = {}

    async def put(*args: Any, **kwargs: Any) -> None:
        sent[kwargs["order_id"]] = kwargs["value"]

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        return [_row(wb_id, sent[wb_id], "sgtinNotFound", "КИЗ не найден")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        assert not result.orders
        assert [err.code for err in result.order_errors] == ["meta_validation_fail"]
        assert result.order_errors[0].message == "WB не принял маркировку: КИЗ не найден"
    async with SessionLocal() as session:
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "rejected"
        assert marking.reason == "КИЗ не найден"
        order = await session.get(FbsOrder, seed.order_ids[0])
        assert order is not None
        assert order.meta_details_json["sgtin"]["decision"] == "sgtinNotFound"
        assert order.metadata_delivery_allowed is False
        assert await session.scalar(select(FbsWbOperation.id)) is None


@pytest.mark.asyncio
async def test_exact_reprint_is_not_blocked_by_a_rejected_readback(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Перепечатать ЧЗ» of an already printed code still prints it (WMS-514 R7/R13)."""
    seed = await seed_tape(async_client, monkeypatch, 2)
    sent: dict[int, str] = {}
    puts: list[str] = []
    decision = "pending"

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["value"])
        sent[kwargs["order_id"]] = kwargs["value"]

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        reason = None if decision == "pending" else "КИЗ не найден"
        return [_row(wb_id, sent[wb_id], decision, reason)]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        first = await print_tape(session, async_client, seed)
        assert not first.order_errors and len(first.orders) == 1
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "pending"
        marking_id, value = marking.id, marking.value
    decision = "sgtinNotFound"
    async with SessionLocal() as session:
        reprinted = await _print_reprint(session, async_client, seed, marking_id)
        assert not reprinted.order_errors
        assert [row.codes for row in reprinted.orders] == [[value]]
    async with SessionLocal() as session:
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "rejected"
    assert puts == [value, value]


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", ["optional", "read_error"])
async def test_replacement_unknown_result_is_reconciled_to_the_new_code(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, readback: str,
) -> None:
    """F1: after an accepted PUT B the old code is not written back; a retry confirms B."""
    from test_fbs_kiz import _cis

    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as session:
        initial = await print_tape(session, async_client, seed)
        assert len(initial.orders) == 1 and not initial.order_errors
        old = await session.scalar(select(FbsOrderMarking.value))
    wb_id = (await _wb_order_ids(seed))[0]
    new = _cis("NEWREPRECON")
    calls: list[tuple[str, str | None]] = []
    echo = False

    async def put(*args: Any, **kwargs: Any) -> None:
        calls.append(("put", kwargs["value"]))

    async def delete(*args: Any, **kwargs: Any) -> None:
        calls.append(("delete", None))

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append(("get", None))
        if echo:
            return [_row(wb_id, new, "sgtinIntroduced")]
        if readback == "read_error":
            raise WildberriesClientError("upstream_error", status_code=503)
        return [_row(wb_id, None, "optional")]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(kiz, "put_marketplace_order_meta", put)
    monkeypatch.setattr(kiz, "delete_marketplace_order_meta", delete)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)

    async def commit() -> str:
        response = await async_client.post(
            "/operations/fbs-orders/kiz/commit",
            headers=seed.headers,
            json={
                "idempotency_key": "replace-reconcile",
                "pairs": [{"order_id": str(seed.order_ids[0]), "value": new, "confirmed": True}],
            },
        )
        assert response.status_code == 200, response.text
        return str(response.json()[0]["code"])

    assert await commit() == "wb_pending_confirmation"
    assert calls == [("delete", None), ("put", new), ("get", None)]
    async with SessionLocal() as session:
        markings = list(await session.scalars(select(FbsOrderMarking)))
        assert [(row.value, row.meta_status) for row in markings] == [(new, "unknown")]
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
        assert operation.local_entity_id == markings[0].id
        # The replaced code is retired exactly as in a confirmed replacement.
        old_status = await session.scalar(
            select(MarkingCode.status).where(MarkingCode.cis_code == old)
        )
        assert old_status == "void"

    calls.clear()
    echo = True
    assert await commit() == "ok"
    assert calls == [("get", None)]
    async with SessionLocal() as session:
        markings = list(await session.scalars(select(FbsOrderMarking)))
        assert [(row.value, row.meta_status) for row in markings] == [(new, "accepted")]
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "confirmed"
    assert ("put", old) not in calls
