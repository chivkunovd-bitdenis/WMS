"""Permanent queue bindings and short-lived PC pairing (no print attempt journal)."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_connection import PrintConnection
from app.models.warehouse import Warehouse
from app.services.fbs_print_job_service import lock_print_intent


class ConnectionError(ValueError):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


_pairing_clients: dict[str, tuple[float, int]] = {}
_pairing_lock = Lock()


def check_pairing_rate(client: str) -> None:
    """Bound unauthenticated pair creation before DB work; independent of login."""
    now = time.monotonic()
    with _pairing_lock:
        for key, (since, _) in list(_pairing_clients.items()):
            if now - since >= 60:
                del _pairing_clients[key]
        since, count = _pairing_clients.get(client, (now, 0))
        if count >= 10 or (client not in _pairing_clients and len(_pairing_clients) >= 1000):
            raise ConnectionError(429, "pairing_rate_limited")
        _pairing_clients[client] = (since, count + 1)


async def begin_pairing(
    session: AsyncSession,
    *,
    connection_id: uuid.UUID,
    device_token: str,
    queue_name: str,
    platform: str,
) -> tuple[PrintConnection, str | None]:
    await lock_print_intent(session, connection_id)
    connection = await session.get(PrintConnection, connection_id)
    code = digest(device_token + ":pair")[:16].upper()
    if connection is not None:
        if (
            connection.token_hash != digest(device_token)
            or connection.queue_name != queue_name
            or connection.platform != platform
        ):
            raise ConnectionError(409, "pairing_conflict")
        if connection.tenant_id is not None:
            return connection, None
        if utc(connection.pairing_expires_at) <= datetime.now(UTC):
            raise ConnectionError(410, "pairing_expired")
    else:
        await session.execute(
            delete(PrintConnection).where(
                PrintConnection.tenant_id.is_(None),
                PrintConnection.pairing_expires_at < datetime.now(UTC),
            )
        )
        connection = PrintConnection(
            id=connection_id,
            token_hash=digest(device_token),
            pairing_hash=digest(code),
            pairing_expires_at=datetime.now(UTC) + timedelta(minutes=15),
            queue_name=queue_name,
            platform=platform,
            is_default=False,
        )
        session.add(connection)
        await session.flush()
    return connection, code


async def resolve_pairing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    code: str,
) -> PrintConnection:
    warehouse = await session.scalar(
        select(Warehouse)
        .where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
        .with_for_update()
    )
    if warehouse is None:
        raise ConnectionError(404, "warehouse_not_found")
    normalized = re.sub(r"[\s-]", "", code).upper()
    connection = await session.scalar(
        select(PrintConnection)
        .where(PrintConnection.pairing_hash == digest(normalized))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None or utc(connection.pairing_expires_at) <= datetime.now(UTC):
        raise ConnectionError(404, "pairing_not_found_or_expired")
    if connection.tenant_id is not None and (
        connection.tenant_id != tenant_id or connection.warehouse_id != warehouse_id
    ):
        raise ConnectionError(409, "pairing_already_used")
    return connection


async def confirm_pairing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    user_id: uuid.UUID,
    code: str,
) -> PrintConnection:
    connection = await resolve_pairing(session, tenant_id, warehouse_id, code)
    if connection.tenant_id is not None:
        # Lost confirmation response is safe to replay; don't replace a later
        # deliberate binding when replaying an older confirmation.
        return connection
    await session.execute(
        update(PrintConnection)
        .where(PrintConnection.warehouse_id == warehouse_id, PrintConnection.is_default.is_(True))
        .values(is_default=False)
    )
    connection.tenant_id = tenant_id
    connection.warehouse_id = warehouse_id
    connection.paired_by_user_id = user_id
    connection.is_default = True
    await session.flush()
    return connection
