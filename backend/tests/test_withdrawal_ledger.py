"""WMS-517 emulator-only ledger acceptance; never calls a live CRPT endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.marking_withdrawals import _scope
from app.db.session import SessionLocal, engine
from app.db.withdrawal_repository import (
    WithdrawalError,
    WithdrawalScope,
    current_items,
    get_operation,
    registry,
)
from app.main import create_app
from app.models.base import Base
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_supply import FbsSupply
from app.models.marking_withdrawal import (
    WithdrawalDocument,
    WithdrawalItem,
    WithdrawalObservation,
    WithdrawalOperation,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.integration_fernet import encrypt_secret
from app.services.true_api_withdrawal import (
    CreateOutcome,
    DocumentInfo,
    Environment,
    TrueApiConfig,
    TrueApiError,
    TrueApiWithdrawalClient,
)
from app.services.wb_order_price_service import capture_wb_price_snapshot
from app.services.withdrawal_recovery import (
    apply_recovery,
    body_matches,
    claim_work,
    poll_delay,
    purge_expired_tokens,
    record_create_result,
    recover_one,
)
from app.services.withdrawal_service import create_operation, retry_operation

INN = "7701234567"


async def seed(
    session: AsyncSession,
) -> tuple[WithdrawalScope, FbsOrderMarking, FbsOrder, FbsSupply]:
    tenant = Tenant(name="withdrawal", slug=uuid.uuid4().hex)
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(tenant_id=tenant.id, code="wh", name="Warehouse")
    session.add_all([seller, warehouse])
    await session.flush()
    user = User(
        tenant_id=tenant.id, seller_id=seller.id, role="fulfillment_seller", password_hash="test"
    )
    product = Product(tenant_id=tenant.id, seller_id=seller.id, name="Long product", sku_code="SKU")
    supply = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        wb_supply_id=uuid.uuid4().hex,
        name="Supply",
        delivery_type="warehouse_sc",
        status="in_delivery",
        delivered_at=datetime(2026, 9, 22, 21, 30, tzinfo=UTC),
    )
    session.add_all([user, product, supply])
    await session.flush()
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        wb_order_id=uuid.uuid4().int % 1_000_000_000,
        supply_id=supply.id,
        product_id=product.id,
        marketplace="wb",
        status="in_delivery",
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
        mapping_status="mapped",
        reserve_status="reserved",
    )
    session.add(order)
    await session.flush()
    marking = FbsOrderMarking(
        tenant_id=tenant.id,
        order_id=order.id,
        kind="sgtin",
        value="010460123456789021test",
        source="external",
        meta_status="sent",
    )
    session.add(marking)
    await session.flush()
    await capture_wb_price_snapshot(
        session,
        tenant_id=tenant.id,
        seller_id=seller.id,
        order_id=order.id,
        row={"finalPrice": 99999999999999999, "currencyCode": 643},
    )
    await session.commit()
    return WithdrawalScope(tenant.id, seller.id, user.id), marking, order, supply


async def operation(session: AsyncSession) -> tuple[WithdrawalScope, WithdrawalOperation]:
    scope, marking, _, _ = await seed(session)
    op = await create_operation(
        session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    await session.commit()
    return scope, op


async def document(
    session: AsyncSession,
    *,
    state: str = "submitted",
    known_id: bool = True,
) -> tuple[WithdrawalScope, WithdrawalOperation, WithdrawalDocument]:
    scope, op = await operation(session)
    op.participant_inn = INN
    op.certificate_thumbprint = "public-thumbprint"
    op.token_enc = encrypt_secret(str(uuid.uuid4()))
    op.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
    op.state = state
    item = (await current_items(session, scope, op.id))[0]
    payload = json.dumps(
        {
            "inn": INN,
            "action": "DISTANCE",
            "action_date": "2026-09-23",
            "products": [{"cis": item.cis, "product_cost": int(item.product_cost)}],
        },
        separators=(",", ":"),
    ).encode()
    doc = WithdrawalDocument(
        operation_id=op.id,
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        attempt=1,
        environment="sandbox",
        pg="lp",
        participant_inn=INN,
        exact_payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        signature="Zml4dHVyZQ==",
        certificate_thumbprint=op.certificate_thumbprint,
        state=state,
        gis_document_id=str(uuid.uuid4()) if known_id else None,
        request_started_at=datetime.now(UTC) - timedelta(seconds=10),
        next_poll_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    session.add(doc)
    await session.flush()
    item.document_id = doc.id
    await session.commit()
    return scope, op, doc


def info(doc: WithdrawalDocument, status: str, external_id: str | None = None) -> DocumentInfo:
    raw = {
        "number": external_id or doc.gis_document_id,
        "productGroup": [doc.pg],
        "type": "LK_RECEIPT",
        "status": status,
        "body": json.loads(doc.exact_payload),
        "errors": [{"code": "E42", "error": "Фактическая ошибка документа"}],
        "commonErrors": ["Ошибка общая"],
    }
    return DocumentInfo(raw["number"], status, raw["body"], raw["errors"], raw["commonErrors"], raw)


class TestLimiter:
    __test__ = False

    async def acquire(self, environment: Environment, participant_inn: str) -> None:
        pass


async def test_registry_server_scope_and_moscow_date(db_session: AsyncSession) -> None:
    scope, marking, order, supply = await seed(db_session)
    rows, total = await registry(
        db_session, scope, date_from=date(2026, 9, 23), date_to=date(2026, 9, 23), search="SKU"
    )
    assert total == 1 and rows[0]["row_id"] == marking.id
    assert rows[0]["status"] == "not_withdrawn"
    assert (await registry(db_session, scope, date_to=date(2026, 9, 22)))[1] == 0
    wrong = WithdrawalScope(scope.tenant_id, uuid.uuid4(), scope.user_id)
    assert (await registry(db_session, wrong))[1] == 0
    # Pool/scanned provenance never becomes a filter.
    marking.source = "pool"
    await db_session.flush()
    assert (await registry(db_session, scope))[1] == 1
    for field, value in (
        ("status", "cancelled"),
        ("pick_status", "returned"),
        ("marketplace", "ozon"),
    ):
        previous = getattr(order, field)
        setattr(order, field, value)
        await db_session.flush()
        assert (await registry(db_session, scope))[1] == 0
        setattr(order, field, previous)
    supply.delivered_at = None
    await db_session.flush()
    assert (await registry(db_session, scope))[1] == 0


async def test_create_reload_and_overlap_resume_without_duplicate(db_session: AsyncSession) -> None:
    scope, marking, _, _ = await seed(db_session)
    request_id = uuid.uuid4()
    op = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=request_id
    )
    await db_session.commit()
    assert (
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=request_id
        )
    ).id == op.id
    assert (
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
    ).id == op.id
    assert (await get_operation(db_session, scope, op.id)).id == op.id
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalOperation)) == 1
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalItem)) == 1
    item = (await current_items(db_session, scope, op.id))[0]
    assert item.cis == marking.value and item.product_cost == 99999999999999999
    assert item.price_snapshot_id is not None
    with pytest.raises(WithdrawalError, match="idempotency_selection_mismatch"):
        await create_operation(
            db_session, scope, row_ids=[uuid.uuid4()], client_request_id=request_id
        )
    with pytest.raises(WithdrawalError, match="withdrawal_not_found"):
        await get_operation(
            db_session, WithdrawalScope(scope.tenant_id, uuid.uuid4(), scope.user_id), op.id
        )


async def test_unshipped_and_forged_selection_is_rejected(db_session: AsyncSession) -> None:
    scope, marking, _, supply = await seed(db_session)
    supply.delivered_at = None
    await db_session.commit()
    with pytest.raises(WithdrawalError, match="withdrawal_rows_not_found"):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )


async def test_registry_missing_price_is_an_actual_local_error(db_session: AsyncSession) -> None:
    scope, _, order, _ = await seed(db_session)
    await capture_wb_price_snapshot(
        db_session,
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        order_id=order.id,
        row={"currencyCode": 840, "finalPrice": 100},
    )
    rows, _ = await registry(db_session, scope)
    assert rows[0]["status"] == "error"
    assert rows[0]["error"]["code"] == "missing_rub_final_price"


async def test_partial_success_survives_neighbour_failure_and_retry(
    db_session: AsyncSession,
) -> None:
    scope, op, successful = await document(db_session)
    original = (await current_items(db_session, scope, op.id))[0]
    # Add a second document/marking to the same test operation, representing a
    # different CRPT product group. Production document building remains gated.
    marking = FbsOrderMarking(
        tenant_id=scope.tenant_id,
        order_id=original.order_id,
        kind="sgtin",
        value="010460123456789021second",
        source="external",
        meta_status="sent",
    )
    db_session.add(marking)
    await db_session.flush()
    item_values = {
        column.name: getattr(original, column.name)
        for column in WithdrawalItem.__table__.columns
        if column.name not in {"id", "created_at", "marking_id", "cis", "document_id"}
    }
    second_item = WithdrawalItem(**item_values, marking_id=marking.id, cis=marking.value)
    payload = json.loads(successful.exact_payload)
    payload["products"][0]["cis"] = marking.value
    exact = json.dumps(payload).encode()
    doc_values = {
        column.name: getattr(successful, column.name)
        for column in WithdrawalDocument.__table__.columns
        if column.name
        not in {"id", "created_at", "gis_document_id", "pg", "exact_payload", "payload_sha256"}
    }
    failed = WithdrawalDocument(
        **doc_values,
        gis_document_id=str(uuid.uuid4()),
        pg="shoes",
        exact_payload=exact,
        payload_sha256=hashlib.sha256(exact).hexdigest(),
    )
    db_session.add(failed)
    await db_session.flush()
    second_item.document_id = failed.id
    db_session.add(second_item)
    await db_session.commit()
    for _ in range(2):
        work = await claim_work(db_session)
        assert work is not None
        doc = successful if work.document_id == successful.id else failed
        await apply_recovery(
            db_session,
            work,
            info=info(
                doc,
                "CHECKED_OK" if doc.id == successful.id else "CHECKED_NOT_OK",
            ),
        )
    await db_session.refresh(op)
    assert op.state == "partial_failed"
    await retry_operation(db_session, scope, op.id, expected_attempt=1)
    await db_session.commit()
    assert op.state == "created" and op.attempt == 2
    await db_session.refresh(successful)
    await db_session.refresh(failed)
    assert successful.state == "succeeded" and failed.state == "failed"
    items = await current_items(db_session, scope, op.id)
    assert {(item.marking_id, item.state, item.attempt) for item in items} == {
        (original.marking_id, "succeeded", 1),
        (marking.id, "pending", 2),
    }


async def test_possible_duplicate_incident_cannot_disappear_on_later_read(
    db_session: AsyncSession,
) -> None:
    _, _, doc = await document(db_session, state="reconciling", known_id=False)
    first = await claim_work(db_session)
    assert first is not None
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    await apply_recovery(db_session, first, incident="possible_duplicate", reconciliation_ids=ids)
    second = await claim_work(db_session, now=datetime.now(UTC) + timedelta(minutes=1))
    assert second is not None
    await apply_recovery(
        db_session, second, info=info(doc, "CHECKED_OK", ids[0]), reconciliation_ids=[ids[0]]
    )
    await db_session.refresh(doc)
    assert doc.state == "reconciling" and doc.incident == "possible_duplicate"
    assert doc.gis_document_id is None and set(doc.reconciliation_ids) == set(ids)


async def test_retry_retains_old_price_error_and_new_attempt(db_session: AsyncSession) -> None:
    scope, marking, order, _ = await seed(db_session)
    await capture_wb_price_snapshot(
        db_session,
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        order_id=order.id,
        row={"finalPrice": None, "currencyCode": 643},
    )
    op = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    await db_session.commit()
    old = (await current_items(db_session, scope, op.id))[0]
    assert op.state == "failed" and old.error["code"] == "missing_rub_final_price"
    await capture_wb_price_snapshot(
        db_session,
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        order_id=order.id,
        row={"finalPrice": 12345, "currencyCode": 643},
    )
    await db_session.commit()
    await retry_operation(db_session, scope, op.id, expected_attempt=1)
    await db_session.commit()
    new = (await current_items(db_session, scope, op.id))[0]
    assert new.attempt == 2 and new.product_cost == 12345 and new.document_id is None
    assert old.state == "failed" and old.error["code"] == "missing_rub_final_price"
    assert not old.holds_claim and old.price_snapshot_id != new.price_snapshot_id
    assert (await retry_operation(db_session, scope, op.id, expected_attempt=1)).attempt == 2


@pytest.mark.parametrize(
    "status,expected",
    [
        ("CHECKED_OK", "succeeded"),
        ("CHECKED_NOT_OK", "failed"),
        ("PARSE_ERROR", "failed"),
        ("PROCESSING_ERROR", "failed"),
        ("IN_PROGRESS", "submitted"),
        ("WAIT_FOR_CONTINUATION", "submitted"),
        ("UNDEFINED", "reconciling"),
        ("ACCEPTED", "reconciling"),
        ("NEW_STATUS", "reconciling"),
    ],
)
async def test_only_checked_ok_is_success_and_errors_survive_reload(
    db_session: AsyncSession,
    status: str,
    expected: str,
) -> None:
    scope, op, doc = await document(db_session)
    work = await claim_work(db_session)
    assert work is not None
    result = info(doc, status)
    await apply_recovery(db_session, work, info=result)
    await db_session.refresh(doc)
    item = (await current_items(db_session, scope, op.id))[0]
    assert doc.state == expected
    assert item.state == (expected if expected in {"succeeded", "failed"} else "pending")
    if expected == "failed":
        assert item.error["scope"] == "document" and item.error["errors"] == result.errors
        assert item.error["commonErrors"] == result.common_errors
    if expected == "reconciling":
        attempt = op.attempt
        assert (
            await retry_operation(db_session, scope, op.id, expected_attempt=attempt)
        ).attempt == attempt
        assert item.error is None
    observations = list(await db_session.scalars(select(WithdrawalObservation)))
    assert len(observations) == 1 and observations[0].status == status


@pytest.mark.parametrize("http_status", [400, 401, 403, 422, 500, 503, None])
async def test_create_reject_vs_uncertain_keeps_exact_body(
    db_session: AsyncSession,
    http_status: int | None,
) -> None:
    scope, op, doc = await document(db_session, state="submitting", known_id=False)
    definite = http_status in {400, 401, 403, 422}
    raw = b'{"errors":[{"code":"original","message":"provider response"}]}'
    error = TrueApiError(
        "failure",
        status_code=http_status,
        response_body=raw,
        create_outcome=CreateOutcome.DEFINITE_REJECT if definite else CreateOutcome.UNCERTAIN,
    )
    await record_create_result(
        db_session, scope, operation_id=op.id, document_id=doc.id, error=error
    )
    await db_session.refresh(doc)
    assert doc.state == ("failed" if definite else "reconciling")
    assert doc.response_body == raw and doc.http_status == http_status
    if not definite:
        assert (await retry_operation(db_session, scope, op.id, expected_attempt=1)).attempt == 1


@pytest.mark.parametrize("matches", [0, 1, 2])
async def test_lost_create_read_reconciliation_never_posts(
    db_session: AsyncSession,
    matches: int,
) -> None:
    scope, op, doc = await document(db_session, state="submitting", known_id=False)
    ids = [str(uuid.uuid4()) for _ in range(matches)]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.method == "GET"
        if request.url.path.endswith("/doc/list"):
            assert request.url.params["senderInn"] == INN
            assert request.url.params["documentType"] == "LK_RECEIPT"
            return httpx.Response(
                200, json={"results": [{"number": i} for i in ids], "nextPage": False}
            )
        external = request.url.path.split("/")[-2]
        return httpx.Response(200, json=[info(doc, "CHECKED_OK", external).raw])

    work = await claim_work(db_session)
    assert work is not None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TrueApiWithdrawalClient(
            http, TrueApiConfig(Environment.SANDBOX), TestLimiter(), INN
        )
        await recover_one(SessionLocal, work, client)
    await db_session.refresh(doc)
    await db_session.refresh(op)
    assert calls and set(calls) == {"GET"}
    assert doc.state == ("succeeded" if matches == 1 else "reconciling")
    assert doc.gis_document_id == (ids[0] if matches == 1 else None)
    assert doc.incident == ("possible_duplicate" if matches == 2 else None)
    if matches != 1:
        assert (await retry_operation(db_session, scope, op.id, expected_attempt=1)).attempt == 1


async def test_lease_fencing_and_restart_recovery(db_session: AsyncSession) -> None:
    _, _, doc = await document(db_session)
    first = await claim_work(db_session)
    assert first is not None and await claim_work(db_session) is None
    second = await claim_work(db_session, now=datetime.now(UTC) + timedelta(minutes=6))
    assert second is not None and second.lease_id != first.lease_id
    assert not await apply_recovery(db_session, first, info=info(doc, "CHECKED_NOT_OK"))
    assert await apply_recovery(db_session, second, info=info(doc, "CHECKED_OK"))
    await db_session.refresh(doc)
    assert doc.state == "succeeded"


async def test_token_expiry_invalidates_secret_without_terminal_failure(
    db_session: AsyncSession,
) -> None:
    _, op, doc = await document(db_session)
    op.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    await purge_expired_tokens(db_session)
    await db_session.refresh(op)
    assert op.token_enc is None
    work = await claim_work(db_session)
    assert work is not None

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Expired auth must not reach transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        client = TrueApiWithdrawalClient(
            http, TrueApiConfig(Environment.SANDBOX), TestLimiter(), INN
        )
        await recover_one(SessionLocal, work, client)
    await db_session.refresh(doc)
    assert doc.state == "reconciling" and doc.incident == "auth_required"


def test_semantic_reconciliation_requires_exact_cis_cost_and_mod() -> None:
    body = {
        "action": "DISTANCE",
        "inn": INN,
        "action_date": "2026-09-23",
        "fias_id": "fias",
        "products": [{"cis": "code", "product_cost": 100}],
    }
    exact = json.dumps(body).encode()
    assert body_matches(exact, body)
    for changed in (
        {**body, "fias_id": "wrong"},
        {**body, "inn": "1111111111"},
        {**body, "products": [{"cis": "code", "product_cost": 101}]},
        {**body, "products": [{"cis": "other", "product_cost": 100}]},
        {**body, "products": body["products"] * 2},
    ):
        assert not body_matches(exact, changed)
    assert [poll_delay(i) for i in range(7)] == [2, 5, 10, 30, 60, 60, 60]


async def test_payload_cannot_be_replaced(db_session: AsyncSession) -> None:
    _, _, doc = await document(db_session)
    doc.exact_payload = b"changed"
    with pytest.raises(ValueError, match="withdrawal_document_is_immutable"):
        await db_session.flush()
    await db_session.rollback()


async def test_database_prevents_second_claim(db_session: AsyncSession) -> None:
    scope, op = await operation(db_session)
    old = (await current_items(db_session, scope, op.id))[0]
    values = {
        column.name: getattr(old, column.name)
        for column in WithdrawalItem.__table__.columns
        if column.name not in {"id", "created_at", "attempt"}
    }
    db_session.add(WithdrawalItem(**values, attempt=2))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_database_rejects_cross_seller_document_item_link(db_session: AsyncSession) -> None:
    if engine.dialect.name == "sqlite":
        await db_session.execute(text("PRAGMA foreign_keys=ON"))
    _, _, doc = await document(db_session)
    other_scope, other_op = await operation(db_session)
    item = (await current_items(db_session, other_scope, other_op.id))[0]
    item.document_id = doc.id
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_api_gates_signatures_scopes_and_never_returns_tokens(
    db_session: AsyncSession,
) -> None:
    scope, marking, _, _ = await seed(db_session)
    app = create_app()
    app.dependency_overrides[_scope] = lambda: scope
    prefix = "/operations/marking-codes/self/withdrawals"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(
            prefix + "/operations",
            json={
                "row_ids": [str(marking.id)],
                "client_request_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["integration_gate"] == "B3_AUTH_PROFILE_UNCONFIRMED"
        assert data["items"][0]["status"] == "not_withdrawn"
        operation_id = data["operation_id"]
        response = await http.post(
            prefix + f"/operations/{operation_id}/auth-signature",
            json={"thumbprint": "cert", "signature": "ZmFrZQ=="},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "B3_AUTH_PROFILE_UNCONFIRMED"
        response = await http.post(
            prefix + "/operations",
            json={
                "row_ids": [str(marking.id)],
                "client_request_id": str(uuid.uuid4()),
                "cis": "forged",
            },
        )
        assert response.status_code == 422
        assert (await http.get(prefix + f"/operations/{uuid.uuid4()}")).status_code == 404
        app.dependency_overrides[_scope] = lambda: WithdrawalScope(
            scope.tenant_id,
            uuid.uuid4(),
            scope.user_id,
        )
        assert (await http.get(prefix + f"/operations/{operation_id}")).status_code == 404
        assert all(
            key not in json.dumps(data) for key in ("token_enc", "auth_challenge", "signature")
        )
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalDocument)) == 0


async def test_self_boundary_enforces_seller_role_and_honest_sign_permission(
    db_session: AsyncSession,
) -> None:
    scope, _, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    assert user is not None
    assert await _scope(db_session, user, scope.seller_id) == scope
    db_session.add(SellerStaffPermissions(user_id=user.id, can_honest_sign=False))
    await db_session.flush()
    with pytest.raises(HTTPException) as denied:
        await _scope(db_session, user, scope.seller_id)
    assert denied.value.status_code == 403
    user.role = "fulfillment_admin"
    with pytest.raises(HTTPException) as wrong_role:
        await _scope(db_session, user, scope.seller_id)
    assert wrong_role.value.status_code == 403


@pytest.mark.parametrize("action", ["response_body", "incident", "reconciliation_ids", "delete"])
async def test_observation_orm_rejects_update_and_delete(
    db_session: AsyncSession,
    action: str,
) -> None:
    _, _, doc = await document(db_session)
    observation = WithdrawalObservation(
        document_id=doc.id,
        response_body=b"original response",
        incident="possible_duplicate",
        reconciliation_ids=["original-document"],
    )
    db_session.add(observation)
    await db_session.commit()
    observation_id = observation.id
    if action == "delete":
        await db_session.delete(observation)
    elif action == "response_body":
        observation.response_body = b"replacement response"
    elif action == "incident":
        observation.incident = "replacement incident"
    else:
        observation.reconciliation_ids = ["replacement-document"]
    with pytest.raises(ValueError, match="withdrawal_observation_is_immutable"):
        await db_session.flush()
    await db_session.rollback()
    persisted = await db_session.get(WithdrawalObservation, observation_id)
    assert persisted is not None
    assert persisted.response_body == b"original response"
    assert persisted.incident == "possible_duplicate"
    assert persisted.reconciliation_ids == ["original-document"]


def test_migration_upgrade_and_downgrade_match_ledger_schema() -> None:
    path = Path(__file__).parents[1] / "alembic/versions/20260923_0518_withdrawal_ledger.py"
    spec = importlib.util.spec_from_file_location("withdrawal_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "20260923_0517"
    names = {
        "withdrawal_operations",
        "withdrawal_documents",
        "withdrawal_items",
        "withdrawal_observations",
    }
    local_engine = create_engine("sqlite://")
    with local_engine.begin() as connection:
        Base.metadata.create_all(
            connection,
            tables=[table for table in Base.metadata.sorted_tables if table.name not in names],
        )
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            inspector = inspect(connection)
            for name in names:
                assert {column["name"] for column in inspector.get_columns(name)} == set(
                    Base.metadata.tables[name].columns.keys()
                )
            constraints = inspector.get_check_constraints("withdrawal_documents")
            assert "ck_withdrawal_recoverable" in {value["name"] for value in constraints}
            # Exercise database triggers directly, bypassing ORM events. This
            # isolated migration schema leaves FK checks off: document linkage
            # is covered separately by test_database_rejects_cross_seller_*.
            observation_id = uuid.uuid4()
            connection.execute(
                WithdrawalObservation.__table__.insert().values(
                    id=observation_id,
                    document_id=uuid.uuid4(),
                    created_at=datetime.now(UTC),
                    response_body=b"original response",
                    incident="possible_duplicate",
                    reconciliation_ids=["original-document"],
                )
            )
            for statement in (
                "UPDATE withdrawal_observations SET response_body = X'00'",
                "UPDATE withdrawal_observations SET incident = 'replaced'",
                "UPDATE withdrawal_observations SET reconciliation_ids = '[]'",
                "DELETE FROM withdrawal_observations",
            ):
                with (
                    pytest.raises(IntegrityError, match="withdrawal_observation_is_immutable"),
                    connection.begin_nested(),
                ):
                    connection.execute(text(statement))
                persisted = connection.execute(
                    select(
                        WithdrawalObservation.response_body,
                        WithdrawalObservation.incident,
                        WithdrawalObservation.reconciliation_ids,
                    ).where(WithdrawalObservation.id == observation_id)
                ).one()
                assert tuple(persisted) == (
                    b"original response",
                    "possible_duplicate",
                    ["original-document"],
                )
            module.downgrade()
            assert not names.intersection(inspect(connection).get_table_names())
            assert not connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND name LIKE 'withdrawal_observation_%'"
                )
            ).all()
    local_engine.dispose()


def test_postgresql_migration_renders_audit_guards_and_cleanup() -> None:
    # SQL generation only; execution on PostgreSQL is still an explicit gate.
    path = Path(__file__).parents[1] / "alembic/versions/20260923_0518_withdrawal_ledger.py"
    spec = importlib.util.spec_from_file_location("withdrawal_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        module.upgrade()
        module.downgrade()
    sql = output.getvalue()
    assert "BEFORE UPDATE OR DELETE ON withdrawal_observations" in sql
    assert "RAISE EXCEPTION 'withdrawal_observation_is_immutable'" in sql
    assert "DROP TRIGGER withdrawal_observation_immutable ON withdrawal_observations" in sql
    assert "DROP FUNCTION protect_withdrawal_observation()" in sql


@pytest.mark.postgresql_concurrency
@pytest.mark.parametrize("same_request", [True, False])
async def test_postgresql_concurrent_clicks_share_one_operation(
    db_session: AsyncSession,
    same_request: bool,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires explicitly isolated WMS_TEST_DATABASE_URL PostgreSQL")
    scope, marking, _, _ = await seed(db_session)
    request_id = uuid.uuid4()
    async with SessionLocal() as first, SessionLocal() as second:
        op = await create_operation(
            first, scope, row_ids=[marking.id], client_request_id=request_id
        )
        waiter = asyncio.create_task(
            create_operation(
                second,
                scope,
                row_ids=[marking.id],
                client_request_id=request_id if same_request else uuid.uuid4(),
            )
        )
        await asyncio.sleep(0.05)
        assert not waiter.done()
        await first.commit()
        result = await asyncio.wait_for(waiter, 5)
        await second.commit()
        assert result.id == op.id
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalOperation)) == 1
