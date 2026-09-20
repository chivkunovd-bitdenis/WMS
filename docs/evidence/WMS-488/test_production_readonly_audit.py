"""Synthetic checks of the C9/C11 evidence tool, not product acceptance.

From backend with PYTHONPATH=.: python -m pytest -q \
  ../docs/evidence/WMS-488/test_production_readonly_audit.py
No production database, credentials, task execution, or external requests.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated

# Explicit synthetic settings before any application module is imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "synthetic-wms488-test-secret-at-least-32-characters"

import pytest
import pytest_asyncio
from app.api.background_jobs import get_background_job
from app.api.deps import get_current_user
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models import Base
from app.models.background_job import BackgroundJob
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_MODULE_PATH = Path(__file__).with_name("production_readonly_audit.py")
_SPEC = importlib.util.spec_from_file_location(
    "wms488_production_readonly_audit", _MODULE_PATH
)
assert _SPEC and _SPEC.loader
AUDIT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = AUDIT
_SPEC.loader.exec_module(AUDIT)


@pytest_asyncio.fixture
async def fixture_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    private = ["DO_NOT_LOG_PAYLOAD", "DO_NOT_LOG_RESULT", "DO_NOT_LOG_ERROR"]
    async with factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(), name="Private synthetic tenant", slug=AUDIT.AVPACK_SLUG
        )
        home = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Private home")
        foreign = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Private other")
        session.add_all([tenant, home, foreign])
        for index, (role, manager) in enumerate(
            [
                (FULFILLMENT_SELLER, False),
                (FULFILLMENT_SELLER, True),
                (FULFILLMENT_ADMIN, False),
            ]
        ):
            user = User(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                seller_id=home.id if role == FULFILLMENT_SELLER else None,
                role=role,
                email=f"private-{index}@example.invalid",
                password_hash="fixture",
                can_manage_seller_shops=manager,
            )
            private += [str(user.id), user.email]
            session.add(user)
        fixtures = [
            ("wildberries_cards_sync", str(home.id)),
            ("storage_measurement_rebuild", str(home.id)),
            ("wildberries_cards_sync", str(foreign.id)),
            ("movements_digest", None),
            ("wildberries_cards_sync", "malformed-owner"),
            ("fbs_label_print", str(home.id)),
            ("inbound_marking_check", None),
            ("future_ff_job", str(home.id)),
        ]
        for kind, scope in fixtures:
            payload = {"marker": private[0]}
            if scope is not None:
                payload["seller_id"] = scope
            job = BackgroundJob(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                job_type=kind,
                status="done",
                payload_json=payload,
                result_json={"marker": private[1]},
                error_message=private[2],
            )
            private.append(str(job.id))
            session.add(job)
        private += [
            str(tenant.id),
            str(home.id),
            str(foreign.id),
            home.name,
            foreign.name,
        ]
        await session.commit()
    yield factory, private
    await engine.dispose()


def synthetic_policy_router(*, broken=None):
    """A known-safe or deliberately broken contract to validate the checker."""
    router = APIRouter(prefix="/operations/background-jobs")

    @router.get("/{job_id}")
    async def read(
        job_id: uuid.UUID,
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ):
        job = await session.get(BackgroundJob, job_id)
        assert job is not None
        scope = AUDIT.as_uuid((job.payload_json or {}).get("seller_id"))
        if user.role == FULFILLMENT_SELLER and (
            job.job_type not in AUDIT.SELLER_JOB_TYPES or scope != user.seller_id
        ):
            if broken == "denial-with-private-fields":
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=404,
                    content={"detail": {"result_json": job.result_json}},
                )
            if broken == "allow-foreign":
                return {
                    "payload_json": job.payload_json,
                    "result_json": job.result_json,
                    "error_message": job.error_message,
                }
            raise HTTPException(404, "job_not_found")
        return await get_background_job(job_id, user, session)

    return router


def assert_redacted(output, private):
    rendered = json.dumps(output)
    for value in private:
        assert value not in rendered
    assert "payload_json" not in rendered
    assert "result_json" not in rendered
    assert "error_message" not in rendered
    assert "/operations/background-jobs/" not in rendered


@pytest.mark.asyncio
async def test_job_probe_accepts_safe_contract_and_redacts_every_record(fixture_db):
    factory, private = fixture_db
    output = await AUDIT.run_audit(
        factory, include_catalog=False, job_router=synthetic_policy_router()
    )
    assert {row["verdict"] for row in output} == {"pass"}
    seller_rows = [row for row in output if "manager" in row]
    assert {(row["manager"], row["scenario"]) for row in seller_rows} == {
        (manager, scenario)
        for manager in (False, True)
        for scenario in AUDIT.JOB_CLASSES
    }
    assert all(1 <= row["checked"] <= row["available"] for row in output)
    assert_redacted(output, private)


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["denial-with-private-fields", "allow-foreign"])
async def test_probe_detects_leaky_response_without_logging_it(fixture_db, broken):
    factory, private = fixture_db
    output = await AUDIT.run_audit(
        factory,
        include_catalog=False,
        job_router=synthetic_policy_router(broken=broken),
    )
    assert any(row["verdict"] == "fail" for row in output)
    assert_redacted(output, private)


@pytest.mark.asyncio
async def test_absent_job_class_is_not_accepted_as_pass(fixture_db):
    factory, private = fixture_db
    async with factory() as session:
        await session.execute(text("DELETE FROM background_jobs"))
        await session.commit()
    output = await AUDIT.run_audit(
        factory, include_catalog=False, job_router=synthetic_policy_router()
    )
    seller_rows = [row for row in output if "manager" in row]
    assert len(seller_rows) == 8
    assert AUDIT.combined_verdict(output) == "not-covered"
    assert all(
        row["verdict"] == "not-covered" and row["checked"] == 0 for row in seller_rows
    )
    assert_redacted(output, private)


@pytest.mark.asyncio
async def test_readonly_session_blocks_accidental_write(fixture_db):
    factory, _ = fixture_db
    async with AUDIT.readonly_session(factory) as session:
        count_before = len((await session.scalars(select(BackgroundJob.id))).all())
        with pytest.raises(DBAPIError):
            await session.execute(text("DELETE FROM background_jobs"))
    async with AUDIT.readonly_session(factory) as session:
        assert (
            len((await session.scalars(select(BackgroundJob.id))).all()) == count_before
        )


@pytest.mark.asyncio
async def test_current_product_is_observed_separately_from_tool_self_tests(
    fixture_db, capsys
):
    factory, private = fixture_db
    output = await AUDIT.run_audit(factory, include_catalog=False)
    # The tool must survive either side of a future product fix. This observation
    # deliberately does not make a hard-coded vulnerable version a required test.
    assert all(row["verdict"] in {"pass", "fail"} for row in output)
    assert_redacted(output, private)
    print(
        json.dumps(
            {
                "current_product_c11": AUDIT.combined_verdict(output),
                "checks": [
                    {"scenario": row["scenario"], "verdict": row["verdict"]}
                    for row in output
                ],
            }
        )
    )
    captured = capsys.readouterr()
    assert "current_product_c11" in captured.out


def test_sample_includes_oldest_newest_and_each_type():
    home = uuid.uuid4()
    jobs = [
        AUDIT.JobReference(uuid.uuid4(), "wildberries_cards_sync", home, False, None)
        for _ in range(10)
    ]
    other_type = AUDIT.JobReference(
        uuid.uuid4(), "storage_measurement_rebuild", home, False, None
    )
    selected = AUDIT.sample_jobs([*jobs, other_type])
    assert jobs[0] in selected and jobs[-1] in selected and other_type in selected
    assert len(selected) == 4
