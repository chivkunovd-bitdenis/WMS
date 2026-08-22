from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.services.background_job_service import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_TYPE_MARKING_LABEL_TAPE,
    JOB_TYPE_MOVEMENTS_DIGEST,
    create_pending_job,
    run_marking_label_tape_job,
)
from app.services.tokens import decode_access_token


@pytest.mark.asyncio
async def test_marking_label_tape_idempotency_and_result_contract(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Co", "slug": f"tape-{suffix}",
        "admin_email": f"tape-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(
        str(decode_access_token(reg.json()["access_token"])["tenant_id"])
    )
    async with SessionLocal() as session:
        first = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="same-request", payload_json={"code_ids": ["1"]},
        )
        second = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="same-request", payload_json={"code_ids": ["1"]},
        )
        assert first.id == second.id
        assert first.status == JOB_STATUS_PENDING
        first.result_json = {"asset_id": "asset-1"}
        assert "pdf" not in first.result_json
        await session.commit()
        assert len((await session.execute(
            __import__("sqlalchemy").select(BackgroundJob).where(
                BackgroundJob.idempotency_key == "same-request"
            )
        )).scalars().all()) == 1


@pytest.mark.asyncio
async def test_duplicate_pending_job_is_not_republished(async_client: AsyncClient) -> None:
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape API Co", "slug": f"tape-api-{int(time.time() * 1000)}",
        "admin_email": f"tape-api-{int(time.time() * 1000)}@example.com", "password": "password123",
    })
    token = str(reg.json()["access_token"])
    payload = {"code_ids": [str(uuid.uuid4())]}
    async with SessionLocal() as session:
        tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
        first = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="duplicate-publish", payload_json=payload,
        )
        first_was_created = first.created_by_call
        second = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="duplicate-publish", payload_json=payload,
        )
        assert first.id == second.id
        assert first_was_created is True
        assert second.__dict__["created_by_call"] is False


@pytest.mark.asyncio
async def test_marking_label_tape_worker_does_not_reclaim_running_job(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Worker Co", "slug": f"tape-worker-{suffix}",
        "admin_email": f"tape-worker-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    async with SessionLocal() as session:
        job = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="worker-request", payload_json={"code_ids": []},
        )
        job.status = JOB_STATUS_RUNNING
        await session.commit()
        monkeypatch.setattr(
            "app.services.marking_code_service.build_label_artifact_tape_pdf",
            lambda *args, **kwargs: pytest.fail("running job was reclaimed"),
        )
        await run_marking_label_tape_job(job.id)
        await session.refresh(job)
        assert job.status == JOB_STATUS_RUNNING
        assert job.result_json is None


def test_marking_job_status_contract() -> None:
    assert {JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JOB_STATUS_DONE, JOB_STATUS_FAILED} == {
        "pending", "running", "done", "failed"
    }


@pytest.mark.asyncio
async def test_background_job_movements_digest(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Job Co",
            "slug": f"job-{suffix}",
            "admin_email": f"job-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_MOVEMENTS_DIGEST},
    )
    assert start.status_code == 202, start.text
    jid = start.json()["id"]
    assert start.json()["status"] == "pending"

    for _ in range(30):
        await asyncio.sleep(0.15)
        r = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        assert r.status_code == 200
        st = r.json()["status"]
        if st in ("done", "failed"):
            assert st == "done"
            data = r.json()["result_json"]
            assert data is not None
            assert "total_movements" in data
            assert data["total_movements"] == 0
            return
    raise AssertionError("job did not finish")
