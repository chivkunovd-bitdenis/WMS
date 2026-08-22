from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.services.background_job_service import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_TYPE_MARKING_LABEL_TAPE,
    JOB_TYPE_MOVEMENTS_DIGEST,
    MARKING_LABEL_TAPE_RUNNING_LEASE,
    create_pending_job,
    purge_expired_label_tape_assets,
    run_marking_label_tape_job,
    should_enqueue_marking_label_tape_job,
)
from app.services.tokens import decode_access_token


def test_label_tape_and_expiry_cleanup_share_print_queue() -> None:
    from app.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["wms.marking_label_tape"] == {"queue": "print"}
    assert routes["wms.purge_expired_label_tape_assets"] == {"queue": "print"}


def test_marking_label_tape_enqueue_failure_keeps_request_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.marking_codes import _enqueue_marking_label_tape_job

    def broker_down(*args: object, **kwargs: object) -> None:
        raise ConnectionError("broker_unavailable")

    monkeypatch.setattr(
        "app.tasks.background_jobs.run_marking_label_tape_task.apply_async", broker_down
    )

    # Publishing is deliberately best-effort: the active row remains pending
    # and the next identical request safely republishes it.
    _enqueue_marking_label_tape_job(uuid.uuid4())


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
async def test_duplicate_pending_job_is_republished_without_creating_a_second_job(
    async_client: AsyncClient,
) -> None:
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
        first_was_created = first.__dict__["created_by_call"]
        second = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="duplicate-publish", payload_json=payload,
        )
        assert first.id == second.id
        assert first_was_created is True
        assert second.__dict__["created_by_call"] is False
        assert should_enqueue_marking_label_tape_job(second) is True


@pytest.mark.asyncio
async def test_done_marking_job_is_reused_while_asset_is_available(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Retry Co", "slug": f"tape-retry-{suffix}",
        "admin_email": f"tape-retry-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(
        str(decode_access_token(reg.json()["access_token"])["tenant_id"])
    )
    async with SessionLocal() as session:
        first = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="retryable-request", payload_json={"code_ids": ["1"]},
        )
        from app.models.fbs_print_asset import (
            PRINT_ASSET_KIND_LABEL_TAPE,
            PRINT_ASSET_STATUS_READY,
            FbsPrintAsset,
        )
        from app.models.seller import Seller

        seller = Seller(tenant_id=tenant_id, name="Tape seller")
        session.add(seller)
        await session.flush()
        asset = FbsPrintAsset(
            tenant_id=tenant_id,
            seller_id=seller.id,
            kind=PRINT_ASSET_KIND_LABEL_TAPE,
            status=PRINT_ASSET_STATUS_READY,
            storage_path="fbs-print-assets/label-tapes/ready.pdf",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )
        session.add(asset)
        await session.flush()
        first.status = JOB_STATUS_DONE
        first.result_json = {"asset_id": str(asset.id)}
        await session.commit()

        second = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="retryable-request", payload_json={"code_ids": ["1"]},
        )

        assert second.id == first.id
        assert second.status == JOB_STATUS_DONE
        assert second.__dict__["created_by_call"] is False
        assert should_enqueue_marking_label_tape_job(second) is False


@pytest.mark.asyncio
async def test_failed_marking_job_can_be_retried_with_same_idempotency_key(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Failed Co", "slug": f"tape-failed-{suffix}",
        "admin_email": f"tape-failed-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    async with SessionLocal() as session:
        first = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="failed-request", payload_json={"code_ids": ["1"]},
        )
        first.status = JOB_STATUS_FAILED
        await session.commit()

        second = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="failed-request", payload_json={"code_ids": ["1"]},
        )

        assert second.id != first.id
        assert second.status == JOB_STATUS_PENDING
        assert second.__dict__["created_by_call"] is True


@pytest.mark.asyncio
async def test_expired_tape_cleanup_retains_audit_row_and_releases_request_key(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.fbs_print_asset import (
        PRINT_ASSET_KIND_LABEL_TAPE,
        PRINT_ASSET_STATUS_READY,
        FbsPrintAsset,
    )
    from app.models.seller import Seller

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Audit Co", "slug": f"tape-audit-{suffix}",
        "admin_email": f"tape-audit-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    deleted_paths: list[str] = []
    monkeypatch.setattr(
        "app.services.fbs_print_asset_storage.delete_stored_asset",
        deleted_paths.append,
    )

    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant_id, name="Tape audit seller")
        session.add(seller)
        await session.flush()
        asset = FbsPrintAsset(
            tenant_id=tenant_id,
            seller_id=seller.id,
            kind=PRINT_ASSET_KIND_LABEL_TAPE,
            status=PRINT_ASSET_STATUS_READY,
            storage_path="fbs-print-assets/label-tapes/expired.pdf",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(asset)
        await session.flush()
        job = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="expired-request", payload_json={"code_ids": ["1"]},
        )
        job.status = JOB_STATUS_DONE
        job.result_json = {"asset_id": str(asset.id)}
        asset_id = asset.id
        job_id = job.id
        await session.commit()

    assert await purge_expired_label_tape_assets() == 1
    assert await purge_expired_label_tape_assets() == 0
    assert deleted_paths == ["fbs-print-assets/label-tapes/expired.pdf"]

    async with SessionLocal() as session:
        retained_asset = await session.get(FbsPrintAsset, asset_id)
        retained_job = await session.get(BackgroundJob, job_id)
        assert retained_asset is not None
        assert retained_asset.storage_path is None
        assert retained_job is not None
        assert retained_job.result_json == {"asset_id": str(asset_id)}

        retry = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="expired-request", payload_json={"code_ids": ["1"]},
        )
        assert retry.id != job_id
        assert retry.status == JOB_STATUS_PENDING


@pytest.mark.asyncio
async def test_marking_label_tape_worker_does_not_reclaim_fresh_running_job(
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
        job.started_at = datetime.now(UTC)
        await session.commit()
        monkeypatch.setattr(
            "app.services.marking_code_service.build_label_artifact_tape_pdf",
            lambda *args, **kwargs: pytest.fail("running job was reclaimed"),
        )
        await run_marking_label_tape_job(job.id)
        await session.refresh(job)
        assert job.status == JOB_STATUS_RUNNING
        assert job.result_json is None


@pytest.mark.asyncio
async def test_marking_label_tape_worker_reclaims_stale_running_job(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Recovery Co", "slug": f"tape-recovery-{suffix}",
        "admin_email": f"tape-recovery-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    async with SessionLocal() as session:
        job = await create_pending_job(
            session, tenant_id, job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="stale-worker-request", payload_json={"code_ids": []},
        )
        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC) - MARKING_LABEL_TAPE_RUNNING_LEASE - timedelta(seconds=1)
        await session.commit()

        async def interrupted_build(*args: object, **kwargs: object) -> bytes:
            raise RuntimeError("recovered_stale_job")

        monkeypatch.setattr(
            "app.services.marking_code_service.build_label_artifact_tape_pdf",
            interrupted_build,
        )
        await run_marking_label_tape_job(job.id)
        await session.refresh(job)
        assert job.status == JOB_STATUS_FAILED
        assert job.error_message == "recovered_stale_job"


@pytest.mark.asyncio
async def test_marking_label_tape_heartbeat_prevents_duplicate_worker_and_asset(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.fbs_print_asset import FbsPrintAsset
    from app.models.marking_code import MarkingCode
    from app.models.seller import Seller

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Heartbeat Co", "slug": f"tape-heartbeat-{suffix}",
        "admin_email": f"tape-heartbeat-{suffix}@example.com", "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    build_started = asyncio.Event()
    finish_build = asyncio.Event()
    build_calls = 0

    async def slow_build(*args: object, **kwargs: object) -> bytes:
        nonlocal build_calls
        build_calls += 1
        build_started.set()
        await finish_build.wait()
        return b"one-pdf"

    monkeypatch.setattr(
        "app.services.background_job_service.MARKING_LABEL_TAPE_RUNNING_LEASE",
        timedelta(milliseconds=80),
    )
    monkeypatch.setattr(
        "app.services.background_job_service.MARKING_LABEL_TAPE_HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "app.services.marking_code_service.build_label_artifact_tape_pdf",
        slow_build,
    )
    monkeypatch.setattr(
        "app.services.fbs_print_asset_storage.save_pdf",
        lambda path, content: path,
    )

    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant_id, name="Heartbeat seller")
        session.add(seller)
        await session.flush()
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller.id,
            cis_code="010460000000000121HEARTBEAT",
        )
        session.add(code)
        await session.flush()
        job = await create_pending_job(
            session,
            tenant_id,
            job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="heartbeat-request",
            payload_json={"code_ids": [str(code.id)]},
        )
        job_id = job.id

    first_worker = asyncio.create_task(run_marking_label_tape_job(job_id))
    await asyncio.wait_for(build_started.wait(), timeout=1)
    await asyncio.sleep(0.12)
    await run_marking_label_tape_job(job_id)
    finish_build.set()
    await first_worker

    async with SessionLocal() as session:
        completed = await session.get(BackgroundJob, job_id)
        asset_count = await session.scalar(
            select(func.count(FbsPrintAsset.id)).where(FbsPrintAsset.tenant_id == tenant_id)
        )
        assert completed is not None
        assert completed.status == JOB_STATUS_DONE
        assert build_calls == 1
        assert asset_count == 1


@pytest.mark.asyncio
async def test_marking_label_tape_worker_losing_lease_preserves_new_owner_result(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.fbs_print_asset import (
        PRINT_ASSET_KIND_LABEL_TAPE,
        PRINT_ASSET_STATUS_READY,
        FbsPrintAsset,
    )
    from app.models.marking_code import MarkingCode
    from app.models.seller import Seller

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Tape Lease Transfer Co",
        "slug": f"tape-lease-transfer-{suffix}",
        "admin_email": f"tape-lease-transfer-{suffix}@example.com",
        "password": "password123",
    })
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    build_started = asyncio.Event()
    new_owner_finished = asyncio.Event()
    release_old_worker = asyncio.Event()

    async def stalled_build(*args: object, **kwargs: object) -> bytes:
        build_started.set()
        await release_old_worker.wait()
        return b"%PDF-old-worker"

    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant_id, name="Lease transfer seller")
        session.add(seller)
        await session.flush()
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller.id,
            cis_code="010460000000000121LEASETRANSFER",
        )
        session.add(code)
        await session.flush()
        job = await create_pending_job(
            session,
            tenant_id,
            job_type=JOB_TYPE_MARKING_LABEL_TAPE,
            idempotency_key="lease-transfer-request",
            payload_json={"code_ids": [str(code.id)]},
        )
        job_id = job.id
        seller_id = seller.id

    async def transfer_lease_and_publish_result(
        refreshed_job_id: uuid.UUID,
        expected_started_at: datetime,
    ) -> datetime | None:
        del expected_started_at
        async with SessionLocal() as takeover_session:
            asset = FbsPrintAsset(
                tenant_id=tenant_id,
                seller_id=seller_id,
                kind=PRINT_ASSET_KIND_LABEL_TAPE,
                status=PRINT_ASSET_STATUS_READY,
                content_type="application/pdf",
                storage_path="fbs-print-assets/label-tapes/new-owner.pdf",
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            )
            takeover_session.add(asset)
            await takeover_session.flush()
            taken_over = await takeover_session.get(BackgroundJob, refreshed_job_id)
            assert taken_over is not None
            taken_over.started_at = datetime.now(UTC)
            taken_over.status = JOB_STATUS_DONE
            taken_over.result_json = {"asset_id": str(asset.id)}
            taken_over.error_message = None
            taken_over.finished_at = datetime.now(UTC)
            await takeover_session.commit()
        new_owner_finished.set()
        return None

    monkeypatch.setattr(
        "app.services.background_job_service.MARKING_LABEL_TAPE_HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "app.services.background_job_service._refresh_marking_label_tape_lease",
        transfer_lease_and_publish_result,
    )
    monkeypatch.setattr(
        "app.services.marking_code_service.build_label_artifact_tape_pdf",
        stalled_build,
    )

    old_worker = asyncio.create_task(run_marking_label_tape_job(job_id))
    await asyncio.wait_for(build_started.wait(), timeout=1)
    await asyncio.wait_for(new_owner_finished.wait(), timeout=1)
    release_old_worker.set()
    await old_worker

    async with SessionLocal() as session:
        preserved = await session.get(BackgroundJob, job_id)
        assets = list(
            (
                await session.scalars(
                    select(FbsPrintAsset).where(FbsPrintAsset.tenant_id == tenant_id)
                )
            ).all()
        )
        assert preserved is not None
        assert preserved.status == JOB_STATUS_DONE
        assert preserved.result_json == {"asset_id": str(assets[0].id)}
        assert preserved.error_message is None
        assert len(assets) == 1


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
