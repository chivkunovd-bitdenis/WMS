"""WMS-325: two real PostgreSQL connections, authenticated concurrent cancellations."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine, get_db
from app.main import create_app
from app.models.billing import BillingInvoice, BillingInvoiceV2, BillingLedgerEntry
from app.models.document_event import DocumentEvent
from app.models.operation_fact import OperationFact
from app.models.user import User
from app.services import billing_invoice_service as legacy
from app.services import billing_invoice_v2_service as v2
from app.services.tokens import create_access_token
from tests.test_document_events import _register_admin

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="Real PostgreSQL row locks required"
)


def _client(session: AsyncSession) -> AsyncClient:
    app = create_app()

    async def database() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = database
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    )


async def _wait_for_block(holder: AsyncSession, holder_pid: int, waiter_pid: int) -> None:
    # Observe the actual row-lock wait through the holder, never a third connection.
    connection = await holder.connection()
    async with asyncio.timeout(5):
        while not await connection.scalar(
            text("SELECT :holder = ANY(pg_blocking_pids(:waiter))"),
            {"holder": holder_pid, "waiter": waiter_pid},
        ):
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("kind", ["legacy", "v2"])
@pytest.mark.parametrize("rollback_first", [False, True])
async def test_cancel_two_authenticated_requests_one_committed_transition(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    rollback_first: bool,
) -> None:
    first_headers, claims = await _register_admin(async_client)
    tenant_id = uuid.UUID(str(claims["tenant_id"]))
    first_actor_id = uuid.UUID(str(claims["sub"]))
    seller = await async_client.post("/sellers", headers=first_headers, json={"name": "Synthetic"})
    assert seller.status_code == 201
    seller_id = uuid.UUID(seller.json()["id"])
    async with SessionLocal() as seed:
        second_actor = User(
            tenant_id=tenant_id,
            email=f"cancel-{uuid.uuid4().hex}@example.com",
            role="fulfillment_admin",
            password_hash="synthetic-unused",
        )
        seed.add(second_actor)
        invoice: BillingInvoice | BillingInvoiceV2
        if kind == "legacy":
            invoice = BillingInvoice(
                tenant_id=tenant_id,
                seller_id=seller_id,
                number="SYNTHETIC",
                period=date(2026, 7, 1),
                status="issued",
                total_amount=100,
                ff_profile_snapshot={},
                seller_profile_snapshot={},
                lines=[],
            )
        else:
            invoice = BillingInvoiceV2(
                tenant_id=tenant_id,
                seller_id=seller_id,
                number="SYNTHETIC",
                creation_mode="manual",
                status="issued",
                total_amount_kopecks=100,
                issued_by_user_id=first_actor_id,
            )
        seed.add(invoice)
        await seed.commit()
        invoice_id, second_actor_id = invoice.id, second_actor.id
        second_actor_name = second_actor.email
    second_headers = {
        "Authorization": "Bearer "
        + create_access_token(
            user_id=second_actor_id,
            tenant_id=tenant_id,
            role="fulfillment_admin",
        )
    }
    path = f"/billing/{'invoices' if kind == 'legacy' else 'invoices-v2'}/{invoice_id}/cancel"
    model = BillingInvoice if kind == "legacy" else BillingInvoiceV2
    ready, release = asyncio.Event(), asyncio.Event()
    async with SessionLocal() as first, SessionLocal() as second:
        assert first.bind is not None and first.bind.dialect.name == "postgresql"
        first_pid = int(await first.scalar(text("SELECT pg_backend_pid()")))
        second_pid = int(await second.scalar(text("SELECT pg_backend_pid()")))
        assert first_pid != second_pid
        # Keep a strong reference: SQLAlchemy identity-map entries are otherwise weak.
        stale = await second.get(model, invoice_id)
        assert isinstance(stale, (BillingInvoice, BillingInvoiceV2)) and stale.status == "issued"
        original_commit = first.commit

        async def controlled_first_commit() -> None:
            # Both status UPDATE and audit INSERT have reached PostgreSQL;
            # hold their shared transaction before its final commit/rollback.
            await first.flush()
            ready.set()
            await release.wait()
            if rollback_first:
                await first.rollback()
                raise RuntimeError("synthetic cancellation rolled back")
            await original_commit()

        monkeypatch.setattr(first, "commit", controlled_first_commit)
        async with _client(first) as first_client, _client(second) as second_client:
            first_request = asyncio.create_task(first_client.post(path, headers=first_headers))
            second_request = None
            try:
                await asyncio.wait_for(ready.wait(), timeout=5)
                second_request = asyncio.create_task(
                    second_client.post(path, headers=second_headers)
                )
                await _wait_for_block(first, first_pid, second_pid)
                assert not second_request.done()
                release.set()
                first_response, second_response = await asyncio.wait_for(
                    asyncio.gather(first_request, second_request),
                    timeout=5,
                )
                assert first_response.status_code == (500 if rollback_first else 200)
                assert second_response.status_code == 200, second_response.text
                assert second_response.json()["status"] == "cancelled"
                assert stale.status == "cancelled"  # locked reread refreshes the cached issued row
            finally:
                release.set()
                pending = [task for task in (first_request, second_request) if task is not None]
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                await first.rollback()
                await second.rollback()

    async with SessionLocal() as check:
        rows = list(
            (
                await check.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_type == "billing_invoice",
                        DocumentEvent.document_id == invoice_id,
                    )
                )
            ).all()
        )
        assert len(rows) == 1
        row = rows[0]
        expected_actor = second_actor_id if rollback_first else first_actor_id
        assert row.actor_user_id == expected_actor and row.source == "user"
        assert row.payload_json["actor_user_id_snapshot"] == str(expected_actor)
        if rollback_first:
            assert row.payload_json["actor_name_snapshot"] == second_actor_name
        assert row.payload_json["before"]["status"] == "issued"
        assert row.payload_json["after"]["status"] == "cancelled"
        persisted = await check.get(model, invoice_id)
        assert isinstance(persisted, (BillingInvoice, BillingInvoiceV2))
        assert persisted.status == "cancelled"
        if isinstance(persisted, BillingInvoice):
            assert persisted.total_amount == Decimal("100")
        else:
            assert persisted.total_amount_kopecks == 100
            assert persisted.issued_by_user_id == first_actor_id
        assert await check.scalar(select(func.count()).select_from(BillingLedgerEntry)) == 0
        assert await check.scalar(select(func.count()).select_from(OperationFact)) == 0


@pytest.mark.parametrize("kind", ["legacy", "v2"])
async def test_missing_invoice_has_no_history(
    async_client: AsyncClient,
    kind: str,
) -> None:
    _, claims = await _register_admin(async_client)
    async with SessionLocal() as session:
        missing_id = uuid.uuid4()
        call = legacy.cancel_invoice if kind == "legacy" else v2.cancel_invoice_v2
        with pytest.raises(ValueError):
            await call(
                session, tenant_id=uuid.UUID(str(claims["tenant_id"])), invoice_id=missing_id
            )
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 0
