"""WMS-556: real self boundary and durable queue, with no external transports."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from test_withdrawal_ledger import document, seed

from app.api.auth import SwitchSellerBody, me, switch_seller
from app.api.deps import get_current_user, get_effective_seller_id
from app.core.settings import Settings, settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.marking_withdrawal import WithdrawalDocument, WithdrawalOperation
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.user import User
from app.services.true_api_withdrawal import Environment, TrueApiConfig
from app.services.withdrawal_access import allowed_withdrawal_sellers, withdrawal_allowed
from app.services.withdrawal_recovery import (
    apply_recovery,
    claim_work,
    purge_expired_tokens,
    recover_one,
)
from app.services.withdrawal_runtime import WithdrawalRuntime, get_withdrawal_runtime
from app.services.withdrawal_submission import claim_submit, submit_one
from app.tasks.withdrawal_recovery import run_withdrawal_jobs

PREFIX = "/operations/marking-codes/self/withdrawals"


@pytest.mark.parametrize("suffix", ["", ",", ",not-a-uuid", ",*", ", ", ",null"])
def test_c1_invalid_configuration_closes_entire_list(monkeypatch, suffix):
    identifier = uuid.uuid4()
    raw = str(identifier) + suffix if suffix else ""
    monkeypatch.setattr(settings, "withdrawal_seller_allowlist", raw)
    assert allowed_withdrawal_sellers() == frozenset()
    assert not withdrawal_allowed(identifier)
    assert not withdrawal_allowed(None)


def test_c2_exact_uuid_only_and_settings_default_closed(monkeypatch):
    first, second = uuid.uuid4(), uuid.uuid4()
    monkeypatch.delenv("WITHDRAWAL_SELLER_ALLOWLIST", raising=False)
    assert Settings(_env_file=None).withdrawal_seller_allowlist == ""
    monkeypatch.setattr(settings, "withdrawal_seller_allowlist", f" {first}, {second} ")
    assert allowed_withdrawal_sellers() == frozenset([first, second])
    assert not withdrawal_allowed(uuid.uuid4())
    monkeypatch.setattr(settings, "withdrawal_seller_allowlist", first.hex)
    assert not withdrawal_allowed(first)


@pytest.mark.asyncio
async def test_c1_c3_every_endpoint_denies_before_runtime_or_ledger(db_session, monkeypatch):
    scope, marking, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    assert user is not None
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    runtime = Mock(side_effect=AssertionError("denied endpoint requested provider runtime"))

    def unexpected_runtime():
        return runtime()

    app.dependency_overrides[get_withdrawal_runtime] = unexpected_runtime
    operation_id = uuid.uuid4()
    certificate = {"thumbprint": "fixture", "expires_at": "2099-01-01T00:00:00Z"}
    requests = [
        ("GET", "", None),
        ("GET", "/products", None),
        ("GET", f"/operations/{operation_id}", None),
        (
            "POST",
            "/operations",
            {
                "row_ids": [str(marking.id)],
                "client_request_id": str(uuid.uuid4()),
            },
        ),
        ("POST", f"/operations/{operation_id}/retry", {"expected_attempt": 1}),
        ("POST", f"/operations/{operation_id}/reauth-challenge", {"certificate": certificate}),
        (
            "POST",
            f"/operations/{operation_id}/auth-signature",
            {
                "thumbprint": "fixture",
                "signature": "ZmFrZQ==",
            },
        ),
        (
            "POST",
            f"/operations/{operation_id}/document-signatures",
            {
                "documents": [
                    {
                        "document_id": str(uuid.uuid4()),
                        "payload_sha256": "a" * 64,
                        "thumbprint": "fixture",
                        "signature": "ZmFrZQ==",
                    }
                ]
            },
        ),
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        for configured, effective in [
            ("", scope.seller_id),
            ("invalid", scope.seller_id),
            (str(scope.seller_id), uuid.uuid4()),
        ]:
            monkeypatch.setattr(settings, "withdrawal_seller_allowlist", configured)
            app.dependency_overrides[get_effective_seller_id] = lambda value=effective: value
            for method, path, payload in requests:
                result = await http.request(
                    method, PREFIX + path, json=payload, params={"seller_id": str(scope.seller_id)}
                )
                assert result.status_code == 403, (path, result.text)
                assert result.json()["detail"] == "withdrawal_not_available"
    runtime.assert_not_called()
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalOperation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalDocument)) == 0


@pytest.mark.asyncio
async def test_c2_c4_capability_follows_real_delegated_seller_switch(db_session, monkeypatch):
    scope, _, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    assert user is not None
    user.can_manage_seller_shops = True
    other = Seller(tenant_id=scope.tenant_id, name="Other shop")
    db_session.add(other)
    await db_session.flush()
    db_session.add(SellerShopDelegation(user_id=user.id, target_seller_id=other.id, enabled=True))
    await db_session.commit()
    for seller_id, expected in [
        (scope.seller_id, True),
        (other.id, False),
        (scope.seller_id, True),
    ]:
        token = await switch_seller(SwitchSellerBody(seller_id=seller_id), user, db_session)
        profile = await me(
            user,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token.access_token),
            db_session,
        )
        assert profile.active_seller_id == str(seller_id)
        assert profile.withdrawal_enabled is expected
        assert profile.seller_permissions is not None and profile.seller_permissions.honest_sign
        assert "allowlist" not in profile.model_dump_json()
    monkeypatch.setattr(settings, "withdrawal_seller_allowlist", "")
    assert not (await me(user, None, db_session)).withdrawal_enabled


@pytest.mark.asyncio
async def test_c2_c5_allowed_registry_and_idempotent_create(db_session):
    scope, marking, order, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    provider = Mock(side_effect=AssertionError("certificate-free create must not call provider"))
    app.dependency_overrides[get_withdrawal_runtime] = lambda: WithdrawalRuntime(
        TrueApiConfig(Environment.SANDBOX), provider
    )
    payload = {"row_ids": [str(marking.id)], "client_request_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        registry = await http.get(PREFIX)
        assert registry.status_code == 200
        assert [row["row_id"] for row in registry.json()["rows"]] == [str(marking.id)]
        products = await http.get(PREFIX + "/products")
        assert [row["id"] for row in products.json()] == [str(order.product_id)]
        created = await http.post(PREFIX + "/operations", json=payload)
        assert created.status_code == 200, created.text
        # Deliver the same request concurrently after the first persisted result.
        repeated = await asyncio.gather(
            *[http.post(PREFIX + "/operations", json=payload) for _ in range(2)]
        )
        assert all(result.status_code == 200 for result in repeated)
        assert all(
            result.json()["operation_id"] == created.json()["operation_id"] for result in repeated
        )
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalOperation)) == 1
    provider.assert_not_called()


def snapshot(row):
    return {
        column.name: value.replace(tzinfo=UTC) if isinstance(value, datetime) else value
        for column in row.__table__.columns
        for value in [getattr(row, column.name)]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending_signature", "submitting", "reconciling", "submitted"])
async def test_c6_denied_documents_never_claimed_or_mutated(db_session, monkeypatch, state):
    denied_scope, denied_op, denied_doc = await document(db_session)
    allowed_scope, _, allowed_doc = await document(db_session)
    denied_doc.state = allowed_doc.state = state
    allowed_doc_id = allowed_doc.id
    denied_op.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    await db_session.refresh(denied_op)
    await db_session.refresh(denied_doc)
    before = snapshot(denied_op), snapshot(denied_doc)
    provider = Mock(side_effect=AssertionError("unexpected external call"))
    runtime = WithdrawalRuntime(TrueApiConfig(Environment.SANDBOX), provider)
    for configuration in [
        "",
        "invalid",
        f"{allowed_scope.seller_id},invalid",
        str(allowed_scope.seller_id),
    ]:
        monkeypatch.setattr(settings, "withdrawal_seller_allowlist", configuration)
        await purge_expired_tokens(db_session)
        work = await (
            claim_submit(db_session, runtime)
            if state == "pending_signature"
            else claim_work(db_session)
        )
        if configuration == str(allowed_scope.seller_id):
            assert work is not None and work.document_id == allowed_doc_id
        else:
            assert work is None
            assert await run_withdrawal_jobs() == 0
        await db_session.refresh(denied_op)
        await db_session.refresh(denied_doc)
        assert (snapshot(denied_op), snapshot(denied_doc)) == before
    assert not withdrawal_allowed(denied_scope.seller_id)
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_c6_revoked_seller_cannot_execute_or_apply_held_recovery(db_session, monkeypatch):
    _, operation, doc = await document(db_session)
    work = await claim_work(db_session)
    assert work is not None
    await db_session.refresh(operation)
    await db_session.refresh(doc)
    before = snapshot(operation), snapshot(doc)
    monkeypatch.setattr(settings, "withdrawal_seller_allowlist", "")
    provider = Mock(side_effect=AssertionError("revoked recovery called provider"))
    await recover_one(SessionLocal, work, provider)
    assert not await apply_recovery(db_session, work, incident="should-not-be-written")
    await db_session.refresh(operation)
    await db_session.refresh(doc)
    assert (snapshot(operation), snapshot(doc)) == before
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_c7_master_gate_blocks_create_retry_and_worker(db_session):
    scope, marking, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    provider = Mock(side_effect=AssertionError("production transport must remain closed"))
    runtime = WithdrawalRuntime(TrueApiConfig(Environment.PRODUCTION), provider)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_withdrawal_runtime] = lambda: runtime
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        for path, body in [
            ("/operations", {"row_ids": [str(marking.id)], "client_request_id": str(uuid.uuid4())}),
            (f"/operations/{uuid.uuid4()}/retry", {"expected_attempt": 1}),
        ]:
            result = await http.post(PREFIX + path, json=body)
            assert result.status_code == 409
            assert result.json()["detail"]["code"] == "WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED"
    assert not await submit_one(SessionLocal, runtime)
    assert await db_session.scalar(select(func.count()).select_from(WithdrawalOperation)) == 0
    provider.assert_not_called()


def test_c10_frontend_contains_no_rollout_identity_or_allowlist():
    # The target identity belongs to requirements/deployment, never to client code.
    root = Path(__file__).parents[2]
    import re

    requirements = (root / "docs/requirements/WMS-556.md").read_text()
    target = re.search(r"seller_id=([0-9a-f-]{36})", requirements)
    assert target
    for folder in [root / "frontend/src", root / "frontend/dist"]:
        for path in folder.rglob("*"):
            if path.suffix in {".ts", ".tsx", ".js", ".json", ".html"}:
                text = path.read_text()
                assert target.group(1) not in text, path
                assert "WITHDRAWAL_SELLER_ALLOWLIST" not in text, path


def test_c10_compose_processes_share_default_closed_allowlist():
    import yaml

    root = Path(__file__).parents[2]
    for name in ["docker-compose.yml", "docker-compose.prod.yml"]:
        services = yaml.safe_load((root / name).read_text())["services"]
        values = [
            services[role]["environment"]["WITHDRAWAL_SELLER_ALLOWLIST"]
            for role in ["api", "celery_worker", "celery_beat"]
        ]
        assert values == ["${WITHDRAWAL_SELLER_ALLOWLIST:-}"] * 3
