"""R18-R24 public withdrawal regression contract; real DB, HTTP/Redis I/O only."""

# ruff: noqa: F811 -- imported pytest boundary fixtures are injected by name.

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from test_withdrawal_ledger import INN
from test_withdrawal_orchestration import MOD, SIGNATURE, Emulator
from test_wms517_sales_contract import (
    build,
    fixture_order,
    sale,
    sales_http,  # noqa: F401
)
from test_wms517_sales_regressions import redis_boundary  # noqa: F401
from test_wms517_sales_report_singleflight_contract import (
    redis_ownership_io,  # noqa: F401 -- actual Redis ownership Lua fixture
)

from app.api.deps import get_current_user
from app.api.marking_withdrawals import withdrawal_products
from app.db.session import SessionLocal
from app.db.withdrawal_repository import WithdrawalError, current_items, get_operation, registry
from app.main import create_app
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.marking_withdrawal import WithdrawalItem, WithdrawalOperation
from app.models.user import User
from app.services.withdrawal_orchestration import (
    CertificateSelection,
    SignedWithdrawalDocument,
    accept_document_signatures,
    prepare_challenge,
    scoped_documents,
)
from app.services.withdrawal_recovery import claim_work, recover_one
from app.services.withdrawal_runtime import get_withdrawal_runtime
from app.services.withdrawal_service import create_operation, retry_operation
from app.services.withdrawal_submission import submit_one

pytestmark = pytest.mark.asyncio


async def add_same_scope_order(db, original, *, rid, serial, age_days=2):
    order = FbsOrder(
        tenant_id=original.tenant_id,
        seller_id=original.seller_id,
        warehouse_id=original.warehouse_id,
        product_id=original.product_id,
        supply_id=original.supply_id,
        marketplace="wb",
        wb_order_id=original.wb_order_id + 1,
        wb_rid=rid,
        status="in_delivery",
        wb_status="sorted",
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=datetime.now(UTC) - timedelta(days=age_days),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(order)
    await db.flush()
    marking = FbsOrderMarking(
        tenant_id=original.tenant_id,
        order_id=order.id,
        kind="sgtin",
        value=f"010460123456789021{serial}",
        source="external",
        meta_status="sent",
    )
    db.add(marking)
    await db.commit()
    return marking, order


async def test_mixed_return_after_create_preserves_selection_and_builds_only_healthy(
    db_session, sales_http, redis_boundary
):
    scope, a_mark, a_order, _ = await fixture_order(db_session, sales_http)
    b_mark, b_order = await add_same_scope_order(
        db_session,
        a_order,
        rid="partial-healthy-B",
        serial="healthyB",
    )
    a_sale = sale(a_order.wb_rid, identifier="S-A", price="12.34")
    b_sale = sale(b_order.wb_rid, identifier="S-B", price="56.78")
    sales_http.rows = [a_sale, b_sale]
    selected = [a_mark.id, b_mark.id]
    request_id = uuid.uuid4()
    operation = await create_operation(
        db_session,
        scope,
        row_ids=selected,
        client_request_id=request_id,
    )
    await db_session.commit()
    op_id, selection_hash = operation.id, operation.selection_hash
    original = {
        item.marking_id: (item.id, copy.deepcopy(item.preflight_evidence))
        for item in await current_items(db_session, scope, op_id)
    }
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        operation = await prepare_challenge(
            db_session,
            scope,
            op_id,
            CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=1)),
            runtime,
        )
        returned = sale(
            a_order.wb_rid,
            identifier="R-A",
            price="-12.34",
            changed="2026-10-05T15:00:00",
        )
        sales_http.rows = [a_sale, returned, b_sale]
        await build(db_session, scope, operation, runtime, emulator)
        async with SessionLocal() as reader:
            operation = await get_operation(reader, scope, op_id)
            documents = await scoped_documents(reader, scope, operation)
            items = {item.marking_id: item for item in await current_items(reader, scope, op_id)}
            assert len(documents) == 1, "returned A must not block healthy B's signable document"
            assert set(items) == set(selected), (
                "fresh sales must not silently shrink requested rows"
            )
            assert {key: item.id for key, item in items.items()} == {
                key: value[0] for key, value in original.items()
            }
            assert operation.selection_hash == selection_hash
            assert (operation.tenant_id, operation.seller_id, operation.client_request_id) == (
                scope.tenant_id,
                scope.seller_id,
                request_id,
            )
            assert operation.attempt == 1 and operation.workflow_lease_id is None
            assert items[a_mark.id].state == "failed" and items[a_mark.id].error
            assert items[a_mark.id].document_id is None
            # Preserve the old S foundation and retain the actual R reason, not
            # an unexplained dropped row or a guessed return for missing evidence.
            failed_history = json.dumps(
                {
                    "evidence": items[a_mark.id].preflight_evidence,
                    "error": items[a_mark.id].error,
                },
                sort_keys=True,
            )
            for actual in (a_order.wb_rid, "S-A", "R-A", "supplier/sales"):
                assert actual in failed_history
            assert items[b_mark.id].document_id == documents[0].id
            payload = json.loads(documents[0].exact_payload)
            assert len(payload["products"]) == 1
            assert payload["products"][0]["cis"] == items[b_mark.id].provider_cis
            assert payload["products"][0]["product_cost"] == 5678
            assert a_mark.value.encode() not in documents[0].exact_payload
            assert (
                documents[0].payload_sha256
                == hashlib.sha256(documents[0].exact_payload).hexdigest()
            )
            assert documents[0].state == "pending_signature"
            assert await reader.scalar(select(func.count(WithdrawalOperation.id))) == 1
            assert await reader.scalar(select(func.count(WithdrawalItem.id))) == 2
            claims = list(
                await reader.scalars(
                    select(WithdrawalItem).where(
                        WithdrawalItem.holds_claim.is_(True),
                    )
                )
            )
            assert len({item.provider_cis for item in claims}) == len(claims)
            assert items[b_mark.id].holds_claim
            doc_id, digest = documents[0].id, documents[0].payload_sha256
            error_before = copy.deepcopy(items[a_mark.id].error)
        assert not any(path.endswith("/lk/documents/create") for path in emulator.calls)
        await accept_document_signatures(
            db_session,
            scope,
            op_id,
            [SignedWithdrawalDocument(doc_id, digest, "fixture-thumb", SIGNATURE)],
            runtime,
        )
        assert await submit_one(SessionLocal, runtime)
        assert not await submit_one(SessionLocal, runtime)
        async with SessionLocal() as worker:
            work = await claim_work(worker, now=datetime.now(UTC) + timedelta(seconds=3))
        assert work is not None
        await recover_one(SessionLocal, work, runtime.client(INN, "sandbox"))
        async with SessionLocal() as reader:
            operation = await get_operation(reader, scope, op_id)
            items = {item.marking_id: item for item in await current_items(reader, scope, op_id)}
            assert operation.state == "partial_failed"
            assert items[a_mark.id].state == "failed" and items[a_mark.id].error == error_before
            assert items[a_mark.id].document_id is None
            assert items[b_mark.id].state == "succeeded"
            resumed = await create_operation(
                reader,
                scope,
                row_ids=selected,
                client_request_id=request_id,
            )
            assert resumed.id == op_id and resumed.selection_hash == selection_hash
            assert await reader.scalar(select(func.count(WithdrawalOperation.id))) == 1
        assert sum(path.endswith("/lk/documents/create") for path in emulator.calls) == 1


@pytest.mark.parametrize("phase", ["create", "retry", "build"])
async def test_old_missing_history_does_not_block_selected_current_sale(
    db_session, sales_http, redis_boundary, phase
):
    scope, current_mark, current_order, _ = await fixture_order(db_session, sales_http)
    old_mark, old_order = await add_same_scope_order(
        db_session,
        current_order,
        rid="outside-guaranteed-history",
        serial="oldhistory",
        age_days=100,
    )
    # The complete empty archive proves the old sale is absent; the current sale remains usable.
    sales_http.rows = [sale(current_order.wb_rid, identifier="S-current", price="7.89")]
    sales_http.finance_missing_archive = True
    rows, total = await registry(db_session, scope)
    assert total == 1 and rows[0]["row_id"] == current_mark.id
    products = await withdrawal_products(db_session, scope, search=None, limit=100)
    assert [row["id"] for row in products] == [current_order.product_id]
    with pytest.raises(WithdrawalError, match="withdrawal_rows_not_found"):
        await create_operation(
            db_session,
            scope,
            row_ids=[old_mark.id],
            client_request_id=uuid.uuid4(),
        )
    operation = await create_operation(
        db_session,
        scope,
        row_ids=[current_mark.id],
        client_request_id=uuid.uuid4(),
    )
    await db_session.commit()
    op_id = operation.id
    if phase == "retry":
        item = (await current_items(db_session, scope, op_id))[0]
        item.state = "failed"
        item.error = {"source": "crpt", "code": "definite-terminal-reject"}
        operation.state = "failed"
        await db_session.commit()
        operation = await retry_operation(db_session, scope, op_id, expected_attempt=1)
        await db_session.commit()
        assert operation.attempt == 2
    if phase == "build":
        emulator = Emulator([MOD])
        async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
            runtime = emulator.runtime(http)
            operation = await prepare_challenge(
                db_session,
                scope,
                op_id,
                CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=1)),
                runtime,
            )
            await build(db_session, scope, operation, runtime, emulator)
    async with SessionLocal() as reader:
        operation = await get_operation(reader, scope, op_id)
        items = await current_items(reader, scope, op_id)
        assert len(items) == 1 and items[0].marking_id == current_mark.id
        assert items[0].product_cost == 789 and items[0].state == "pending"
        assert items[0].preflight_evidence["wb_sale"]["complete"] is True
        assert items[0].preflight_evidence["wb_sale"]["srid"] == current_order.wb_rid
        if phase == "build":
            docs = await scoped_documents(reader, scope, operation)
            assert len(docs) == 1
            assert json.loads(docs[0].exact_payload)["products"][0]["product_cost"] == 789
        assert await reader.scalar(select(func.count(WithdrawalOperation.id))) == 1


@pytest.mark.parametrize(
    "price",
    [
        "1.0000000000000000000000000000000001",
        "1e999999999999999999",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "0",
        "-0.01",
        "1000000000000000.00",
    ],
)
async def test_extreme_finished_price_is_per_item_error_and_healthy_continues(
    db_session, sales_http, redis_boundary, price
):
    scope, bad_mark, bad_order, _ = await fixture_order(db_session, sales_http)
    healthy_mark, healthy_order = await add_same_scope_order(
        db_session,
        bad_order,
        rid="decimal-healthy-B",
        serial="decimalB",
    )
    sales_http.rows = [
        sale(bad_order.wb_rid, identifier="S-bad", price=price),
        sale(healthy_order.wb_rid, identifier="S-good", price="12.34"),
    ]
    operation = await create_operation(
        db_session,
        scope,
        row_ids=[bad_mark.id, healthy_mark.id],
        client_request_id=uuid.uuid4(),
    )
    await db_session.commit()
    op_id = operation.id
    async with SessionLocal() as reader:
        items = {item.marking_id: item for item in await current_items(reader, scope, op_id)}
        assert items[bad_mark.id].state == "failed", "fractional kopeks must not round to 100"
        assert items[bad_mark.id].product_cost is None
        assert items[bad_mark.id].error["code"] == "invalid_sale_price"
        assert items[bad_mark.id].preflight_evidence["wb_sale"]["finishedPrice"] == price
        assert (
            items[healthy_mark.id].state == "pending"
            and items[healthy_mark.id].product_cost == 1234
        )
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        operation = await prepare_challenge(
            db_session,
            scope,
            op_id,
            CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=1)),
            runtime,
        )
        await build(db_session, scope, operation, runtime, emulator)
    async with SessionLocal() as reader:
        operation = await get_operation(reader, scope, op_id)
        docs = await scoped_documents(reader, scope, operation)
        assert len(docs) == 1
        payload = json.loads(docs[0].exact_payload)
        assert len(payload["products"]) == 1
        assert payload["products"][0]["product_cost"] == 1234
        assert bad_mark.value.encode() not in docs[0].exact_payload
        assert operation.workflow_lease_id is None


@pytest.mark.parametrize(
    "price,kopeks",
    [
        ("0.01", 1),
        ("999999999999999.99", 99999999999999999),
        ("1.0000000000000000000000000000000000", 100),
    ],
)
async def test_exact_valid_finished_price_boundaries(
    db_session, sales_http, redis_boundary, price, kopeks
):
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = [sale(order.wb_rid, price=price)]
    operation = await create_operation(
        db_session,
        scope,
        row_ids=[marking.id],
        client_request_id=uuid.uuid4(),
    )
    await db_session.commit()
    async with SessionLocal() as reader:
        items = await current_items(reader, scope, operation.id)
        assert len(items) == 1 and items[0].state == "pending"
        assert items[0].product_cost == kopeks
        assert items[0].preflight_evidence["wb_sale"]["finishedPrice"] == price


@pytest.mark.parametrize("price", ["1e999999999999999999", "sNaN"])
async def test_api_extreme_price_returns_item_error_without_http_500(
    db_session, sales_http, redis_boundary, price
):
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = [sale(order.wb_rid, price=price)]
    app = create_app()
    user = await db_session.get(User, scope.user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as vendor:
        runtime = emulator.runtime(vendor)
        app.dependency_overrides[get_withdrawal_runtime] = lambda: runtime
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/operations/marking-codes/self/withdrawals/operations",
                json={"row_ids": [str(marking.id)], "client_request_id": str(uuid.uuid4())},
            )
    assert response.status_code == 200, "bad sale price must be a per-item result, never HTTP 500"
    payload = response.json()
    assert payload["state"] == "failed" and len(payload["items"]) == 1
    assert payload["items"][0]["error"]["code"] == "invalid_sale_price"
    assert payload["documents"] == []
    assert not emulator.calls
