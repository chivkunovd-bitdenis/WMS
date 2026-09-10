"""WMS-325: bounded marking/settings/template audit, synthetic PostgreSQL only."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.document_event import DocumentEvent
from app.models.inbound_intake import InboundIntakeLine
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode, MarkingCodeEvent, MarkingPool, MarkingPoolProduct
from app.models.print_template import PrintTemplate
from app.models.product import Product
from app.models.user import User
from app.services import document_event_service as audit
from app.services import inbound_marking_service as inbound
from app.services import marking_code_service as marking
from app.services import print_template_service as templates
from app.services.inbound_intake_service import InboundIntakeError
from app.services.tokens import create_access_token
from tests.test_document_events import _register_admin
from tests.test_inbound_marking import CIS, _setup
from tests.test_print_templates import _seed_tenant_seller_product
from tests.test_wms325_invoice_cancel_concurrency import _wait_for_block

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL required")
PREFIX = "/operations/marking-codes"
LAYOUT = {"units": [{"block": "cz", "copies": 2}]}


@pytest.fixture
def fail_audit_insert() -> Iterator[Callable[[], None]]:
    enabled = False

    def break_insert(
        _conn: Any, _cursor: Any, statement: str, parameters: Any, _context: Any, _executemany: bool
    ) -> tuple[str, Any]:
        if enabled and statement.startswith("INSERT INTO document_event "):
            return "SELECT nonexistent_wms325_column", {}
        return statement, parameters

    def enable() -> None:
        nonlocal enabled
        enabled = True

    event.listen(engine.sync_engine, "before_cursor_execute", break_insert, retval=True)
    try:
        yield enable
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", break_insert)


async def _seed(
    client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    token, tenant, actor, seller, product = await _seed_tenant_seller_product(client)
    async with SessionLocal() as session:
        pool = MarkingPool(
            tenant_id=tenant, seller_id=seller, gtin="04601234567890", title="Synthetic"
        )
        template = PrintTemplate(
            tenant_id=tenant,
            seller_id=seller,
            name="Before",
            layout_json=json.dumps(LAYOUT),
            is_default=True,
        )
        session.add_all([pool, template])
        await session.commit()
        return {"Authorization": f"Bearer {token}"}, tenant, actor, product, pool.id, template.id


async def _events(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentEvent]:
    return list(
        (
            await session.scalars(
                select(DocumentEvent)
                .where(DocumentEvent.document_id == document_id)
                .order_by(DocumentEvent.created_at, DocumentEvent.id)
            )
        ).all()
    )


async def _other_actor(tenant: uuid.UUID) -> uuid.UUID:
    async with SessionLocal() as session:
        user = User(
            tenant_id=tenant,
            role="fulfillment_admin",
            email=f"other-{uuid.uuid4().hex}@example.com",
            password_hash="synthetic-unused",
        )
        session.add(user)
        await session.commit()
        return user.id


async def test_pool_http_actor_noop_rejection_and_admin_history(async_client: AsyncClient) -> None:
    headers, tenant, actor, product, pool, _ = await _seed(async_client)
    for _repeat in range(2):
        r = await async_client.put(
            f"{PREFIX}/pools/{pool}/products",
            headers=headers,
            json={"product_ids": [str(product), str(product)]},
        )
        assert r.status_code == 200, r.text
        r = await async_client.put(
            f"{PREFIX}/pools/{pool}/threshold",
            headers=headers,
            json={"low_stock_threshold": 5, "forecast_days_threshold": 3},
        )
        assert r.status_code == 200, r.text
    r = await async_client.put(
        f"{PREFIX}/pools/{pool}/products",
        headers=headers,
        json={"product_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 404
    r = await async_client.put(
        f"{PREFIX}/pools/{pool}/threshold", headers=headers, json={"low_stock_threshold": -1}
    )
    assert r.status_code == 422
    async with SessionLocal() as session:
        rows = await _events(session, pool)
        assert len(rows) == 2
        assert all(row.actor_user_id == actor and row.source == "user" for row in rows)
        assert all(row.payload_json["actor_user_id_snapshot"] == str(actor) for row in rows)
        product_event = next(row for row in rows if "product_ids" in row.payload_json["before"])
        assert product_event.payload_json["before"] == {"product_ids": []}
        assert product_event.payload_json["after"] == {"product_ids": [str(product)]}
        # Explicit system execution must not inherit the last HTTP user.
        with audit.system_document_events():
            await marking.set_pool_threshold(
                session, tenant, pool, low_stock_threshold=None, forecast_days_threshold=None
            )
        rows = await _events(session, pool)
        assert len(rows) == 3
        assert sum(row.source == "system" and row.actor_user_id is None for row in rows) == 1
    r = await async_client.get(
        "/operations/document-events",
        headers=headers,
        params={"document_type": "marking_pool", "document_id": str(pool)},
    )
    assert r.status_code == 200 and len(r.json()) == 3
    other_headers, _ = await _register_admin(async_client)
    r = await async_client.get(
        "/operations/document-events",
        headers=other_headers,
        params={"document_type": "marking_pool", "document_id": str(pool)},
    )
    assert r.status_code == 200 and r.json() == []
    async with SessionLocal() as session:
        staff = User(
            tenant_id=tenant,
            role="fulfillment_staff",
            email="synthetic-staff@example.com",
            password_hash="synthetic-unused",
        )
        session.add(staff)
        await session.commit()
        staff_token = create_access_token(user_id=staff.id, tenant_id=tenant, role=staff.role)
    r = await async_client.get(
        "/operations/document-events",
        headers={"Authorization": f"Bearer {staff_token}"},
        params={"document_type": "marking_pool", "document_id": str(pool)},
    )
    assert r.status_code == 403


async def test_template_http_default_peers_owner_and_deleted_identity(
    async_client: AsyncClient,
) -> None:
    headers, tenant, actor, _, _, old_id = await _seed(async_client)
    owner = await _other_actor(tenant)
    async with SessionLocal() as session:
        old = await session.get(PrintTemplate, old_id)
        assert old is not None
        seller = old.seller_id
        # Owner is a scope field, not the actor executing the request.
        old.user_id = owner
        await session.commit()
    r = await async_client.put(
        f"{PREFIX}/print-templates/{old_id}", headers=headers, json={"name": "Renamed"}
    )
    assert r.status_code == 200
    r = await async_client.put(
        f"{PREFIX}/print-templates/{old_id}", headers=headers, json={"name": "Renamed"}
    )
    assert r.status_code == 200
    r = await async_client.put(
        f"{PREFIX}/print-templates/{old_id}",
        headers=headers,
        json={"layout": {"units": [{"block": "invalid", "copies": 1}]}},
    )
    assert r.status_code == 422
    async with SessionLocal() as session:
        rows = await _events(session, old_id)
        assert len(rows) == 1 and rows[0].actor_user_id == actor
        assert rows[0].payload_json["after"]["owner_user_id"] == str(owner)
        with audit.document_event_actor(actor):
            replacement = await templates.create_print_template(
                session,
                tenant,
                name="Replacement",
                layout={**LAYOUT, "unrecognized": "UNEXPECTED_LAYOUT_CONTENT"},
                seller_id=seller,
                user_id=owner,
                is_default=True,
            )
        assert replacement.id is not None
        new_id = replacement.id
        rows = await _events(session, old_id)
        assert len(rows) == 2
        default_event = next(
            row for row in rows if row.payload_json["after"]["is_default"] is False
        )
        assert default_event.payload_json["before"]["is_default"] is True
        created = (await _events(session, new_id))[0]
        assert created.payload_json["before"] is None
        assert created.payload_json["after"]["layout_units"] == [{"block": "cz", "copies": 2}]
        assert "UNEXPECTED_LAYOUT_CONTENT" not in json.dumps(created.payload_json)
        assert "layout_json" not in created.payload_json["after"]
        name_snapshot = created.payload_json["actor_name_snapshot"]
        user = await session.get(User, actor)
        assert user is not None
        user.email = "synthetic-renamed@example.com"
        await session.commit()
    r = await async_client.delete(f"{PREFIX}/print-templates/{new_id}", headers=headers)
    assert r.status_code == 204
    r = await async_client.delete(f"{PREFIX}/print-templates/{new_id}", headers=headers)
    assert r.status_code == 404
    r = await async_client.get(
        "/operations/document-events",
        headers=headers,
        params={"document_type": "print_template", "document_id": str(new_id)},
    )
    assert r.status_code == 200 and len(r.json()) == 2
    created_out = next(row for row in r.json() if row["event_type"] == "document_created")
    assert created_out["actor"]["name"] == name_snapshot
    removed = next(row for row in r.json() if row["payload"]["after"] is None)
    assert removed["payload"]["before"]["template_id"] == str(new_id)
    async with SessionLocal() as session:
        assert await session.get(PrintTemplate, new_id) is None


async def _mutate(
    session: AsyncSession,
    tenant: uuid.UUID,
    product: uuid.UUID,
    pool: uuid.UUID,
    template: uuid.UUID,
    kind: str,
) -> None:
    if kind == "threshold":
        await marking.set_pool_threshold(
            session, tenant, pool, low_stock_threshold=7, forecast_days_threshold=2
        )
    elif kind == "products":
        await marking.set_pool_products(session, tenant, pool, [product])
    elif kind == "create":
        await templates.create_print_template(session, tenant, name="New", layout=LAYOUT)
    elif kind == "delete":
        await templates.delete_print_template(session, tenant, template)
    else:
        await templates.update_print_template(session, tenant, template, name="After")


@pytest.mark.parametrize("kind", ["threshold", "products", "create", "update", "delete"])
@pytest.mark.parametrize("failure", ["rollback", "audit_failure"])
async def test_mutation_rollback_and_real_audit_sql_failure(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    failure: str,
    fail_audit_insert: Callable[[], None],
) -> None:
    _, tenant, actor, product, pool, template = await _seed(async_client)
    async with SessionLocal() as session:
        if failure == "rollback":

            async def rollback_commit() -> None:
                await session.flush()
                await session.rollback()
                raise RuntimeError("synthetic rollback")

            monkeypatch.setattr(session, "commit", rollback_commit)
        else:
            fail_audit_insert()
        with audit.document_event_actor(actor):
            if failure == "rollback":
                with pytest.raises(RuntimeError, match="synthetic rollback"):
                    await _mutate(session, tenant, product, pool, template, kind)
            else:
                await _mutate(session, tenant, product, pool, template, kind)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 0
        changed = failure == "audit_failure"
        p = await session.get(MarkingPool, pool)
        t = await session.get(PrintTemplate, template)
        assert p is not None
        if kind == "threshold":
            assert p.low_stock_threshold == (7 if changed else None)
        elif kind == "products":
            assert await session.scalar(
                select(func.count()).select_from(MarkingPoolProduct)
            ) == int(changed)
        elif kind == "create":
            assert await session.scalar(select(func.count()).select_from(PrintTemplate)) == 1 + int(
                changed
            )
        elif kind == "delete":
            assert (t is None) == changed
        else:
            assert t is not None and t.name == ("After" if changed else "Before")
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0


@pytest.mark.parametrize("kind", ["threshold", "products", "update"])
@pytest.mark.parametrize("rollback_first", [False, True])
async def test_concurrent_repeated_mutation_one_event_and_fresh_identity(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, kind: str, rollback_first: bool
) -> None:
    _, tenant, actor, product, pool, template = await _seed(async_client)
    other = await _other_actor(tenant)
    ready, release = asyncio.Event(), asyncio.Event()
    async with SessionLocal() as first, SessionLocal() as second:
        holder = int(await first.scalar(text("SELECT pg_backend_pid()")))
        waiter = int(await second.scalar(text("SELECT pg_backend_pid()")))
        assert holder != waiter
        stale = await second.get(
            PrintTemplate if kind == "update" else MarkingPool,
            template if kind == "update" else pool,
        )
        original_commit = first.commit

        async def held_commit() -> None:
            await first.flush()
            ready.set()
            await release.wait()
            if rollback_first:
                await first.rollback()
                raise RuntimeError("synthetic rollback")
            await original_commit()

        monkeypatch.setattr(first, "commit", held_commit)

        async def run(session: AsyncSession, who: uuid.UUID) -> None:
            with audit.document_event_actor(who):
                await _mutate(session, tenant, product, pool, template, kind)

        one = asyncio.create_task(run(first, actor))
        two = None
        try:
            await asyncio.wait_for(ready.wait(), 5)
            two = asyncio.create_task(run(second, other))
            await _wait_for_block(first, holder, waiter)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(one, two, return_exceptions=True), 5)
            assert results[1] is None
            assert isinstance(results[0], RuntimeError) if rollback_first else results[0] is None
            assert stale is not None
            if isinstance(stale, PrintTemplate):
                assert stale.name == "After"
            elif kind == "threshold":
                assert isinstance(stale, MarkingPool) and stale.low_stock_threshold == 7
        finally:
            release.set()
            tasks = [t for t in (one, two) if t is not None]
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    async with SessionLocal() as session:
        rows = await _events(session, template if kind == "update" else pool)
        assert len(rows) == 1
        assert rows[0].actor_user_id == (other if rollback_first else actor)


@pytest.mark.parametrize("printed_pool", [False, True])
@pytest.mark.parametrize("failure", ["none", "rollback", "audit_failure"])
async def test_detach_retains_operation_ids_without_cis(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    printed_pool: bool,
    failure: str,
    fail_audit_insert: Callable[[], None],
) -> None:
    tenant, original_actor, request, line_id = await _setup(async_client)
    actor = await _other_actor(tenant)
    async with SessionLocal() as session:
        line = await session.get(InboundIntakeLine, line_id)
        assert line is not None
        product = await session.get(Product, line.product_id)
        assert product is not None
        if printed_pool:
            code = MarkingCode(
                tenant_id=tenant,
                seller_id=product.seller_id,
                cis_code=CIS,
                source="pool",
                status="printed",
            )
            session.add(code)
            await session.flush()
            original = MarkingCodeEvent(
                tenant_id=tenant, seller_id=product.seller_id, code_id=code.id, event_type="printed"
            )
            session.add(original)
            await session.commit()
        attached = await inbound.attach_code(
            session, tenant, request, line_id=line_id, cis_code=CIS, actor_user_id=original_actor
        )
        code_id = uuid.UUID(attached["id"])
        attachment = await session.scalar(
            select(MarkingCodeEvent).where(
                MarkingCodeEvent.code_id == code_id, MarkingCodeEvent.event_type == "imported"
            )
        )
        assert attachment is not None
        attachment_id = attachment.id
        count_before = len(await _events(session, request))
        if failure == "rollback":

            async def rollback_commit() -> None:
                await session.flush()
                await session.rollback()
                raise RuntimeError("synthetic rollback")

            monkeypatch.setattr(session, "commit", rollback_commit)
        if failure == "audit_failure":
            fail_audit_insert()
        if failure == "none":
            token = create_access_token(user_id=actor, tenant_id=tenant, role="fulfillment_admin")
            response = await async_client.delete(
                f"/operations/inbound-intake-requests/{request}/marking-codes/{code_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 204, response.text
        else:
            with audit.document_event_actor(actor):
                if failure == "rollback":
                    with pytest.raises(RuntimeError, match="synthetic rollback"):
                        await inbound.delete_code(session, tenant, request, code_id)
                else:
                    await inbound.delete_code(session, tenant, request, code_id)
    async with SessionLocal() as session:
        rows = await _events(session, request)
        assert len(rows) == count_before + int(failure == "none")
        assert (await session.get(MarkingCodeEvent, attachment_id) is not None) == (
            failure == "rollback"
        )
        assert (await session.get(MarkingCode, code_id) is not None) == (
            printed_pool or failure == "rollback"
        )
        if failure == "none":
            row = next(
                row
                for row in rows
                if (row.payload_json.get("before") or {}).get("attachment_event_id")
                == str(attachment_id)
            )
            assert row.actor_user_id == actor
            assert row.payload_json["before"]["attached_by_user_id"] == str(original_actor)
            assert row.payload_json["before"]["line_id"] == str(line_id)
            assert row.payload_json["after"]["attached"] is False
            assert row.payload_json["after"]["code_exists"] == printed_pool
            assert CIS not in json.dumps(row.payload_json)
            assert "cis_code" not in json.dumps(row.payload_json)
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0


@pytest.mark.parametrize("mode", ["switch", "create_empty"])
async def test_concurrent_default_changes_serialize_scope_without_stale_peer_audits(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _, tenant, actor, _, _, old_id = await _seed(async_client)
    other = await _other_actor(tenant)
    async with SessionLocal() as seed:
        old = await seed.get(PrintTemplate, old_id)
        assert old is not None
        seller = old.seller_id
        second_template = PrintTemplate(
            tenant_id=tenant,
            seller_id=seller,
            name="Second",
            layout_json=json.dumps(LAYOUT),
            is_default=False,
        )
        if mode == "switch":
            seed.add(second_template)
        else:
            await seed.delete(old)
        await seed.commit()
        second_id = second_template.id
    ready, release = asyncio.Event(), asyncio.Event()
    created_ids: dict[str, uuid.UUID] = {}
    async with SessionLocal() as first, SessionLocal() as second:
        holder = int(await first.scalar(text("SELECT pg_backend_pid()")))
        waiter = int(await second.scalar(text("SELECT pg_backend_pid()")))
        assert holder != waiter
        stale = await second.get(PrintTemplate, old_id) if mode == "switch" else None
        commit = first.commit

        async def held_commit() -> None:
            await first.flush()
            ready.set()
            await release.wait()
            await commit()

        monkeypatch.setattr(first, "commit", held_commit)

        async def change(
            session: AsyncSession, who: uuid.UUID, name: str, target: uuid.UUID
        ) -> None:
            with audit.document_event_actor(who):
                if mode == "switch":
                    row = await templates.update_print_template(
                        session,
                        tenant,
                        target,
                        name=name,
                        is_default=True,
                        layout={"units": [{"block": "label", "copies": 3}]},
                    )
                else:
                    row = await templates.create_print_template(
                        session, tenant, name=name, seller_id=seller, layout=LAYOUT, is_default=True
                    )
                assert row.id is not None
                created_ids[name] = row.id

        one = asyncio.create_task(change(first, actor, "First", second_id))
        two = None
        try:
            await asyncio.wait_for(ready.wait(), 5)
            two = asyncio.create_task(change(second, other, "Last", old_id))
            await _wait_for_block(first, holder, waiter)
            release.set()
            await asyncio.wait_for(asyncio.gather(one, two), 5)
            if stale is not None:
                assert stale.is_default is True and stale.name == "Last"
        finally:
            release.set()
            tasks = [t for t in (one, two) if t is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    async with SessionLocal() as check:
        models = list(
            (
                await check.scalars(select(PrintTemplate).where(PrintTemplate.tenant_id == tenant))
            ).all()
        )
        assert len(models) == 2
        assert [model.name for model in models if model.is_default] == ["Last"]
        first_rows = await _events(check, created_ids["First"])
        assert len(first_rows) == 2
        cleared = next(row for row in first_rows if row.actor_user_id == other)
        assert cleared.payload_json["before"]["is_default"] is True
        assert cleared.payload_json["after"]["is_default"] is False
        last_rows = await _events(check, created_ids["Last"])
        assert len(last_rows) == (2 if mode == "switch" else 1)
        final = next(row for row in last_rows if row.actor_user_id == other)
        assert final.payload_json["after"]["name"] == "Last"
        if mode == "switch":
            assert final.payload_json["before"]["is_default"] is False
            assert final.payload_json["after"]["layout_units"] == [{"block": "label", "copies": 3}]


@pytest.mark.parametrize("kind", ["template", "attachment"])
@pytest.mark.parametrize("rollback_first", [False, True])
async def test_concurrent_deletion_records_only_persisted_actor(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    rollback_first: bool,
) -> None:
    if kind == "template":
        _, tenant, actor, _, _, target = await _seed(async_client)
        document_id = target
    else:
        tenant, actor, document_id, line = await _setup(async_client)
        async with SessionLocal() as seed:
            attached = await inbound.attach_code(
                seed, tenant, document_id, line_id=line, cis_code=CIS, actor_user_id=actor
            )
            target = uuid.UUID(attached["id"])
    other = await _other_actor(tenant)
    async with SessionLocal() as seed:
        count_before = len(await _events(seed, document_id))
    ready, release = asyncio.Event(), asyncio.Event()
    async with SessionLocal() as first, SessionLocal() as second:
        holder = int(await first.scalar(text("SELECT pg_backend_pid()")))
        waiter = int(await second.scalar(text("SELECT pg_backend_pid()")))
        assert holder != waiter
        # The access path can already have cached the object before deletion.
        stale = await second.get(PrintTemplate if kind == "template" else MarkingCode, target)
        assert stale is not None
        commit = first.commit

        async def held_commit() -> None:
            await first.flush()
            ready.set()
            await release.wait()
            if rollback_first:
                await first.rollback()
                raise RuntimeError("synthetic rollback")
            await commit()

        monkeypatch.setattr(first, "commit", held_commit)

        async def remove(session: AsyncSession, who: uuid.UUID) -> None:
            with audit.document_event_actor(who):
                if kind == "template":
                    await templates.delete_print_template(session, tenant, target)
                else:
                    await inbound.delete_code(session, tenant, document_id, target)

        one = asyncio.create_task(remove(first, actor))
        two = None
        try:
            await asyncio.wait_for(ready.wait(), 5)
            two = asyncio.create_task(remove(second, other))
            await _wait_for_block(first, holder, waiter)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(one, two, return_exceptions=True), 5)
            if rollback_first:
                assert isinstance(results[0], RuntimeError) and results[1] is None
            else:
                assert results[0] is None
                error_type = (
                    templates.PrintTemplateServiceError
                    if kind == "template"
                    else InboundIntakeError
                )
                assert isinstance(results[1], error_type)
                assert "not_found" in str(results[1])
        finally:
            release.set()
            tasks = [task for task in (one, two) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    async with SessionLocal() as check:
        rows = await _events(check, document_id)
        assert len(rows) == count_before + 1
        mutation = [
            row
            for row in rows
            if (kind == "template" and row.payload_json.get("after") is None)
            or (
                kind == "attachment"
                and (row.payload_json.get("after") or {}).get("attached") is False
            )
        ]
        assert len(mutation) == 1
        assert mutation[0].actor_user_id == (other if rollback_first else actor)
        assert await check.get(PrintTemplate if kind == "template" else MarkingCode, target) is None


async def test_template_creation_api_uses_authenticated_actor_for_shared_scope(
    async_client: AsyncClient,
) -> None:
    headers, tenant, actor, _, _, template = await _seed(async_client)
    async with SessionLocal() as session:
        existing = await session.get(PrintTemplate, template)
        assert existing is not None
        seller = existing.seller_id
    response = await async_client.post(
        f"{PREFIX}/print-templates",
        headers=headers,
        json={"name": "Shared", "seller_id": str(seller), "layout": LAYOUT, "is_default": False},
    )
    assert response.status_code == 201, response.text
    template_id = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        row = (await _events(session, template_id))[0]
        assert row.tenant_id == tenant and row.actor_user_id == actor
        assert row.payload_json["after"]["owner_user_id"] is None
        assert row.payload_json["actor_user_id_snapshot"] == str(actor)
