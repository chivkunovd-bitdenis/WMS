from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.services.background_job_service import JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC


@pytest.mark.asyncio
async def test_wb_supplies_sync_job_happy_path(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_supplies(
        client: object,
        *,
        api_token: str,
        supplies_api_base: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        assert api_token == "wb-supplies-token"
        return [
            {"supplyID": 70001, "preorderID": 80001, "statusID": 5},
            {"supplyID": None, "preorderID": 80002, "statusID": 1},
        ]

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_supplies_list",
        fake_supplies,
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Sup Co",
            "slug": f"wbsup-{suffix}",
            "admin_email": f"wbsup-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "S"})
    sid = s.json()["id"]
    p = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=h,
        json={"supplies_api_token": "wb-supplies-token"},
    )
    assert p.status_code == 200

    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC, "seller_id": sid},
    )
    assert start.status_code == 202
    jid = start.json()["id"]

    for _ in range(40):
        await asyncio.sleep(0.12)
        r = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("done", "failed"):
            assert body["status"] == "done"
            assert body["result_json"]["supplies_received"] == 2
            assert body["result_json"]["supplies_saved"] == 2
            ic = await async_client.get(
                f"/integrations/wildberries/sellers/{sid}/imported-supplies",
                headers=h,
            )
            assert ic.status_code == 200
            keys = {row["external_key"] for row in ic.json()}
            assert keys == {"s:70001", "p:80002"}
            return
    raise AssertionError("job did not finish")


@pytest.mark.asyncio
async def test_wb_supplies_sync_fails_without_token(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Sup Co2",
            "slug": f"wbsup2-{suffix}",
            "admin_email": f"wbsup2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "S2"})
    sid = s.json()["id"]
    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC, "seller_id": sid},
    )
    assert start.status_code == 202
    jid = start.json()["id"]
    for _ in range(40):
        await asyncio.sleep(0.12)
        r = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        body = r.json()
        if body["status"] in ("done", "failed"):
            assert body["status"] == "failed"
            assert body["error_message"] == "missing_supplies_token"
            return
    raise AssertionError("job did not finish")
