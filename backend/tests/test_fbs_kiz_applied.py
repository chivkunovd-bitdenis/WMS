from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_fbs_kiz import (
    _cis,
    _create_order,
    _create_supply,
    _patch_wb_acceptance,
    _register_ff_admin,
    _setup_seller_warehouse,
)

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrderMarking
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.packaging_task import PackagingTaskLine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "available_pool",
        "available_external",
        "printed",
        "printed_bound",
        "reserved_bound",
        "wrong_line",
    ],
)
async def test_scan_known_code_records_application_once_without_reprinting(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=981001,
        sticker_code="APPLIED081",
        wb_barcode="APPLIED081",
        with_packaging=True,
    )
    bound = mode.endswith("_bound")
    already_counted = mode not in {"available_pool", "available_external"}
    initial_status = (
        "reserved" if mode == "reserved_bound" else "printed" if already_counted else "available"
    )
    value = _cis("APPLIED081")
    printed_at = datetime.now(UTC) if initial_status == "printed" else None
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line
        line.qty_marking_printed = int(already_counted)
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=value,
            source="external_fbs" if mode == "available_external" else "pool",
            status=initial_status,
            printed_at=printed_at,
            label_artifact_pdf=b"retained-artifact",
            packaging_task_line_id=None if mode == "wrong_line" else line.id,
        )
        session.add(code)
        await session.flush()
        code_id = code.id
        if bound:
            session.add(
                FbsOrderMarking(
                    tenant_id=tenant_id,
                    order_id=order.order_id,
                    kind="sgtin",
                    value=value,
                    marking_code_id=code.id,
                    source="pool",
                    meta_status="accepted",
                    check_status="ok",
                )
            )
        await session.commit()
    sent = _patch_wb_acceptance(monkeypatch)
    pair = {"order_id": str(order.order_id), "value": value}
    validated = await async_client.post(
        "/operations/fbs-orders/kiz/validate", headers=headers, json=pair
    )
    if mode == "wrong_line":
        assert validated.status_code == 409, validated.text
    else:
        assert validated.status_code == 200, validated.text
    payload = {"idempotency_key": "applied081", "pairs": [{**pair, "confirmed": False}]}
    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    if mode == "wrong_line":
        assert response.json()[0]["code"] == "duplicate_kiz", response.text
        assert sent == {}
        return
    assert response.json()[0]["status"] == "ok", response.text
    assert sent == ({} if bound else {order.wb_order_id: value})
    repeated = await async_client.post(
        "/operations/fbs-orders/kiz/commit", headers=headers, json=payload
    )
    assert repeated.json()[0]["status"] == "ok", repeated.text
    duplicate = await async_client.post(
        "/operations/fbs-orders/kiz/validate", headers=headers, json=pair
    )
    assert duplicate.status_code == 409, duplicate.text
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code and code.status == "applied" and code.applied_at is not None
        assert code.source == ("external_fbs" if mode == "available_external" else "pool")
        assert code.printed_at == printed_at
        assert code.label_artifact_pdf == b"retained-artifact"
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line and line.qty_marking_printed == 1 and line.qty_marking_external == 0
        assert (
            await session.scalar(
                select(func.count(MarkingCodeEvent.id)).where(
                    MarkingCodeEvent.code_id == code_id, MarkingCodeEvent.event_type == "applied"
                )
            )
            == 1
        )
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
        )
        assert marking and marking.meta_status == "accepted" and marking.marking_code_id == code_id


@pytest.mark.asyncio
async def test_print_scan_history_and_reprint_keep_the_same_applied_code(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.packaging_task import PackagingTask
    from app.models.product import Product

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=981002,
        sticker_code="REPRINT081",
        wb_barcode="REPRINT081",
        with_packaging=True,
    )
    value = _cis("REPRINT081")
    async with SessionLocal() as session:
        task = await session.get(PackagingTask, order.packaging_task_id)
        assert task
        task.status = "in_progress"
        product = await session.get(Product, order.product_id)
        assert product
        product.requires_honest_sign = True
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=value,
            source="pool",
            status="available",
        )
        session.add(code)
        await session.commit()
        code_id = str(code.id)
    print_url = f"/operations/marking-codes/packaging-lines/{order.packaging_task_line_id}/print"
    printed = await async_client.post(print_url, headers=headers, json={"reprint": False})
    assert printed.status_code == 200, printed.text
    assert printed.json()["codes"] == [value]
    _patch_wb_acceptance(monkeypatch)
    pair = {"order_id": str(order.order_id), "value": value}
    validated = await async_client.post(
        "/operations/fbs-orders/kiz/validate", headers=headers, json=pair
    )
    assert validated.status_code == 200, validated.text
    applied = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={"idempotency_key": "reprint081", "pairs": [pair]},
    )
    assert applied.json()[0]["status"] == "ok", applied.text
    # Non-printed external and voided labels on the same line must not enter this list.
    async with SessionLocal() as session:
        for status in ["applied", "void"]:
            session.add(
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=order.product_id,
                    packaging_task_line_id=order.packaging_task_line_id,
                    cis_code=_cis(status),
                    status=status,
                    printed_at=datetime.now(UTC) if status == "void" else None,
                )
            )
        await session.commit()
    history = await async_client.get(
        f"/operations/marking-codes/packaging-task-lines/{order.packaging_task_line_id}/printed-codes",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert [(row["id"], row["status"]) for row in history.json()["codes"]] == [(code_id, "applied")]
    repeated = await async_client.post(
        print_url, headers=headers, json={"reprint": True, "code_ids": [code_id]}
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["is_reprint"] is True
    assert repeated.json()["codes"] == [value]
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code.id)
        assert code and code.status == "applied" and code.applied_at and code.printed_at
        events = list(
            (
                await session.scalars(
                    select(MarkingCodeEvent.event_type)
                    .where(MarkingCodeEvent.code_id == code.id)
                    .order_by(MarkingCodeEvent.created_at)
                )
            ).all()
        )
        assert events == ["printed", "applied", "reprinted"]
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line and line.qty_marking_printed == 1 and line.qty_marking_external == 0
