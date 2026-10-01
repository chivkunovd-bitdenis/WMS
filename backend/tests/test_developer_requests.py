from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.developer_request import DeveloperRequest
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.tenant import Tenant
from app.models.user import User
from app.services.developer_request_sync import sync_developer_requests, sync_request
from app.services.developer_request_trello import TrelloClient, TrelloConfig, card_payload, marker
from app.services.tokens import create_access_token


async def _user(*, tenant_id=None, role=FULFILLMENT_ADMIN, seller_id=None):
    async with SessionLocal() as session:
        if tenant_id is None:
            tenant = Tenant(name="Клиент Alpha", slug=str(uuid.uuid4()))
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
        user = User(
            tenant_id=tenant_id,
            seller_id=seller_id,
            email=f"{uuid.uuid4()}@example.test",
            role=role,
            password_hash="test-unused",
        )
        session.add(user)
        await session.commit()
        token = create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            role=role,
            seller_id=seller_id,
        )
        return user, {"Authorization": f"Bearer {token}"}


def _body(**kwargs):
    return {"idempotency_key": str(uuid.uuid4()), "type": "bug", "description": "Ошибка", **kwargs}


async def _create(client, headers, **kwargs):
    result = await client.post("/developer-requests", headers=headers, json=_body(**kwargs))
    assert result.status_code == 200, result.text
    return uuid.UUID(result.json()["id"])


async def _row(request_id):
    async with SessionLocal() as session:
        return await session.get(DeveloperRequest, request_id)


async def _due(request_id):
    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == request_id)
            .values(
                next_sync_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_api_isolation_validation_and_idempotency(async_client):
    author, headers = await _user(role=FULFILLMENT_STAFF)
    _, same_tenant = await _user(tenant_id=author.tenant_id)
    _, other_tenant = await _user()
    body = _body(
        screen="hidden",
        problem="hidden",
        proposal="hidden",
        page_url="https://wms.test/fbs/orders?token=DO-NOT-SAVE#private",
    )
    first = await async_client.post("/developer-requests", headers=headers, json=body)
    repeat = await async_client.post("/developer-requests", headers=headers, json=body)
    assert first.status_code == repeat.status_code == 200
    assert first.json()["id"] == repeat.json()["id"]
    assert first.json()["status"] == "review"
    assert all(first.json()[key] is None for key in ("screen", "problem", "proposal"))
    changed = await async_client.post(
        "/developer-requests", headers=headers, json={**body, "description": "Другое"}
    )
    assert changed.status_code == 409
    row = await _row(uuid.UUID(first.json()["id"]))
    assert row.tenant_id == author.tenant_id and row.created_by_user_id == author.id
    assert row.page_url == "/fbs/orders"
    assert "DO-NOT-SAVE" not in first.text
    for foreign in (same_tenant, other_tenant):
        listed = await async_client.get("/developer-requests", headers=foreign)
        assert listed.json() == []
        one = await async_client.get(f"/developer-requests/{row.id}", headers=foreign)
        assert one.status_code == 404
    assert (await async_client.get("/developer-requests")).status_code == 401
    assert (
        await async_client.post(
            "/developer-requests", headers=headers, json=_body(tenant_id=str(uuid.uuid4()))
        )
    ).status_code == 422
    assert (
        await async_client.post(
            "/developer-requests", headers=headers, json=_body(description="  \n")
        )
    ).status_code == 422
    for key in ("screen", "problem", "proposal"):
        values = dict(type="improvement", screen="Упаковка", problem="Проблема", proposal="Решение")
        values[key] = " \n"
        response = await async_client.post(
            "/developer-requests", headers=headers, json=_body(**values)
        )
        assert response.status_code == 422
    improvement = await _create(
        async_client,
        headers,
        type="improvement",
        screen="Упаковка FBS",
        problem="Много действий",
        proposal="Одно действие",
    )
    detail = await async_client.get(f"/developer-requests/{improvement}", headers=headers)
    assert detail.json()["description"] is None
    assert detail.json()["proposal"] == "Одно действие"
    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == improvement)
            .values(
                created_at=datetime.now(UTC) + timedelta(seconds=2),
            )
        )
        await session.commit()
    listed = await async_client.get("/developer-requests", headers=headers)
    assert [item["id"] for item in listed.json()] == [str(improvement), str(row.id)]
    await _create(
        async_client, headers
    )  # A fresh intentional submission may have identical content.


@pytest.mark.asyncio
async def test_effective_seller_from_auth_only(async_client):
    author, _ = await _user(role=FULFILLMENT_SELLER)
    async with SessionLocal() as session:
        home = Seller(tenant_id=author.tenant_id, name="Home")
        active = Seller(tenant_id=author.tenant_id, name="Delegated")
        session.add_all([home, active])
        await session.flush()
        await session.execute(
            update(User)
            .where(User.id == author.id)
            .values(
                seller_id=home.id,
                can_manage_seller_shops=True,
            )
        )
        session.add(
            SellerShopDelegation(user_id=author.id, target_seller_id=active.id, enabled=True)
        )
        await session.commit()
    token = create_access_token(
        user_id=author.id, tenant_id=author.tenant_id, role=author.role, seller_id=active.id
    )
    headers = {"Authorization": f"Bearer {token}"}
    request_id = await _create(async_client, headers)
    row = await _row(request_id)
    assert row.seller_id == active.id and "Delegated" in row.client_name


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_concurrent_same_submission_returns_one_row(async_client):
    _, headers = await _user()
    body = _body()
    responses = await asyncio.gather(
        *[async_client.post("/developer-requests", headers=headers, json=body) for _ in range(2)]
    )
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DeveloperRequest)) == 1


class FakeTrello:
    def __init__(self):
        self.config = TrelloConfig(
            "test-key",
            "test-token",
            "board",
            {
                "review": "review",
                "queue": "queued",
                "work": "in_progress",
                "done": "completed",
            },
            "client-label",
        )
        self.cards = []
        self.posts = []
        self.mode = "ok"
        self.list_id = "review"
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block_post = False

    async def handle(self, request):
        if request.method == "GET" and request.url.path == "/1/boards/board":
            return httpx.Response(
                200, json={"closed": False, "prefs": {"permissionLevel": "private"}}
            )
        if request.url.path == "/1/boards/board/lists":
            return httpx.Response(200, json=[{"id": key} for key in self.config.lists])
        if request.method == "POST":
            self.posts.append(parse_qs(request.content.decode()))
            assert "test-key" not in str(request.url) and "test-token" not in str(request.url)
            if self.block_post:
                self.entered.set()
                await self.release.wait()
            if self.mode == "reject":
                return httpx.Response(429, json={"message": "test-token"})
            card = {
                "id": "card",
                "idList": self.list_id,
                "idBoard": "board",
                "desc": self.posts[-1]["desc"][0],
            }
            if self.mode != "lost_before_create":
                self.cards.append(card)
            if self.mode in ("timeout", "lost_before_create"):
                raise httpx.ReadTimeout("SECRET-SHOULD-NOT-LEAK test-token", request=request)
            if self.mode == "server_error":
                return httpx.Response(500, text="SECRET-SHOULD-NOT-LEAK test-token")
            return httpx.Response(200, json=card)
        if self.mode == "get_error":
            return httpx.Response(500, text="SECRET-SHOULD-NOT-LEAK test-token")
        for card in self.cards:
            card["idList"] = self.list_id
        if request.url.path == "/1/boards/board/cards":
            return httpx.Response(200, json=self.cards)
        return httpx.Response(200, json=self.cards[0])

    def http(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))


@pytest.mark.asyncio
async def test_dispatch_payload_and_four_statuses(async_client):
    _, headers = await _user()
    request_id = await _create(
        async_client,
        headers,
        type="improvement",
        screen="Упаковка FBS",
        problem="Много действий",
        proposal="Одно действие",
    )
    fake = FakeTrello()
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        assert await sync_request(request_id, client)
        assert len(fake.posts) == 1
        payload = fake.posts[0]
        assert payload["idLabels"] == ["client-label"] and payload["idList"] == ["review"]
        assert "Клиент: Клиент Alpha" in payload["name"][0]
        assert all(
            part in payload["desc"][0]
            for part in (
                "Дата поступления:",
                "Упаковка FBS",
                "Много действий",
                "Одно действие",
                str(request_id),
            )
        )
        for list_id, expected in fake.config.lists.items():
            fake.list_id = list_id
            await _due(request_id)
            await sync_request(request_id, client)
            row = await _row(request_id)
            assert row.status == expected
        for mode, list_id in (("ok", "unmapped"), ("get_error", "review")):
            fake.mode, fake.list_id = mode, list_id
            await _due(request_id)
            await sync_request(request_id, client)
            assert (await _row(request_id)).status == "completed"
        assert len(fake.posts) == 1
    result = await async_client.get("/developer-requests", headers=headers)
    assert len(result.json()) == 1  # No external/imported task exposure.


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "server_error"])
async def test_unknown_create_recovery_never_repeats_post(async_client, failure, caplog):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()
    fake.mode = failure
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        await sync_request(request_id, client)
        row = await _row(request_id)
        assert row.delivery_state == "outcome_unknown" and row.trello_card_id is None
        assert "test-token" not in row.last_error and "SECRET" not in row.last_error
        fake.mode = "get_error"
        await _due(request_id)
        await sync_request(request_id, client)
        assert len(fake.posts) == 1
        fake.mode = "ok"
        await _due(request_id)
        await sync_request(request_id, client)
        row = await _row(request_id)
        assert row.delivery_state == "linked" and row.trello_card_id == "card"
        assert len(fake.posts) == 1
    assert "SECRET-SHOULD-NOT-LEAK" not in caplog.text
    assert "test-token" not in caplog.text


@pytest.mark.asyncio
async def test_absent_marker_does_not_authorize_recreate(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()
    fake.mode = "lost_before_create"
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        await sync_request(request_id, client)
        fake.mode = "ok"
        for _ in range(2):
            await _due(request_id)
            await sync_request(request_id, client)
        row = await _row(request_id)
        assert row.delivery_state == "outcome_unknown" and len(fake.posts) == 1
        assert row.last_error == "trello_create_outcome_unknown"


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_overlapping_workers_create_only_once(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()
    fake.block_post = True
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        first = asyncio.create_task(sync_request(request_id, client))
        await asyncio.wait_for(fake.entered.wait(), 10)
        assert not await sync_request(request_id, client)
        row = await _row(request_id)
        assert row.delivery_state == "outcome_unknown"  # Durable before provider response.
        fake.release.set()
        await first
        assert len(fake.posts) == 1
        assert (await _row(request_id)).delivery_state == "linked"


@pytest.mark.asyncio
async def test_expired_worker_lease_recovers_by_marker(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    row = await _row(request_id)
    fake = FakeTrello()
    fake.cards = [{"id": "card", "idList": "review", "idBoard": "board", "desc": marker(row)}]
    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == request_id)
            .values(
                delivery_state="outcome_unknown",
                trello_board_id="board",
                create_attempts=1,
                lease_token=uuid.uuid4(),
                lease_until=datetime.now(UTC) - timedelta(seconds=10),
            )
        )
        await session.commit()
    async with fake.http() as http:
        await sync_request(request_id, TrelloClient(fake.config, http))
    assert (await _row(request_id)).trello_card_id == "card" and not fake.posts


@pytest.mark.asyncio
async def test_explicit_rejection_retry_is_bounded(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()
    fake.mode = "reject"
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        for _ in range(7):
            await _due(request_id)
            await sync_request(request_id, client)
    row = await _row(request_id)
    assert row.delivery_state == "pending" and row.create_attempts == 5
    assert row.last_error == "trello_create_retry_exhausted" and len(fake.posts) == 5
    assert row.status == "review"


@pytest.mark.asyncio
async def test_unconfigured_keeps_local_success_and_optional_label(async_client, monkeypatch):
    monkeypatch.setattr(settings, "trello_api_key", None)
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    assert await sync_developer_requests() == 0
    row = await _row(request_id)
    assert row.delivery_state == "pending" and row.status == "review"
    fake = FakeTrello()
    fake.config = TrelloConfig("test-key", "test-token", "board", fake.config.lists, None)
    assert "idLabels" not in card_payload(row, fake.config)
    async with fake.http() as http:
        await sync_request(request_id, TrelloClient(fake.config, http))
    assert (await _row(request_id)).delivery_state == "linked"


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_expired_inflight_worker_cannot_overwrite_successor(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()
    fake.block_post = True
    async with fake.http() as http:
        client = TrelloClient(fake.config, http)
        first = asyncio.create_task(sync_request(request_id, client))
        await asyncio.wait_for(fake.entered.wait(), 10)
        async with SessionLocal() as session:
            await session.execute(
                update(DeveloperRequest)
                .where(
                    DeveloperRequest.id == request_id,
                )
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        await sync_request(request_id, client)  # Only a read, first POST still in flight.
        fake.release.set()
        await first
        row = await _row(request_id)
        assert row.delivery_state == "outcome_unknown" and row.trello_card_id is None
        await _due(request_id)
        await sync_request(request_id, client)
        assert (await _row(request_id)).trello_card_id == "card"
        assert len(fake.posts) == 1


@pytest.mark.asyncio
async def test_public_board_and_changed_board_never_receive_cards(async_client):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    fake = FakeTrello()

    async def public_board(request):
        if request.url.path == "/1/boards/board":
            return httpx.Response(
                200, json={"closed": False, "prefs": {"permissionLevel": "public"}}
            )
        return await fake.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(public_board)) as http:
        await sync_request(request_id, TrelloClient(fake.config, http))
    row = await _row(request_id)
    assert row.last_error == "trello_board_must_be_private" and row.delivery_state == "pending"
    assert not fake.posts
    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == request_id)
            .values(
                trello_board_id="original-board",
                delivery_state="outcome_unknown",
            )
        )
        await session.commit()
    await _due(request_id)
    async with fake.http() as http:
        await sync_request(request_id, TrelloClient(fake.config, http))
    assert (await _row(request_id)).last_error == "trello_board_config_changed"
    assert not fake.posts
