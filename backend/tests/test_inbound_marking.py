from __future__ import annotations

import io
import json
import uuid
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.inbound_intake import InboundIntakeLine
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.product import Product
from app.models.seller import Seller
from app.services import fbs_marking_service as wb
from app.services import inbound_intake_service as intake
from app.services import inbound_marking_service as svc
from app.services import marking_code_service as marking
from tests.test_inbound_intake_service_be01 import _auth_ids, _setup_request

CIS = "010460123456789021SERIAL1234567\x1d91KEY1\x1d92SIGNATURE+/="


async def _setup(client: httpx.AsyncClient) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant, user = await _auth_ids(client)
    req_id, product_id = await _setup_request(client, tenant, expected_qty=2)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        seller = Seller(tenant_id=tenant, name="Marking seller")
        session.add(seller)
        await session.flush()
        product.seller_id = seller.id
        await session.commit()
        req = await intake.begin_receiving(session, tenant, req_id, actor_user_id=user)
        line_id = req.lines[0].id
        await intake.set_line_actual_qty(session, tenant, req_id, line_id, actual_qty=2)
    return tenant, user, req_id, line_id


@pytest.mark.asyncio
async def test_attach_preserves_full_code_qty_and_idempotency(
    async_client: httpx.AsyncClient,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        first = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        again = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code="]d2" + CIS, actor_user_id=user
        )
        assert first == again
        assert first["cis_code"] == CIS and first["cz_status"] == "pending"
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 1
        assert (await session.get(InboundIntakeLine, line)).actual_qty == 2
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        code = await session.get(MarkingCode, uuid.UUID(first["id"]))
        assert code.status == "applied" and code.source == "external_fbs"
        assert await marking.count_available_for_product(session, tenant, code.product_id) == 0
        assert await marking.is_unbound_received_code(session, code)
        with pytest.raises(intake.InboundIntakeError, match="request_not_found"):
            await svc.attach_code(
                session, uuid.uuid4(), req, line_id=line, cis_code=CIS, actor_user_id=user
            )


@pytest.mark.asyncio
async def test_capacity_and_existing_lifecycle_are_not_overwritten(
    async_client: httpx.AsyncClient,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        first = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        code = await session.get(MarkingCode, uuid.UUID(first["id"]))
        code.status = "shipped"
        await session.commit()
        # Repeating a receipt scan is read-idempotent even after later lifecycle progress.
        await svc.attach_code(session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user)
        assert code.status == "shipped"
        assert not await marking.is_unbound_received_code(session, code)
        await svc.attach_code(
            session,
            tenant,
            req,
            line_id=line,
            cis_code=CIS.replace("SERIAL", "SECOND"),
            actor_user_id=user,
        )
        with pytest.raises(intake.InboundIntakeError, match="marking_quantity_exceeded"):
            await svc.attach_code(
                session,
                tenant,
                req,
                line_id=line,
                cis_code=CIS.replace("SERIAL", "THIRDX"),
                actor_user_id=user,
            )
        await session.rollback()
        assert await session.scalar(select(func.count(MarkingCode.id))) == 2


@pytest.mark.parametrize(
    ("payload", "status", "reason"),
    [
        (
            {
                "outerStatus": "INTRODUCED",
                "checkResult": True,
                "codeResolveData": {"verified": True},
            },
            "introduced",
            "введён",
        ),
        ({"outerStatus": "APPLIED", "checkResult": False}, "problem", "не введён"),
        (
            {
                "codeFounded": False,
                "checkResult": False,
                "status": "not_found_dm",
                "codeResolveData": {"valid": True, "verified": False},
            },
            "problem",
            "не найден",
        ),
        (
            {
                "outerStatus": "INTRODUCED",
                "checkResult": True,
                "codeResolveData": {"verified": False},
            },
            "problem",
            "Криптоподпись",
        ),
        ({"outerStatus": "INTRODUCED", "checkResult": False}, "unavailable", "не подтвердил"),
        ({"outerStatus": "NEW_FUTURE_STATUS", "checkResult": True}, "unavailable", "не подтвердил"),
        ([], "unavailable", "не подтвердил"),
    ],
)
def test_check_contract_is_conservative(payload: Any, status: str, reason: str) -> None:
    result = svc.interpret_check(payload)
    assert result["status"] == status
    assert reason in result["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("offline", [False, True])
async def test_background_check_is_idempotent_and_has_no_stock_effect(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    offline: bool,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        item = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        job = await svc.schedule_check(session, tenant, req)
        assert job is not None
        assert await svc.schedule_check(session, tenant, req) is None
    calls = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs["json"]["code"])
        if offline:
            raise httpx.ConnectError("offline")
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"outerStatus": "APPLIED", "checkResult": False},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await svc.run_check_job(job)
    await svc.run_check_job(job)
    assert calls == [CIS]
    async with SessionLocal() as session:
        result = await svc.list_codes(session, tenant, req)
        assert not result["checking"]
        assert result["items"][0]["cz_status"] == ("unavailable" if offline else "problem")
        code = await session.get(MarkingCode, uuid.UUID(item["id"]))
        assert code.status == "applied"
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 1


def test_xlsx_only_problems_keeps_codes_as_text() -> None:
    items = [
        {"article": "=1+1", "cis_code": CIS, "cz_status": status, "cz_reason": status}
        for status in ["introduced", "pending", "problem", "unavailable"]
    ]
    workbook = load_workbook(io.BytesIO(svc.export_problems(items)))
    sheet = workbook.active
    assert sheet.max_row == 3
    assert sheet["A2"].value == "=1+1" and sheet["A2"].data_type == "s"
    assert sheet["B2"].value.replace("\\u001d", "\x1d") == CIS


@pytest.mark.asyncio
async def test_wb_only_admits_unbound_received_code(async_client: httpx.AsyncClient) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        item = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        code = await session.get(MarkingCode, uuid.UUID(item["id"]))
        order = FbsOrder(tenant_id=tenant, seller_id=code.seller_id, product_id=code.product_id)
        claimed = await wb._claim_pool_code_if_present(
            session, tenant_id=tenant, order=order, cis_raw=CIS
        )
        assert claimed.id == code.id and code.status == "applied"
        event = await session.scalar(select(MarkingCodeEvent))
        original = event.meta_json
        event.meta_json = json.dumps({"source_process": "fbs"})
        await session.flush()
        with pytest.raises(wb.FbsMarkingError, match="duplicate_kiz"):
            await wb._claim_pool_code_if_present(
                session, tenant_id=tenant, order=order, cis_raw=CIS
            )
        event.meta_json = original
        for status in ["reserved", "void", "shipped", "introduced"]:
            code.status = status
            await session.flush()
            assert not await marking.is_unbound_received_code(session, code)


@pytest.mark.asyncio
async def test_failed_check_scheduling_cannot_undo_posting(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.user import User

    tenant, user_id, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user_id
        )
        user = await session.get(User, user_id)
        email = user.email
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def fail_schedule(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated scheduling failure")

    monkeypatch.setattr(svc, "schedule_check", fail_schedule)
    response = await async_client.post(
        f"/operations/inbound-intake-requests/{req}/complete-receiving", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sorting"
    again = await async_client.post(
        f"/operations/inbound-intake-requests/{req}/complete-receiving", headers=headers
    )
    assert again.status_code == 409, again.text
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.inbound_intake_line_id == line
                )
            )
            == 1
        )
        assert (await svc.list_codes(session, tenant, req))["items"][0][
            "cz_status"
        ] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize("race", [False, True])
async def test_receiving_code_binds_as_external_once_and_cannot_be_printed(
    async_client: httpx.AsyncClient,
    marketplace: str,
    race: bool,
) -> None:
    import asyncio

    from sqlalchemy import text

    from app.db.session import engine

    if race and engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    from app.models.packaging_task import PackagingTaskLine
    from app.services.fbs_kiz_service import _prepare_code_for_binding
    from app.services.ozon_kiz_service import OzonKizError, _claim_or_create_code
    from tests.test_fbs_kiz import (
        _create_order,
        _create_supply,
        _register_ff_admin,
        _setup_seller_warehouse,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller, warehouse, tenant = await _setup_seller_warehouse(async_client, headers, suffix)
    supply = await _create_supply(
        tenant_id=tenant, seller_id=seller, warehouse_id=warehouse, suffix=suffix
    )
    seeded = await _create_order(
        tenant_id=tenant,
        seller_id=seller,
        warehouse_id=warehouse,
        supply_id=supply,
        suffix=suffix,
        wb_order_id=396001,
        sticker_code="RCPT396",
        wb_barcode="RCPT396",
        with_packaging=True,
    )
    async with SessionLocal() as session:
        req = await intake.create_request(session, tenant, warehouse_id=warehouse)
        req_id = req.id
        await intake.add_line(session, tenant, req_id, product_id=seeded.product_id, expected_qty=1)
        req = await intake.get_request(session, tenant, req_id)
        await session.refresh(req, attribute_names=["lines"])
        req.status = "receiving"
        req.lines[0].actual_qty = 1
        await session.commit()
        user = (await async_client.get("/auth/me", headers=headers)).json()
        item = await svc.attach_code(
            session,
            tenant,
            req_id,
            line_id=req.lines[0].id,
            cis_code=CIS,
            actor_user_id=uuid.UUID(user["id"]),
        )
        code = await session.get(MarkingCode, uuid.UUID(item["id"]))
        assert await marking.count_available_for_product(session, tenant, seeded.product_id) == 0
        order = await session.get(FbsOrder, seeded.order_id)
        line = await session.get(PackagingTaskLine, seeded.packaging_task_line_id)
        if marketplace == "wb":
            bound, from_pool = await _prepare_code_for_binding(session, tenant, order, CIS, line)
        else:
            bound, from_pool = await _claim_or_create_code(
                session, order, seeded.product_id, CIS, line
            )
        assert bound.id == code.id and not from_pool
        assert code.status == "applied" and code.packaging_task_line_id == line.id
        if race:
            async with SessionLocal() as contender:
                # Hold a stale identity-map copy before the other transaction commits.
                stale = await contender.get(MarkingCode, code.id)
                assert stale.packaging_task_line_id is None
                other_order = FbsOrder(
                    tenant_id=tenant,
                    seller_id=seller,
                    product_id=seeded.product_id,
                    id=uuid.uuid4(),
                )
                other_line = await contender.get(PackagingTaskLine, line.id)
                pid = await contender.scalar(text("SELECT pg_backend_pid()"))

                async def competing_claim() -> str:
                    try:
                        if marketplace == "wb":
                            await _claim_or_create_code(
                                contender, other_order, seeded.product_id, CIS, other_line
                            )
                        else:
                            await _prepare_code_for_binding(
                                contender, tenant, other_order, CIS, other_line
                            )
                    except (OzonKizError, intake.InboundIntakeError) as exc:
                        return exc.code
                    except Exception as exc:
                        from app.services.fbs_kiz_service import FbsKizError

                        if isinstance(exc, FbsKizError):
                            return exc.code
                        raise
                    return "unexpected_second_claim"

                pending = asyncio.create_task(competing_claim())
                try:
                    async with SessionLocal() as observer:
                        async with asyncio.timeout(10):
                            while True:
                                waiting = await observer.scalar(
                                    text(
                                        "SELECT wait_event_type FROM pg_stat_activity "
                                        "WHERE pid = :pid"
                                    ),
                                    {"pid": pid},
                                )
                                await observer.rollback()
                                if waiting == "Lock":
                                    break
                                assert not pending.done(), "Claim bypassed code row lock"
                                await asyncio.sleep(0.01)
                    await session.commit()
                    assert await asyncio.wait_for(pending, 10) == "duplicate_kiz"
                finally:
                    await session.rollback()
                    if not pending.done():
                        pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        else:
            await session.commit()
        assert not await marking.is_unbound_received_code(session, code)
        with pytest.raises(OzonKizError, match="duplicate_kiz"):
            await _claim_or_create_code(session, order, seeded.product_id, CIS, line)
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,status,error",
    [
        ("pool", "available", "marking_code_in_pool"),
        ("external_fbs", "applied", "marking_code_already_used"),
        ("external_fbs", "shipped", "marking_code_already_used"),
        ("external_fbs", "void", "marking_code_already_used"),
    ],
)
async def test_existing_lifecycle_is_rejected_without_silent_reassignment(
    async_client: httpx.AsyncClient,
    source: str,
    status: str,
    error: str,
) -> None:
    tenant, user, req, line_id = await _setup(async_client)
    async with SessionLocal() as session:
        line = await session.get(InboundIntakeLine, line_id)
        product = await session.get(Product, line.product_id)
        code = MarkingCode(
            tenant_id=tenant,
            seller_id=product.seller_id,
            product_id=product.id,
            cis_code=CIS,
            source=source,
            status=status,
        )
        session.add(code)
        await session.commit()
        with pytest.raises(intake.InboundIntakeError, match=error):
            await svc.attach_code(
                session, tenant, req, line_id=line_id, cis_code=CIS, actor_user_id=user
            )
        assert code.status == status and code.source == source
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("same_code", [True, False])
async def test_concurrent_receipt_scan_serializes_capacity_and_duplicate(
    async_client: httpx.AsyncClient,
    same_code: bool,
) -> None:
    import asyncio

    from sqlalchemy import text

    from app.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as setup:
        await intake.set_line_actual_qty(setup, tenant, req, line, actual_qty=1)
    async with SessionLocal() as first, SessionLocal() as second:
        await svc._request(first, tenant, req, lock=True)
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))

        async def scan_second() -> str:
            try:
                result = await svc.attach_code(
                    second,
                    tenant,
                    req,
                    line_id=line,
                    cis_code=CIS if same_code else CIS.replace("SERIAL", "SECOND"),
                    actor_user_id=user,
                )
                return str(result["id"])
            except intake.InboundIntakeError as exc:
                await second.rollback()
                return exc.code

        pending = asyncio.create_task(scan_second())
        try:
            async with SessionLocal() as observer:
                async with asyncio.timeout(10):
                    while True:
                        waiting = await observer.scalar(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                            {"pid": second_pid},
                        )
                        await observer.rollback()
                        if waiting == "Lock":
                            break
                        assert not pending.done(), "Receipt scan bypassed request row lock"
                        await asyncio.sleep(0.01)
            result = await svc.attach_code(
                first, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
            )
            assert await asyncio.wait_for(pending, 10) == (
                result["id"] if same_code else "marking_quantity_exceeded"
            )
        finally:
            await first.rollback()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(MarkingCode.id))) == 1
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 1
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.parametrize("resolved", [None, {}, {"verified": None}, {"verified": 1}])
def test_green_requires_explicit_verified_true(resolved: Any) -> None:
    assert (
        svc.interpret_check(
            {"outerStatus": "INTRODUCED", "checkResult": True, "codeResolveData": resolved}
        )["status"]
        == "unavailable"
    )


@pytest.mark.asyncio
async def test_failed_job_is_persisted_when_receipt_was_deleted(
    async_client: httpx.AsyncClient,
) -> None:
    from app.models.background_job import BackgroundJob

    tenant, _, _, _ = await _setup(async_client)
    async with SessionLocal() as session:
        job = BackgroundJob(
            tenant_id=tenant,
            job_type=svc.JOB_TYPE,
            status="pending",
            payload_json={"request_id": str(uuid.uuid4())},
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    await svc.run_check_job(job_id)
    async with SessionLocal() as session:
        saved = await session.get(BackgroundJob, job_id)
        assert saved.status == "failed" and saved.error_message == "check_interrupted"
        assert saved.finished_at is not None


@pytest.mark.asyncio
async def test_automatic_check_preserves_finished_answers_manual_check_rechecks(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    calls = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs["json"]["code"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "outerStatus": "INTRODUCED",
                "checkResult": True,
                "codeResolveData": {"verified": True},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    async with SessionLocal() as session:
        await svc.attach_code(session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user)
        job_id = await svc.schedule_check(session, tenant, req)
    await svc.run_check_job(job_id)
    async with SessionLocal() as session:
        original = (await svc.list_codes(session, tenant, req))["items"][0]
        assert await svc.schedule_check(session, tenant, req) is None
        assert (await svc.list_codes(session, tenant, req))["items"][0] == original
        await svc.attach_code(
            session,
            tenant,
            req,
            line_id=line,
            cis_code=CIS.replace("SERIAL", "SECOND"),
            actor_user_id=user,
        )
        job_id = await svc.schedule_check(session, tenant, req)
    await svc.run_check_job(job_id)
    assert calls == [CIS, CIS.replace("SERIAL", "SECOND")]
    async with SessionLocal() as session:
        job_id = await svc.schedule_check(session, tenant, req, force=True)
    await svc.run_check_job(job_id)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_delete_wrong_input_releases_capacity_and_allows_correct_product(
    async_client: httpx.AsyncClient,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        await intake.set_line_actual_qty(session, tenant, req, line, actual_qty=1)
        wrong = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        await svc.delete_code(session, tenant, req, uuid.UUID(wrong["id"]))
        assert (await svc.list_codes(session, tenant, req))["items"] == []
        corrected = await svc.attach_code(
            session,
            tenant,
            req,
            line_id=line,
            cis_code=CIS.replace("SERIAL", "SECOND"),
            actor_user_id=user,
        )
        assert corrected["id"] != wrong["id"]
        product = await session.get(Product, uuid.UUID(corrected["product_id"]))
        other = Product(
            tenant_id=tenant, seller_id=product.seller_id, name="Right product", sku_code="RIGHT396"
        )
        session.add(other)
        await session.commit()
        other_line = await intake.add_or_increment_received_product(
            session, tenant, req, product_id=other.id, actual_qty=1
        )
        restored = await svc.attach_code(
            session, tenant, req, line_id=other_line.id, cis_code=CIS, actor_user_id=user
        )
        assert restored["product_id"] == str(other.id)
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_deletion_during_check_and_rescan_are_drained_without_stuck_job(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.background_job import BackgroundJob

    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        first = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        job_id = await svc.schedule_check(session, tenant, req)
    calls = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs["json"]["code"])
        if len(calls) == 1:
            async with SessionLocal() as session:
                await svc.delete_code(session, tenant, req, uuid.UUID(first["id"]))
                await svc.attach_code(
                    session,
                    tenant,
                    req,
                    line_id=line,
                    cis_code=CIS.replace("SERIAL", "SECOND"),
                    actor_user_id=user,
                )
                # The automatic posting trigger meets the currently running job.
                assert await svc.schedule_check(session, tenant, req) is None
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"outerStatus": "APPLIED", "checkResult": False},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await svc.run_check_job(job_id)
    async with SessionLocal() as session:
        assert (await session.get(BackgroundJob, job_id)).status == "done"
        items = (await svc.list_codes(session, tenant, req))["items"]
        assert len(items) == 1 and items[0]["cz_status"] == "problem"
        assert items[0]["cis_code"] == CIS.replace("SERIAL", "SECOND")
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("alteration", ["history", "printed", "shipped", "other_receipt", "posted"])
async def test_delete_preserves_existing_history_and_scope(
    async_client: httpx.AsyncClient,
    alteration: str,
) -> None:
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        item = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        code_id = uuid.UUID(item["id"])
        code = await session.get(MarkingCode, code_id)
        if alteration == "history":
            session.add(
                MarkingCodeEvent(
                    tenant_id=tenant,
                    seller_id=code.seller_id,
                    code_id=code_id,
                    event_type="applied",
                )
            )
        elif alteration in {"printed", "shipped"}:
            code.status = alteration
        elif alteration == "posted":
            (await svc._request(session, tenant, req)).status = "sorting"
        else:
            event = await session.scalar(
                select(MarkingCodeEvent).where(MarkingCodeEvent.code_id == code_id)
            )
            meta = json.loads(event.meta_json)
            meta["request_id"] = str(uuid.uuid4())
            event.meta_json = json.dumps(meta)
        await session.commit()
        with pytest.raises(intake.InboundIntakeError):
            await svc.delete_code(session, tenant, req, code_id)
        assert await session.get(MarkingCode, code_id) is not None
        with pytest.raises(intake.InboundIntakeError, match="request_not_found"):
            await svc.delete_code(session, uuid.uuid4(), req, code_id)


@pytest.mark.asyncio
async def test_printed_pool_inspection_and_removal_preserve_original_code_and_history(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    tenant, user, req, line_id = await _setup(async_client)
    async with SessionLocal() as session:
        line = await session.get(InboundIntakeLine, line_id)
        product = await session.get(Product, line.product_id)
        code = MarkingCode(
            tenant_id=tenant,
            seller_id=product.seller_id,
            product_id=None,
            cis_code=CIS,
            source="pool",
            status="printed",
            printed_at=datetime.now(UTC),
            label_artifact_pdf=b"existing-label",
        )
        session.add(code)
        await session.flush()
        code_id = code.id
        original = MarkingCodeEvent(
            tenant_id=tenant, seller_id=product.seller_id, code_id=code_id, event_type="printed"
        )
        session.add(original)
        await session.commit()
        original_id = original.id
        await svc.attach_code(
            session, tenant, req, line_id=line_id, cis_code=CIS, actor_user_id=user
        )
        assert code.source == "pool" and code.status == "printed" and code.product_id is None
        listed = await svc.list_codes(session, tenant, req)
        assert listed["items"][0]["product_id"] == str(product.id)
        job_id = await svc.schedule_check(session, tenant, req)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"outerStatus": "APPLIED", "checkResult": False},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await svc.run_check_job(job_id)
    async with SessionLocal() as session:
        listed = await svc.list_codes(session, tenant, req)
        assert listed["items"][0]["cz_status"] == "problem"
        sheet = load_workbook(io.BytesIO(svc.export_problems(listed["items"]))).active
        assert sheet.max_row == 2 and sheet["A2"].value == product.sku_code
        await svc.delete_code(session, tenant, req, code_id)
        code = await session.get(MarkingCode, code_id)
        assert code.status == "printed" and code.source == "pool" and code.product_id is None
        assert code.printed_at is not None and code.label_artifact_pdf == b"existing-label"
        assert await session.get(MarkingCodeEvent, original_id) is not None
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 1
        assert (await svc.list_codes(session, tenant, req))["items"] == []
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_delete_never_erases_code_referenced_by_fbs_order(
    async_client: httpx.AsyncClient,
) -> None:
    from app.models.fbs_order import FbsOrderMarking
    from app.models.inbound_intake import InboundIntakeRequest

    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        item = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        code = await session.get(MarkingCode, uuid.UUID(item["id"]))
        receipt = await session.get(InboundIntakeRequest, req)
        # A minimal persisted FBS order uses the same synthetic seller and warehouse.
        from datetime import UTC, datetime

        order = FbsOrder(
            tenant_id=tenant,
            seller_id=code.seller_id,
            warehouse_id=receipt.warehouse_id,
            product_id=code.product_id,
            wb_order_id=396990,
            wb_rid="396990",
            mapping_status="mapped",
            reserve_status="reserved",
            deadline_at=datetime.now(UTC),
            status="assembling",
            created_at_wb=datetime.now(UTC),
        )
        session.add(order)
        await session.flush()
        binding = FbsOrderMarking(
            tenant_id=tenant,
            order_id=order.id,
            kind="sgtin",
            value=CIS,
            marking_code_id=code.id,
            source="operator",
            meta_status="rejected",
        )
        session.add(binding)
        await session.commit()
        binding_id = binding.id
        with pytest.raises(intake.InboundIntakeError, match="marking_code_already_used"):
            await svc.delete_code(session, tenant, req, code.id)
        assert (await session.get(FbsOrderMarking, binding_id)).marking_code_id == code.id


@pytest.mark.asyncio
async def test_delete_api_is_authenticated_and_returns_no_content(
    async_client: httpx.AsyncClient,
) -> None:
    from app.models.user import User

    tenant, user_id, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        item = await svc.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user_id
        )
        email = (await session.get(User, user_id)).email
    url = f"/operations/inbound-intake-requests/{req}/marking-codes/{item['id']}"
    assert (await async_client.delete(url)).status_code == 401
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await async_client.delete(url, headers=headers)
    assert response.status_code == 204 and response.content == b""
    assert (await async_client.delete(url, headers=headers)).status_code == 404
