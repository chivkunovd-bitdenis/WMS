from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient

from app.services.background_job_service import JOB_TYPE_WILDBERRIES_CARDS_SYNC


@pytest.mark.asyncio
async def test_wb_cards_sync_job_happy_path(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(
        client: object,
        *,
        api_token: str,
        content_api_base: str | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        assert api_token == "wb-secret-token"
        return {"cards": [{"nmID": 1}, {"nmID": 2}], "cursor": {"limit": 100}}

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_cards_list",
        fake_fetch,
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Sync Co",
            "slug": f"wbs-{suffix}",
            "admin_email": f"wbs-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "SellerWB"})
    sid = s.json()["id"]
    p = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=h,
        json={"content_api_token": "wb-secret-token"},
    )
    assert p.status_code == 200

    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": sid},
    )
    assert start.status_code == 202, start.text
    jid = start.json()["id"]

    for _ in range(40):
        await asyncio.sleep(0.12)
        r = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert "payload_json" in body
        assert body["payload_json"] == {"seller_id": sid}
        if body["status"] in ("done", "failed"):
            assert body["status"] == "done"
            assert body["result_json"]["cards_received"] == 2
            assert body["result_json"]["cards_saved"] == 2
            assert body["result_json"]["seller_id"] == sid
            assert body["result_json"]["cursor_present"] is True
            ic = await async_client.get(
                f"/integrations/wildberries/sellers/{sid}/imported-cards",
                headers=h,
            )
            assert ic.status_code == 200
            rows = ic.json()
            assert len(rows) == 2
            assert {r["nm_id"] for r in rows} == {1, 2}
            return
    raise AssertionError("job did not finish")


@pytest.mark.asyncio
async def test_wb_cards_sync_job_fails_without_content_token(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Sync Co2",
            "slug": f"wbs2-{suffix}",
            "admin_email": f"wbs2-adm-{suffix}@example.com",
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
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": sid},
    )
    assert start.status_code == 202
    jid = start.json()["id"]

    for _ in range(40):
        await asyncio.sleep(0.12)
        r = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("done", "failed"):
            assert body["status"] == "failed"
            assert body["error_message"] == "missing_content_token"
            return
    raise AssertionError("job did not finish")


@pytest.mark.asyncio
async def test_wb_cards_sync_start_validation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Sync Co3",
            "slug": f"wbs3-{suffix}",
            "admin_email": f"wbs3-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    r = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "seller_id_required"

    r2 = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={
            "job_type": "movements_digest",
            "seller_id": str(uuid.uuid4()),
        },
    )
    assert r2.status_code == 422
    assert r2.json()["detail"] == "seller_id_not_allowed"

    missing = uuid.UUID("00000000-0000-4000-8000-000000000088")
    r3 = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": str(missing)},
    )
    assert r3.status_code == 404
