"""WMS-639 R4-R6: read-only machine access of the dispatcher agent to developer requests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.developer_request import DeveloperRequest
from tests.test_developer_requests import _body, _create, _row, _user

KEY = "k" * 40
AGENT = {"X-Support-Agent-Key": KEY}


@pytest.fixture(autouse=True)
def _agent_key(monkeypatch):
    monkeypatch.setattr(settings, "support_agent_key", KEY)


@pytest.mark.asyncio
async def test_agent_reads_requests_of_all_clients_with_all_fields(async_client):
    _, headers_a = await _user()
    _, headers_b = await _user()
    bug = await _create(
        async_client, headers_a, description="Не открывается поставка", page_url="/fbs/supplies?x=1"
    )
    improvement = await _create(
        async_client,
        headers_b,
        type="improvement",
        screen="Упаковка",
        problem="Много кликов",
        proposal="Одна кнопка",
    )
    listed = await async_client.get("/support-agent/developer-requests", headers=AGENT)
    assert listed.status_code == 200
    rows = {row["id"]: row for row in listed.json()}
    assert set(rows) == {str(bug), str(improvement)}
    one = rows[str(bug)]
    assert one["type"] == "bug" and one["description"] == "Не открывается поставка"
    assert one["page_url"] == "/fbs/supplies" and one["client_name"].startswith("Клиент Alpha")
    assert one["delivery_state"] == "pending" and one["trello_card_id"] is None
    assert one["created_at"] and one["status"] == "review"
    assert rows[str(improvement)]["proposal"] == "Одна кнопка"
    for forbidden in ("tenant_id", "created_by_user_id", "idempotency_key", "payload_hash"):
        assert forbidden not in one
    single = await async_client.get(f"/support-agent/developer-requests/{bug}", headers=AGENT)
    assert single.status_code == 200 and single.json()["id"] == str(bug)
    missing = await async_client.get(
        f"/support-agent/developer-requests/{uuid.uuid4()}", headers=AGENT
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_cursor_returns_only_newer_records_oldest_first(async_client):
    _, headers = await _user()
    ids = [await _create(async_client, headers, description=f"Ошибка {i}") for i in range(3)]
    first = (
        await async_client.get("/support-agent/developer-requests?limit=2", headers=AGENT)
    ).json()
    assert [row["id"] for row in first] == [str(ids[0]), str(ids[1])]
    cursor = first[-1]
    rest = (
        await async_client.get(
            "/support-agent/developer-requests",
            headers=AGENT,
            params={"after_created_at": cursor["created_at"], "after_id": cursor["id"]},
        )
    ).json()
    assert [row["id"] for row in rest] == [str(ids[2])]
    assert (
        await async_client.get("/support-agent/developer-requests?limit=0", headers=AGENT)
    ).status_code == 422


@pytest.mark.asyncio
async def test_key_is_required_wrong_key_rejected_and_off_without_key(async_client, monkeypatch):
    path = "/support-agent/developer-requests"
    assert (await async_client.get(path)).status_code == 401
    assert (
        await async_client.get(path, headers={"X-Support-Agent-Key": "x" * 40})
    ).status_code == 401
    monkeypatch.setattr(settings, "support_agent_key", None)
    assert (await async_client.get(path, headers=AGENT)).status_code == 404
    monkeypatch.setattr(settings, "support_agent_key", "short")
    short = {"X-Support-Agent-Key": "short"}
    assert (await async_client.get(path, headers=short)).status_code == 404


@pytest.mark.asyncio
async def test_key_does_not_open_user_endpoints_and_cannot_write(async_client):
    author, headers = await _user()
    request_id = await _create(async_client, headers)
    for call in (
        async_client.get("/developer-requests", headers=AGENT),
        async_client.get(f"/developer-requests/{request_id}", headers=AGENT),
        async_client.post("/developer-requests", headers=AGENT, json=_body()),
        async_client.post("/support-agent/developer-requests", headers=AGENT, json=_body()),
        async_client.patch(f"/support-agent/developer-requests/{request_id}", headers=AGENT),
        async_client.delete(f"/support-agent/developer-requests/{request_id}", headers=AGENT),
        async_client.put(f"/support-agent/developer-requests/{request_id}", headers=AGENT),
    ):
        assert (await call).status_code in (401, 404, 405)
    # The existing user contour (WMS-624 R10) is unchanged: another author still gets 404.
    _, other = await _user()
    assert (
        await async_client.get(f"/developer-requests/{request_id}", headers=other)
    ).status_code == 404
    assert (
        await async_client.get(f"/developer-requests/{request_id}", headers=headers)
    ).status_code == 200
    assert (await _row(request_id)).created_by_user_id == author.id
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DeveloperRequest)) == 1
