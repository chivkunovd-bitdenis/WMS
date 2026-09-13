"""WMS-444: a retried FBO pack is one work fact, not another physical unit."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.billing import BillingLedgerEntry
from app.models.operation_fact import OperationFact
from app.models.packaging_task import PackagingTaskEvent, PackagingTaskLine
from app.models.user import User
from app.services import packaging_task_service as packaging
from tests.test_inventory_counts import TenantSetup, _product, _tenant


async def _task(client: AsyncClient, setup: TenantSetup, quantity: int = 3) -> dict:
    product = await _product(client, setup, name="Товар для упаковки")
    response = await client.post(
        "/operations/packaging-tasks", headers=setup.headers,
        json={"warehouse_id": str(setup.warehouse_id), "lines": [{
            "product_id": str(product), "storage_location_id": str(setup.location_id),
            "quantity": quantity,
        }]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _url(task: dict) -> str:
    return f"/operations/packaging-tasks/{task['id']}/lines/{task['lines'][0]['id']}/pack"


async def _assert_facts(task: dict, packed: int, events: int) -> None:
    async with SessionLocal() as session:
        assert await session.scalar(select(PackagingTaskLine.qty_packed_in_task).where(
            PackagingTaskLine.id == uuid.UUID(task["lines"][0]["id"]),
        )) == packed
        task_id = uuid.UUID(task["id"])
        assert await session.scalar(select(func.count()).select_from(PackagingTaskEvent).where(
            PackagingTaskEvent.task_id == task_id,
            PackagingTaskEvent.action == "manual_pack",
        )) == events
        facts = list((await session.scalars(select(OperationFact).where(
            OperationFact.document_id == task_id,
            OperationFact.operation_code == "packing_completed",
        ))).all())
        assert len(facts) == events
        assert sum(fact.item_quantity for fact in facts) == packed
        assert await session.scalar(select(func.count()).select_from(BillingLedgerEntry)) == 0


@pytest.mark.asyncio
async def test_lost_response_replay_then_new_attempt(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "PackReplay")
    task = await _task(async_client, setup)
    payload = {"quantity": 1, "idempotency_key": "one-physical-unit"}
    first = await async_client.post(_url(task), headers=setup.headers, json=payload)
    assert first.status_code == 200, first.text
    # The successful response is lost; the reopened client resends the same attempt.
    for _ in range(2):
        retry = await async_client.post(_url(task), headers=setup.headers, json=payload)
        assert retry.status_code == 200, retry.text
        assert retry.json()["packaging_task"]["lines"][0]["qty_packed_in_task"] == 1
    await _assert_facts(task, 1, 1)
    second = await async_client.post(
        _url(task), headers=setup.headers,
        json={"quantity": 1, "idempotency_key": "another-physical-unit"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["packaging_task"]["lines"][0]["qty_packed_in_task"] == 2
    await _assert_facts(task, 2, 2)


@pytest.mark.asyncio
async def test_payload_conflicts_and_tenant_boundary(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "PackConflict")
    task = await _task(async_client, setup)
    other_task = await _task(async_client, setup)
    payload = {"quantity": 1, "idempotency_key": "one-attempt"}
    first = await async_client.post(_url(task), headers=setup.headers, json=payload)
    assert first.status_code == 200, first.text
    for url, changed in (
        (_url(task), {**payload, "quantity": 2}),
        (_url(other_task), payload),
        (_url(task).replace(task["lines"][0]["id"], other_task["lines"][0]["id"]), payload),
        (_url(task), {**payload, "order_id": str(uuid.uuid4())}),
    ):
        conflict = await async_client.post(url, headers=setup.headers, json=changed)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"] == "idempotency_conflict"
    # An actor change must not acquire another person's receipt.
    async with SessionLocal() as session:
        actor = User(
            tenant_id=setup.tenant_id, email="other-pack-actor@example.com",
            password_hash="unused-test-password", role="fulfillment_staff",
        )
        session.add(actor)
        await session.commit()
        with pytest.raises(packaging.PackagingTaskServiceError, match="idempotency_conflict"):
            await packaging.record_pack_progress(
                session, setup.tenant_id, uuid.UUID(task["id"]),
                uuid.UUID(task["lines"][0]["id"]), 1,
                acting_user_id=actor.id, idempotency_key="one-attempt",
            )
        facts = list((await session.scalars(select(OperationFact).where(
            OperationFact.document_id == uuid.UUID(task["id"]),
        ))).all())
        events = first.json()["packaging_task"]["events"]
        assert len(facts) == len(events) == 1
        assert str(facts[0].actor_user_id) == events[0]["created_by_user_id"]
        assert facts[0].actor_user_id != actor.id
    other = await _tenant(async_client, "OtherPackTenant")
    forbidden = await async_client.post(_url(task), headers=other.headers, json=payload)
    assert forbidden.status_code == 404, forbidden.text
    independent = await _task(async_client, other)
    own = await async_client.post(_url(independent), headers=other.headers, json=payload)
    assert own.status_code == 200, own.text
    await _assert_facts(task, 1, 1)
    await _assert_facts(other_task, 0, 0)
    await _assert_facts(independent, 1, 1)


@pytest.mark.asyncio
async def test_replay_after_completion_and_legacy_no_key(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "PackCompleteReplay")
    task = await _task(async_client, setup)
    payload = {"quantity": 1, "idempotency_key": "first-unit"}
    for body in (payload, {"quantity": 1}, {"quantity": 1}):
        response = await async_client.post(_url(task), headers=setup.headers, json=body)
        assert response.status_code == 200, response.text
    completed = await async_client.post(
        f"/operations/packaging-tasks/{task['id']}/complete",
        headers=setup.headers, json={"acknowledge_all_packed": False},
    )
    assert completed.status_code == 200, completed.text
    retry = await async_client.post(_url(task), headers=setup.headers, json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["packaging_task"]["status"] == "done"
    await _assert_facts(task, 3, 3)


@pytest.mark.asyncio
async def test_replay_after_undo_does_not_restore_reversed_work(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "PackUndoReplay")
    task = await _task(async_client, setup)
    payload = {"quantity": 1, "idempotency_key": "reversed-unit"}
    assert (await async_client.post(
        _url(task), headers=setup.headers, json=payload,
    )).status_code == 200
    undo = await async_client.post(
        f"/operations/packaging-tasks/{task['id']}/undo-last", headers=setup.headers,
    )
    assert undo.status_code == 200, undo.text
    retry = await async_client.post(_url(task), headers=setup.headers, json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["packaging_task"]["lines"][0]["qty_packed_in_task"] == 0
    async with SessionLocal() as session:
        facts = list((await session.scalars(select(OperationFact).where(
            OperationFact.document_id == uuid.UUID(task["id"]),
        ))).all())
        assert sorted(fact.operation_code for fact in facts) == [
            "packing_completed", "packing_reversal",
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_deliveries_do_not_exceed_plan(
    async_client: AsyncClient, same_key: bool,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Row/advisory lock concurrency requires PostgreSQL")
    setup = await _tenant(async_client, "PackConcurrent")
    task = await _task(async_client, setup, quantity=1)
    responses = await asyncio.gather(*(
        async_client.post(
            _url(task), headers=setup.headers,
            json={"quantity": 1, "idempotency_key": "same" if same_key else str(index)},
        ) for index in range(2)
    ))
    assert sorted(response.status_code for response in responses) == (
        [200, 200] if same_key else [200, 409]
    ), [response.text for response in responses]
    await _assert_facts(task, 1, 1)


@pytest.mark.asyncio
async def test_concurrent_key_reused_across_documents_is_conflict(
    async_client: AsyncClient,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Row/advisory lock concurrency requires PostgreSQL")
    setup = await _tenant(async_client, "PackConcurrentDocuments")
    tasks = [await _task(async_client, setup), await _task(async_client, setup)]
    responses = await asyncio.gather(*(
        async_client.post(
            _url(task), headers=setup.headers,
            json={"quantity": 1, "idempotency_key": "same-attempt-different-document"},
        ) for task in tasks
    ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    for task, response in zip(tasks, responses, strict=True):
        expected = int(response.status_code == 200)
        await _assert_facts(task, expected, expected)


@pytest.mark.asyncio
async def test_failure_rolls_back_quantity_event_and_fact(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await _tenant(async_client, "PackRollback")
    task = await _task(async_client, setup)
    original = packaging.record_packaging_event

    async def fail_after_fact(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("injected failure before commit")

    payload = {"quantity": 1, "idempotency_key": "failed-attempt"}
    with monkeypatch.context() as patch:
        patch.setattr(packaging, "record_packaging_event", fail_after_fact)
        with pytest.raises(RuntimeError, match="injected failure"):
            await async_client.post(_url(task), headers=setup.headers, json=payload)
    await _assert_facts(task, 0, 0)
    retry = await async_client.post(_url(task), headers=setup.headers, json=payload)
    assert retry.status_code == 200, retry.text
    await _assert_facts(task, 1, 1)
