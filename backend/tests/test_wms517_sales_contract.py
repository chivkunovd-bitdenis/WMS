"""WMS-517 SC1-SC12: real withdrawal entrypoints, isolated DB, HTTP-only fixtures.

No production credentials, external signing, or live network calls. The fixture
does not emulate sale selection: production code must parse the actual WB rows.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_withdrawal_ledger import INN, seed  # type: ignore[import-not-found]
from test_withdrawal_orchestration import MOD, SIGNATURE, Emulator  # type: ignore[import-not-found]

from app.api.deps import get_current_user
from app.api.marking_withdrawals import withdrawal_products
from app.db.session import SessionLocal
from app.db.withdrawal_repository import WithdrawalError, current_items, get_operation, registry
from app.main import create_app
from app.models.billing import BillingProfile
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.marking_code import MarkingCode
from app.models.marking_withdrawal import WithdrawalDocument, WithdrawalOperation
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.user import User
from app.services.integration_fernet import encrypt_secret
from app.services.withdrawal_orchestration import (
    CertificateSelection,
    SignedWithdrawalDocument,
    accept_document_signatures,
    authenticate_and_build,
    prepare_challenge,
    prepare_reauth,
    scoped_documents,
)
from app.services.withdrawal_recovery import claim_work, recover_one
from app.services.withdrawal_service import MAX_OPERATION_ROWS, create_operation, retry_operation
from app.services.withdrawal_submission import submit_one


def sale(
    rid: str,
    *,
    identifier: str = "S1",
    price: Any = "123.45",
    changed: str = "2026-10-05T12:00:00.1234567",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "srid": rid,
        "saleID": identifier,
        "finishedPrice": price,
        "date": "2026-10-04T09:00:00",
        "lastChangeDate": changed,
        "nmId": 42,
        "barcode": "4601234567890",
        **extra,
    }


class SalesHTTP:
    """Only HTTP response boundary; no local eligibility or price implementation."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.pages: list[Any] | None = None
        self.status: int | None = None
        self.finance_status = 204
        self.error: str | None = None
        self.requests: list[httpx.Request] = []
        self.waits: list[float] = []
        self.tokens: dict[uuid.UUID, str] = {}
        self.rows_by_token: dict[str, list[dict[str, Any]]] = {}
        self.delivered: set[str] = set()
        self.cursor_index = 0

    def reset(self) -> None:
        self.delivered.clear()
        self.cursor_index = 0

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.host == "finance-api.wildberries.ru"
            and request.url.path == "/api/finance/v1/sales-reports/detailed"
        ):
            # The documented finance report POST reads history; no WB mutation
            # endpoint is allowed by this fixture.
            body = json.loads(request.content)
            assert body["dateFrom"] and body["dateTo"]
            assert body["period"] == "weekly" and body["limit"] == 100000
            assert isinstance(body["rrdId"], int) and body["rrdId"] >= 0
            self.requests.append(request)
            return httpx.Response(self.finance_status, request=request)
        assert request.method == "GET", "Sales audit must never mutate WB"
        assert request.url.path == "/api/v1/supplier/sales", "orders is not sale evidence"
        assert request.url.params.get("flag", "0") == "0", "flag=1 loses multi-day history"
        assert request.url.params.get("dateFrom"), "Sales cursor is mandatory"
        self.requests.append(request)
        if self.error == "timeout":
            raise httpx.ReadTimeout("fixture sales timeout", request=request)
        if self.error == "json":
            return httpx.Response(200, content=b"{invalid", request=request)
        if self.status:
            return httpx.Response(
                self.status,
                json={"error": "fixture-restricted-body"},
                headers={"Retry-After": "2"},
                request=request,
            )
        if self.pages is not None:
            index = self.cursor_index
            self.cursor_index += 1
            assert index < len(self.pages), "Pagination must terminate or detect stuck cursor"
            page = self.pages[index]
            if isinstance(page, Exception):
                raise page
            if isinstance(page, int):
                return httpx.Response(page, json={"error": "second page failed"}, request=request)
            return httpx.Response(200, json=page, request=request)
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        rows = self.rows_by_token.get(token, self.rows)
        # Each fresh scan: one data page followed by the required empty terminator.
        cursor = request.url.params["dateFrom"]
        last = rows[-1]["lastChangeDate"] if rows else None
        if rows and cursor != last:
            return httpx.Response(200, json=rows, request=request)
        return httpx.Response(200, json=[], request=request)


@pytest.fixture
def sales_http(monkeypatch: pytest.MonkeyPatch) -> SalesHTTP:
    boundary = SalesHTTP()
    original_send = httpx.AsyncClient.send

    async def send(
        client: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        if request.url.host and request.url.host.endswith("wildberries.ru"):
            return await boundary.handle(request)
        # Explicit ASGI/CRPT fixture transports may proceed; any actual socket is forbidden.
        assert isinstance(client._transport, (httpx.MockTransport, httpx.ASGITransport))
        return await original_send(client, request, **kwargs)

    async def pause(seconds: float) -> None:
        boundary.waits.append(seconds)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    monkeypatch.setattr(asyncio, "sleep", pause)
    return boundary


async def fixture_order(db: AsyncSession, boundary: SalesHTTP) -> Any:
    scope, marking, order, supply = await seed(db, sales_evidence=False)
    order.wb_rid = f"rid-{order.wb_order_id}.0.0"
    order.wb_status = "sorted"
    order.created_at_wb = datetime(2026, 9, 22, 10, tzinfo=UTC)
    boundary.rows = [sale(order.wb_rid)]
    # Synthetic fixture credential in this isolated DB, so either dependency
    # import style uses the real tenant-scoped resolver. No real credential read.
    token = boundary.tokens.setdefault(scope.seller_id, f"fixture-{scope.seller_id}")
    db.add(
        SellerWildberriesCredentials(
            seller_id=scope.seller_id,
            marketplace_token_encrypted=encrypt_secret(token),
            marketplace_scope_ok=True,
        )
    )
    db.add(
        BillingProfile(
            tenant_id=scope.tenant_id, seller_id=scope.seller_id, legal_name="Fixture", inn=INN
        )
    )
    await db.commit()
    return scope, marking, order, supply


async def prepare(
    db: AsyncSession, scope: Any, marking: Any, runtime: Any, emulator: Emulator
) -> Any:
    operation = await create_operation(
        db, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    await db.commit()
    operation = await prepare_challenge(
        db,
        scope,
        operation.id,
        CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=2)),
        runtime,
    )
    return operation


async def build(
    db: AsyncSession, scope: Any, operation: Any, runtime: Any, emulator: Emulator
) -> Any:
    return await authenticate_and_build(
        db,
        scope,
        operation.id,
        thumbprint="fixture-thumb",
        challenge_uuid=uuid.UUID(emulator.challenge),
        expected_attempt=operation.attempt,
        signature=SIGNATURE,
        runtime=runtime,
    )


async def test_sc1_registry_uses_exact_sale_not_wb_status(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    # WB status does not veto the exact S sale.
    rows, total = await registry(db_session, scope)
    assert total == 1 and rows[0]["row_id"] == marking.id
    order.wb_status = "sold"
    sales_http.rows = [sale("another-rid", nmId=order.wb_nm_id, barcode=order.wb_barcode)]
    await db_session.commit()
    assert (await registry(db_session, scope))[1] == 0, "sold/order/product are not sale evidence"
    assert await withdrawal_products(db_session, scope, search=None, limit=100) == []


async def test_sc1_forged_unsold_create_rejected(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    order.wb_status = "sold"
    sales_http.rows = []
    await db_session.commit()
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
    assert await db_session.scalar(select(func.count(WithdrawalOperation.id))) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("wb_rid", None),
        ("wb_rid", ""),
        ("status", "cancelled"),
        ("status", "defect"),
        ("pick_status", "returned"),
        ("marketplace", "ozon"),
        ("supply_id", None),
    ],
)
async def test_sc2_local_scope_and_exact_rid(
    db_session: AsyncSession, sales_http: SalesHTTP, field: str, value: Any
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    setattr(order, field, value)
    await db_session.commit()
    assert (await registry(db_session, scope))[1] == 0
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )


async def test_sc2_foreign_seller_sale_does_not_authorize_same_rid(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    own, marking, order, _ = await fixture_order(db_session, sales_http)
    foreign, _, _, _ = await seed(db_session)
    sales_http.rows = []
    sales_http.tokens[foreign.seller_id] = "fixture-foreign"
    sales_http.rows_by_token = {
        sales_http.tokens[own.seller_id]: [],
        "fixture-foreign": [sale(order.wb_rid)],
    }
    assert (await registry(db_session, own))[1] == 0
    assert sales_http.requests and all(
        request.headers.get("Authorization", "").removeprefix("Bearer ")
        == sales_http.tokens[own.seller_id]
        for request in sales_http.requests
    )
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, foreign, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )


async def test_sc2_foreign_pool_code_is_excluded_even_with_exact_sale(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    foreign, _, _, _ = await seed(db_session)
    code = MarkingCode(
        tenant_id=foreign.tenant_id,
        seller_id=foreign.seller_id,
        cis_code=marking.value,
        source="pool",
        status="shipped",
    )
    db_session.add(code)
    await db_session.flush()
    marking.marking_code_id = code.id
    marking.source = "pool"
    await db_session.commit()
    assert (await registry(db_session, scope))[1] == 0
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("kind", ["return", "unknown", "conflicting_sale", "conflicting_rid"])
async def test_sc3_returns_unknown_and_conflicts_are_order_independent(
    db_session: AsyncSession, sales_http: SalesHTTP, reverse: bool, kind: str
) -> None:
    scope, _, order, _ = await fixture_order(db_session, sales_http)
    first = sale(order.wb_rid)
    second = {
        "return": sale(
            order.wb_rid, identifier="R1", price="-123.45", changed="2026-10-05T13:00:00"
        ),
        "unknown": sale(order.wb_rid, identifier="X1"),
        "conflicting_sale": sale(order.wb_rid, identifier="S2", price="42.00"),
        "conflicting_rid": sale("foreign-rid", identifier="S1"),
    }[kind]
    sales_http.rows = [first, second] if not reverse else [second, first]
    assert (await registry(db_session, scope))[1] == 0


async def test_sc3_same_sale_update_deduplicates(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = [sale(order.wb_rid), sale(order.wb_rid, changed="2026-10-05T14:00:00")]
    rows, total = await registry(db_session, scope)
    assert total == 1 and [row["row_id"] for row in rows] == [marking.id]
    assert len(sales_http.requests) >= 2, "Read through the empty sales terminator"


async def test_sc4_return_on_second_page_and_exact_cursor(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, _, order, _ = await fixture_order(db_session, sales_http)
    first = sale(order.wb_rid)
    returned = sale(
        order.wb_rid, identifier="R1", price="-123.45", changed="2026-10-05T13:00:00.9876543"
    )
    sales_http.pages = [[first], [first, returned], []]
    assert (await registry(db_session, scope))[1] == 0, "Later R excludes the first-page S"
    assert len(sales_http.requests) == 3
    assert sales_http.requests[1].url.params["dateFrom"] == first["lastChangeDate"]
    assert sales_http.requests[2].url.params["dateFrom"] == returned["lastChangeDate"]


async def test_sc4_stalled_cursor_is_incomplete_not_empty_success(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, _, order, _ = await fixture_order(db_session, sales_http)
    row = sale(order.wb_rid)
    sales_http.pages = [[row], [row], [row]]
    with pytest.raises(WithdrawalError):
        await registry(db_session, scope)
    assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 0


@pytest.mark.parametrize("failure", [401, 403, 429, "timeout", "json", "second-page"])
async def test_sc5_incomplete_transport_cannot_prepare_from_legacy_snapshot(
    db_session: AsyncSession, sales_http: SalesHTTP, failure: Any, caplog: pytest.LogCaptureFixture
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    if isinstance(failure, int):
        sales_http.status = failure
    elif failure == "second-page":
        sales_http.pages = [[sale(order.wb_rid)], 403]
    else:
        sales_http.error = failure
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
    assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 0
    assert "fixture-restricted-body" not in caplog.text
    assert all(token not in caplog.text for token in sales_http.tokens.values())
    if failure == 429 and len(sales_http.requests) > 1:
        assert sales_http.waits and min(sales_http.waits) >= 2


async def test_sc6_old_missing_sale_reports_coverage_not_unsold(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, supply = await fixture_order(db_session, sales_http)
    order.created_at_wb = datetime.now(UTC) - timedelta(days=120)
    supply.delivered_at = datetime.now(UTC) - timedelta(days=110)
    sales_http.rows = []
    # This case represents unavailable historical evidence, not a complete
    # finance report proving no sale; retain the coverage-error assertion.
    sales_http.finance_status = 503
    await db_session.commit()
    with pytest.raises(WithdrawalError, match=r"(?i)coverage|history|90|incomplete"):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )


async def test_sc5_failed_refresh_preserves_prior_useful_attempt(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        op = await prepare(db_session, scope, marking, runtime, emulator)
        op = await build(db_session, scope, op, runtime, emulator)
        doc = (await scoped_documents(db_session, scope, op))[0]
        item = (await current_items(db_session, scope, op.id))[0]
        saved = (
            doc.exact_payload,
            doc.payload_sha256,
            json.dumps(item.preflight_evidence, sort_keys=True),
        )
        op_id = op.id
        sales_http.status = 403
        with pytest.raises(WithdrawalError):
            await registry(db_session, scope)
        await db_session.rollback()
        op = await get_operation(db_session, scope, op_id)
        doc = (await scoped_documents(db_session, scope, op))[0]
        item = (await current_items(db_session, scope, op_id))[0]
        assert saved == (
            doc.exact_payload,
            doc.payload_sha256,
            json.dumps(item.preflight_evidence, sort_keys=True),
        )
        assert not any(path.endswith("/lk/documents/create") for path in emulator.calls)


@pytest.mark.parametrize("change", ["return", "binding"])
async def test_sc7_return_between_view_and_document_blocks_unsigned_attempt(
    db_session: AsyncSession, sales_http: SalesHTTP, change: str
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        assert (await registry(db_session, scope))[1] == 1
        operation = await prepare(db_session, scope, marking, runtime, emulator)
        if change == "return":
            sales_http.rows.append(
                sale(order.wb_rid, identifier="R1", price="-123.45", changed="2026-10-05T15:00:00")
            )
        else:
            order.wb_rid = "rebound-order"
            await db_session.commit()
        try:
            operation = await build(db_session, scope, operation, runtime, emulator)
        except WithdrawalError:
            await db_session.rollback()
        documents = await db_session.scalars(select(WithdrawalDocument))
        assert list(documents) == [], "Stale sales evidence must not become signable bytes"
        assert not any(path.endswith("/lk/documents/create") for path in emulator.calls)


async def test_sc8_moscow_handover_filters_keep_same_sales_set(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, supply = await fixture_order(db_session, sales_http)
    supply.delivered_at = datetime(2026, 9, 22, 21, tzinfo=UTC)  # exactly Moscow midnight
    await db_session.commit()
    rows, total = await registry(
        db_session,
        scope,
        date_from=date(2026, 9, 23),
        date_to=date(2026, 9, 23),
        search="SKU",
        product_id=order.product_id,
        only_not_withdrawn=True,
        limit=250,
    )
    assert total == 1 and rows[0]["row_id"] == marking.id
    assert (await registry(db_session, scope, date_to=date(2026, 9, 22)))[1] == 0
    assert len(sales_http.requests) >= 2, "Sales date must not replace the handover period"


@pytest.mark.parametrize("count", [305, MAX_OPERATION_ROWS])
async def test_sc9_all_pages_and_maximum_selection_keep_every_unique_code(
    db_session: AsyncSession, sales_http: SalesHTTP, count: int
) -> None:
    scope, first, order, _ = await fixture_order(db_session, sales_http)
    markings = [first]
    for number in range(1, count):
        # One sales row proves one actual FBS unit/order; never fan one sale out
        # into thousands of unrelated codes.
        unit = FbsOrder(
            id=uuid.uuid4(),
            tenant_id=scope.tenant_id,
            seller_id=scope.seller_id,
            warehouse_id=order.warehouse_id,
            wb_order_id=number + 2_000_000_000,
            wb_rid=f"bulk-rid-{number}",
            supply_id=order.supply_id,
            product_id=order.product_id,
            marketplace="wb",
            status="in_delivery",
            wb_status="sorted",
            created_at_wb=order.created_at_wb,
            deadline_at=datetime.now(UTC),
            mapping_status="mapped",
            reserve_status="reserved",
        )
        db_session.add(unit)
        assert unit.wb_rid is not None
        sales_http.rows.append(sale(unit.wb_rid, identifier=f"S{number + 1}"))
        marking = FbsOrderMarking(
            tenant_id=scope.tenant_id,
            order_id=unit.id,
            kind="sgtin",
            value=f"010460123456789021bulk{number:06d}",
            source="external",
            meta_status="sent",
        )
        db_session.add(marking)
        markings.append(marking)
    await db_session.commit()
    selected: list[uuid.UUID] = []
    for offset in range(0, count, 250):
        rows, total = await registry(db_session, scope, limit=250, offset=offset)
        assert total == count
        selected.extend(cast(uuid.UUID, row["row_id"]) for row in rows)
    assert len(set(selected)) == count
    operation = await create_operation(
        db_session, scope, row_ids=selected, client_request_id=uuid.uuid4()
    )
    items = await current_items(db_session, scope, operation.id)
    assert len(items) == count and {item.marking_id for item in items} == set(selected)
    assert {item.product_cost for item in items} == {12345}, "Full set uses matched sale prices"


@pytest.mark.parametrize(
    "price", [0, -1, None, "NaN", "Infinity", "123.456", True, "1000000000000000.00"]
)
async def test_sc10_invalid_finished_price_never_falls_back(
    db_session: AsyncSession, sales_http: SalesHTTP, price: Any
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = [sale(order.wb_rid, price=price)]
    operation = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    items = await current_items(db_session, scope, operation.id)
    assert items and all(item.state == "failed" and item.error for item in items)
    assert all(item.product_cost is None for item in items), (
        "Legacy finalPrice cannot rescue invalid sale"
    )


@pytest.mark.parametrize("price", ["123.45", 123.45])
async def test_sc10_exact_cost_and_immutable_source_survive_later_wb_change(
    db_session: AsyncSession, sales_http: SalesHTTP, price: Any
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = [sale(order.wb_rid, price=price)]
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        operation = await prepare(db_session, scope, marking, runtime, emulator)
        operation = await build(db_session, scope, operation, runtime, emulator)
        docs = await scoped_documents(db_session, scope, operation)
        assert len(docs) == 1
        exact = docs[0].exact_payload
        assert json.loads(exact)["products"][0]["product_cost"] == 12345
        item = (await current_items(db_session, scope, operation.id))[0]
        evidence = json.dumps(item.preflight_evidence, ensure_ascii=False)
        for value in ("supplier/sales", order.wb_rid, "S1", "123.45", "lastChangeDate"):
            assert value in evidence, "Immutable attempt must retain the exact WB source"
        sales_http.rows = [sale(order.wb_rid, price="777.77")]
        operation_id = operation.id
        await db_session.rollback()
        reloaded = await get_operation(db_session, scope, operation_id)
        assert (await scoped_documents(db_session, scope, reloaded))[0].exact_payload == exact


async def test_sc11_certificate_hash_binding_and_reload(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        op = await prepare(db_session, scope, marking, runtime, emulator)
        op = await build(db_session, scope, op, runtime, emulator)
        doc = (await scoped_documents(db_session, scope, op))[0]
        op_id, doc_id, digest = op.id, doc.id, doc.payload_sha256
        assert digest == hashlib.sha256(doc.exact_payload).hexdigest()
        for thumbprint, payload_hash in [("wrong-cert", digest), ("fixture-thumb", "0" * 64)]:
            with pytest.raises(WithdrawalError, match="signature_mismatch"):
                await accept_document_signatures(
                    db_session,
                    scope,
                    op_id,
                    [SignedWithdrawalDocument(doc_id, payload_hash, thumbprint, SIGNATURE)],
                    runtime,
                )
            await db_session.rollback()
        op = await get_operation(db_session, scope, op_id)
        assert op.state == "documents_pending_signature"
        assert (await scoped_documents(db_session, scope, op))[0].signature is None
        assert not any(path.endswith("/lk/documents/create") for path in emulator.calls)


async def test_sc11_expired_certificate_and_cancel_never_start_auth(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        op = await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
        await db_session.commit()
        op_id = op.id
        await prepare_challenge(db_session, scope, op_id, None, runtime)
        with pytest.raises(WithdrawalError, match="certificate_expired"):
            await prepare_challenge(
                db_session,
                scope,
                op_id,
                CertificateSelection("fixture-thumb", datetime.now(UTC) - timedelta(seconds=1)),
                runtime,
            )
        assert emulator.calls == []
        assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 0


@pytest.mark.parametrize("lost", [False, True])
async def test_sc12_submitted_reauth_recovery_ignores_later_return_without_new_post(
    db_session: AsyncSession, sales_http: SalesHTTP, lost: bool
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD], lose_create=lost)
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        op = await prepare(db_session, scope, marking, runtime, emulator)
        op = await build(db_session, scope, op, runtime, emulator)
        doc = (await scoped_documents(db_session, scope, op))[0]
        op_id, before = op.id, (doc.exact_payload, doc.payload_sha256)
        signed = SignedWithdrawalDocument(doc.id, doc.payload_sha256, "fixture-thumb", SIGNATURE)
        await accept_document_signatures(db_session, scope, op_id, [signed], runtime)
        await accept_document_signatures(db_session, scope, op_id, [signed], runtime)
        assert await submit_one(SessionLocal, runtime)
        assert not await submit_one(SessionLocal, runtime)
        sales_http.rows = [sale(order.wb_rid, identifier="R1", price="-123.45")]
        sales_http.status = 403  # recovery must not depend on a fresh sales query
        await db_session.rollback()
        op = await get_operation(db_session, scope, op_id)
        op.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()
        # Exercise the actual worker expiry path before requesting reauthentication.
        async with SessionLocal() as session:
            expired_work = await claim_work(session, now=datetime.now(UTC) + timedelta(seconds=3))
        assert expired_work is not None
        await recover_one(SessionLocal, expired_work, runtime.client(INN, "sandbox"))
        await db_session.rollback()
        db_session.expire_all()
        sales_calls = len(sales_http.requests)
        op = await prepare_reauth(
            db_session,
            scope,
            op_id,
            CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=1)),
            runtime,
        )
        op = await build(db_session, scope, op, runtime, emulator)
        assert len(sales_http.requests) == sales_calls
        doc = (await scoped_documents(db_session, scope, op))[0]
        assert before == (doc.exact_payload, doc.payload_sha256)
        async with SessionLocal() as session:
            work = await claim_work(session, now=datetime.now(UTC) + timedelta(seconds=3))
        assert work is not None
        await recover_one(SessionLocal, work, runtime.client(INN, "sandbox"))
        await db_session.rollback()
        final = await get_operation(db_session, scope, op_id)
        assert final.state == "succeeded"
        assert sum(path.endswith("/lk/documents/create") for path in emulator.calls) == 1


async def test_sc12_terminal_retry_rechecks_sale_and_return(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    op = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    item = (await current_items(db_session, scope, op.id))[0]
    item.state = "failed"
    item.error = {"source": "crpt", "code": "definite-terminal-reject"}
    op.state = "failed"
    await db_session.commit()
    sales_http.rows.append(
        sale(order.wb_rid, identifier="R1", price="-123.45", changed="2026-10-05T16:00:00")
    )
    with pytest.raises(WithdrawalError):
        await retry_operation(db_session, scope, op.id, expected_attempt=1)
    assert op.attempt == 1, "Return cannot create a new withdrawal attempt"


async def test_sc1_api_registry_products_and_forged_create_share_sale_scope(
    db_session: AsyncSession, sales_http: SalesHTTP
) -> None:
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    sales_http.rows = []
    app = create_app()
    user = await db_session.get(User, scope.user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        prefix = "/operations/marking-codes/self/withdrawals"
        response = await http.get(prefix)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
        products = await http.get(prefix + "/products")
        assert products.status_code == 200 and products.json() == []
        response = await http.post(
            prefix + "/operations",
            json={"row_ids": [str(marking.id)], "client_request_id": str(uuid.uuid4())},
        )
        assert response.status_code in {404, 409}, response.text
