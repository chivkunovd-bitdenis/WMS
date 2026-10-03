from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
from app.services import developer_request_sync as sync_service
from app.services.developer_request_content import (
    TRELLO_DESCRIPTION_MAX_LENGTH,
    card_description,
    description_length,
    marker,
)
from app.services.developer_request_sync import sync_developer_requests, sync_request
from app.services.developer_request_trello import TrelloClient, TrelloConfig, card_payload
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
async def test_explicit_rejection_backoff_recovers_after_many_rejections(async_client):
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
        assert row.delivery_state == "pending" and row.create_attempts == 7
        assert row.last_error == "trello_http_429" and len(fake.posts) == 7
        deadline = row.next_sync_at
        if deadline.tzinfo is None:  # SQLite stores UTC without tzinfo.
            deadline = deadline.replace(tzinfo=UTC)
        delay = (deadline - datetime.now(UTC)).total_seconds()
        assert 3500 <= delay <= 3600
        fake.mode = "ok"
        await _due(request_id)
        await sync_request(request_id, client)
    row = await _row(request_id)
    assert row.delivery_state == "linked" and len(fake.cards) == 1
    assert row.create_attempts == 8 and row.status == "review"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["second_page", "duplicate", "partial_failure", "repeated_page"])
async def test_recovery_scans_all_trello_pages_before_linking(async_client, mode):
    _, headers = await _user()
    request_id = await _create(async_client, headers)
    row = await _row(request_id)
    fake = FakeTrello()
    first_page = [
        {"id": f"{number:024x}", "idBoard": "board", "idList": "review", "desc": "Other task"}
        for number in range(2000, 1000, -1)
    ]
    older_card = {
        "id": f"{1000:024x}",
        "idBoard": "board",
        "idList": "work",
        "desc": marker(row),
        "closed": True,
    }
    if mode in {"duplicate", "partial_failure"}:
        first_page[0]["desc"] = marker(row)
    reads = []

    async def paged_provider(request):
        if request.url.path == "/1/boards/board/cards":
            reads.append(dict(request.url.params))
            assert request.url.params["filter"] == "all"
            assert request.url.params["sort"] == "-id"
            assert request.url.params["limit"] == "1000"
            if "before" not in request.url.params:
                return httpx.Response(200, json=first_page)
            assert request.url.params["before"] == first_page[-1]["id"]
            if mode == "partial_failure":
                return httpx.Response(500)
            if mode == "repeated_page":
                return httpx.Response(200, json=first_page)
            return httpx.Response(200, json=[older_card])
        return await fake.handle(request)

    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == request_id)
            .values(
                delivery_state="outcome_unknown",
                trello_board_id="board",
                create_attempts=1,
            )
        )
        await session.commit()
    async with httpx.AsyncClient(transport=httpx.MockTransport(paged_provider)) as http:
        await sync_request(request_id, TrelloClient(fake.config, http))
    row = await _row(request_id)
    assert len(reads) == 2 and not fake.posts
    if mode == "second_page":
        assert row.delivery_state == "linked" and row.trello_card_id == older_card["id"]
        assert row.status == "in_progress"
    else:
        assert row.delivery_state == "outcome_unknown" and row.trello_card_id is None
        assert (
            row.last_error
            == {
                "duplicate": "trello_duplicate_marker",
                "partial_failure": "trello_http_500",
                "repeated_page": "trello_paging_not_advancing",
            }[mode]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("request_type", ["bug", "improvement"])
@pytest.mark.parametrize("unicode_text", [False, True])
async def test_description_limit_exact_boundary_and_replay(
    async_client, request_type, unicode_text
):
    _, headers = await _user()
    values = {
        "type": request_type,
        "description": "" if request_type == "bug" else None,
        "screen": "Экран" if request_type == "improvement" else None,
        "problem": "Проблема" if request_type == "improvement" else None,
        "proposal": "" if request_type == "improvement" else None,
    }
    preview = DeveloperRequest(
        id=uuid.uuid4(),
        client_name="Клиент Alpha",
        created_at=datetime.now(UTC),
        page_url="/fbs",
        **values,
    )
    available = TRELLO_DESCRIPTION_MAX_LENGTH - description_length(card_description(preview))
    text = ("😀" * (available // 2) + "Я" * (available % 2)) if unicode_text else "Я" * available
    text_field = "description" if request_type == "bug" else "proposal"
    body = _body(**{**values, text_field: text, "page_url": "/fbs?ignored=yes#ignored"})
    accepted = await async_client.post("/developer-requests", headers=headers, json=body)
    assert accepted.status_code == 200, accepted.text
    row = await _row(uuid.UUID(accepted.json()["id"]))
    full_description = card_description(row)
    assert description_length(full_description) == 16384
    assert "😀" in full_description if unicode_text else "😀" not in full_description
    fake = FakeTrello()
    async with fake.http() as http:
        await sync_request(row.id, TrelloClient(fake.config, http))
    assert fake.posts[0]["desc"] == [full_description]  # Same persisted UUID/time and renderer.
    async with SessionLocal() as session:
        # Existing idempotent replies cannot be invalidated by a later client-name change.
        await session.execute(
            update(Tenant).where(Tenant.id == row.tenant_id).values(name="X" * 200)
        )
        await session.commit()
    repeated = await async_client.post("/developer-requests", headers=headers, json=body)
    assert repeated.status_code == 200 and repeated.json()["id"] == accepted.json()["id"]
    async with SessionLocal() as session:
        await session.execute(
            update(Tenant).where(Tenant.id == row.tenant_id).values(name="Клиент Alpha")
        )
        await session.commit()
    rejected = await async_client.post(
        "/developer-requests",
        headers=headers,
        json={
            **body,
            "idempotency_key": str(uuid.uuid4()),
            text_field: text + "Я",
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == {
        "code": "developer_request_description_too_long",
        "message": (
            "Обращение слишком длинное для передачи разработчикам. "
            "Сократите текст и отправьте ещё раз."
        ),
        "max_length": 16384,
        "actual_length": 16385,
    }
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DeveloperRequest)) == 1
    assert len(fake.posts) == 1


@pytest.mark.asyncio
async def test_combined_improvement_limit_rejects_without_trello_config(async_client, monkeypatch):
    monkeypatch.setattr(settings, "trello_api_key", None)
    _, headers = await _user()
    result = await async_client.post(
        "/developer-requests",
        headers=headers,
        json=_body(
            type="improvement",
            screen="Упаковка",
            problem="П" * 9000,
            proposal="Р" * 9000,
        ),
    )
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "developer_request_description_too_long"
    assert result.json()["detail"]["actual_length"] > 18000
    assert await sync_developer_requests() == 0
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DeveloperRequest)) == 0


async def _scheduler_fixture(monkeypatch, count, *, uncertain=False):
    user, _ = await _user()
    start = datetime.now(UTC) + timedelta(days=1)
    state = SimpleNamespace(now=start, fail=False, reads=[], list_id="work")
    fake = FakeTrello()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.now if tz is not None else state.now.replace(tzinfo=None)

    async def provider(request):
        state.now += timedelta(milliseconds=100)  # Nonzero HTTP time; no wall-clock sleep.
        if request.url.path.startswith("/1/cards/"):
            card_id = request.url.path.rsplit("/", 1)[-1]
            state.reads.append(card_id)
            if state.fail:
                return httpx.Response(500)
            return httpx.Response(
                200,
                json={
                    "id": card_id,
                    "idList": state.list_id,
                    "idBoard": "board",
                    "desc": "test",
                },
            )
        assert request.method == "GET"
        if uncertain and request.url.path == "/1/boards/board/cards":
            if state.fail:
                return httpx.Response(500)
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "recovered-card",
                        "idList": state.list_id,
                        "idBoard": "board",
                        "desc": state.request_marker,
                    }
                ],
            )
        return await fake.handle(request)

    monkeypatch.setattr(sync_service, "datetime", Clock)
    monkeypatch.setattr(
        sync_service,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(transport=httpx.MockTransport(provider)),
        ),
    )
    monkeypatch.setattr(TrelloConfig, "from_settings", classmethod(lambda cls, config: fake.config))
    monkeypatch.setattr(settings, "trello_sync_interval_sec", 60)
    async with SessionLocal() as session:
        rows = [
            DeveloperRequest(
                tenant_id=user.tenant_id,
                created_by_user_id=user.id,
                client_name="Client",
                idempotency_key=uuid.uuid4(),
                payload_hash="test",
                type="bug",
                title="Bug",
                description="Bug",
                trello_card_id=None if uncertain else f"card-{i}",
                trello_board_id="board",
                delivery_state="outcome_unknown" if uncertain else "linked",
                create_attempts=1,
                next_sync_at=start - timedelta(seconds=count - i),
            )
            for i in range(count)
        ]
        session.add_all(rows)
        await session.commit()
    state.request_marker = marker(rows[0])
    return start, state, [row.id for row in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 51])
async def test_consecutive_scheduled_passes_ignore_http_delay_and_preserve_batch_fairness(
    async_client,
    monkeypatch,
    count,
):
    start, state, ids = await _scheduler_fixture(monkeypatch, count)
    assert await sync_developer_requests() == min(count, 50)
    assert state.now > start
    assert len(state.reads) == min(count, 50)
    assert (await _row(ids[0])).status == "in_progress"
    if count > 50:
        assert (await _row(ids[50])).status == "review"

    # The real scheduler scans next_sync_at itself; do not force rows due between runs.
    state.now = start + timedelta(seconds=60)
    state.list_id = "done"
    state.reads.clear()
    assert await sync_developer_requests() == min(count, 50)
    assert (await _row(ids[0])).status == "completed"
    if count > 50:
        assert state.reads[0] == "card-50"  # Old waiting work precedes already-polled rows.
        assert (await _row(ids[50])).status == "completed"
        assert (await _row(ids[49])).status == "in_progress"  # Batch cap is still fifty.


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [False, True])
async def test_scheduled_error_keeps_completion_based_backoff(async_client, monkeypatch, uncertain):
    start, state, ids = await _scheduler_fixture(monkeypatch, 1, uncertain=uncertain)
    state.fail = True
    assert await sync_developer_requests() == 1
    completed_at = state.now
    row = await _row(ids[0])
    assert row.status == "review" and row.last_error == "trello_http_500"
    deadline = row.next_sync_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    assert deadline == completed_at + timedelta(seconds=120)

    state.fail = False
    state.now = start + timedelta(seconds=60)
    assert await sync_developer_requests() == 0
    state.now = start + timedelta(seconds=120)
    assert await sync_developer_requests() == 0  # Backoff includes failed HTTP request time.
    state.now = deadline
    assert await sync_developer_requests() == 1
    assert (await _row(ids[0])).status == "in_progress"
