from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.core.settings import settings
from app.models.billing import (
    BillingLedgerEntry,
    BillingLedgerLine,
    BillingTariffMatrixConfig,
    BillingTariffServiceState,
    BillingTariffVersionV2,
)
from app.models.operation_fact import OperationFact, OperationFactLine
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User
from app.services.billing_tariff_matrix_service import (
    BillingTariffMatrixError,
    ensure_disabled_tariff_matrix,
    get_tariff_matrix,
    list_tariff_matrix_versions,
    save_tariff_matrix,
)


@pytest.mark.asyncio
async def test_new_tenant_gets_persisted_disabled_matrix_including_storage(async_client) -> None:
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Matrix tenant",
            "slug": f"matrix-{uuid.uuid4().hex}",
            "admin_email": f"matrix-{uuid.uuid4().hex}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    me = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        config = await session.scalar(
            select(BillingTariffMatrixConfig).where(
                BillingTariffMatrixConfig.tenant_id == tenant_id
            )
        )
        assert config is not None
        states = (
            await session.scalars(
                select(BillingTariffServiceState).where(
                    BillingTariffServiceState.tenant_id == tenant_id
                )
            )
        ).all()
    # Хранение переехало в общую матрицу: держать его на отдельном экране
    # означало единственную услугу с другим местом настройки. Сборка заказов FBS
    # пришла туда же — за штуку товара.
    assert {state.service_code for state in states} == {
        "inbound",
        "marketplace_outbound",
        "packing",
        "return",
        "storage",
        "fbs_order",
    }
    assert all(not state.enabled for state in states)


@pytest.mark.asyncio
async def test_matrix_bootstrap_is_idempotent_and_missing_matrix_is_not_silent(
    async_client,
) -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        tenant = Tenant(name="Matrix bootstrap", slug=f"matrix-bootstrap-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        first = await ensure_disabled_tariff_matrix(session, tenant=tenant)
        second = await ensure_disabled_tariff_matrix(session, tenant=tenant)
        assert first.id == second.id
        await session.commit()

    async with SessionLocal() as session:
        loaded = await get_tariff_matrix(session, tenant_id=tenant.id)
        assert loaded.id == first.id
        await session.execute(
            BillingTariffMatrixConfig.__table__.delete().where(
                BillingTariffMatrixConfig.id == first.id
            )
        )
        await session.commit()
        with pytest.raises(BillingTariffMatrixError, match="billing_tariff_matrix_config_missing"):
            await get_tariff_matrix(session, tenant_id=tenant.id)


@pytest.mark.asyncio
async def test_matrix_service_rejects_rate_overflow_before_writing(async_client) -> None:
    from app.db.session import SessionLocal

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)
    services = {
        "inbound": True,
        "marketplace_outbound": False,
        "packing": False,
        "return": False,
    }
    overflow_version = {
        "seller_id": None,
        "product_id": None,
        "employee_user_id": None,
        "service_code": "inbound",
        "unit": "item",
        "enabled": True,
        "rate": 2_147_483_648,
        "valid_from_at": now,
        "valid_to_at": None,
    }
    async with SessionLocal() as session:
        tenant = Tenant(
            id=tenant_id, name="Matrix overflow", slug=f"matrix-overflow-{tenant_id.hex}"
        )
        session.add(tenant)
        await session.flush()
        await ensure_disabled_tariff_matrix(session, tenant=tenant)
        await session.commit()

        with pytest.raises(BillingTariffMatrixError, match="billing_tariff_matrix_rate_invalid"):
            await save_tariff_matrix(
                session,
                tenant_id=tenant_id,
                revision=0,
                services=services,
                versions=[overflow_version],
            )
        await session.rollback()
        persisted = await get_tariff_matrix(session, tenant_id=tenant_id)
        assert persisted.revision == 0
        assert await list_tariff_matrix_versions(session, tenant_id=tenant_id) == []
        await session.delete(tenant)
        await session.commit()


def _postgres_matrix_test_url() -> str:
    url = os.environ.get("WMS_TARIFF_MATRIX_POSTGRES_URL")
    if not url:
        pytest.skip("WMS_TARIFF_MATRIX_POSTGRES_URL required for real PostgreSQL tariff proof")
    return url


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_postgresql_two_sessions_accept_exactly_one_matrix_revision() -> None:
    """Tenant row locking turns the same-revision race into one named stale result."""
    engine = create_async_engine(_postgres_matrix_test_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid.uuid4()
    async with sessions() as session:
        session.add(Tenant(id=tenant_id, name="Matrix race", slug=f"matrix-race-{tenant_id.hex}"))
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        await ensure_disabled_tariff_matrix(session, tenant=tenant)
        await session.commit()

    barrier = asyncio.Barrier(2)
    now = datetime.now(UTC).replace(microsecond=0)
    drafts = {
        "inbound": (
            {
                "inbound": True,
                "marketplace_outbound": False,
                "packing": False,
                "return": False,
            },
            [
                {
                    "seller_id": None,
                    "product_id": None,
                    "employee_user_id": None,
                    "service_code": "inbound",
                    "unit": "item",
                    "enabled": True,
                    "rate": 101,
                    "valid_from_at": now,
                    "valid_to_at": None,
                }
            ],
        ),
        "packing": (
            {
                "inbound": False,
                "marketplace_outbound": False,
                "packing": True,
                "return": False,
            },
            [
                {
                    "seller_id": None,
                    "product_id": None,
                    "employee_user_id": None,
                    "service_code": "packing",
                    "unit": "item",
                    "enabled": True,
                    "rate": 202,
                    "valid_from_at": now + timedelta(minutes=1),
                    "valid_to_at": None,
                }
            ],
        ),
    }

    async def attempt(label: str) -> str:
        services, versions = drafts[label]
        async with sessions() as session:
            await barrier.wait()
            try:
                await save_tariff_matrix(
                    session,
                    tenant_id=tenant_id,
                    revision=0,
                    services=services,
                    versions=versions,
                )
                await session.commit()
                return f"winner:{label}"
            except BillingTariffMatrixError as exc:
                await session.rollback()
                return str(exc)

    try:
        outcomes = await asyncio.gather(attempt("inbound"), attempt("packing"))
        winners = [outcome for outcome in outcomes if outcome.startswith("winner:")]
        assert len(winners) == 1
        assert outcomes.count("billing_tariff_matrix_stale_revision") == 1
        winner = winners[0].removeprefix("winner:")
        async with sessions() as session:
            config = await get_tariff_matrix(session, tenant_id=tenant_id)
            assert config.revision == 1
            states = {state.service_code: state.enabled for state in config.service_states}
            rows = await list_tariff_matrix_versions(session, tenant_id=tenant_id)
            if winner == "inbound":
                assert states == drafts["inbound"][0]
                assert [(row.service_code, row.rate) for row in rows] == [("inbound", 101)]
            else:
                assert states == drafts["packing"][0]
                assert [(row.service_code, row.rate) for row in rows] == [("packing", 202)]
    finally:
        async with sessions() as session:
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_postgresql_composite_ledger_line_foreign_keys_reject_foreign_tenant() -> None:
    """All four referenced ledger-line identities are bound to the line tenant."""
    engine = create_async_engine(_postgres_matrix_test_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    async with sessions() as session:
        session.add_all(
            [
                Tenant(id=tenant_a, name="Matrix FK A", slug=f"matrix-fk-a-{tenant_a.hex}"),
                Tenant(id=tenant_b, name="Matrix FK B", slug=f"matrix-fk-b-{tenant_b.hex}"),
            ]
        )
        await session.flush()
        product_b = Product(tenant_id=tenant_b, name="Foreign product", sku_code="foreign-proof")
        fact_b = OperationFact(
            tenant_id=tenant_b,
            operation_code="proof",
            source_kind="proof",
            source_event_id=uuid.uuid4(),
            document_type="proof",
            document_id=uuid.uuid4(),
            source="system",
            occurred_at=now,
            item_quantity=1,
            integrity_status="complete",
        )
        tariff_b = BillingTariffVersionV2(
            tenant_id=tenant_b,
            service_code="inbound",
            unit="item",
            enabled=True,
            rate=1,
            valid_from_at=now,
        )
        entry_a = BillingLedgerEntry(
            tenant_id=tenant_a,
            service_code="inbound",
            source="proof",
            source_type="proof",
            source_id=uuid.uuid4(),
            event_kind="completed",
            unit="item",
            quantity=Decimal("1"),
            occurred_at=now,
        )
        entry_b = BillingLedgerEntry(
            tenant_id=tenant_b,
            service_code="inbound",
            source="proof",
            source_type="proof",
            source_id=uuid.uuid4(),
            event_kind="completed",
            unit="item",
            quantity=Decimal("1"),
            occurred_at=now,
        )
        session.add_all([product_b, fact_b, tariff_b, entry_a, entry_b])
        await session.flush()
        fact_line_b = OperationFactLine(
            tenant_id=tenant_b,
            operation_fact_id=fact_b.id,
            product_id=product_b.id,
            item_quantity=1,
        )
        session.add(fact_line_b)
        await session.flush()

        async def rejects_foreign(**foreign_ref: uuid.UUID) -> None:
            nested = await session.begin_nested()
            references = {"ledger_entry_id": entry_a.id, **foreign_ref}
            session.add(
                BillingLedgerLine(
                    tenant_id=tenant_a,
                    product_snapshot={},
                    physical_quantity=Decimal("1"),
                    billing_quantity=Decimal("1"),
                    billing_unit="item",
                    tariff_snapshot={},
                    rate=1,
                    amount=1,
                    **references,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await nested.rollback()

        await rejects_foreign(ledger_entry_id=entry_b.id)
        await rejects_foreign(operation_fact_line_id=fact_line_b.id)
        await rejects_foreign(product_id=product_b.id)
        await rejects_foreign(tariff_version_v2_id=tariff_b.id)
        await session.rollback()

    async with sessions() as session:
        await session.execute(delete(Tenant).where(Tenant.id.in_((tenant_a, tenant_b))))
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_postgresql_v2_scope_check_rejects_invalid_direct_inserts() -> None:
    engine = create_async_engine(_postgres_matrix_test_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with sessions() as session:
        session.add(Tenant(id=tenant_id, name="Matrix check", slug=f"matrix-check-{tenant_id.hex}"))
        await session.flush()
        employee = User(
            tenant_id=tenant_id,
            email=f"check-{tenant_id.hex}@example.test",
            password_hash="test",
            role="fulfillment_staff",
        )
        product = Product(tenant_id=tenant_id, name="Check product", sku_code="check-product")
        session.add_all([employee, product])
        await session.flush()

        async def rejects(**values: object) -> None:
            nested = await session.begin_nested()
            session.add(
                BillingTariffVersionV2(tenant_id=tenant_id, rate=1, valid_from_at=now, **values)
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await nested.rollback()

        await rejects(service_code="storage_liter_day", unit="item", enabled=True)
        await rejects(service_code="picking", unit="item", enabled=True)
        await rejects(
            employee_user_id=employee.id,
            service_code="packing",
            unit="item",
            enabled=True,
        )
        await rejects(
            employee_user_id=employee.id,
            product_id=product.id,
            service_code="inbound",
            unit="item",
            enabled=True,
        )
        await rejects(
            product_id=product.id,
            service_code="inbound",
            unit="item",
            enabled=True,
        )
        await session.rollback()
    async with sessions() as session:
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await session.commit()
    await engine.dispose()


@pytest.mark.postgresql_concurrency
def test_postgresql_0113_isolated_upgrade_downgrade_reupgrade() -> None:
    raw_url = os.environ.get("WMS_TARIFF_MATRIX_MIGRATION_DATABASE_URL")
    if not raw_url:
        pytest.skip("WMS_TARIFF_MATRIX_MIGRATION_DATABASE_URL required for isolated Alembic proof")
    migration_url = make_url(raw_url)
    admin_url = migration_url
    if admin_url.drivername == "postgresql+psycopg_async":
        admin_url = admin_url.set(drivername="postgresql+psycopg")
    database_name = f"wms_2b_migration_{uuid.uuid4().hex}"
    test_url = admin_url.set(database=database_name)
    admin = create_engine(admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url",
        migration_url.set(database=database_name).render_as_string(hide_password=False),
    )
    previous_database_url = os.environ.get("DATABASE_URL")
    migration_async_url = migration_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    os.environ["DATABASE_URL"] = migration_async_url
    previous_settings_url = settings.database_url
    object.__setattr__(settings, "database_url", migration_async_url)
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {database_name}"))
        command.upgrade(cfg, "20260826_0110")
        engine = create_engine(test_url)
        tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenants (id,name,slug) VALUES (:id,'migration',:slug)"),
                {"id": tenant_id, "slug": f"migration-{tenant_id.hex}"},
            )
            conn.execute(
                text("INSERT INTO sellers (id,tenant_id,name) VALUES (:id,:tenant,'seller')"),
                {"id": seller_id, "tenant": tenant_id},
            )
            conn.execute(
                text(
                    "INSERT INTO billing_tariff_versions (id,tenant_id,seller_id,service_code,unit,amount,valid_from,valid_to) VALUES (:id,:tenant,NULL,'inbound','item',125,DATE '2010-03-28',DATE '2010-03-28'),(:seller_row,:tenant,:seller,'marketplace_outbound','document',900,DATE '2010-03-27',NULL)"  # noqa: E501
                ),
                {
                    "id": uuid.uuid4(),
                    "seller_row": uuid.uuid4(),
                    "tenant": tenant_id,
                    "seller": seller_id,
                },
            )
        command.upgrade(cfg, "20260826_0112")
        command.upgrade(cfg, "20260827_0113")
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT rate,valid_from_at,valid_to_at FROM billing_tariff_versions_v2 ORDER BY rate"  # noqa: E501
                )
            ).all()
            assert [(row.rate, row.valid_from_at, row.valid_to_at) for row in rows] == [
                (125, datetime(2010, 3, 27, 21, tzinfo=UTC), datetime(2010, 3, 28, 20, tzinfo=UTC)),
                (900, datetime(2010, 3, 26, 21, tzinfo=UTC), None),
            ]
            names = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE conname IN ('ck_billing_tariff_v2_scope','ex_billing_tariff_v2_common_interval','fk_billing_ledger_lines_tenant_entry')"  # noqa: E501
                    )
                )
            }
            assert names == {
                "ck_billing_tariff_v2_scope",
                "ex_billing_tariff_v2_common_interval",
                "fk_billing_ledger_lines_tenant_entry",
            }
            assert "uq_billing_tariff_v2_common_start" in {
                item["name"] for item in inspect(conn).get_indexes("billing_tariff_versions_v2")
            }
        command.downgrade(cfg, "20260826_0112")
        command.upgrade(cfg, "20260827_0113")
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM billing_tariff_versions_v2")) == 2
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        object.__setattr__(settings, "database_url", previous_settings_url)
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name"
                ),
                {"name": database_name},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {database_name}"))
        admin.dispose()
