"""Isolated emulator tests: no live CRPT, certificates or private keys."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_withdrawal_ledger import INN, seed  # type: ignore[import-not-found]

from app.api.marking_withdrawals import _output, router, withdrawal_products
from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.db.withdrawal_repository import WithdrawalError, current_items, get_operation
from app.models.billing import BillingProfile
from app.services.true_api_withdrawal import (
    CisInfo,
    Environment,
    TrueApiConfig,
    TrueApiWithdrawalClient,
)
from app.services.withdrawal_document_builder import WithdrawalProduct, build_withdrawal_documents
from app.services.withdrawal_mod_service import required_external_mod
from app.services.withdrawal_orchestration import (
    CertificateSelection,
    SignedWithdrawalDocument,
    accept_document_signatures,
    authenticate_and_build,
    cis_error,
    prepare_challenge,
    scoped_documents,
)
from app.services.withdrawal_recovery import claim_work, recover_one
from app.services.withdrawal_runtime import WithdrawalRuntime
from app.services.withdrawal_service import create_operation, retry_operation
from app.services.withdrawal_submission import submit_one

SIGNATURE = base64.b64encode(b"fixture-only-signature").decode()
FIAS = str(uuid.uuid4())
MOD = {"inn": INN, "productGroups": ["lp"], "fiasId": FIAS, "kpp": "770101001"}


class FixtureLimiter:
    async def acquire(self, environment: Environment, participant_inn: str) -> None:
        assert environment == Environment.SANDBOX
        assert participant_inn == INN


class Emulator:
    def __init__(self, rows: list[dict[str, Any]], *, lose_create: bool = False) -> None:
        self.rows = rows
        self.lose_create = lose_create
        self.calls: list[str] = []
        self.identifier = str(uuid.uuid4())
        self.challenge = str(uuid.uuid4())
        self.payload: dict[str, Any] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path.endswith("/auth/key"):
            return httpx.Response(200, json={"uuid": self.challenge, "data": "exact challenge"})
        if path.endswith("/auth/simpleSignIn"):
            return httpx.Response(
                200,
                json={
                    "uuidToken": str(uuid.uuid4()),
                    "expireDate": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                },
            )
        if path.endswith("/cises/info"):
            return httpx.Response(
                200,
                json=[
                    {
                        "cisInfo": {
                            "requestedCis": cis,
                            "cis": cis,
                            "productGroup": "lp",
                            "productGroupId": 1,
                            "ownerInn": INN,
                            "status": "INTRODUCED",
                            "gtin": "04601234567890",
                        }
                    }
                    for cis in json.loads(request.content)
                ],
            )
        if path.endswith("/mods/list"):
            assert request.url.params["page"] == "0"
            assert request.url.params["inns"] == INN
            return httpx.Response(
                200, json={"result": self.rows, "total": len(self.rows), "nextPage": False}
            )
        if path.endswith("/lk/documents/create"):
            self.payload = json.loads(
                base64.b64decode(json.loads(request.content)["product_document"])
            )
            if self.lose_create:
                raise httpx.ReadTimeout("emulated lost response")
            return httpx.Response(200, json=self.identifier)
        if path.endswith("/doc/list"):
            return httpx.Response(
                200, json={"results": [{"number": self.identifier}], "nextPage": False}
            )
        if path.endswith("/info"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": self.identifier,
                        "productGroup": ["lp"],
                        "status": "CHECKED_OK",
                        "type": "LK_RECEIPT",
                        "body": self.payload,
                    }
                ],
            )
        raise AssertionError(path)

    def runtime(self, http: httpx.AsyncClient) -> WithdrawalRuntime:
        config = TrueApiConfig(Environment.SANDBOX, browser_auth_profile_verified=True)
        return WithdrawalRuntime(
            config,
            lambda inn: TrueApiWithdrawalClient(http, config, FixtureLimiter(), inn),
            "emulator-explicit-metadata-v1",
            {"lp": "started"},
        )


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([], "external_mod_missing"),
        ([{**MOD, "inn": "1234567890"}], "external_mod_missing"),
        ([{**MOD, "fiasId": "not-uuid"}], "external_mod_missing"),
        ([{**MOD, "kpp": None}], "external_mod_missing"),
        ([MOD, MOD], "external_mod_ambiguous"),
        ([MOD, {**MOD, "fiasId": str(uuid.uuid4())}], "external_mod_ambiguous"),
    ],
)
def test_external_mod_exact_cardinality(rows: list[dict[str, Any]], expected: str) -> None:
    with pytest.raises(WithdrawalError, match=expected):
        required_external_mod(inn=INN, pg="lp", rows=rows)


def test_external_mod_unique_valid_scope_and_ip_rules() -> None:
    assert required_external_mod(
        inn=INN,
        pg="lp",
        rows=[
            MOD,
            {**MOD, "inn": "1234567890"},
            {**MOD, "productGroups": ["shoes"]},
            {**MOD, "fiasId": None},
        ],
    ) == (FIAS, MOD["kpp"])
    assert required_external_mod(inn=INN, pg="books", rows=[]) == (None, None)
    assert required_external_mod(
        inn="123456789012", pg="lp", rows=[{**MOD, "inn": "123456789012", "kpp": None}]
    ) == (FIAS, None)
    assert all("mods/mappings" not in getattr(route, "path", "") for route in router.routes)


@pytest.mark.parametrize(
    "mode,extended,expected",
    [
        (None, None, "traceability_mode_unknown"),
        ("started", None, None),
        ("started", "CONNECT_TAP", None),
        ("started", "OTHER", "cis_status_not_allowed"),
        ("not_started", "OTHER", None),
        ("not_started", "MOVING_BY_UD", "cis_status_not_allowed"),
    ],
)
def test_traceability_requires_explicit_versioned_mode(
    mode: str | None,
    extended: str | None,
    expected: str | None,
) -> None:
    info = CisInfo("cis", "cis", "lp", 1, INN, "INTRODUCED", extended, "gtin", None, None, {})
    result = cis_error(info, inn=INN, traceability_mode=mode)
    assert (result["code"] if result else None) == expected
    owner_error = cis_error(replace(info, owner_inn="other"), inn=INN, traceability_mode=mode)
    assert owner_error is not None and owner_error["code"] == "cis_owner_mismatch"


def test_builder_group_split_exact_bytes_and_moscow_date() -> None:
    products = [
        WithdrawalProduct(uuid.uuid4(), f"КИЗ-{number}", 100, "lp", FIAS, "770101001")
        for number in range(3)
    ]
    products.append(WithdrawalProduct(uuid.uuid4(), "other", 20, "books"))
    documents = build_withdrawal_documents(
        inn=INN,
        attempt_started_at=datetime(2026, 9, 23, 22, tzinfo=UTC),
        products=products,
        max_codes=1,
    )
    assert len(documents) == 4
    for document in documents:
        assert hashlib.sha256(document.exact_payload).hexdigest() == document.payload_sha256
        body = json.loads(document.exact_payload)
        assert body["action_date"] == "2026-09-24"
        assert set(body) <= {"inn", "action", "action_date", "fias_id", "kpp", "products"}
        assert set(body["products"][0]) == {"cis", "product_cost"}
    maximum = max(len(document.exact_payload) for document in documents)
    split = build_withdrawal_documents(
        inn=INN,
        attempt_started_at=datetime(2026, 9, 23, 22, tzinfo=UTC),
        products=products,
        max_bytes=maximum,
    )
    assert len(split) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("lose_create", [False, True])
async def test_emulator_sign_submit_recover_once(
    db_session: AsyncSession, lose_create: bool
) -> None:
    scope, marking, order, _ = await seed(db_session)
    db_session.add(
        BillingProfile(
            tenant_id=scope.tenant_id, seller_id=scope.seller_id, legal_name="Fixture", inn=INN
        )
    )
    await db_session.commit()
    emulator = Emulator([MOD], lose_create=lose_create)
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        operation = await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
        await db_session.commit()
        operation = await prepare_challenge(
            db_session,
            scope,
            operation.id,
            CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=2)),
            runtime,
        )
        operation = await authenticate_and_build(
            db_session,
            scope,
            operation.id,
            thumbprint="fixture-thumb",
            challenge_uuid=uuid.UUID(emulator.challenge),
            expected_attempt=1,
            signature=SIGNATURE,
            runtime=runtime,
        )
        assert operation.state == "documents_pending_signature"
        documents = await scoped_documents(db_session, scope, operation)
        assert len(documents) == 1
        document = documents[0]
        body = json.loads(document.exact_payload)
        assert body["fias_id"] == FIAS
        assert body["products"] == [{"cis": marking.value, "product_cost": 99999999999999999}]
        output = await _output(db_session, scope, operation, runtime)
        assert output.items[0].wb_order_id == str(order.wb_order_id)
        assert base64.b64decode(output.documents[0].payload_base64) == document.exact_payload
        products = await withdrawal_products(db_session, scope, search=None, limit=100)
        assert products[0]["id"] == order.product_id
        signed = SignedWithdrawalDocument(
            document.id, document.payload_sha256, "fixture-thumb", SIGNATURE
        )
        operation_id = operation.id
        with pytest.raises(WithdrawalError, match="signature_mismatch"):
            await accept_document_signatures(
                db_session, scope, operation.id, [replace(signed, payload_sha256="0" * 64)], runtime
            )
        await db_session.rollback()
        await accept_document_signatures(db_session, scope, operation_id, [signed], runtime)
        await accept_document_signatures(db_session, scope, operation_id, [signed], runtime)
        assert await submit_one(SessionLocal, runtime)
        assert not await submit_one(SessionLocal, runtime)
        async with SessionLocal() as recovery_session:
            work = await claim_work(recovery_session, now=datetime.now(UTC) + timedelta(seconds=3))
        assert work is not None
        await recover_one(SessionLocal, work, runtime.client(INN, "sandbox"))
        await db_session.rollback()
        final = await get_operation(db_session, scope, operation_id)
        assert final.state == "succeeded"
        assert (await current_items(db_session, scope, operation_id))[0].state == "succeeded"
        assert len([path for path in emulator.calls if path.endswith("/lk/documents/create")]) == 1


@pytest.mark.asyncio
async def test_missing_mod_retry_and_evidence_scope(db_session: AsyncSession) -> None:
    scope, marking, _, _ = await seed(db_session)
    db_session.add(
        BillingProfile(
            tenant_id=scope.tenant_id, seller_id=scope.seller_id, legal_name="Fixture", inn=INN
        )
    )
    await db_session.commit()
    emulator = Emulator([])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        operation = await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
        await db_session.commit()
        certificate = CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=2))
        operation = await prepare_challenge(db_session, scope, operation.id, certificate, runtime)
        await authenticate_and_build(
            db_session,
            scope,
            operation.id,
            thumbprint="fixture-thumb",
            challenge_uuid=uuid.UUID(emulator.challenge),
            expected_attempt=1,
            signature=SIGNATURE,
            runtime=runtime,
        )
        items = await current_items(db_session, scope, operation.id)
        assert items[0].error is not None
        assert items[0].error["code"] == "external_mod_missing"
        assert not await scoped_documents(db_session, scope, operation)
        emulator.rows = [MOD]
        operation = await retry_operation(db_session, scope, operation.id, expected_attempt=1)
        await db_session.commit()
        operation = await prepare_challenge(db_session, scope, operation.id, certificate, runtime)
        operation = await authenticate_and_build(
            db_session,
            scope,
            operation.id,
            thumbprint="fixture-thumb",
            challenge_uuid=uuid.UUID(emulator.challenge),
            expected_attempt=2,
            signature=SIGNATURE,
            runtime=runtime,
        )
        assert operation.state == "documents_pending_signature"
        retried_items = await current_items(db_session, scope, operation.id)
        assert retried_items[0].preflight_evidence is not None
        assert retried_items[0].preflight_evidence["external_mods"] == [MOD]
        assert "app.tasks.withdrawal_recovery" in celery_app.conf.include
        assert celery_app.conf.beat_schedule["withdrawal-poll"]["task"] == "wms.withdrawal_poll"
