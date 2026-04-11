from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.services.background_job_service import JOB_TYPE_MOVEMENTS_DIGEST


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
