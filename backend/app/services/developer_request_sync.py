"""Durable dispatch and polling; a lost create response is recovered by reads only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select, update

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.developer_request import DeveloperRequest
from app.services.developer_request_trello import TrelloClient, TrelloConfig, TrelloError

LEASE_SECONDS = 300
MAX_CREATE_ATTEMPTS = 5


async def sync_request(request_id: uuid.UUID, client: TrelloClient) -> bool:
    token = uuid.uuid4()
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        claimed = await session.scalar(
            update(DeveloperRequest)
            .where(
                DeveloperRequest.id == request_id,
                DeveloperRequest.next_sync_at <= now,
                or_(DeveloperRequest.lease_until.is_(None), DeveloperRequest.lease_until < now),
            )
            .values(lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS))
            .returning(DeveloperRequest.id)
        )
        await session.commit()
        if claimed is None:
            return False
        row = await session.get(DeveloperRequest, request_id)
        assert row is not None
        changes: dict[str, Any] = {}
        card: dict[str, Any] | None
        try:
            if row.trello_board_id and row.trello_board_id != client.config.board_id:
                raise TrelloError("trello_board_config_changed")
            await client.check_board()
            if row.trello_card_id:
                card = await client.get_card(row.trello_card_id)
            elif row.delivery_state == "outcome_unknown":
                card = await client.find_card(row)
                if card is None:
                    raise TrelloError("trello_create_outcome_unknown")
            elif row.create_attempts >= MAX_CREATE_ATTEMPTS:
                raise TrelloError("trello_create_retry_exhausted")
            else:
                # Persist uncertainty BEFORE the request. A killed worker cannot lead
                # a successor to blindly repeat POST. Fence a worker whose lease expired.
                reserved = await session.scalar(
                    update(DeveloperRequest)
                    .where(
                        DeveloperRequest.id == request_id,
                        DeveloperRequest.lease_token == token,
                        DeveloperRequest.lease_until > datetime.now(UTC),
                        DeveloperRequest.delivery_state == "pending",
                    )
                    .values(
                        delivery_state="outcome_unknown",
                        trello_board_id=client.config.board_id,
                        create_attempts=DeveloperRequest.create_attempts + 1,
                    )
                    .returning(DeveloperRequest.id)
                    .execution_options(synchronize_session="fetch")
                )
                await session.commit()
                if reserved is None:
                    return False
                try:
                    card = await client.create_card(row)
                except TrelloError as exc:
                    if exc.rejected:
                        # An explicit 4xx is a known rejection, unlike timeout/5xx.
                        changes["delivery_state"] = "pending"
                    raise
            assert card is not None
            changes.update(
                trello_card_id=card["id"],
                trello_board_id=client.config.board_id,
                delivery_state="linked",
                last_error=None,
            )
            mapped_status = client.config.lists.get(card["idList"])
            if mapped_status is not None and row.status != mapped_status:
                changes.update(status=mapped_status, updated_at=datetime.now(UTC))
        except TrelloError as exc:
            changes["last_error"] = exc.code
        # Compare-and-set fences late replies from expired workers. They can be
        # reconciled on the next run using the durable board/UUID marker.
        interval = settings.trello_sync_interval_sec
        if changes.get("last_error"):
            interval = min(3600, interval * (2 ** min(row.create_attempts, 5)))
        changes.update(
            lease_token=None,
            lease_until=None,
            next_sync_at=datetime.now(UTC) + timedelta(seconds=interval),
        )
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == request_id, DeveloperRequest.lease_token == token)
            .values(**changes)
        )
        await session.commit()
        return True


async def sync_developer_requests() -> int:
    config = TrelloConfig.from_settings(settings)
    if config is None:
        return 0
    async with SessionLocal() as session:
        ids = list(
            await session.scalars(
                select(DeveloperRequest.id)
                .where(DeveloperRequest.next_sync_at <= datetime.now(UTC))
                .order_by(DeveloperRequest.next_sync_at)
                .limit(50)
            )
        )
    async with httpx.AsyncClient() as http:
        client = TrelloClient(config, http)
        count = 0
        for request_id in ids:
            count += int(await sync_request(request_id, client))
        return count
