"""Readiness contracts use official shapes with synthetic identities; never live CRPT."""

import importlib.util
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from test_true_api_withdrawal import FIXTURES, INN, SIGNATURE, client

from app.models import Base
from app.models.marking_withdrawal import WithdrawalObservation
from app.railway_entrypoint import role_command
from app.services import true_api_withdrawal as api
from app.services.withdrawal_provider_ki import provider_ki
from app.services.withdrawal_traceability import (
    FULL,
    PUBLISHED_START_DATES,
    SNAPSHOT_DATE,
    SNAPSHOT_VERSION,
    SOURCE_URL,
    traceability_mode,
)


def test_versioned_official_traceability_has_no_invented_dates() -> None:
    assert str(SNAPSHOT_DATE) == "2026-09-24" and SNAPSHOT_VERSION.endswith(str(SNAPSHOT_DATE))
    assert SOURCE_URL == "https://docs.crpt.ru/gismt/Прослеживаемость_товаров/"
    assert not PUBLISHED_START_DATES
    assert {
        "otp",
        "perfumery",
        "lp",
        "milk",
        "furslp",
        "ncp",
        "shoes",
        "electronics",
        "tires",
    } == FULL
    assert traceability_mode("furslp") == "started"
    assert traceability_mode("furs") == "not_started"
    assert traceability_mode("unpublished") is None


@pytest.mark.parametrize("tail", ["", "\x1d91fixture\x1d92cryptographic-data"])
def test_provider_ki_preserves_original_and_projects_gs1(tail: str) -> None:
    ki = "010460123456789021ABCDEFGHIJKLMNOPQRST"
    original = ki + tail
    assert provider_ki(original) == ki
    assert original == ki + tail


@pytest.mark.parametrize(
    "value",
    [
        "bad",
        "010460123456789021",
        "010460123456789021abc\x1d10batch",
        "010460123456789021abc\x1d92",
        "010460123456789021abc\n",
    ],
)
def test_ambiguous_provider_codes_fail_before_http(value: str) -> None:
    with pytest.raises(ValueError):
        provider_ki(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 401, 403, 422, 429, 500, 503])
async def test_auth_provider_error_fields_survive_without_tokens(status: int) -> None:
    body = {
        "code": "CERT_REJECTED",
        "error_message": "Certificate rejected",
        "description": "Provider detail",
        "uuidToken": "must-not-escape",
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json=body, headers={"Retry-After": "4"})
        )
    ) as http:
        with pytest.raises(api.TrueApiError) as failure:
            await client(http).sign_in(
                FIXTURES["auth_key"]["uuid"],
                SIGNATURE,
                certificate_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
    retained = json.loads(failure.value.response_body)
    assert retained["code"] == body["code"]
    assert retained["error_message"] == body["error_message"]
    assert retained["description"] == body["description"]
    assert "must-not-escape" not in repr(failure.value) + failure.value.response_body.decode()
    if status == 429:
        assert failure.value.retry_after == 4


@pytest.mark.asyncio
async def test_retry_after_defers_shared_participant_without_replay() -> None:
    class Limiter:
        def __init__(self):
            self.deferred = []

        async def acquire(self, environment, inn):
            pass

        async def defer(self, environment, inn, seconds):
            self.deferred.append((environment, inn, seconds))

    limiter = Limiter()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"code": 429}, headers={"Retry-After": "7"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(api.TrueApiError):
            await client(http, limiter).challenge()
    assert len(calls) == 1
    assert limiter.deferred == [(api.Environment.SANDBOX, INN, 7)]


@pytest.mark.postgresql_concurrency
def test_postgresql_real_migration_guards_and_downgrade_cleanup() -> None:
    url = os.environ.get("WMS_TEST_DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        pytest.skip("Requires explicitly isolated WMS_TEST_DATABASE_URL PostgreSQL")
    engine = create_engine(make_url(url).set(drivername="postgresql+psycopg"))
    schema = "wms517_" + uuid.uuid4().hex
    names = {
        "withdrawal_operations",
        "withdrawal_documents",
        "withdrawal_items",
        "withdrawal_observations",
    }
    modules = []
    for filename in [
        "20260923_0518_withdrawal_ledger.py",
        "20260924_0519_withdrawal_orchestration.py",
        "20260924_0520_withdrawal_provider_ki.py",
    ]:
        spec = importlib.util.spec_from_file_location(
            "migration_" + filename[:13], Path(__file__).parents[1] / "alembic/versions" / filename
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    # Entire schema and DDL are transaction-local and rolled back even on failure.
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        Base.metadata.create_all(
            connection,
            tables=[table for table in Base.metadata.sorted_tables if table.name not in names],
        )
        with Operations.context(MigrationContext.configure(connection)):
            for module in modules:
                module.upgrade()
            for name in names:
                assert {column["name"] for column in inspect(connection).get_columns(name)} == set(
                    Base.metadata.tables[name].columns.keys()
                )
            # Only remove the unrelated document FK in this disposable schema;
            # audit triggers themselves remain installed and exercised by SQL.
            for fk in inspect(connection).get_foreign_keys("withdrawal_observations"):
                connection.execute(
                    text(f'ALTER TABLE withdrawal_observations DROP CONSTRAINT "{fk["name"]}"')
                )
            connection.execute(
                WithdrawalObservation.__table__.insert().values(
                    id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    response_body=b"original",
                    reconciliation_ids=["evidence"],
                )
            )
            for statement in [
                "UPDATE withdrawal_observations SET response_body = decode('00','hex')",
                "UPDATE withdrawal_observations SET incident = 'changed'",
                "DELETE FROM withdrawal_observations",
            ]:
                with (
                    pytest.raises(DBAPIError, match="withdrawal_observation_is_immutable"),
                    connection.begin_nested(),
                ):
                    connection.execute(text(statement))
            assert (
                connection.execute(
                    text("SELECT response_body FROM withdrawal_observations")
                ).scalar()
                == b"original"
            )
            for module in reversed(modules):
                module.downgrade()
            assert not names.intersection(inspect(connection).get_table_names())
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                        "ON p.pronamespace=n.oid WHERE n.nspname=:schema "
                        "AND p.proname LIKE 'protect_withdrawal%'"
                    ),
                    {"schema": schema},
                ).scalar()
                == 0
            )
        transaction.rollback()
    engine.dispose()


def test_deployment_roles_share_image_and_safe_configuration() -> None:
    import tomllib

    import yaml

    root = Path(__file__).parents[2]
    config = yaml.safe_load((root / "docker-compose.prod.yml").read_text())
    services = config["services"]
    keys = [
        "WITHDRAWAL_ENVIRONMENT",
        "WITHDRAWAL_PRODUCTION_SUBMIT_ENABLED",
        "CELERY_BROKER_URL",
        "WMS_SECRETS_FERNET_KEY",
    ]
    expected = {key: services["api"]["environment"][key] for key in keys}
    assert expected["WITHDRAWAL_PRODUCTION_SUBMIT_ENABLED"].endswith(":-false}")
    for role in ["celery_worker", "celery_beat"]:
        assert {key: services[role]["environment"][key] for key in keys} == expected
        assert (
            services[role]["depends_on"]["migrations"]["condition"]
            == "service_completed_successfully"
        )
    for role in ["worker", "beat"]:
        railway = tomllib.loads((root / f"backend/railway.{role}.toml").read_text())
        assert railway["deploy"]["numReplicas"] == 1
        assert f"WMS_SERVICE_ROLE={role}" in railway["deploy"]["startCommand"]
        assert role_command(role) == ["celery", "-A", "app.celery_app", role, "--loglevel=info"]
    assert role_command("api")[0] == "uvicorn"


def test_official_contract_fixture_manifest_is_linked_to_executable_tests() -> None:
    root = Path(__file__).parent
    manifest = json.loads((root / "fixtures/true_api_contract_sources.json").read_text())
    assert manifest["source"] == FIXTURES["source"]
    for row in manifest["contracts"]:
        assert row["path"].startswith(("/api/v3/true-api/", "/api/v4/true-api/"))
        assert row["response"]
        if "fixture" in row:
            assert row["fixture"] in FIXTURES
    refs = [row["test"] for row in manifest["contracts"]] + list(manifest["failure_tests"].values())
    for ref in refs:
        file, name = ref.split("::")
        assert f"def {name}(" in (root / file).read_text()


@pytest.mark.postgresql_concurrency
@pytest.mark.asyncio
async def test_postgresql_recovery_skips_a_locked_document(db_session) -> None:
    from sqlalchemy import select
    from test_withdrawal_ledger import document

    from app.db.session import SessionLocal, engine
    from app.models.marking_withdrawal import WithdrawalDocument
    from app.services.withdrawal_recovery import claim_work

    if engine.dialect.name != "postgresql":
        pytest.skip("Requires explicitly isolated WMS_TEST_DATABASE_URL PostgreSQL")
    _, _, doc = await document(db_session)
    async with SessionLocal() as owner, SessionLocal() as other:
        await owner.scalar(
            select(WithdrawalDocument).where(WithdrawalDocument.id == doc.id).with_for_update()
        )
        assert await claim_work(other) is None
        await owner.rollback()
        first = await claim_work(other)
        assert first is not None
        assert await claim_work(owner) is None  # Persisted lease survives transaction end.


@pytest.mark.asyncio
async def test_old_401_cannot_clear_new_reauthenticated_session(db_session) -> None:
    from test_withdrawal_ledger import document

    from app.services.integration_fernet import encrypt_secret
    from app.services.withdrawal_recovery import apply_recovery, claim_work

    _, operation, _ = await document(db_session)
    work = await claim_work(db_session)
    assert work is not None
    operation.token_enc = encrypt_secret(str(uuid.uuid4()))
    newer = operation.token_enc
    operation.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.commit()
    await apply_recovery(db_session, work, incident="auth_required")
    assert operation.token_enc == newer


@pytest.mark.asyncio
@pytest.mark.parametrize("inn", ["7701234567", "123456789012"])
async def test_sign_in_always_sends_server_inn_and_obeys_crpt_expiry(inn: str) -> None:
    from test_true_api_withdrawal import RecordingLimiter

    expiry = datetime.now(UTC) + timedelta(minutes=2)

    def handler(request):
        assert json.loads(request.content) == {
            "uuid": FIXTURES["auth_key"]["uuid"],
            "data": SIGNATURE,
            "unitedToken": True,
            "inn": inn,
        }
        return httpx.Response(
            200, json={"uuidToken": str(uuid.uuid4()), "expireDate": expiry.isoformat()}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        transport = api.TrueApiWithdrawalClient(
            http, api.TrueApiConfig(api.Environment.SANDBOX), RecordingLimiter(), inn
        )
        auth = await transport.sign_in(
            FIXTURES["auth_key"]["uuid"],
            SIGNATURE,
            certificate_expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    assert auth.expires_at == expiry


@pytest.mark.asyncio
async def test_same_provider_ki_with_different_crypto_tail_cannot_be_claimed_twice(
    db_session,
) -> None:
    from test_withdrawal_ledger import seed

    from app.db.withdrawal_repository import WithdrawalError
    from app.models.fbs_order import FbsOrderMarking
    from app.services.withdrawal_service import create_operation

    scope, marking, order, _ = await seed(db_session)
    original = marking.value
    marking.value = original + "\x1d91first\x1d92crypto"
    await db_session.commit()
    await create_operation(db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4())
    alternate = FbsOrderMarking(
        tenant_id=scope.tenant_id,
        order_id=order.id,
        kind="sgtin",
        value=original + "\x1d91second\x1d92other",
        source="external",
        meta_status="sent",
    )
    db_session.add(alternate)
    await db_session.commit()
    with pytest.raises(WithdrawalError, match="selection_overlaps_existing_operation"):
        await create_operation(
            db_session, scope, row_ids=[alternate.id], client_request_id=uuid.uuid4()
        )
